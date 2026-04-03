"""
Unified Safety & UI State Module - Single Source of Truth
=========================================================
Centralizes crisis, abuse, third-person detection and UI state mapping.
Used by both chatbot_logic (for pipeline) and app (for fallback/consistency).
"""
import re


def compute_ui_state_from_message(message: str) -> str:
    """
    Determine UI state from raw message content.
    CRITICAL: Third person MUST be checked BEFORE crisis keywords
    because phrases like "my friend wants to die" contain "want to die".

    Returns one of:
    - normal_chat
    - crisis_2_modal / crisis_1_card (user crisis)
    - abuse_card (user safety)
    - third_person_crisis_card / third_person_safety_card
    """
    if not message or not isinstance(message, str):
        return "normal_chat"

    message_lower = message.lower().strip()

    first_person_re = re.compile(r"\b(i|i'm|im|i've|ive|me|myself)\b")
    has_first_person = bool(first_person_re.search(message_lower))
    third_person_subject_re = re.compile(
        r"\b(my friend|my friends|my sister|my brother|my mother|my father|my mom|my dad|"
        r"my family|he|she|they|someone|person)\b"
    )
    has_third_person_subject = bool(third_person_subject_re.search(message_lower))

    # FIRST: Check for user-directed severe crisis
    crisis_strong_direct = [
        "kill myself", "end my life", "hurt myself", "hurting myself",
        "harm myself", "want to hurt myself", "thinking of hurting", "thoughts of hurting",
        "about to hurt myself",
    ]
    for keyword in crisis_strong_direct:
        if keyword in message_lower:
            return "crisis_2_modal"

    crisis_strong_contextual = [
        "want to die", " suicide", "kill me", "end it all",
        "can't live anymore", "cannot live anymore", "dont want to live", "don't want to live",
    ]
    for keyword in crisis_strong_contextual:
        if keyword in message_lower and (has_first_person or not has_third_person_subject):
            return "crisis_2_modal"

    # SECOND: Check for user-directed abuse/violence
    abuse_keywords = [
        "abuse", "abusing", "abused", "harassment", "harassed",
        "assault", "assaulted", "unsafe", "hit me", "hitting me", "hurt me",
        "beat me", "beating me", "beaten", "beated", "bullied", "domestic violence",
    ]
    user_abuse_patterns = [
        "hit me", "hurt me", "beat me", "beating me", "beaten", "beated", "bullied",
        "was abused", "was assaulted", "i am abused", "i was hit", "i was beaten",
        "i am being abused", "i'm being abused", "im being abused",
        "someone is abusing me", "someone abused me", "someone is hurting me",
        "someone hurt me", "i am being harassed", "i'm being harassed",
        "someone is harassing me", "i feel unsafe", "i am unsafe", "i'm unsafe",
    ]
    for keyword in user_abuse_patterns:
        if keyword in message_lower:
            return "abuse_card"

    # THIRD: Third-person crisis vs third-person safety card split
    third_person_crisis_markers = [
        "wants to die", "want to die", "suicidal", "kill himself", "kill herself",
        "kill themselves", "hurt himself", "hurt herself", "hurt themselves",
        "harm himself", "harm herself", "harm themselves",
        "end his life", "end her life", "end their life", "self harm",
        "can't live anymore", "cannot live anymore", "doesn't want to live", "doesnt want to live",
    ]
    third_person_safety_markers = [
        "being abused", "is abused", "abused", "harassed", "harassment", "assaulted",
        "beaten", "beated", "bullied", "unsafe", "hit by", "hurt by",
    ]

    if has_third_person_subject:
        for keyword in third_person_crisis_markers:
            if keyword in message_lower:
                return "third_person_crisis_card"
        for keyword in third_person_safety_markers:
            if keyword in message_lower:
                return "third_person_safety_card"

    # FOURTH: Generic abuse fallback
    for keyword in abuse_keywords:
        if keyword in message_lower:
            return "abuse_card"

    # FIFTH: Check for crisis keywords - SOFT (user context)
    crisis_soft = [
        "tired of living", "better off dead", "nothing matters",
        "giving up", "no reason to live", "life not worth living",
        "ending everything", "end everything", "feel like ending everything",
    ]
    for keyword in crisis_soft:
        if keyword in message_lower and (has_first_person or not has_third_person_subject):
            return "crisis_1_card"

    return "normal_chat"


def ui_state_to_crisis_level(ui_state: str) -> int:
    """Map UI state to crisis_level for database storage."""
    if ui_state == "crisis_2_modal":
        return 2
    if ui_state in ("crisis_1_card", "abuse_card"):
        return 1
    return 0


def ui_state_to_intent(ui_state: str) -> str:
    """Map UI state to intent for database storage."""
    mapping = {
        "crisis_2_modal": "crisis",
        "crisis_1_card": "crisis",
        "abuse_card": "abuse",
        "third_person_card": "third_person",  # backward compatibility
        "third_person_crisis_card": "third_person",
        "third_person_safety_card": "third_person",
    }
    return mapping.get(ui_state, "general")
