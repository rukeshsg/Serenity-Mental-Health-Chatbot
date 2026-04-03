"""
Advanced Features Module for Mental Health Support Chatbot
===========================================================

This module adds production-ready improvements:
1. Response Caching - Reduces LLM API calls
2. Rate Limiting - Prevents abuse
3. Circuit Breaker - Handles external API failures gracefully
4. Conversation Context Window - Better memory management
5. Multi-turn Crisis Tracking - Follow-up on safety concerns
6. Response Quality Scoring - Feedback loop for improvements
7. Graceful Degradation - Fallback chain for component failures
"""

import time
import hashlib
import threading
from collections import deque
from datetime import datetime, timedelta
from functools import wraps
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 1. RESPONSE CACHING
# ============================================================

class ResponseCache:
    """LRU cache for LLM responses to reduce API calls."""
    
    def __init__(self, max_size=500, ttl_seconds=3600):
        self.cache = {}
        self.timestamps = {}
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, text, intent, context):
        """Create cache key from input parameters."""
        combined = f"{text}|{intent}|{context}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get(self, text, intent, context=""):
        """Retrieve cached response if valid."""
        key = self._make_key(text, intent, context)
        
        if key in self.cache:
            # Check TTL
            if time.time() - self.timestamps[key] < self.ttl:
                self.hits += 1
                return self.cache[key]
            else:
                # Expired
                del self.cache[key]
                del self.timestamps[key]
        
        self.misses += 1
        return None
    
    def set(self, text, intent, context, response):
        """Store response in cache."""
        key = self._make_key(text, intent, context)
        
        # Evict oldest if full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.timestamps.keys(), key=self.timestamps.get)
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]
        
        self.cache[key] = response
        self.timestamps[key] = time.time()
    
    def get_stats(self):
        """Return cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# Global cache instance
response_cache = ResponseCache()


# ============================================================
# 2. RATE LIMITING
# ============================================================

class RateLimiter:
    """Token bucket rate limiter for API protection."""
    
    def __init__(self, max_requests=30, window_seconds=60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = {}  # user_id -> deque of timestamps
        self._lock = threading.Lock()
    
    def is_allowed(self, user_id="anonymous"):
        """Check if request is allowed under rate limit."""
        with self._lock:
            now = time.time()
            
            if user_id not in self.requests:
                self.requests[user_id] = deque()
            
            # Remove expired timestamps
            while self.requests[user_id] and now - self.requests[user_id][0] > self.window:
                self.requests[user_id].popleft()
            
            # Check limit
            if len(self.requests[user_id]) >= self.max_requests:
                return False
            
            # Add current request
            self.requests[user_id].append(now)
            return True
    
    def get_remaining(self, user_id="anonymous"):
        """Get remaining requests for user."""
        with self._lock:
            now = time.time()
            if user_id not in self.requests:
                return self.max_requests
            
            # Clean expired
            while self.requests[user_id] and now - self.requests[user_id][0] > self.window:
                self.requests[user_id].popleft()
            
            return max(0, self.max_requests - len(self.requests[user_id]))


# Global rate limiter
rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


# ============================================================
# 3. CIRCUIT BREAKER
# ============================================================

class CircuitBreaker:
    """Circuit breaker pattern for external API calls."""
    
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == "open":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "half-open"
                    logger.info("Circuit breaker: transitioning to half-open")
                else:
                    raise Exception("Circuit breaker is OPEN - service unavailable")
            
            try:
                result = func(*args, **kwargs)
                
                # Success - close circuit
                if self.state == "half-open":
                    self.state = "closed"
                    self.failures = 0
                    logger.info("Circuit breaker: closed")
                
                return result
                
            except Exception as e:
                self.failures += 1
                self.last_failure_time = time.time()
                
                if self.failures >= self.failure_threshold:
                    self.state = "open"
                    logger.warning(f"Circuit breaker OPENED after {self.failures} failures")
                
                raise e
    
    def reset(self):
        """Manually reset circuit breaker."""
        with self._lock:
            self.failures = 0
            self.state = "closed"
            self.last_failure_time = None
    
    def get_state(self):
        """Get current circuit breaker state."""
        return self.state


# Circuit breakers for different services
llm_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
rag_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)


# ============================================================
# 4. CONVERSATION CONTEXT MANAGER
# ============================================================

class ConversationContextManager:
    """Manages multi-turn conversation context with sliding window."""
    
    def __init__(self, max_turns=10, context_window=5):
        self.max_turns = max_turns  # Total history to keep
        self.context_window = context_window  # Recent turns for LLM
        self.sessions = {}  # session_id -> deque of turns
    
    def add_turn(self, session_id, user_message, bot_response, intent, metadata=None):
        """Add a conversation turn to history."""
        if session_id not in self.sessions:
            self.sessions[session_id] = deque(maxlen=self.max_turns)
        
        turn = {
            "timestamp": datetime.now().isoformat(),
            "user": user_message,
            "bot": bot_response,
            "intent": intent,
            "metadata": metadata or {}
        }
        
        self.sessions[session_id].append(turn)
    
    def get_recent_context(self, session_id):
        """Get recent conversation context for LLM."""
        if session_id not in self.sessions:
            return []
        
        turns = list(self.sessions[session_id])
        recent = turns[-self.context_window:]
        
        context = []
        for turn in recent:
            context.append(f"User: {turn['user']}")
            context.append(f"Assistant: {turn['bot']}")
        
        return "\n".join(context)
    
    def get_emotional_trajectory(self, session_id):
        """Analyze emotional trajectory from conversation history."""
        if session_id not in self.sessions:
            return "neutral"
        
        intents = [t["intent"] for t in self.sessions[session_id]]
        
        # Count crisis indicators
        crisis_count = intents.count("crisis") + intents.count("self_harm")
        distress_count = intents.count("distress") + intents.count("depression")
        
        if crisis_count > 0:
            return "concerning"
        elif distress_count > len(intents) * 0.5:
            return "distressed"
        elif any(i in intents for i in ["greeting", "normal", "casual"]):
            return "stable"
        
        return "neutral"
    
    def clear_session(self, session_id):
        """Clear session history."""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def get_session_summary(self, session_id):
        """Get summary of conversation session."""
        if session_id not in self.sessions:
            return None
        
        turns = list(self.sessions[session_id])
        
        return {
            "turn_count": len(turns),
            "first_turn": turns[0]["timestamp"] if turns else None,
            "last_turn": turns[-1]["timestamp"] if turns else None,
            "emotional_trajectory": self.get_emotional_trajectory(session_id),
            "intents": [t["intent"] for t in turns]
        }


# Global context manager
context_manager = ConversationContextManager()


# ============================================================
# 5. CRISIS ESCALATION TRACKER
# ============================================================

class CrisisEscalationTracker:
    """Tracks crisis patterns across conversation sessions."""
    
    def __init__(self):
        self.crisis_events = {}  # user_id -> list of crisis events
        self._lock = threading.Lock()
    
    def log_crisis(self, user_id, crisis_level, context):
        """Log a crisis event for tracking."""
        with self._lock:
            if user_id not in self.crisis_events:
                self.crisis_events[user_id] = []
            
            event = {
                "timestamp": datetime.now().isoformat(),
                "level": crisis_level,
                "context": context
            }
            
            self.crisis_events[user_id].append(event)
            
            # Keep only last 20 events per user
            if len(self.crisis_events[user_id]) > 20:
                self.crisis_events[user_id] = self.crisis_events[user_id][-20:]
    
    def get_crisis_count(self, user_id, hours=24):
        """Get crisis event count in time window."""
        with self._lock:
            if user_id not in self.crisis_events:
                return 0
            
            cutoff = datetime.now() - timedelta(hours=hours)
            count = 0
            
            for event in self.crisis_events[user_id]:
                event_time = datetime.fromisoformat(event["timestamp"])
                if event_time > cutoff:
                    count += 1
            
            return count
    
    def should_escalate(self, user_id):
        """Determine if crisis escalation is needed."""
        recent_2h = self.get_crisis_count(user_id, hours=2)
        recent_24h = self.get_crisis_count(user_id, hours=24)
        
        # Escalate if: 2+ crises in 2 hours OR 4+ crises in 24 hours
        return recent_2h >= 2 or recent_24h >= 4
    
    def get_recent_crisis_context(self, user_id):
        """Get recent crisis context for follow-up."""
        with self._lock:
            if user_id not in self.crisis_events:
                return []
            
            return self.crisis_events[user_id][-3:]


# Global crisis tracker
crisis_tracker = CrisisEscalationTracker()


# ============================================================
# 6. RESPONSE QUALITY MONITOR
# ============================================================

class ResponseQualityMonitor:
    """Monitors and scores response quality based on feedback."""
    
    def __init__(self):
        self.feedback_history = deque(maxlen=1000)
        self.intent_scores = {}  # intent -> list of scores
    
    def record_feedback(self, intent, rating):
        """Record user feedback for a response."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "rating": rating  # 1 = positive, -1 = negative
        }
        
        self.feedback_history.append(entry)
        
        # Track per-intent
        if intent not in self.intent_scores:
            self.intent_scores[intent] = deque(maxlen=100)
        self.intent_scores[intent].append(rating)
    
    def get_intent_score(self, intent):
        """Get average score for specific intent."""
        if intent not in self.intent_scores or not self.intent_scores[intent]:
            return None
        
        scores = list(self.intent_scores[intent])
        return sum(scores) / len(scores)
    
    def get_overall_score(self):
        """Get overall response quality score."""
        if not self.feedback_history:
            return None
        
        ratings = [e["rating"] for e in self.feedback_history]
        return sum(ratings) / len(ratings)
    
    def get_quality_report(self):
        """Generate quality report."""
        report = {
            "total_feedback": len(self.feedback_history),
            "overall_score": self.get_overall_score(),
            "by_intent": {}
        }
        
        for intent, scores in self.intent_scores.items():
            if scores:
                report["by_intent"][intent] = {
                    "count": len(scores),
                    "avg_score": sum(scores) / len(scores)
                }
        
        return report


