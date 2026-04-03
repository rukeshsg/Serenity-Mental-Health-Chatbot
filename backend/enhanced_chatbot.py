"""
Enhanced Chatbot with Advanced Features
======================================
Integrates all advanced features into the chatbot pipeline.
"""

from advanced_features import (
    response_cache, rate_limiter, llm_circuit_breaker, rag_circuit_breaker,
    context_manager, crisis_tracker, quality_monitor, degradation,
    with_caching, with_rate_limiting, with_circuit_breaker
)
from chatbot_logic import chatbot as base_chatbot
from logger import save_intent, get_recent_intents


class EnhancedChatbot:
    """
    Enhanced chatbot with:
    - Response caching
    - Rate limiting
    - Circuit breakers
    - Conversation context tracking
    - Crisis escalation monitoring
    - Quality monitoring
    """
    
    def __init__(self):
        self.cache = response_cache
        self.rate_limiter = rate_limiter
        self.context = context_manager
        self.crisis = crisis_tracker
        self.quality = quality_monitor
        self.circuit_breaker_llm = llm_circuit_breaker
        self.circuit_breaker_rag = rag_circuit_breaker
    
    def process_message(self, user_text, session_id="default", user_id="anonymous"):
        """
        Process message with all advanced features.
        
        Args:
            user_text: User's input message
            session_id: Current session identifier
            user_id: User identifier for tracking
        
        Returns:
            dict: Response with metadata
        """
        # 1. Rate Limiting Check
        if not self.rate_limiter.is_allowed(user_id):
            return {
                "success": False,
                "response": "I'm receiving a lot of messages. Please wait a moment before sending another.",
                "ui_state": "rate_limited",
                "rate_limit_remaining": 0
            }
        
        remaining = self.rate_limiter.get_remaining(user_id)
        
        # 2. Check conversation context for follow-up
        recent_context = self.context.get_recent_context(session_id)
        emotional_trajectory = self.context.get_emotional_trajectory(session_id)
        
        # 3. Check crisis escalation
        if self.crisis.should_escalate(user_id):
            crisis_context = self.crisis.get_recent_crisis_context(user_id)
            # Add escalation warning to context
        
        # 4. Process through base chatbot
        try:
            # Try cached response first (skip for crisis/safety)
            cached = self.cache.get(user_text, "", "")
            
            if cached and not self._is_safety_message(user_text):
                response = cached
                cached_response = True
            else:
                # Call base chatbot
                response = base_chatbot(user_text)
                cached_response = False
                
                # Cache the response
                if not self._is_safety_message(user_text):
                    self.cache.set(user_text, "", "", response)
            
            # 5. Update conversation context
            intent = self._extract_intent(response)
            self.context.add_turn(session_id, user_text, response, intent)
            
            # 6. Determine UI state
            ui_state = self._determine_ui_state(response, user_text)
            
            return {
                "success": True,
                "response": response,
                "session_id": session_id,
                "ui_state": ui_state,
                "cached": cached_response,
                "rate_limit_remaining": remaining,
                "emotional_trajectory": emotional_trajectory,
                "circuit_breaker_state": {
                    "llm": self.circuit_breaker_llm.get_state(),
                    "rag": self.circuit_breaker_rag.get_state()
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "response": "I'm here to support you. Please try again.",
                "error": str(e),
                "ui_state": "error"
            }
    
    def _is_safety_message(self, text):
        """Check if message is a safety/crisis response."""
        safety_keywords = [
            "helpline", "crisis", "aasra", "icall", "108",
            "you are not alone", "i hear you", "support"
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in safety_keywords)
    
    def _extract_intent(self, response):
        """Extract intent from response for tracking."""
        if "greeting" in response.lower():
            return "greeting"
        elif any(kw in response.lower() for kw in ["sorry", "hear you", "understand"]):
            return "empathy"
        return "support"
    
    def _determine_ui_state(self, response, user_text):
        """Determine UI state from response."""
        text = response.lower()
        
        if "kill myself" in user_text.lower() or "suicide" in user_text.lower():
            return "crisis_2_modal"
        elif "nothing matters" in user_text.lower():
            return "crisis_1_card"
        elif "abuse" in user_text.lower() or "harassment" in user_text.lower():
            return "abuse_card"
        elif any(p in user_text.lower() for p in ["friend", "he ", "she ", "they "]):
            return "third_person_card"
        
        return "normal_chat"
    
    def record_feedback(self, intent, rating):
        """Record user feedback for quality monitoring."""
        self.quality.record_feedback(intent, rating)
    
    def get_quality_report(self):
        """Get quality monitoring report."""
        return self.quality.get_quality_report()
    
    def get_cache_stats(self):
        """Get cache performance statistics."""
        return self.cache.get_stats()
    
    def get_session_info(self, session_id):
        """Get session information."""
        return self.context.get_session_summary(session_id)


# Global enhanced chatbot instance
enhanced_chatbot = EnhancedChatbot()


# Convenience function for backward compatibility
def chatbot_enhanced(user_text, session_id="default", user_id="anonymous"):
    """Enhanced chatbot entry point."""
    result = enhanced_chatbot.process_message(user_text, session_id, user_id)
    return result["response"]
