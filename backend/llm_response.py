"""LLM response generation with supportive fallbacks and anti-repetition."""

import logging
import os
import random
import re

import requests


logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
    except ImportError:
        pass

if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set. LLM responses will use fallback mode.")
    OPENROUTER_API_KEY = None


_session_clients = {}

SHORT_GREETING_INPUTS = {"hi", "hii", "hello", "hey", "yo", "hi there", "hello there"}
SHORT_ACK_INPUTS = {"ok", "okay", "kk", "hmm", "huh", "fine", "yeah", "yep", "alright"}
FOLLOW_UP_INPUTS = {"why", "how", "what do you mean", "what", "how so", "why is that"}
UNCERTAIN_INPUTS = {"idk", "i dont know", "i don't know", "not sure", "hmm", "uh"}
AVOID_OPENING_PATTERNS = (
    "it sounds like",
    "that sounds",
    "it seems",
    "can you tell me more",
    "i can imagine how that must feel",
)
DEFAULT_HELPLINE_BLOCK = "AASRA (24/7): +91 9820466726\niCall (24/7): +91 9152987821\nEmergency (India): 108"
FOLLOW_UP_PREFIXES = ("why", "how")
STUCK_PATTERNS = (
    "i cant start",
    "i can't start",
    "cant even start",
    "can't even start",
    "dont know where to start",
    "don't know where to start",
    "dont know what to do",
    "don't know what to do",
    "unable to start",
    "stuck",
)
CONFUSION_MARKERS = (
    "idk",
    "i dont know",
    "i don't know",
    "not sure",
    "confused",
    "weird",
    "off",
)
POSITIVE_MARKERS = (
    "did really well",
    "went fine",
    "went well",
    "proud",
    "relieved",
    "happy",
    "thanks",
    "thank you",
)
ACTION_HINTS = ("try", "start", "pick", "take", "set", "open", "write", "choose", "focus", "step")
FORBIDDEN_MEMORY_PHRASES = ("you mentioned earlier", "earlier you said")
CONFUSION_METAPHORS = ("fog", "puzzle", "loop")
EXPLICIT_SELF_HARM_MARKERS = (
    "hurt myself",
    "kill myself",
    "end my life",
    "ending everything",
    "end everything",
    "feel like ending everything",
    "end it all",
    "want to die",
    "suicide",
    "suicidal",
    "self harm",
    "harm myself",
    "don't want to live",
    "dont want to live",
)


def get_llm_client(session_id=None):
    global _session_clients
    sid = session_id or "_default"
    if sid not in _session_clients:
        _session_clients[sid] = {"chat_history": [], "recent_replies": []}
    return _session_clients[sid]


def clear_session_client(session_id):
    global _session_clients
    if session_id in _session_clients:
        _session_clients[session_id]["chat_history"] = []
        _session_clients[session_id]["recent_replies"] = []


def llm_call(system_prompt, user_prompt, temperature=0.7, session_id=None):
    if not OPENROUTER_API_KEY:
        return None

    client = get_llm_client(session_id)
    chat_history = client["chat_history"]

    try:
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history[-12:])
        messages.append({"role": "user", "content": user_prompt})

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta-llama/llama-3-8b-instruct",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 300,
            },
            timeout=20,
        )
        result = response.json()
        if "choices" not in result or not result["choices"]:
            logger.warning("OpenRouter API error: %s", result.get("error", "Unknown error"))
            return None

        reply = result["choices"][0]["message"]["content"].strip()
        chat_history.append({"role": "user", "content": user_prompt})
        chat_history.append({"role": "assistant", "content": reply})
        if len(chat_history) > 20:
            chat_history[:] = chat_history[-20:]
        return reply
    except Exception as exc:
        logger.warning("LLM request failed: %s", str(exc)[:120])
        return None


def detect_distress_type(text):
    system_prompt = """You are a mental health classifier. Classify the user's mental state into ONLY ONE of these words:
- depression
- anxiety
- anger
- sadness
- stress
- fear

Reply with ONLY the word, nothing else."""

    result = llm_call(system_prompt, text, temperature=0.1)
    if result:
        valid_types = ["depression", "anxiety", "anger", "sadness", "stress", "fear"]
        cleaned = result.lower().strip()
        for value in valid_types:
            if value in cleaned:
                return value
    return "normal"


def _pick_non_repetitive(options, recent_responses=None):
    recent_responses = set(r.strip() for r in (recent_responses or []) if r)
    candidates = [option for option in options if option not in recent_responses] or list(options)
    return random.choice(candidates)