# Global quality monitor
quality_monitor = ResponseQualityMonitor()


# ============================================================
# 7. GRACEFUL DEGRADATION CHAIN
# ============================================================

class GracefulDegradation:
    """Implements fallback chain for component failures."""
    
    def __init__(self):
        self.fallbacks = {}
    
    def register_fallback(self, primary_func, fallback_func):
        """Register a fallback for primary function."""
        self.fallbacks[primary_func.__name__] = fallback_func
    
    def execute_with_fallback(self, primary_func, *args, **kwargs):
        """Execute primary function with fallback on failure."""
        func_name = primary_func.__name__
        
        try:
            return primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary function {func_name} failed: {e}")
            
            if func_name in self.fallbacks:
                logger.info(f"Executing fallback for {func_name}")
                return self.fallbacks[func_name](*args, **kwargs)
            
            # No fallback - re-raise
            raise


# Global degradation handler
degradation = GracefulDegradation()


# ============================================================
# DECORATORS FOR EASY INTEGRATION
# ============================================================

def with_caching(cache=None):
    """Decorator to add caching to functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try cache first for LLM responses
            if cache and len(args) >= 2:
                cached = cache.get(str(args[0]), str(args[1]) if len(args) > 1 else "")
                if cached:
                    return cached
            
            result = func(*args, **kwargs)
            
            # Store in cache
            if cache and len(args) >= 2:
                cache.set(str(args[0]), str(args[1]) if len(args) > 1 else "", "", result)
            
            return result
        return wrapper
    return decorator


def with_rate_limiting(limiter=None):
    """Decorator to add rate limiting."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if limiter:
                user_id = kwargs.get("user_id", "anonymous")
                if not limiter.is_allowed(user_id):
                    raise Exception("Rate limit exceeded. Please wait before sending more messages.")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_circuit_breaker(breaker=None):
    """Decorator to add circuit breaker protection."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if breaker:
                return breaker.call(func, *args, **kwargs)
            return func(*args, **kwargs)
        return wrapper
    return decorator
