import logging
import re
from threading import RLock

from backend.crisis_module import (
    detect_user_help_request,
    handle_crisis_logic,
    session_crisis_store,
)
from backend.logger import save_intent
from backend.rag_engine import search, hybrid_search, situations, responses, faiss_index, bm25_index
from backend.llm_response import (
    generate_reply,
    detect_distress_type,
    generate_human_response,
    generate_crisis_response,
    SHORT_GREETING_INPUTS,
    SHORT_ACK_INPUTS,
    FOLLOW_UP_INPUTS,
    UNCERTAIN_INPUTS,
)
from backend.safety_module import check_abuse_harassment
from backend.llm_analyzer import analyze_situation
from backend.safety_reply import generate_safety_reply
from backend.input_sanitizer import sanitize_input
from backend.safety_ui_state import compute_ui_state_from_message

logger = logging.getLogger(__name__)
_response_metadata_store = {}
_response_metadata_lock = RLock()


def _normalize_confidence_score(confidence):
    try:
        return max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        return 0.0


def _store_response_metadata(session_id, intent, confidence, ui_state):
    metadata = {
        "intent": (intent or "").strip(),
        "confidence": _normalize_confidence_score(confidence),
        "ui_state": (ui_state or "normal_chat").strip() or "normal_chat",
    }
    with _response_metadata_lock:
        _response_metadata_store[session_id or "default_session"] = metadata
    return metadata


def get_last_response_metadata(session_id):
    with _response_metadata_lock:
        metadata = _response_metadata_store.get(session_id or "default_session", {})
    return dict(metadata)


# Try ML intent engine, fallback to keyword-based if unavailable
try:
    from backend.models.intent_engine_bilstm import predict_intent

    logger.info("Intent engine: ML (BiLSTM)")
except Exception as e:
    logger.warning("ML intent engine unavailable: %s", str(e)[:50])
    from backend.models.fallback_intent_engine import predict_intent

    logger.info("Intent engine: fallback keyword-based")


# Import advanced features
try:
    from backend.advanced_features import (
        response_cache,
        rate_limiter,
        llm_circuit_breaker,
        context_manager,
        crisis_tracker,
        quality_monitor,
    )

    ADVANCED_FEATURES_ENABLED = True
    logger.info("Advanced features: loaded")
except ImportError:
    ADVANCED_FEATURES_ENABLED = False
    logger.warning("Advanced features: not available")

logger.info("Chatbot ready")


UNPROMPTED_HELPLINE_PATTERNS = [
    r"\bAASRA\b",
    r"\biCall\b",
    r"\bVandrevala\b",
    r"\bEmergency\s*\(India\)\b",
    r"\bWomen Helpline\b",
    r"\bNational Commission for Women\b",
    r"https?://\S*befrienders\S*",
    r"https?://\S*7cups\S*",
    r"\b108\b",
]