def _ensure_question(text: str, fallback_question: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return fallback_question
    if "?" in cleaned:
        return cleaned
    return f"{cleaned} {fallback_question}"


def _clean_reply(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _opening_fragment(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", "", (text or "").strip().lower())
    return " ".join(cleaned.split()[:6])


def _is_repetitive_reply(reply: str, recent_responses=None) -> bool:
    cleaned = _clean_reply(reply).lower()
    if not cleaned:
        return True

    opening = _opening_fragment(cleaned)
    recent_openings = {_opening_fragment(item) for item in (recent_responses or []) if item}

    if opening and opening in recent_openings:
        return True

    lowered_recent = " ".join((recent_responses or [])).lower()
    return any(pattern in cleaned and pattern in lowered_recent for pattern in AVOID_OPENING_PATTERNS)


def _has_question(text: str) -> bool:
    return "?" in (text or "")


def _format_list(values, limit=5):
    items = [str(value).strip() for value in (values or []) if str(value).strip()]
    if not items:
        return "None"
    return " | ".join(items[-limit:])


def _remember_reply(session_id, reply):
    if not reply:
        return
    client = get_llm_client(session_id)
    recent_replies = client.setdefault("recent_replies", [])
    recent_replies.append(_clean_reply(reply))
    if len(recent_replies) > 8:
        del recent_replies[:-8]


def _combined_recent_replies(conversation_context=None, session_id=None, limit=6):
    conversation_context = conversation_context or {}
    combined = []
    combined.extend(str(item).strip() for item in (conversation_context.get("recent_bot_replies") or []) if str(item).strip())
    combined.extend(get_llm_client(session_id).get("recent_replies", []))

    deduped = []
    seen = set()
    for item in combined:
        key = item.strip()
        if key and key not in seen:
            deduped.append(key)
            seen.add(key)
    return deduped[-limit:]


def _recent_reply_had_question(recent_responses=None):
    recent_responses = [item for item in (recent_responses or []) if item]
    if not recent_responses:
        return False
    return _has_question(recent_responses[-1])


def _is_follow_up_message(cleaned_text):
    text = (cleaned_text or "").strip()
    return (
        text in FOLLOW_UP_INPUTS
        or any(text.startswith(f"{prefix} ") for prefix in FOLLOW_UP_PREFIXES)
        or "what do you mean" in text
    )


def _is_stuck_input(text):
    cleaned = (text or "").lower()
    return any(pattern in cleaned for pattern in STUCK_PATTERNS)


def _is_confusion_input(text):
    cleaned = (text or "").lower()
    return any(marker in cleaned for marker in CONFUSION_MARKERS)


def _is_positive_input(text):
    cleaned = (text or "").lower()
    return any(marker in cleaned for marker in POSITIVE_MARKERS)


def _is_explicit_self_harm_text(text):
    cleaned = (text or "").lower()
    return any(marker in cleaned for marker in EXPLICIT_SELF_HARM_MARKERS)


def _infer_support_intent_from_text(text):
    cleaned = (text or "").lower()
    if any(word in cleaned for word in ("exam", "panic", "anxious", "anxiety", "worry", "worried")):
        return "anxiety"
    if any(word in cleaned for word in ("stress", "overwhelmed", "too much work", "deadline", "focus", "cant start", "can't start")):
        return "stress"
    if any(word in cleaned for word in ("sad", "down", "cry", "lonely")):
        return "sadness"
    if any(word in cleaned for word in ("angry", "mad", "frustrated", "annoyed")):
        return "anger"
    if any(word in cleaned for word in ("scared", "afraid", "fear")):
        return "fear"
    return "normal"


def _recent_self_harm_context(conversation_context=None):
    conversation_context = conversation_context or {}
    recent_user_messages = conversation_context.get("recent_user_messages") or []
    recent_context = conversation_context.get("recent_context") or ""
    return any(_is_explicit_self_harm_text(item) for item in recent_user_messages) or _is_explicit_self_harm_text(recent_context)


def _contains_action_step(text):
    lowered = (text or "").lower()
    return any(hint in lowered for hint in ACTION_HINTS)


def _contains_helpline(text):
    lowered = (text or "").lower()
    return "aasra" in lowered or "icall" in lowered or "emergency" in lowered or "+91 9820466726" in lowered


def _should_recover_missing_reply(conversation_context=None, cleaned_text=""):
    conversation_context = conversation_context or {}
    unresolved = (conversation_context.get("unanswered_user_message") or "").strip()
    recent_replies = conversation_context.get("recent_bot_replies") or []
    return bool(unresolved and not recent_replies and unresolved.lower() != cleaned_text)


def _reply_violates_support_rules(reply, cleaned_text, conversation_context=None, session_id=None, require_action=False):
    if not reply:
        return True

    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    lowered = _clean_reply(reply).lower()

    if _is_repetitive_reply(reply, recent_responses):
        return True
    if any(phrase in lowered for phrase in FORBIDDEN_MEMORY_PHRASES):
        return True
    if any(pattern in lowered for pattern in AVOID_OPENING_PATTERNS):
        return True
    if _recent_reply_had_question(recent_responses) and _has_question(reply):
        return True
    if cleaned_text in SHORT_GREETING_INPUTS.union(SHORT_ACK_INPUTS).union(UNCERTAIN_INPUTS) and _has_question(reply):
        return True
    if _is_follow_up_message(cleaned_text) and _has_question(reply):
        return True
    if _is_confusion_input(cleaned_text) and any(marker in lowered for marker in CONFUSION_METAPHORS):
        return True
    if _is_positive_input(cleaned_text) and _has_question(reply):
        return True
    if require_action and not _contains_action_step(reply):
        return True
    return False


def _reply_violates_crisis_rules(reply, recent_responses=None, require_helpline=False):
    if not reply:
        return True
    lowered = _clean_reply(reply).lower()
    if _is_repetitive_reply(reply, recent_responses):
        return True
    if lowered.count("?") > 1:
        return True
    if "are you safe" in lowered and any("are you safe" in item.lower() for item in (recent_responses or [])):
        return True
    if require_helpline and not _contains_helpline(reply):
        return True
    return False


def _detect_progression_stage(conversation_context=None):
    conversation_context = conversation_context or {}
    turn_count = int(conversation_context.get("turn_count") or 0)
    if turn_count <= 1:
        return "early"
    if turn_count <= 4:
        return "mid"
    return "later"


def _build_micro_action_suggestions(intent, user_text):
    text = (user_text or "").lower()
    suggestions = []

    if intent in {"stress", "anxiety"} or "exam" in text or "deadline" in text:
        suggestions.extend([
            "Try shrinking the next step to just 5 minutes.",
            "Pick one small task instead of the whole list.",
            "Take one slow breath, then start with the easiest part.",
        ])

    if intent in {"stress", "anger"} or any(word in text for word in ["frustrated", "annoyed", "irritated", "stuck"]):
        suggestions.extend([
            "A short break and reset might help more than forcing it right now.",
            "Step away for a minute, loosen your shoulders, then come back to one small thing.",
        ])

    if any(word in text for word in ["focus", "concentrate", "distracted", "procrastinating", "study"]):
        suggestions.extend([
            "You could try putting your phone away for one short work block.",
            "Set a timer for 10 minutes and only do the first tiny piece.",
        ])

    deduped = []
    for suggestion in suggestions:
        if suggestion not in deduped:
            deduped.append(suggestion)
    return deduped


def _build_emotional_continuity(conversation_context=None):
    # Avoid inferred emotional memory unless it is explicitly restated by the user.
    return ""


def _handle_short_input(cleaned_text, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    recent_user_messages = conversation_context.get("recent_user_messages", [])
    has_prior_context = len(recent_user_messages) > 1 or bool(conversation_context.get("recent_context"))

    if cleaned_text in SHORT_GREETING_INPUTS:
        options = [
            "Hey, I'm here with you. We can take this one message at a time.",
            "Hi. I'm glad you checked in.",
            "Hey, good to see you here.",
            "Hello. I'm here with you.",
        ]
        return _pick_non_repetitive(options, recent_responses)

    if cleaned_text in SHORT_ACK_INPUTS and has_prior_context:
        options = [
            "Okay. We can keep this simple and go one step at a time.",
            "Alright. No pressure to say a lot right now.",
            "Okay. We can stay with this gently.",
            "Alright. We can keep going at your pace.",
        ]
        return _pick_non_repetitive(options, recent_responses)

    if cleaned_text in UNCERTAIN_INPUTS:
        options = [
            "That's okay. We can keep this simple.",
            "No pressure. A few words is enough.",
            "That's alright. We can slow this down.",
            "Okay. We can take one small step at a time.",
        ]
        return _pick_non_repetitive(options, recent_responses)

    return None


def _build_follow_up_fallback(cleaned_text, intent, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    unanswered_user_message = (conversation_context.get("unanswered_user_message") or "").strip()
    recent_messages = " ".join(conversation_context.get("recent_user_messages") or []).lower()
    full_context = f"{recent_messages} {cleaned_text}".strip()
    exam_context = any(word in full_context for word in ("exam", "test", "study", "fail", "panic"))
    work_context = any(word in full_context for word in ("work", "task", "deadline", "focus"))
    prefix = f"I don't want to miss what you said about \"{unanswered_user_message}.\" " if unanswered_user_message else ""

    if _is_follow_up_message(cleaned_text):
        if cleaned_text.startswith("why") and exam_context:
            options = [
                f"{prefix}Panic like that often builds from pressure, expectations, or fear of failing. When your mind treats the exam like one huge threat, everything can start feeling urgent at once.",
                f"{prefix}That kind of panic usually comes from pressure stacking up. Fear of failing, tiredness, and high expectations can all make your body stay on alert.",
            ]
        elif cleaned_text.startswith("why") and work_context:
            options = [
                f"{prefix}That usually happens when pressure has been piling up faster than you can reset. When everything feels urgent, your brain can freeze instead of choosing a starting point.",
                f"{prefix}Stress like this often grows from too many demands landing at once. After a point, even simple tasks can feel harder to begin.",
            ]
        elif cleaned_text.startswith("why"):
            explanation_map = {
                "sadness": "Sadness can build from stress, loneliness, disappointment, or a few hard things piling up together. It is not always one clear reason.",
                "stress": "Stress usually grows when too many demands pile up without enough room to recover. After a while, even small things can feel heavier.",
                "anxiety": "Anxiety often builds from pressure, uncertainty, and fear of what might go wrong. Once it starts looping, your body can stay tense even when you want to calm down.",
                "anger": "Anger usually grows when something feels unfair, exhausting, or repeatedly frustrating. It is often about more than one small moment.",
                "depression": "Low feelings can build from exhaustion, isolation, pressure, or carrying too much for too long. It is not always one simple cause.",
                "fear": "Fear usually grows when something feels uncertain or out of your control. Your mind starts watching for danger even when it wants relief.",
            }
            options = [
                f"{prefix}{explanation_map.get(intent, 'Sometimes feelings like this build from a few pressures at once, not one simple reason.')} We can take it one piece at a time.",
                f"{prefix}{explanation_map.get(intent, 'There is not always one clean answer. A few things can build together and make it feel heavier.')} We can sort through it slowly.",
            ]
        elif cleaned_text.startswith("how"):
            if work_context or _is_stuck_input(recent_messages):
                options = [
                    f"{prefix}Start with the smallest visible step. Open the task, do one minute of it, and let that be enough for now.",
                    f"{prefix}Make the first step tiny. Pick one task, spend five minutes on it, and stop there if you need to.",
                ]
            else:
                options = [
                    f"{prefix}Start by looking for the simplest part of what you are feeling. Naming one piece is enough to begin.",
                    f"{prefix}Keep it small. Notice one thought, one feeling, or one task that stands out the most, and start there.",
                ]
        else:
            options = [
                f"{prefix}I mean this may be coming from a few things at once, not one simple cause. Pressure, tiredness, or difficult thoughts can all mix together.",
                f"{prefix}I mean the feeling can be real even when the reason is not obvious. Sometimes it takes a little time to see what is feeding it.",
            ]
        return _pick_non_repetitive(options, recent_responses)

    if cleaned_text in UNCERTAIN_INPUTS:
        options = [
            f"{prefix}That's okay. You do not need the right words right away.",
            f"{prefix}That's alright. We can keep this simple and go one small step at a time.",
            f"{prefix}No pressure. Even a few words is enough for us to keep going.",
        ]
        return _pick_non_repetitive(options, recent_responses)

    return None


def _build_missing_response_recovery_reply(intent, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    unresolved = (conversation_context.get("unanswered_user_message") or "").strip()
    if not unresolved:
        return None

    unresolved_lower = unresolved.lower()
    if "bad day at home" in unresolved_lower:
        options = [
            "I do not want to miss what you said about having a bad day at home. That kind of tension can make focusing feel almost impossible. Try picking one tiny task, like opening what you need to do and staying with it for one minute.",
            "I do not want to skip past the bad day at home. When something like that lingers, focus can fall apart fast. Start with one very small task so your mind has one clear place to land.",
        ]
    else:
        options = [
            f"I do not want to miss what you said about \"{unresolved}.\" That still matters here. Try taking one very small next step so this feels a little less tangled.",
            f"I do not want to skip over \"{unresolved}.\" That can affect everything that comes after it. Pick one tiny next step and let that be enough for now.",
        ]
    return _pick_non_repetitive(options, recent_responses)


def _build_stuck_reply(intent, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    options = [
        "Getting started can feel impossible when everything feels piled up. Pick the smallest visible step, like opening the task or writing one line, and give it five minutes.",
        "When your brain locks up like this, make the first step tiny. Choose one task, do the first minute of it, and stop there if you need to.",
        "You do not need a full plan right now. Start with one very small action, like opening the page or making a two-item list.",
    ]
    return _pick_non_repetitive(options, recent_responses)


def _build_confusion_reply(cleaned_text, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    if cleaned_text.startswith("how"):
        options = [
            "Start by noticing whether this feels more like tension in your body or noise in your thoughts. Naming just one part is enough.",
            "Keep it simple. Check whether this feels more mental, physical, or emotional, and start with whichever stands out most.",
        ]
    elif "weird" in cleaned_text or "off" in cleaned_text:
        options = [
            "Feeling weird or off can happen when your mind is overloaded or unsettled. You do not need to explain it perfectly for it to matter.",
            "That kind of off feeling can show up when you are tired, stressed, or mentally overloaded. It is okay if it is not clear yet.",
        ]
    else:
        options = [
            "That's okay. You do not need the perfect word for this right now. We can keep it simple and stay with what feels most noticeable.",
            "Not knowing is okay. Start with one basic check: does this feel more like sadness, stress, or mental overload right now?",
        ]
    return _pick_non_repetitive(options, recent_responses)


def _build_positive_reply(cleaned_text, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    if "thanks" in cleaned_text or "thank you" in cleaned_text:
        options = [
            "You are welcome. Give yourself credit for how you handled that.",
            "Of course. You earned that moment, so try not to rush past it.",
        ]
    else:
        options = [
            "That is really good to hear. You should let yourself feel proud of that.",
            "That is a solid win. It is worth giving yourself credit for it.",
        ]
    return _pick_non_repetitive(options, recent_responses)


def _build_crisis_continuation_reply(cleaned_text, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    helpline_already_shared = any(_contains_helpline(item) for item in recent_responses)

    if cleaned_text in UNCERTAIN_INPUTS:
        options = [
            "Thank you for staying with me. I'm here with you, and I want to keep this focused on your safety right now. Please call one of those support numbers now or tell someone near you that you need help.",
            "I'm still here with you. Please reach out to one of those crisis supports now or get a trusted person to stay with you.",
        ]
    else:
        options = [
            "I'm still with you. Stay with another person if you can and keep the focus on the next few minutes.",
            "I'm here with you. Keep things very simple right now and stay close to someone safe if you can.",
        ]

    if not helpline_already_shared:
        options = [
            "Thank you for staying with me. I'm here with you, and your safety matters right now.\n\n"
            f"{DEFAULT_HELPLINE_BLOCK}\n\n"
            "Please call one of these numbers now or tell someone near you that you need help."
        ]

    return _pick_non_repetitive(options, recent_responses)


def _build_support_system_prompt(
    intent,
    user_text,
    rag_context,
    recent_intents,
    conversation_context=None,
    confidence=None,
):
    conversation_context = conversation_context or {}
    progression_stage = _detect_progression_stage(conversation_context)
    confidence_mode = "low-confidence" if confidence is not None and confidence < 0.75 else "normal"
    recent_messages = _format_list(conversation_context.get("recent_user_messages"), limit=5)
    recent_replies = _format_list(conversation_context.get("recent_bot_replies"), limit=4)
    recent_context = conversation_context.get("recent_context") or "None"
    emotional_continuity = _build_emotional_continuity(conversation_context) or "None"
    micro_actions = _format_list(_build_micro_action_suggestions(intent, user_text), limit=3)
    recent_intent_text = _format_list(recent_intents, limit=5)
    trajectory = conversation_context.get("emotional_trajectory") or "neutral"
    profile_hints = conversation_context.get("user_profile_hints") or "None"
    follow_up_mode = conversation_context.get("follow_up_mode") or "none"
    unanswered_user_message = conversation_context.get("unanswered_user_message") or "None"
    last_completed_assistant_reply = conversation_context.get("last_completed_assistant_reply") or "None"

    return f"""You are Serenity, a warm mental health support chatbot.

Your goal is to feel human, natural, and emotionally aware - not robotic, repetitive, or interrogative.

CONVERSATION CONTEXT
- Current intent: {intent}
- Confidence mode: {confidence_mode}
- Conversation stage: {progression_stage}
- Emotional trajectory: {trajectory}
- Emotional continuity note: {emotional_continuity}
- Recent user messages: {recent_messages}
- Recent intents: {recent_intent_text}
- Recent assistant replies (avoid repeating): {recent_replies}
- User profile hints (if available): {profile_hints}
- RAG context (if low confidence): {rag_context or 'None'}
- Micro-actions (optional suggestions): {micro_actions}
- Recent turn context: {recent_context}
- Follow-up mode: {follow_up_mode}
- Possible missed user message needing recovery: {unanswered_user_message}
- Last completed assistant reply to clarify if needed: {last_completed_assistant_reply}

RESPONSE GOALS
1. Acknowledge the user's emotion naturally.
2. Reflect relevant context from recent conversation. Do not act stateless.
3. Then choose only one of these:
   - ask one gentle question
   - offer one small realistic suggestion
   - make one supportive reflection without a question

STRICT RULES
- Anti-repetition:
  - Do not reuse the same opening style as the last reply
  - If the previous reply started with reflection, do not start with reflection again
  - Avoid repeating sentence structures even with different words
- Question control:
  - Do not ask a question in every response
  - Only ask when it adds value
- Natural tone:
  - Use warm, slightly casual, human language
  - Avoid robotic phrases like "It sounds like", "Can you tell me more", or "I can imagine how that must feel"
  - Prefer phrasings like "Yeah, that sounds really exhausting" or "That's honestly a lot to deal with"
- Length:
  - Keep responses concise: 2 to 4 sentences max

MEMORY AND CONTINUITY
- Always consider the last 3 to 5 messages
- If the same emotion repeats, acknowledge it as ongoing
- Use emotional trajectory to maintain continuity

MICRO-ACTIONS
- Suggest small actions only if they naturally fit
- Do not force advice in every reply

CONVERSATION PROGRESSION
- Early stage: empathy
- Mid stage: reflection plus light support
- Later stage: gentle guidance or actionable help
- Do not stay at the same level throughout the conversation

LOW CONFIDENCE MODE
- Do not over-interpret
- Stick closely to the user's exact words
- Prefer reflecting what the user said instead of guessing meaning

POSITIVE EMOTIONS
- Acknowledge and celebrate
- Reinforce confidence
- Do not immediately shift to questioning

NEVER DO
- Do not give medical advice.
- Do not sound robotic or scripted.
- Do not ask too many questions.
- Do not ignore previous context.
- Do not force suggestions unnaturally.

SMART USE
- For stress, frustration, lack of focus, exams, deadlines, or overwhelm, prefer tiny actionable suggestions over abstract advice when they fit.

ADDITIONAL STRICT RULES
- Greeting repetition:
  - For greetings or short acknowledgements like hi, hello, ok, rotate responses naturally
  - Do not repeat the same greeting style within the last 3 turns
- Memory safety:
  - Only reference past emotions or context if the user explicitly mentioned them in this conversation
  - Do not assume, infer, or hallucinate previous emotional states
- Crisis handling:
  - In crisis situations: first provide emotional grounding, then reassure presence, then focus on safety, then provide helpline resources
  - Do not ask "are you safe?" more than once
  - Do not repeat the same safety question
  - Reduce the number of questions and stay direct, calm, and supportive
- Question control:
  - Do not ask a question in every response
  - After positive or stable messages, avoid asking a question immediately
- Language variation:
  - Avoid repeating phrases like "that sounds" or "it seems"
  - Do not use the same sentence structure more than twice consecutively
- Low-clarity handling:
  - For vague inputs like idk, hmm, or unsure, keep responses simple
  - Avoid metaphors and avoid over-explaining
- Progression:
  - If the conversation exceeds 3 turns, shift from empathy toward one gentle suggestion when helpful
  - Avoid repeating only validation after that point
- Micro-actions:
  - If the user feels stuck, overwhelmed, or unable to act, include exactly one small actionable suggestion
  - Do not force suggestions in every response
- Short input handling:
  - For repeated short inputs, respond casually and move the conversation forward
  - Do not repeat the same short-input response
- Follow-up handling:
  - If the user sends short follow-ups like why, how, what do you mean, or idk, treat them as continuation of the previous context
  - Expand or clarify the previous response naturally
  - Do not give a generic emotional reply
  - Do not ignore the follow-up question
- Missing response recovery:
  - If a previous user message may not have received a response, acknowledge that message and continue naturally
  - Do not ignore earlier emotional input when recovering the flow
- Continuity:
  - Always consider the last 3 to 5 messages together
  - Never treat the current message as isolated

FINAL FIX RULES
- Follow-up handling:
  - If the user sends "why", "how", or "what do you mean", treat it as continuation of the immediately previous context
  - Give a simple explanation or clarification
  - Do not refuse the follow-up
  - Do not answer a follow-up with another question
- Memory accuracy:
  - Only reference past emotions or earlier context if they were explicitly stated in this conversation
  - Do not use generic phrases like "you mentioned earlier"
  - Do not hallucinate past context or emotional history
- Anti-repetition:
  - Do not repeat the same greeting within the last 3 turns
  - Do not repeat the same sentence structure more than 2 times in a row
  - Avoid repeating phrases like "that sounds" and "it seems"
- Short input handling:
  - For hi, ok, hmm, and idk, respond casually
  - Do not inject emotional assumptions into very short inputs
  - Move the conversation forward naturally
- Stuck user handling:
  - If the user says they cannot start or do not know what to do, include exactly one small actionable suggestion
- Conversation progression:
  - After 3 or more turns, shift from empathy toward one gentle suggestion when useful
  - Do not keep repeating only validation
- Crisis gating:
  - Crisis-style guidance should only be used for explicit self-harm intent or clear danger
  - Do not treat confusion, stress, idk, or vague uncertainty as crisis by themselves
- Crisis response structure:
  - In crisis situations, follow this order: emotional grounding, presence, one safety check, helpline resources, ongoing support
  - Ask the safety check only once
  - After that, do not keep repeating questions
- OK handling:
  - If the user says "ok", do not end the conversation abruptly
  - Continue gently and help the conversation move forward
- Missing response recovery:
  - If a previous user message may not have received a reply, acknowledge that message and continue naturally
  - Do not ignore unresolved context from the immediately recent conversation

ABSOLUTE FINAL RULES:
- Follow-up ("why", "how"):
  - Must give a clear, direct explanation
  - Example: "Panic like that often builds from pressure, expectations, or fear of failing."
  - No vague responses
  - No emotional avoidance
- Crisis mode:
  - If self-harm intent is present, the response must follow this exact order:
    1. emotional grounding
    2. "I'm here with you"
    3. one safety check only
    4. provide helpline resources
    5. continue support without repeated questions
  - Missing helpline is a failure
- Questions:
  - Use at most one question every two replies
- Repetition:
  - Do not repeat the same opening phrases
  - Avoid "that sounds" and "it seems"
- Stuck users:
  - Must include exactly one small actionable step
- Memory:
  - No fake memory
  - Do not say "you mentioned earlier" unless it is exact and visible in context
- Short inputs:
  - For hi, ok, hmm, and idk, use a casual, neutral reply only
- Confusion:
  - No metaphors
  - Keep it simple and clear
- "ok":
  - Continue gently
  - Do not end the response abruptly

- Output only the reply text.
"""


def _fallback_crisis_response(user_text, crisis_guidance, recent_responses=None):
    stage = crisis_guidance.get("stage", "")
    crisis_kind = crisis_guidance.get("crisis_kind", "self_harm")
    helpline_text = crisis_guidance.get("helpline_text") or DEFAULT_HELPLINE_BLOCK
    include_helpline = bool(crisis_guidance.get("include_helpline")) or crisis_kind == "self_harm"
    helpline_shared = any(_contains_helpline(item) for item in (recent_responses or []))
    recent_question = _recent_reply_had_question(recent_responses)
    cleaned_text = (user_text or "").lower().strip()

    if crisis_kind == "self_harm":
        if include_helpline and not helpline_shared:
            options = [
                "I'm really glad you told me this. I'm here with you, and your safety matters right now. Are you safe in this moment?\n\n"
                f"{helpline_text}\n\n"
                "If you can, call one of these numbers now or reach out to someone nearby who can stay with you.",
                "Thank you for saying this out loud. I'm here with you, and I want to keep the focus on your safety. Are you safe right now?\n\n"
                f"{helpline_text}\n\n"
                "Please contact one of these supports now or tell a trusted person near you that you need help.",
            ]
        elif recent_question:
            options = [
                "Thank you for staying with me. I'm here with you, and I want to keep this focused on your safety right now.\n\n"
                f"{helpline_text if include_helpline and not helpline_shared else 'Please use the support numbers I shared or reach out to someone nearby right now.'}\n\n"
                "Stay with another person if you can and make that call now.",
                "I'm still here with you. Please reach out to one of those crisis supports now or tell someone near you that you need immediate help.\n\n"
                f"{helpline_text if include_helpline and not helpline_shared else 'Your safety matters more than handling this alone.'}",
            ]
        else:
            options = [
                "I'm here with you. Keep this moment very simple and stay focused on being near another person if you can.",
                "I'm still with you. Please stay close to someone safe and keep using the crisis supports that are available right now.",
            ]
    elif stage in {"repeat_detection_show_resources", "user_requested_help"} and include_helpline:
        options = [
            "I'm really sorry you're going through this. I'm here with you, and your safety matters right now.\n\n"
            f"{helpline_text}\n\n"
            "Please reach out now or contact someone you trust to stay with you.",
            "Thank you for asking for help. I'm here with you, and support is available right now.\n\n"
            f"{helpline_text}\n\n"
            "Please contact one of these supports now or ask a trusted person to stay with you.",
        ]
    elif stage == "first_detection":
        options = [
            "I'm really sorry this is happening. I'm here with you, and I want to keep the focus on your safety. Are you safe right now?",
            "Thank you for telling me this. I'm here with you. Are you safe in this moment?",
        ]
    elif stage == "post_crisis_support":
        options = [
            "I'm still here with you. Let's keep this moment simple and stay focused on what helps you feel safer right now.",
            "I'm here with you, and we can keep this steady. Stay close to whatever helps you feel safest in the next few minutes.",
        ]
    else:
        options = [
            "I'm glad you said this out loud. I'm here with you, and what you're feeling matters.",
            "I'm here with you. We can keep this steady and focused on what helps you feel safer.",
        ]

    reply = _pick_non_repetitive(options, recent_responses)
    return _clean_reply(reply)


def generate_human_response(intent, recent_intents=None, conversation_context=None, user_text="", confidence=None, session_id=None):
    recent_intents = recent_intents or []
    conversation_context = conversation_context or {}
    recent_responses = _combined_recent_replies(conversation_context, session_id)
    cleaned_text = (user_text or "").lower().strip()
    progression_stage = _detect_progression_stage(conversation_context)
    ask_allowed = not _recent_reply_had_question(recent_responses)

    if _should_recover_missing_reply(conversation_context, cleaned_text):
        return _build_missing_response_recovery_reply(intent, conversation_context, session_id)

    follow_up_fallback = _build_follow_up_fallback(cleaned_text, intent, conversation_context, session_id)
    if follow_up_fallback:
        return follow_up_fallback
    short_input_reply = _handle_short_input(cleaned_text, conversation_context, session_id)

    if short_input_reply:
        return short_input_reply

    if _is_stuck_input(cleaned_text):
        return _build_stuck_reply(intent, conversation_context, session_id)

    if _is_confusion_input(cleaned_text):
        return _build_confusion_reply(cleaned_text, conversation_context, session_id)

    if _is_positive_input(cleaned_text):
        return _build_positive_reply(cleaned_text, conversation_context, session_id)

    acknowledgements = {
        "greeting": [
            "I'm glad you're here.",
            "It's good to hear from you.",
            "I'm here with you.",
        ],
        "normal": [
            "Thanks for saying that.",
            "I'm with you.",
            "That makes sense to bring here.",
        ],
        "anxiety": [
            "That kind of anxiety can wear you down fast.",
            "Your mind sounds like it has been stuck on high alert.",
            "Anxiety like this can drain a lot of energy quickly.",
        ],
        "depression": [
            "This feels really heavy.",
            "I'm sorry things have felt this low.",
            "That kind of heaviness can make everything harder.",
        ],
        "sadness": [
            "This feels painful.",
            "I'm sorry this has been hitting you so hard.",
            "That kind of sadness can sit heavily for a while.",
        ],
        "anger": [
            "Yeah, that looks really frustrating.",
            "I can see why that would get under your skin.",
            "That looks upsetting and draining.",
        ],
        "stress": [
            "Yeah, this looks really exhausting.",
            "That is a lot to carry at once.",
            "No wonder you feel stretched thin.",
        ],
        "fear": [
            "This feels really unsettling.",
            "That kind of fear can take over your whole headspace.",
            "Yeah, that would be hard to sit with.",
        ],
    }

    reflections = {
        "greeting": [
            "We can take this one step at a time.",
            "This can be a steady place to check in.",
        ],
        "normal": [
            "You do not have to explain it perfectly.",
            "We can keep this simple.",
        ],
        "anxiety": [
            "When that pressure keeps looping, even small things can feel bigger.",
            "When anxiety keeps running, even basic things can feel louder than usual.",
        ],
        "depression": [
            "When that heaviness keeps building, even basic things can feel hard.",
            "Low energy like this can make normal tasks feel much heavier.",
        ],
        "sadness": [
            "When sadness lingers, it can make everything feel slower and heavier.",
            "Sadness like this can stay in the background and wear you down.",
        ],
        "anger": [
            "When something keeps rubbing the same sore spot, anger can come up fast.",
            "When the same pressure keeps hitting, frustration can build quickly.",
        ],
        "stress": [
            "When too many things stack up, your system barely gets a chance to reset.",
            "A pile-up like this can make it hard to find a clear starting point.",
        ],
        "fear": [
            "When fear keeps showing up, it can shrink your sense of breathing room.",
            "Fear like this can make your whole day feel tighter.",
        ],
    }

    questions = {
        "greeting": [
            "What feels most present for you today?",
            "What would help to talk through first?",
        ],
        "normal": [
            "What feels most important right now?",
            "What part of this is bothering you most?",
        ],
        "anxiety": [
            "What part of it feels hardest right now?",
            "What has your mind been circling back to most?",
        ],
        "depression": [
            "What has felt hardest lately?",
            "What has the last day or two been like for you?",
        ],
        "sadness": [
            "What feels most tender about it right now?",
            "Do you want to say what has been hurting most?",
        ],
        "anger": [
            "What part of the situation is bothering you most?",
            "What happened right before this spiked for you?",
        ],
        "stress": [
            "What is taking the biggest toll on you right now?",
            "Which part feels most urgent at the moment?",
        ],
        "fear": [
            "What feels most scary about it right now?",
            "What outcome are you most worried about?",
        ],
    }

    suggestions = _build_micro_action_suggestions(intent, user_text)
    base_ack = _pick_non_repetitive(acknowledgements.get(intent) or acknowledgements["normal"], recent_responses)
    base_reflection = _pick_non_repetitive(reflections.get(intent) or reflections["normal"], recent_responses)
    base_question = _pick_non_repetitive(questions.get(intent) or questions["normal"], recent_responses)
    base_suggestion = _pick_non_repetitive(suggestions, recent_responses) if suggestions else ""

    if progression_stage == "early":
        options = [
            f"{base_ack} {base_reflection}",
            f"{base_ack} {base_question}" if ask_allowed else f"{base_ack} {base_reflection}",
            f"{base_ack} {base_suggestion}" if base_suggestion and intent in {"stress", "anxiety"} else f"{base_ack} {base_reflection}",
        ]
    elif progression_stage == "mid":
        options = [
            f"{base_ack} {base_suggestion}" if base_suggestion else f"{base_ack} {base_reflection}",
            f"{base_ack} {base_reflection}",
            f"{base_ack} {base_question}" if ask_allowed and confidence is not None and confidence < 0.75 else f"{base_ack} {base_reflection}",
        ]
    else:
        options = [
            f"{base_ack} {base_suggestion}" if base_suggestion else f"{base_ack} {base_reflection}",
            f"{base_ack} {base_reflection}",
            f"{base_ack} {base_question}" if ask_allowed and confidence is not None and confidence < 0.6 else f"{base_ack} {base_suggestion or base_reflection}",
        ]

    reply = _clean_reply(_pick_non_repetitive(options, recent_responses))
    return reply


def generate_crisis_response(user_text, crisis_guidance, conversation_context=None, session_id=None):
    conversation_context = conversation_context or {}
    recent_bot_replies = _combined_recent_replies(conversation_context, session_id)
    recent_user_messages = conversation_context.get("recent_user_messages", [])
    recent_explicit_self_harm = any(_is_explicit_self_harm_text(item) for item in recent_user_messages)
    memory = crisis_guidance.get("memory", "None")
    stage = crisis_guidance.get("stage", "supportive_non_crisis")
    crisis_kind = crisis_guidance.get("crisis_kind", "self_harm")
    severity = crisis_guidance.get("severity", "low")
    include_helpline = bool(crisis_guidance.get("include_helpline")) or crisis_kind == "self_harm"
    helpline_text = crisis_guidance.get("helpline_text") or DEFAULT_HELPLINE_BLOCK
    cooldown_active = bool(crisis_guidance.get("cooldown_active"))
    recent_context = conversation_context.get("recent_context", "")

    if crisis_kind == "self_harm" and not (_is_explicit_self_harm_text(user_text) or recent_explicit_self_harm):
        fallback_intent = _infer_support_intent_from_text(user_text)
        reply = generate_human_response(
            fallback_intent,
            conversation_context=conversation_context,
            user_text=user_text,
            confidence=1.0,
            session_id=session_id,
        )
        _remember_reply(session_id, reply)
        return reply

    system_prompt = f"""You are Serenity in SAFETY OVERRIDE mode for a mental health support chat.

CURRENT STAGE: {stage}
CRISIS KIND: {crisis_kind}
SEVERITY: {severity}
RECENT USER MESSAGES: {recent_user_messages or ['None']}
EMOTIONAL MEMORY TO USE IF NATURAL: {memory or 'None'}
RECENT ASSISTANT REPLIES TO AVOID REPEATING: {recent_bot_replies or ['None']}
RECENT CONTEXT: {recent_context or 'None'}
RESOURCE COOLDOWN ACTIVE: {cooldown_active}

PRIORITY ORDER
1. Support immediate safety
2. Be direct, calm, caring, and human
3. Encourage real-world support when appropriate

MANDATORY RULES
- Use short, grounded language
- Sound warm and serious, not chatty
- Do not ask multiple questions
- Ask at most one question, and only if it helps immediate safety
- Do not explore abstractly or ask for a detailed backstory
- Do not use robotic therapy phrases
- Keep it concise: 2 to 3 short sentences before any helpline block
- Do not provide medical advice

STAGE RULES
- supportive_non_crisis: support gently, no helplines
- immediate_self_harm: respond like an active crisis on this very message, include the helpline block, and keep the tone direct and steady
- first_detection: acknowledge pain, say you're glad they told you, ask only a direct safety check if needed
- repeat_detection_show_resources: prioritize safety, encourage immediate offline help, include the helpline block exactly once
- post_crisis_support: keep supporting without automatically repeating resources
- user_requested_help: honor the request and include the helpline block exactly once

CONTINUITY RULES
- If the distress has been repeating, acknowledge that it seems to have been building up
- If cooldown is active, do not mention that policy to the user

ADDITIONAL STRICT RULES
- Crisis sequence:
  - First provide emotional grounding
  - Then reassure presence
  - Then focus on safety
  - Then provide helpline resources if needed
- Safety question limits:
  - Do not ask "are you safe?" more than once
  - Do not repeat the same safety question in different wording
- Question control:
  - Reduce the number of questions as much as possible
  - If a question is used, it must directly support immediate safety
- Memory safety:
  - Only reference earlier emotions or context if the user clearly mentioned them in this conversation
  - Do not invent emotional history
- Language variation:
  - Avoid repeating phrases like "that sounds" or "it seems"
  - Keep the tone direct, calm, and supportive
- If the user sends a very short message like hi, ok, or help, stay calm, respond clearly, and do not pad the reply

ABSOLUTE FINAL RULES
- For explicit self-harm intent, include helpline resources in the same reply. Missing helpline is a failure.
- Follow this exact order:
  1. emotional grounding
  2. "I'm here with you"
  3. one safety check only
  4. helpline resources
  5. continued support without repeated questions
- Ask at most one safety question in the whole reply.
- Do not repeat the safety question in later crisis replies.
- Avoid "that sounds" and "it seems".
- Keep the language grounded and direct.

HELPLINE INCLUSION
- include_helpline = {include_helpline}
- If include_helpline is false, do not mention helplines or emergency numbers
- If include_helpline is true, include this helpline block exactly as written after the conversational part:
{helpline_text or 'None'}

Output only the reply text.
"""

    reply = llm_call(system_prompt, user_text, session_id=session_id)
    if reply and not _reply_violates_crisis_rules(reply, recent_bot_replies, require_helpline=include_helpline):
        reply = _clean_reply(reply)
        _remember_reply(session_id, reply)
        return reply

    reply = _fallback_crisis_response(user_text, crisis_guidance, recent_bot_replies)
    _remember_reply(session_id, reply)
    return reply


def generate_reply(
    user_text,
    intent,
    rag_context,
    recent_intents,
    system_override=None,
    is_crisis=False,
    conversation_context=None,
    session_id=None,
    confidence=None,
):
    conversation_context = conversation_context or {}
    recent_intents = recent_intents or []
    recent_bot_replies = _combined_recent_replies(conversation_context, session_id)
    cleaned_text = (user_text or "").lower().strip()

    if _recent_self_harm_context(conversation_context) and cleaned_text in SHORT_ACK_INPUTS.union(UNCERTAIN_INPUTS):
        reply = _build_crisis_continuation_reply(cleaned_text, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    if _should_recover_missing_reply(conversation_context, cleaned_text):
        reply = _build_missing_response_recovery_reply(intent, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    if _is_follow_up_message(cleaned_text):
        reply = _build_follow_up_fallback(cleaned_text, intent, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    short_input_reply = _handle_short_input(cleaned_text, conversation_context, session_id)
    if short_input_reply:
        _remember_reply(session_id, short_input_reply)
        return short_input_reply

    if _is_stuck_input(cleaned_text):
        reply = _build_stuck_reply(intent, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    if _is_confusion_input(cleaned_text):
        reply = _build_confusion_reply(cleaned_text, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    if _is_positive_input(cleaned_text):
        reply = _build_positive_reply(cleaned_text, conversation_context, session_id)
        _remember_reply(session_id, reply)
        return reply

    if system_override:
        system_prompt = system_override
    else:
        system_prompt = _build_support_system_prompt(
            intent,
            user_text,
            rag_context,
            recent_intents,
            conversation_context=conversation_context,
            confidence=confidence,
        )

    reply = llm_call(system_prompt, user_text, session_id=session_id)
    if reply and not _reply_violates_support_rules(
        reply,
        cleaned_text,
        conversation_context=conversation_context,
        session_id=session_id,
        require_action=_is_stuck_input(cleaned_text),
    ):
        reply = _clean_reply(reply)
        _remember_reply(session_id, reply)
        return reply

    reply = generate_human_response(
        intent,
        recent_intents,
        conversation_context,
        user_text=user_text,
        confidence=confidence,
        session_id=session_id,
    )
    _remember_reply(session_id, reply)
    return reply
