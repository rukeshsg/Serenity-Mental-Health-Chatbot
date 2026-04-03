from collections import deque
from datetime import datetime, timedelta
from threading import RLock


SELF_HARM_HELPLINES = (
    "AASRA (24/7): +91 9820466726\n"
    "iCall (24/7): +91 9152987821\n"
    "Emergency (India): 108\n"
    "International support: https://www.befrienders.org"
)

SELF_HARASSMENT_HELPLINES = (
    "Women Helpline: 181\n"
    "Police Emergency: 112\n"
    "National Commission for Women: 14490\n"
    "iCall: +91 9152987821"
)

CRISIS_CARD_COOLDOWN_HOURS = 48
MESSAGE_WINDOW_SIZE = 5


def _normalized_text(text: str) -> str:
    return (text or "").strip().lower()


def _contains_any(text: str, phrases) -> bool:
    return any(phrase in text for phrase in phrases)


def _safe_iso_to_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def check_crisis_level(text: str) -> int:
    text = _normalized_text(text)

    strong_triggers = [
        "kill myself",
        "end my life",
        "i want to die",
        "i don't want to live",
        "self harm",
        "hurt myself",
        "hurting myself",
        "cutting myself",
        "shoot myself",
        "hang myself",
        "no reason to live",
        "ready to die",
        "gonna kill myself",
        "suicide",
        "end it all now",
        "planning to kill myself",
        "about to hurt myself",
        "want to hurt myself",
        "thinking of hurting",
        "thoughts of hurting",
    ]

    soft_triggers = [
        "ending it all",
        "ending everything",
        "end everything",
        "feel like ending everything",
        "better off dead",
        "no point living",
        "life not worth living",
        "tired of living",
        "giving up",
        "nothing matters anymore",
        "dont want to exist",
        "wish i was never born",
        "lost all hope",
    ]

    if _contains_any(text, strong_triggers):
        return 2

    if _contains_any(text, soft_triggers):
        return 1

    return 0


def detect_user_help_request(text: str) -> bool:
    lowered = _normalized_text(text)
    help_requests = [
        "help me",
        "please help",
        "give helpline",
        "give me helpline",
        "helpline",
        "hotline",
        "emergency number",
        "support number",
        "who can i call",
        "where can i get help",
    ]
    return _contains_any(lowered, help_requests)


class SessionCrisisStateStore:
    def __init__(self):
        self._states = {}
        self._resource_cooldowns = {}
        self._lock = RLock()

    def _default_state(self):
        return {
            "crisis_count": 0,
            "crisis_shown": False,
            "third_person_card_shown": False,
            "user_requested_help": False,
            "recent_intents": deque(maxlen=MESSAGE_WINDOW_SIZE),
            "recent_bot_responses": deque(maxlen=4),
            "recent_user_messages": deque(maxlen=MESSAGE_WINDOW_SIZE),
            "last_crisis_timestamp": None,
        }

    def _subject_key(self, session_id: str, user_id: str = None):
        return f"session:{session_id or 'default_session'}"

    def get_state(self, session_id: str):
        sid = session_id or "default_session"
        with self._lock:
            if sid not in self._states:
                self._states[sid] = self._default_state()
            return self._states[sid]

    def reset_session(self, session_id: str):
        sid = session_id or "default_session"
        with self._lock:
            self._states.pop(sid, None)

    def mark_intent(self, session_id: str, intent: str):
        if not intent:
            return
        state = self.get_state(session_id)
        with self._lock:
            state["recent_intents"].append(intent)

    def note_user_message(self, session_id: str, message: str):
        if not message:
            return
        state = self.get_state(session_id)
        with self._lock:
            state["recent_user_messages"].append(str(message).strip())

    def note_response(self, session_id: str, response: str):
        if not response:
            return
        state = self.get_state(session_id)
        with self._lock:
            state["recent_bot_responses"].append(response.strip())

    def get_recent_intents(self, session_id: str, limit: int = MESSAGE_WINDOW_SIZE):
        state = self.get_state(session_id)
        return list(state["recent_intents"])[-limit:]

    def get_recent_responses(self, session_id: str, limit: int = 4):
        state = self.get_state(session_id)
        return list(state["recent_bot_responses"])[-limit:]

    def get_recent_user_messages(self, session_id: str, limit: int = MESSAGE_WINDOW_SIZE):
        state = self.get_state(session_id)
        return list(state["recent_user_messages"])[-limit:]

    def resource_cooldown_active(self, session_id: str, user_id: str = None):
        subject_key = self._subject_key(session_id, user_id)
        with self._lock:
            entry = self._resource_cooldowns.get(subject_key) or {}
        shown_at = _safe_iso_to_datetime(entry.get("shown_at"))
        if not shown_at:
            return False
        return datetime.utcnow() - shown_at < timedelta(hours=CRISIS_CARD_COOLDOWN_HOURS)

    def mark_resource_shown(self, session_id: str, user_id: str = None, crisis_kind: str = "self_harm"):
        subject_key = self._subject_key(session_id, user_id)
        now_iso = datetime.utcnow().isoformat()
        with self._lock:
            self._resource_cooldowns[subject_key] = {
                "shown_at": now_iso,
                "crisis_kind": crisis_kind,
            }

    def third_person_card_shown(self, session_id: str) -> bool:
        state = self.get_state(session_id)
        return bool(state.get("third_person_card_shown"))

    def mark_third_person_card_shown(self, session_id: str):
        state = self.get_state(session_id)
        with self._lock:
            state["third_person_card_shown"] = True