def _build_conversation_context(session_id, client_messages=None, current_user_text=None):
    context = {
        "recent_context": "",
        "recent_bot_replies": session_crisis_store.get_recent_responses(session_id),
        "recent_user_messages": session_crisis_store.get_recent_user_messages(session_id),
        "emotional_memory": "",
        "emotional_continuity": "",
        "recent_intents": [],
        "turn_count": 0,
        "emotional_trajectory": "neutral",
        "last_completed_assistant_reply": "",
        "unanswered_user_message": "",
        "follow_up_mode": "none",
    }

    normalized_client_messages = [
        item for item in (client_messages or [])
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ]

    if normalized_client_messages:
        recent_window = normalized_client_messages[-8:]
        client_user_messages = [
            str(item.get("text", "")).strip()
            for item in recent_window
            if item.get("role") == "user" and str(item.get("text", "")).strip()
        ]
        client_bot_messages = [
            str(item.get("text", "")).strip()
            for item in recent_window
            if item.get("role") == "bot" and str(item.get("text", "")).strip()
        ]
        if client_user_messages:
            context["recent_user_messages"] = client_user_messages[-5:]
        if client_bot_messages:
            context["recent_bot_replies"] = client_bot_messages[-4:]

        formatted_recent_context = []
        for item in recent_window[-6:]:
            role = "User" if item.get("role") == "user" else "Assistant"
            formatted_recent_context.append(f"{role}: {str(item.get('text', '')).strip()}")
        if formatted_recent_context:
            context["recent_context"] = "\n".join(formatted_recent_context)

        for item in reversed(normalized_client_messages):
            if item.get("role") == "bot":
                context["last_completed_assistant_reply"] = str(item.get("text", "")).strip()
                break

        trailing_user_messages = []
        for item in reversed(normalized_client_messages):
            if item.get("role") != "user":
                break
            text = str(item.get("text", "")).strip()
            if text:
                trailing_user_messages.append(text)
        if len(trailing_user_messages) >= 2:
            context["unanswered_user_message"] = trailing_user_messages[-1]

        context["turn_count"] = sum(1 for item in normalized_client_messages if item.get("role") in {"user", "bot"})

    if ADVANCED_FEATURES_ENABLED:
        stored_recent_context = context_manager.get_recent_context(session_id)
        if stored_recent_context and not context["recent_context"]:
            context["recent_context"] = stored_recent_context
        summary = context_manager.get_session_summary(session_id) or {}
        recent_intents = summary.get("intents", [])
        if not context["turn_count"]:
            context["turn_count"] = summary.get("turn_count", 0)
        context["emotional_trajectory"] = summary.get("emotional_trajectory", "neutral")
    else:
        recent_intents = session_crisis_store.get_recent_intents(session_id)
        if not context["turn_count"]:
            context["turn_count"] = len(context["recent_user_messages"])

    context["recent_intents"] = recent_intents[-5:]

    non_neutral_intents = [
        intent for intent in recent_intents
        if intent in {"sadness", "depression", "anxiety", "stress", "anger", "fear", "abuse", "self_harm", "self_harassment"}
    ]
    for intent in reversed(recent_intents[-5:]):
        if intent in {"sadness", "depression", "anxiety", "stress", "anger", "fear", "abuse", "self_harm", "self_harassment"}:
            memory_map = {
                "sadness": "You mentioned feeling sad earlier.",
                "depression": "You mentioned feeling really low earlier.",
                "anxiety": "You mentioned feeling anxious earlier.",
                "stress": "You mentioned feeling overwhelmed earlier.",
                "anger": "You mentioned feeling angry earlier.",
                "fear": "You mentioned feeling afraid earlier.",
                "abuse": "You mentioned feeling unsafe earlier.",
                "self_harm": "You mentioned feeling overwhelmed earlier.",
                "self_harassment": "You mentioned feeling hurt earlier.",
            }
            context["emotional_memory"] = memory_map.get(intent, "")
            break

    if non_neutral_intents:
        latest_emotion = non_neutral_intents[-1]
        repeated_count = non_neutral_intents.count(latest_emotion)
        if repeated_count >= 2:
            continuity_map = {
                "sadness": "It seems like this sadness has been staying with you for a while.",
                "depression": "It seems like this low feeling has been hanging on for some time.",
                "anxiety": "It seems like this anxiety has kept coming back instead of settling.",
                "stress": "It seems like this stress has been building up over time.",
                "anger": "It seems like this frustration has been building up, not just showing up once.",
                "fear": "It seems like this fear has been lingering in the background for a while.",
                "abuse": "It seems like this sense of being unsafe has been ongoing.",
                "self_harm": "It seems like this pain has been building up over time.",
                "self_harassment": "It seems like this hurt has been building and repeating.",
            }
            context["emotional_continuity"] = continuity_map.get(latest_emotion, "")

    current_text = (current_user_text or "").strip().lower()
    if current_text in {"why", "how", "what do you mean", "what", "how so", "why is that"}:
        context["follow_up_mode"] = "clarification"
    elif current_text in {"idk", "i dont know", "i don't know", "hmm", "uh", "not sure"}:
        context["follow_up_mode"] = "uncertain"

    return context


def _contains_unprompted_helpline_content(text: str) -> bool:
    if not text:
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in UNPROMPTED_HELPLINE_PATTERNS)


def _sanitize_non_crisis_response(user_text, intent, response, recent_intents, conversation_context):
    """
    Guard normal conversational replies from accidentally leaking crisis resources.
    This protects against stale generations or model drift for ordinary distress.
    """
    if not response:
        return generate_human_response(intent, recent_intents, conversation_context, user_text=user_text)

    if detect_user_help_request(user_text):
        return response

    if _contains_unprompted_helpline_content(response):
        logger.warning("Removed unprompted helpline content from non-crisis %s response", intent)
        return generate_human_response(intent, recent_intents, conversation_context, user_text=user_text)

    return response


def _should_use_rag_context(user_text, intent, confidence):
    cleaned_text = (user_text or "").strip().lower()
    if not cleaned_text:
        return False

    short_inputs = SHORT_GREETING_INPUTS.union(SHORT_ACK_INPUTS).union(FOLLOW_UP_INPUTS).union(UNCERTAIN_INPUTS)
    if cleaned_text in short_inputs:
        return False

    word_count = len(cleaned_text.split())
    if confidence is None:
        return word_count >= 3 and intent in {"general", "normal", "distress"}

    if confidence <= 0.8:
        return True

    return intent in {"general", "normal", "distress"} and confidence < 0.9 and word_count >= 4