session_crisis_store = SessionCrisisStateStore()


def _emotional_memory_phrase(recent_intents) -> str:
    recent = [intent for intent in recent_intents if intent not in {"normal", "greeting"}]
    if not recent:
        return ""

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
    return memory_map.get(recent[-1], "")


def _self_harm_context_is_actionable(text: str) -> bool:
    lowered = _normalized_text(text)
    if not lowered:
        return False

    if check_crisis_level(lowered) > 0:
        return True

    direct_risk_phrases = [
        "want to die",
        "suicidal",
        "suicide",
        "end it all",
        "ending everything",
        "end everything",
        "feel like ending everything",
        "end my life",
        "don't want to live",
        "dont want to live",
        "can't live anymore",
        "cannot live anymore",
    ]
    return _contains_any(lowered, direct_risk_phrases)


def _self_harassment_score(text: str) -> int:
    lowered = _normalized_text(text)
    strong_markers = [
        "he is hitting me",
        "she is hitting me",
        "they are hitting me",
        "someone is hitting me",
        "i am not safe",
        "i'm not safe",
        "i was assaulted",
        "i was raped",
        "he threatened me",
        "she threatened me",
        "they threatened me",
    ]
    medium_markers = [
        "abuse",
        "abused",
        "abusing",
        "harassment",
        "harassed",
        "bullied",
        "unsafe",
        "hurt me",
        "hit me",
        "beating me",
        "assaulted",
    ]

    if _contains_any(lowered, strong_markers):
        return 2
    if _contains_any(lowered, medium_markers):
        return 1
    return 0


def _score_message(text: str, crisis_kind: str) -> int:
    if crisis_kind == "self_harassment":
        return _self_harassment_score(text)
    return check_crisis_level(text) if _self_harm_context_is_actionable(text) else 0


def _compute_severity(recent_messages, crisis_kind: str):
    window = [msg for msg in (recent_messages or []) if _normalized_text(msg)]
    if not window:
        return "low", {"scores": [], "total_score": 0, "positive_count": 0, "strong_count": 0}

    scores = [_score_message(message, crisis_kind) for message in window[-MESSAGE_WINDOW_SIZE:]]
    total_score = sum(scores)
    positive_count = sum(1 for score in scores if score > 0)
    strong_count = sum(1 for score in scores if score >= 2)

    if strong_count >= 2 or total_score >= 3:
        severity = "high"
    elif positive_count >= 1:
        severity = "medium"
    else:
        severity = "low"

    return severity, {
        "scores": scores,
        "total_score": total_score,
        "positive_count": positive_count,
        "strong_count": strong_count,
    }


def _build_guidance(
    stage: str,
    crisis_kind: str,
    recent_intents,
    severity: str,
    include_helpline: bool = False,
    user_requested_help: bool = False,
    cooldown_active: bool = False,
):
    return {
        "stage": stage,
        "crisis_kind": crisis_kind,
        "severity": severity,
        "memory": _emotional_memory_phrase(recent_intents),
        "include_helpline": include_helpline,
        "user_requested_help": user_requested_help,
        "cooldown_active": cooldown_active,
        "helpline_text": (
            SELF_HARASSMENT_HELPLINES if crisis_kind == "self_harassment" else SELF_HARM_HELPLINES
        ) if include_helpline else "",
    }


def strong_crisis_response():
    return {
        "tone": "urgent_but_calm",
        "must_include": [
            "clear empathy",
            "validation",
            "immediate safety check question",
            "encouragement to contact real-world support right now",
        ],
        "include_helpline": True,
        "severity": "high",
        "helpline_text": SELF_HARM_HELPLINES,
    }


def soft_crisis_response():
    return {
        "tone": "calm_supportive",
        "must_include": [
            "empathy",
            "validation",
            "safety check question",
            "gentle invitation to share more",
        ],
        "include_helpline": False,
        "severity": "medium",
    }


def handle_crisis_logic(user_text: str, session_id: str, crisis_kind: str = "self_harm", user_id: str = None):
    state = session_crisis_store.get_state(session_id)
    help_requested = detect_user_help_request(user_text)
    recent_intents = session_crisis_store.get_recent_intents(session_id)
    prior_intents = recent_intents[:-1] if recent_intents else []
    recent_messages = session_crisis_store.get_recent_user_messages(session_id)
    severity, _ = _compute_severity(recent_messages, crisis_kind)
    cooldown_active = session_crisis_store.resource_cooldown_active(session_id, user_id)
    crisis_card_already_shown = bool(state.get("crisis_shown")) or cooldown_active

    if help_requested:
        state["user_requested_help"] = True
        state["last_crisis_timestamp"] = datetime.utcnow().isoformat()
        if not crisis_card_already_shown:
            state["crisis_shown"] = True
            session_crisis_store.mark_resource_shown(session_id, user_id, crisis_kind)
            ui_state = "abuse_card" if crisis_kind == "self_harassment" else "crisis_1_card"
            stage = "user_requested_help"
        else:
            ui_state = "normal_chat"
            stage = "user_requested_help_followup"
        return (
            _build_guidance(
                stage=stage,
                crisis_kind=crisis_kind,
                recent_intents=prior_intents,
                severity="high",
                include_helpline=True,
                user_requested_help=True,
                cooldown_active=cooldown_active,
            ),
            ui_state,
        )

    # Explicit first-person self-harm intent must trigger the crisis card immediately.
    if crisis_kind == "self_harm" and _self_harm_context_is_actionable(user_text):
        state["crisis_count"] += 1
        state["last_crisis_timestamp"] = datetime.utcnow().isoformat()
        if crisis_card_already_shown:
            state["crisis_shown"] = True
            return (
                _build_guidance(
                    stage="post_crisis_support",
                    crisis_kind=crisis_kind,
                    recent_intents=prior_intents,
                    severity="high",
                    include_helpline=False,
                    cooldown_active=cooldown_active,
                ),
                "normal_chat",
            )

        state["crisis_shown"] = True
        session_crisis_store.mark_resource_shown(session_id, user_id, crisis_kind)
        return (
            _build_guidance(
                stage="immediate_self_harm",
                crisis_kind=crisis_kind,
                recent_intents=prior_intents,
                severity="high",
                include_helpline=True,
            ),
            "crisis_1_card",
        )

    if severity == "low":
        return (
            _build_guidance(
                stage="supportive_non_crisis",
                crisis_kind=crisis_kind,
                recent_intents=prior_intents,
                severity="low",
                include_helpline=False,
            ),
            "normal_chat",
        )

    state["crisis_count"] += 1
    state["last_crisis_timestamp"] = datetime.utcnow().isoformat()

    if state["crisis_shown"] or cooldown_active:
        state["crisis_shown"] = True
        return (
            _build_guidance(
                stage="post_crisis_support",
                crisis_kind=crisis_kind,
                recent_intents=prior_intents,
                severity=severity,
                include_helpline=False,
                cooldown_active=cooldown_active,
            ),
            "normal_chat",
        )

    if severity == "medium":
        return (
            _build_guidance(
                stage="first_detection",
                crisis_kind=crisis_kind,
                recent_intents=prior_intents,
                severity="medium",
                include_helpline=False,
            ),
            "normal_chat",
        )

    state["crisis_shown"] = True
    session_crisis_store.mark_resource_shown(session_id, user_id, crisis_kind)
    ui_state = "abuse_card" if crisis_kind == "self_harassment" else "crisis_1_card"
    return (
        _build_guidance(
            stage="repeat_detection_show_resources",
            crisis_kind=crisis_kind,
            recent_intents=prior_intents,
            severity="high",
            include_helpline=True,
        ),
        ui_state,
    )