def chatbot(user_text, session_id=None, user_id=None, client_messages=None):
    """
    Main chatbot function with advanced features.

    Args:
        user_text: Raw user input
        session_id: Optional session ID for conversation tracking
        user_id: Optional user ID for personalization

    Returns:
        Tuple of (response: str, ui_state: str)
    """
    if session_id is None:
        session_id = "default_session"
    if user_id is None:
        user_id = "anonymous"

    if ADVANCED_FEATURES_ENABLED:
        if not rate_limiter.is_allowed(user_id):
            _store_response_metadata(session_id, "normal", 0.0, "normal_chat")
            return (
                "I'm receiving a lot of messages. Please wait a moment before sending another message. Take care of yourself! ",
                "normal_chat",
            )

    user_text = sanitize_input(user_text)

    if not user_text or not user_text.strip():
        _store_response_metadata(session_id, "normal", 0.0, "normal_chat")
        return ("I'm here to chat with you. Please share what's on your mind.", "normal_chat")

    session_crisis_store.note_user_message(session_id, user_text)
    situation = analyze_situation(user_text)

    if situation == "self_harm":
        save_intent("crisis", confidence=1.0, user_id=user_id, session_id=session_id)
        session_crisis_store.mark_intent(session_id, "self_harm")

        if ADVANCED_FEATURES_ENABLED:
            crisis_tracker.log_crisis(user_id, 1, user_text[:100])
            if crisis_tracker.should_escalate(user_id):
                logger.warning(
                    "Crisis escalation threshold reached for user %s (%s recent crises)",
                    user_id,
                    crisis_tracker.get_crisis_count(user_id),
                )

        crisis_guidance, ui_state = handle_crisis_logic(user_text, session_id, "self_harm", user_id=user_id)
        conversation_context = _build_conversation_context(session_id, client_messages=client_messages, current_user_text=user_text)
        response = generate_crisis_response(
            user_text,
            crisis_guidance,
            conversation_context=conversation_context,
            session_id=session_id,
        )

        if ADVANCED_FEATURES_ENABLED:
            context_manager.add_turn(session_id, user_text, response, "self_harm", {
                "ui_state": ui_state,
                "help_requested": detect_user_help_request(user_text),
                "crisis_stage": crisis_guidance.get("stage"),
            })

        session_crisis_store.note_response(session_id, response)
        _store_response_metadata(session_id, "self_harm", 1.0, ui_state)
        return (response, ui_state)

    if "third" in situation.lower():
        save_intent("third_person", confidence=1.0, user_id=user_id, session_id=session_id)
        session_crisis_store.mark_intent(session_id, "third_person")
        response = generate_safety_reply(user_text, "third_person")
        session_crisis_store.note_response(session_id, response)
        if ADVANCED_FEATURES_ENABLED:
            context_manager.add_turn(session_id, user_text, response, "third_person")
        ui_state = compute_ui_state_from_message(user_text)
        if ui_state not in ("third_person_crisis_card", "third_person_safety_card"):
            ui_state = "third_person_safety_card"
        _store_response_metadata(session_id, "third_person", 1.0, ui_state)
        return (response, ui_state)

    if situation == "abuse" or check_abuse_harassment(user_text):
        abuse_card_previously_shown = bool(session_crisis_store.get_state(session_id).get("crisis_shown")) or (
            session_crisis_store.resource_cooldown_active(session_id, user_id)
        )
        save_intent("abuse", confidence=1.0, user_id=user_id, session_id=session_id)
        session_crisis_store.mark_intent(session_id, "self_harassment")
        crisis_guidance, ui_state = handle_crisis_logic(user_text, session_id, "self_harassment", user_id=user_id)
        if ui_state == "normal_chat" and not abuse_card_previously_shown:
            session_crisis_store.get_state(session_id)["crisis_shown"] = True
            session_crisis_store.mark_resource_shown(session_id, user_id, "self_harassment")
            crisis_guidance = dict(crisis_guidance or {})
            crisis_guidance["include_helpline"] = True
            crisis_guidance["stage"] = "first_detection_show_resources"
            ui_state = "abuse_card"
        conversation_context = _build_conversation_context(session_id, client_messages=client_messages, current_user_text=user_text)
        response = generate_crisis_response(
            user_text,
            crisis_guidance,
            conversation_context=conversation_context,
            session_id=session_id,
        )
        if ADVANCED_FEATURES_ENABLED:
            context_manager.add_turn(session_id, user_text, response, "self_harassment", {
                "ui_state": ui_state,
                "help_requested": detect_user_help_request(user_text),
                "crisis_stage": crisis_guidance.get("stage"),
            })
        session_crisis_store.note_response(session_id, response)
        _store_response_metadata(session_id, "abuse", 1.0, ui_state)
        return (response, ui_state)

    intent, confidence = predict_intent(user_text)

    if intent == "distress":
        real_intent = detect_distress_type(user_text)
        save_intent(real_intent, confidence=confidence, user_id=user_id, session_id=session_id)
        intent = real_intent
    else:
        save_intent(intent, confidence=confidence, user_id=user_id, session_id=session_id)

    session_crisis_store.mark_intent(session_id, intent)
    recent_intents = session_crisis_store.get_recent_intents(session_id)
    conversation_context = _build_conversation_context(session_id, client_messages=client_messages, current_user_text=user_text)

    if _should_use_rag_context(user_text, intent, confidence):
        if ADVANCED_FEATURES_ENABLED:
            try:
                rag_results = hybrid_search(
                    user_text, faiss_index, bm25_index, situations, responses, k=2
                )
                if rag_results:
                    rag_context = rag_results[0][0]
                else:
                    rag_context = ""
            except Exception:
                try:
                    rag_context = search(user_text, faiss_index, situations, responses)[0]
                except Exception:
                    rag_context = ""
        else:
            try:
                rag_context = search(user_text, faiss_index, situations, responses)[0]
            except Exception:
                rag_context = ""
    else:
        rag_context = ""

    cache_excluded_inputs = SHORT_GREETING_INPUTS.union(SHORT_ACK_INPUTS).union(FOLLOW_UP_INPUTS).union(UNCERTAIN_INPUTS)
    use_safe_cache = (
        ADVANCED_FEATURES_ENABLED
        and intent in {"greeting", "normal"}
        and confidence >= 0.75
        and user_text.strip().lower() not in cache_excluded_inputs
    )

    if use_safe_cache:
        cached_response = response_cache.get(user_text, intent, "")
        if cached_response:
            session_crisis_store.note_response(session_id, cached_response)
            if ADVANCED_FEATURES_ENABLED:
                context_manager.add_turn(session_id, user_text, cached_response, intent, {
                    "confidence": confidence,
                    "rag_used": False,
                    "cache_hit": True,
                })
            _store_response_metadata(session_id, intent, confidence, "normal_chat")
            return (cached_response, "normal_chat")

    if ADVANCED_FEATURES_ENABLED:
        try:
            response = llm_circuit_breaker.call(
                generate_reply,
                user_text,
                intent,
                rag_context,
                recent_intents,
                None,
                False,
                conversation_context,
                session_id,
                confidence,
            )
        except Exception as e:
            logger.warning("LLM circuit breaker fallback triggered: %s", e)
            response = generate_human_response(
                intent,
                recent_intents,
                conversation_context,
                user_text=user_text,
                confidence=confidence,
                session_id=session_id,
            )
    else:
        response = generate_reply(
            user_text,
            intent,
            rag_context,
            recent_intents,
            conversation_context=conversation_context,
            session_id=session_id,
            confidence=confidence,
        )

    response = _sanitize_non_crisis_response(
        user_text,
        intent,
        response,
        recent_intents,
        conversation_context,
    )

    if ADVANCED_FEATURES_ENABLED and use_safe_cache:
        response_cache.set(user_text, intent, "", response)

    if ADVANCED_FEATURES_ENABLED:
        context_manager.add_turn(session_id, user_text, response, intent, {
            "confidence": confidence,
            "rag_used": bool(rag_context),
        })
        trajectory = context_manager.get_emotional_trajectory(session_id)
        if trajectory == "concerning":
            pass

    session_crisis_store.note_response(session_id, response)
    _store_response_metadata(session_id, intent, confidence, "normal_chat")

    return (response, "normal_chat")


def get_chatbot_stats():
    """Get chatbot statistics if advanced features are enabled."""
    if not ADVANCED_FEATURES_ENABLED:
        return {"status": "Advanced features not enabled"}

    return {
        "cache": response_cache.get_stats(),
        "rate_limit_remaining": rate_limiter.get_remaining(),
        "llm_circuit_state": llm_circuit_breaker.get_state(),
        "quality_score": quality_monitor.get_overall_score(),
    }
