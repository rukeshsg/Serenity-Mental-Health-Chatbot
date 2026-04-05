
"""
Flask API Server - Mental Health Support Chatbot (ADVANCEchatbot)
Serves the React UI and provides all backend endpoints.

ADVANCEchatbot: DB-backed sessions, unified safety, PBKDF2 PIN, feedback validation.
"""

import sys
import os
import logging
import re

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, ".env"))

from flask import Flask, request, jsonify, send_from_directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui", "dist")
from flask_cors import CORS
import uuid
import secrets
from datetime import datetime, timedelta

from backend.chatbot_logic import chatbot, get_last_response_metadata
from backend.data.database_manager import DatabaseManager
from backend.llm_analyzer import analyze_situation
from backend.notification_services import notification_service, DeliveryError
from backend.safety_ui_state import (
    compute_ui_state_from_message,
    ui_state_to_crisis_level,
    ui_state_to_intent,
)

# Import quality_monitor for feedback integration
try:
    from backend.advanced_features import quality_monitor
    QUALITY_MONITOR_ENABLED = True
except ImportError:
    quality_monitor = None
    QUALITY_MONITOR_ENABLED = False

app = Flask(__name__)
allowed_origins = [
    origin.strip()
    for origin in os.getenv("SERENITY_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": allowed_origins or "*"}})
logging.basicConfig(level=os.getenv("SERENITY_LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)
app.config["DEBUG"] = os.getenv("SERENITY_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

db = DatabaseManager()
# Keep app sessions effectively persistent so users stay signed in until they
# explicitly log out. We still refresh activity timestamps for bookkeeping.
SESSION_EXPIRY_MINUTES = 60 * 24 * 365 * 10


def is_session_valid(session_id):
    """Check session from DB. Returns (valid: bool, user_id: str|None)."""
    if not session_id:
        return False, None
    sess = db.get_app_session(session_id)
    if not sess:
        return False, None
    return True, sess.get("user_id") or None


def refresh_session(session_id):
    """Extend session expiry."""
    if session_id:
        db.refresh_app_session(session_id, SESSION_EXPIRY_MINUTES)


def get_session_pin_verified(session_id):
    """Check if session has PIN verified."""
    sess = db.get_app_session(session_id)
    return sess.get("pin_verified", False) if sess else False


def _normalize_gender(gender):
    """Normalize optional user gender for profile copy."""
    value = (gender or "").strip().lower().replace(" ", "_")
    if value in {"male", "female", "prefer_not_to_say"}:
        return value
    return ""


def _reverse_relationship_phrase(relationship, gender=""):
    """Map the receiver relationship to the user's relation from their perspective."""
    rel = (relationship or "").strip().lower()
    normalized_gender = _normalize_gender(gender)
    if rel in {"mother", "father", "parent", "guardian"}:
        if normalized_gender == "male":
            return "son"
        if normalized_gender == "female":
            return "daughter"
        return "son/daughter"
    if rel in {"brother", "sister", "sibling"}:
        return "sibling"
    if rel == "friend":
        return "friend"
    if rel == "partner":
        return "partner"
    if rel == "relative":
        return "relative"
    return "loved one"


def _maybe_send_emergency_notification(user_id, ui_state, intent):
    """
    Check if emergency notification should be sent. Only user-related signals (no third_person).
    Max 1 per day. Triggers only when crisis_count or safety_issue_count exceeds threshold.
    """
    if not user_id or str(ui_state).startswith("third_person") or intent == "third_person":
        return
    ec = db.get_emergency_contact(user_id)
    if not ec or not ec.get("enabled") or not ec.get("consent_enabled"):
        return
    if db.was_emergency_notified_today(user_id):
        return
    crisis_count = db.get_user_crisis_count_recent(user_id, hours=NOTIFICATION_WINDOW_HOURS)
    safety_count = db.get_user_safety_count_recent(user_id, hours=NOTIFICATION_WINDOW_HOURS)
    if crisis_count >= CRISIS_COUNT_THRESHOLD or safety_count >= SAFETY_COUNT_THRESHOLD:
        profile = db.get_user_profile(user_id) or {}
        reversed_relation = _reverse_relationship_phrase(ec.get("relationship"), profile.get("gender", ""))
        msg = (
            f"Serenity alert: your {reversed_relation} may need emotional support right now. "
            "Please check in with them today if you can. - Serenity Support"
        )
        try:
            result = notification_service.send_emergency_sms(ec.get("contact_number") or "", msg)
            logger.info(
                "Emergency support SMS delivered for user %s via %s to %s",
                user_id,
                result.provider,
                result.recipient_masked,
            )
            db.log_emergency_notification(user_id)
        except DeliveryError as exc:
            logger.error("Emergency support SMS failed for user %s: %s", user_id, exc)


@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chat endpoint - receives message, returns bot response."""
    data = request.get_json(silent=True) or {}
    message = data.get('message', '')
    session_id = data.get('session_id')
    conversation_id = (data.get('conversation_id') or data.get('chat_session_id') or session_id or "").strip()
    client_user_id = data.get('user_id')
    completed_messages = data.get('completed_messages') or []

    is_valid, user_id = is_session_valid(session_id)
    if not is_valid:
        session_id = session_id or str(uuid.uuid4())
        conversation_id = conversation_id or str(uuid.uuid4())
        user_id = client_user_id if client_user_id else None
        db.save_app_session(session_id, user_id or "", pin_verified=False, expiry_minutes=SESSION_EXPIRY_MINUTES)
        if not user_id:
            user_id = None

    refresh_session(session_id)
    conversation_id = conversation_id or str(uuid.uuid4())

    if user_id:
        db.ensure_conversation(user_id, conversation_id, first_message=message, intent="")

    try:
        try:
            metadata = {}
            result = chatbot(
                message,
                session_id=conversation_id,
                user_id=user_id or "anonymous",
                client_messages=completed_messages,
            )
            if isinstance(result, tuple):
                response, ui_state = result
            else:
                response = result
                ui_state = compute_ui_state_from_message(message)
            metadata = get_last_response_metadata(conversation_id)
        except Exception as e:
            logger.exception("Chatbot error")
            response = "I'm here with you. Please share what's on your mind."
            ui_state = compute_ui_state_from_message(message)
            metadata = {}

        if user_id:
            try:
                crisis_level = ui_state_to_crisis_level(ui_state)
                intent = (metadata.get("intent") or "").strip()
                if not intent or intent == "general":
                    analyzed_situation = analyze_situation(message)
                    if analyzed_situation in {"self_harm", "abuse", "third_person"}:
                        intent = analyzed_situation
                    else:
                        intent = (ui_state_to_intent(ui_state) or "").strip()
                confidence = metadata.get("confidence", 0.0)
                db.save_conversation_turn(
                    user_id,
                    conversation_id,
                    message,
                    str(response),
                    intent=intent,
                    crisis_level=crisis_level,
                    confidence=confidence,
                )
                _maybe_send_emergency_notification(user_id, ui_state, intent)
            except Exception as ex:
                logger.warning("Could not save conversation turn: %s", ex)

        return jsonify({
            'success': True,
            'response': str(response) if response else "I'm here with you.",
            'session_id': session_id,
            'chat_session_id': conversation_id,
            'conversation_id': conversation_id,
            'ui_state': ui_state,
            'status': 'success'
        })

    except Exception as e:
        logger.exception("Chat error")
        return jsonify({
            'success': True,
            'response': "I'm here with you. Even when things are tough, I'm listening.",
            'session_id': session_id or str(uuid.uuid4()),
            'chat_session_id': conversation_id or str(uuid.uuid4()),
            'conversation_id': conversation_id or str(uuid.uuid4()),
            'ui_state': 'normal_chat',
            'status': 'success'
        })


OTP_STORAGE = {}  # email -> {"otp": str, "expires_at": datetime}
OTP_EXPIRY_MINUTES = 5
OTP_REQUEST_TRACKER = {}  # email -> {"last_sent_at": datetime|None, "attempts": [datetime, ...]}
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_REQUESTS_PER_WINDOW = 5
OTP_REQUEST_WINDOW_MINUTES = 15

# Temp storage for emergency contact during onboarding (before user created)
EMERGENCY_CONTACT_TEMP = {}  # email -> {"contact_number": str, "relationship": str}

# Temporary state for secure account email change flow
EMAIL_CHANGE_STATE = {}  # session_id -> {"identity_verified": bool, "new_email": str|None, "expires_at": datetime}
EMAIL_CHANGE_EXPIRY_MINUTES = 15

# Notification thresholds - only user-related signals (no third_person)
CRISIS_COUNT_THRESHOLD = 2
SAFETY_COUNT_THRESHOLD = 1
NOTIFICATION_WINDOW_HOURS = 24


def _normalize_email(email):
    """Normalize and validate email address."""
    if not email or not isinstance(email, str):
        return None
    e = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
        return None
    return e


def _normalize_pin(pin):
    """Normalize PIN - ensure string, strip whitespace."""
    if pin is None:
        return None
    return str(pin).strip()


def _normalize_username(username):
    """Normalize username for display/storage."""
    if username is None:
        return ""
    return " ".join(str(username).strip().split())


def _normalize_contact_number(contact_number):
    """Normalize and validate E.164 emergency contact numbers."""
    raw = (contact_number or "").strip()
    compact = raw.replace(" ", "").replace("-", "")
    if not compact:
        return ""
    if not re.fullmatch(r"\+[1-9]\d{7,14}", compact):
        return None
    return compact


def _prune_otp_rate_limits(now=None):
    """Drop stale OTP rate-limit entries."""
    now = now or datetime.now()
    cutoff = now - timedelta(minutes=OTP_REQUEST_WINDOW_MINUTES)
    stale_emails = []
    for email, entry in OTP_REQUEST_TRACKER.items():
        attempts = [ts for ts in entry.get("attempts", []) if ts >= cutoff]
        last_sent_at = entry.get("last_sent_at")
        if attempts or (last_sent_at and last_sent_at >= cutoff):
            entry["attempts"] = attempts
            OTP_REQUEST_TRACKER[email] = entry
        else:
            stale_emails.append(email)
    for email in stale_emails:
        OTP_REQUEST_TRACKER.pop(email, None)


def _check_otp_rate_limit(email):
    """Return (allowed, message) for OTP requests."""
    now = datetime.now()
    _prune_otp_rate_limits(now)
    entry = OTP_REQUEST_TRACKER.get(email, {"attempts": [], "last_sent_at": None})
    last_sent_at = entry.get("last_sent_at")
    if last_sent_at and (now - last_sent_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
        retry_after = OTP_RESEND_COOLDOWN_SECONDS - int((now - last_sent_at).total_seconds())
        return False, f"Please wait {max(retry_after, 1)} seconds before requesting another OTP."
    if len(entry.get("attempts", [])) >= OTP_MAX_REQUESTS_PER_WINDOW:
        return False, "Too many OTP requests. Please try again in 15 minutes."
    return True, None


def _record_otp_request(email):
    """Track OTP send attempts for rate limiting."""
    now = datetime.now()
    entry = OTP_REQUEST_TRACKER.get(email, {"attempts": [], "last_sent_at": None})
    attempts = [ts for ts in entry.get("attempts", []) if ts >= now - timedelta(minutes=OTP_REQUEST_WINDOW_MINUTES)]
    attempts.append(now)
    OTP_REQUEST_TRACKER[email] = {"attempts": attempts, "last_sent_at": now}


def _issue_otp(email):
    """Generate, deliver, and store OTP for an email. Returns OTP string."""
    otp = f"{secrets.randbelow(900000) + 100000}"
    notification_service.send_otp_email(email, otp, OTP_EXPIRY_MINUTES)
    OTP_STORAGE[email] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    }
    _record_otp_request(email)
    logger.info("OTP issued for %s", email[:2] + "***")
    return otp


def _get_email_change_state(session_id):
    """Get valid email-change state for session, else None."""
    state = EMAIL_CHANGE_STATE.get(session_id)
    if not state or not isinstance(state, dict):
        return None
    exp = state.get("expires_at")
    if exp and datetime.now() > exp:
        EMAIL_CHANGE_STATE.pop(session_id, None)
        return None
    return state


@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    """Step 1: Send OTP to email account."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    
    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    allowed, limit_message = _check_otp_rate_limit(email)
    if not allowed:
        return jsonify({'success': False, 'message': limit_message}), 429
        
    try:
        _issue_otp(email)
    except DeliveryError as exc:
        OTP_STORAGE.pop(email, None)
        return jsonify({'success': False, 'message': str(exc)}), 502
    
    return jsonify({
        'success': True,
        'message': 'OTP sent successfully. Please check your email.'
    })


@app.route('/api/auth/login-pin', methods=['POST'])
def login_with_pin():
    """Existing-user login with email + PIN."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    pin = _normalize_pin(data.get('pin'))

    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not pin or len(pin) < 4 or len(pin) > 6:
        return jsonify({'success': False, 'message': 'Enter your 4-6 digit PIN'}), 400
    if not db.user_exists(email) or not db.user_has_pin(email):
        return jsonify({'success': False, 'message': 'Account not found. Please sign up first.'}), 404
    if not db.verify_pin(email, pin):
        return jsonify({'success': False, 'message': 'Incorrect PIN'}), 401

    session_id = str(uuid.uuid4())
    db.save_app_session(session_id, email, pin_verified=False, expiry_minutes=SESSION_EXPIRY_MINUTES)
    profile = db.get_user_profile(email) or {}

    return jsonify({
        'success': True,
        'session_id': session_id,
        'user_id': email,
        'username': profile.get('username', ''),
        'gender': profile.get('gender', ''),
        'message': 'Login successful. PIN needed for private sections.'
    })


def _get_valid_otp(email):
    """Get OTP if valid and not expired."""
    normalized_email = _normalize_email(email) or email
    entry = OTP_STORAGE.get(normalized_email)
    if not entry or not isinstance(entry, dict):
        return None
    exp = entry.get("expires_at")
    if exp and datetime.now() > exp:
        OTP_STORAGE.pop(normalized_email, None)
        return None
    return entry.get("otp")


@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    """Step 2: Verify OTP. Returns exists=True if returning user, False if new user."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    otp = _normalize_pin(data.get('otp'))
    
    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not otp:
        return jsonify({'success': False, 'message': 'OTP required'}), 400
        
    stored_otp = _get_valid_otp(email)
    if not stored_otp or stored_otp != otp:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401
        
    if db.user_exists(email) and db.user_has_pin(email):
        # Returning user - successful login via OTP
        session_id = str(uuid.uuid4())
        db.save_app_session(session_id, email, pin_verified=False, expiry_minutes=SESSION_EXPIRY_MINUTES)
        OTP_STORAGE.pop(email, None)
        profile = db.get_user_profile(email) or {}
            
        return jsonify({
            'success': True,
            'exists': True,
            'session_id': session_id,
            'user_id': email,
            'username': profile.get('username', ''),
            'gender': profile.get('gender', ''),
            'message': 'Login successful. PIN needed for private sections.'
        })
    else:
        profile = db.get_user_profile(email) or {}
        # New user OR existing user without PIN - must complete onboarding PIN setup
        return jsonify({
            'success': True,
            'exists': False,
            'pin_not_set': True,
            'username': profile.get('username', ''),
            'gender': profile.get('gender', ''),
            'message': 'OTP verified. Please complete onboarding and set your PIN.'
        })


@app.route('/api/auth/store-emergency-contact-temp', methods=['POST'])
def store_emergency_contact_temp():
    """Store emergency contact temporarily during onboarding (after OTP, before PIN). Only called on Agree."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    otp = _normalize_pin(data.get('otp'))
    contact_number = _normalize_contact_number(data.get('contact_number'))
    relationship = (data.get('relationship') or '').strip()

    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not otp:
        return jsonify({'success': False, 'message': 'OTP required'}), 400
    stored_otp = _get_valid_otp(email)
    if not stored_otp or stored_otp != otp:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401
    if not contact_number:
        return jsonify({'success': False, 'message': 'Use E.164 format like +14155550123 for the emergency contact'}), 400

    EMERGENCY_CONTACT_TEMP[email] = {"contact_number": contact_number, "relationship": relationship or "Relative"}
    return jsonify({'success': True})


@app.route('/api/auth/setup-pin', methods=['POST'])
def setup_pin():
    """Setup PIN for new user. Emergency contact (if stored in temp) is saved when user is created."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    otp = _normalize_pin(data.get('otp'))
    session_id = (request.headers.get('Authorization') or '').replace('Bearer ', '').strip()
    pin = _normalize_pin(data.get('pin'))
    pin_confirm = _normalize_pin(data.get('pin_confirm'))
    username = _normalize_username(data.get('username'))
    gender = _normalize_gender(data.get('gender'))

    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not pin or len(pin) < 4 or len(pin) > 6:
        return jsonify({'success': False, 'message': 'PIN must be 4-6 digits'}), 400
    if pin != pin_confirm:
        return jsonify({'success': False, 'message': 'PIN and confirmation do not match'}), 400
    if len(username) > 40:
        return jsonify({'success': False, 'message': 'Username must be 2-40 characters'}), 400
    session_valid, session_user_id = is_session_valid(session_id) if session_id else (False, None)
    can_use_session_for_setup = (
        session_valid
        and session_user_id
        and str(session_user_id).strip().lower() == str(email).strip().lower()
        and db.user_exists(email)
        and not db.user_has_pin(email)
    )

    if not can_use_session_for_setup:
        if not otp:
            return jsonify({'success': False, 'message': 'OTP required'}), 400
        stored_otp = _get_valid_otp(email)
        if not stored_otp or stored_otp != otp:
            return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401

    try:
        if db.user_exists(email):
            if db.user_has_pin(email):
                return jsonify({'success': False, 'message': 'PIN is already set for this account'}), 400
            success = db.update_pin_with_otp(email, pin)
            if success and username:
                db.update_username(email, username)
            if success:
                db.update_gender(email, gender)
        else:
            if len(username) < 2:
                return jsonify({'success': False, 'message': 'Username is required for new accounts'}), 400
            success = db.create_user(email, pin, username=username, gender=gender)

        if success:
            # Save emergency contact if user agreed during onboarding
            temp_ec = EMERGENCY_CONTACT_TEMP.pop(email, None)
            if temp_ec:
                db.save_emergency_contact(email, temp_ec["contact_number"], temp_ec["relationship"], enabled=True, consent_enabled=True)
            if email in EMERGENCY_CONTACT_TEMP:
                del EMERGENCY_CONTACT_TEMP[email]
            new_session_id = str(uuid.uuid4())
            # Do not auto-verify PIN for secure sections; require explicit PIN verification.
            db.save_app_session(new_session_id, email, pin_verified=False, expiry_minutes=SESSION_EXPIRY_MINUTES)
            if otp:
                OTP_STORAGE.pop(email, None)

            return jsonify({
                'success': True,
                'session_id': new_session_id,
                'user_id': email,
                'username': username or (db.get_user_profile(email) or {}).get('username', ''),
                'gender': gender or (db.get_user_profile(email) or {}).get('gender', ''),
                'message': 'PIN setup completed successfully'
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to set PIN'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/auth/verify-pin', methods=['POST'])
def verify_pin():
    """Verify PIN for existing session (for My Stats / Conversation History)."""
    data = request.get_json(silent=True) or {}
    session_id = (request.headers.get('Authorization') or '').replace('Bearer ', '').strip()
    pin = _normalize_pin(data.get('pin'))
    
    if not session_id:
        return jsonify({'success': False, 'message': 'Session required. Please login again.'}), 401
    
    is_valid, user_id = is_session_valid(session_id)
    if not is_valid:
        return jsonify({'success': False, 'message': 'Session expired or invalid. Please login again.'}), 401
    
    if not user_id or not str(user_id).strip():
        return jsonify({'success': False, 'message': 'Please login first to verify your PIN'}), 401
    
    if not db.user_has_pin(user_id):
        return jsonify({
            'success': False,
            'pin_not_set': True,
            'message': 'PIN not set for this account. Please create a PIN first.'
        }), 200

    if not pin or len(pin) < 4:
        return jsonify({'success': False, 'message': 'Please enter your 4-6 digit PIN'}), 400
    
    if db.verify_pin(user_id, pin):
        db.update_app_session_pin_verified(session_id, True)
        refresh_session(session_id)
        return jsonify({
            'success': True,
            'message': 'PIN verified successfully'
        })
    return jsonify({'success': False, 'message': 'Incorrect PIN'}), 403


def _require_auth():
    """Return (session_id, user_id) or (None, None) with error response."""
    session_id = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not session_id:
        return None, None, (jsonify({'success': False, 'message': 'Session required'}), 401)
    is_valid, user_id = is_session_valid(session_id)
    if not is_valid or not user_id:
        return None, None, (jsonify({'success': False, 'message': 'Session expired or invalid'}), 401)
    refresh_session(session_id)
    return session_id, user_id, None


def _require_pin():
    """Require auth + PIN verified."""
    session_id, user_id, err = _require_auth()
    if err:
        return None, None, None, err
    if not get_session_pin_verified(session_id):
        return None, None, None, (jsonify({'success': False, 'message': 'PIN verification required', 'pin_required': True}), 403)
    return session_id, user_id, None, None


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get user settings and emergency contact."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    settings = db.get_user_settings(user_id)
    ec = db.get_emergency_contact(user_id)
    profile = db.get_user_profile(user_id) or {'user_id': user_id, 'username': ''}
    return jsonify({
        'success': True,
        'profile': profile,
        'settings': settings,
        'emergency_contact': ec or {'contact_number': '', 'relationship': '', 'enabled': False, 'consent_enabled': False}
    })


@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Update user settings (crisis_helpline, dark_mode)."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    crisis_helpline = data.get('crisis_helpline_enabled')
    dark_mode = data.get('dark_mode')
    if crisis_helpline is not None:
        db.update_user_settings(user_id, crisis_helpline_enabled=crisis_helpline)
    if dark_mode is not None:
        db.update_user_settings(user_id, dark_mode=dark_mode)
    return jsonify({'success': True})


@app.route('/api/account/username', methods=['PUT'])
def update_account_username():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    username = _normalize_username(data.get('username'))
    success, msg = db.update_username(user_id, username)
    if not success:
        return jsonify({'success': False, 'message': msg or 'Failed to update username'}), 400
    profile = db.get_user_profile(user_id) or {'user_id': user_id, 'username': username}
    return jsonify({'success': True, 'profile': profile, 'message': 'Username updated successfully'})


@app.route('/api/account/profile', methods=['PUT'])
def update_account_profile():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    username = _normalize_username(data.get('username'))
    gender = _normalize_gender(data.get('gender'))
    if username:
        success, msg = db.update_username(user_id, username)
        if not success:
            return jsonify({'success': False, 'message': msg or 'Failed to update profile'}), 400
    success, msg = db.update_gender(user_id, gender)
    if not success:
        return jsonify({'success': False, 'message': msg or 'Failed to update profile'}), 400
    profile = db.get_user_profile(user_id) or {'user_id': user_id, 'username': username, 'gender': gender}
    return jsonify({'success': True, 'profile': profile, 'message': 'Profile updated successfully'})


@app.route('/api/settings/emergency-contact', methods=['GET'])
def get_emergency_contact_api():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    ec = db.get_emergency_contact(user_id)
    return jsonify({'success': True, 'emergency_contact': ec or {'contact_number': '', 'relationship': '', 'enabled': False, 'consent_enabled': False}})


@app.route('/api/settings/emergency-contact', methods=['PUT'])
def update_emergency_contact_api():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    ec = db.get_emergency_contact(user_id) or {}
    raw_contact_number = data.get('contact_number') if data.get('contact_number') is not None else ec.get('contact_number', '')
    contact_number = _normalize_contact_number(raw_contact_number)
    relationship = (data.get('relationship') if data.get('relationship') is not None else ec.get('relationship', '')) or 'Relative'
    enabled = data.get('enabled') if data.get('enabled') is not None else ec.get('enabled', False)
    consent_enabled = data.get('consent_enabled') if data.get('consent_enabled') is not None else ec.get('consent_enabled', False)
    if raw_contact_number and not contact_number:
        return jsonify({'success': False, 'message': 'Use E.164 format like +14155550123 for the emergency contact'}), 400
    if enabled and not contact_number:
        return jsonify({'success': False, 'message': 'A valid emergency contact is required when alerts are enabled'}), 400
    db.save_emergency_contact(user_id, contact_number.strip(), relationship.strip() or 'Relative', enabled=enabled, consent_enabled=consent_enabled)
    return jsonify({'success': True})


@app.route('/api/auth/change-pin', methods=['POST'])
def change_pin():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    old_pin = _normalize_pin(data.get('current_pin'))
    new_pin = _normalize_pin(data.get('new_pin'))
    if not old_pin or not new_pin:
        return jsonify({'success': False, 'message': 'Current PIN and new PIN required'}), 400
    success, msg = db.change_pin(user_id, old_pin, new_pin)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': msg or 'Failed to change PIN'}), 400


@app.route('/api/auth/reset-pin', methods=['POST'])
def reset_pin():
    """Reset PIN via email OTP (step 1: send OTP, step 2: verify OTP and set new PIN)."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email', ''))
    otp = _normalize_pin(data.get('otp'))
    new_pin = _normalize_pin(data.get('new_pin'))
    new_pin_confirm = _normalize_pin(data.get('new_pin_confirm'))
    if not email:
        return jsonify({'success': False, 'message': 'Valid email required'}), 400
    if not db.user_exists(email):
        return jsonify({'success': False, 'message': 'No account found for this email'}), 404
    if not otp or not new_pin:
        return jsonify({'success': False, 'message': 'OTP and new PIN required'}), 400
    stored_otp = _get_valid_otp(email)
    if not stored_otp or stored_otp != otp:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401
    if new_pin != new_pin_confirm:
        return jsonify({'success': False, 'message': 'PIN and confirmation do not match'}), 400
    if len(new_pin) < 4 or len(new_pin) > 6:
        return jsonify({'success': False, 'message': 'PIN must be 4-6 digits'}), 400
    if db.update_pin_with_otp(email, new_pin):
        OTP_STORAGE.pop(email, None)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Failed to reset PIN'}), 400


@app.route('/api/account/change-email/request-old-otp', methods=['POST'])
def request_old_email_otp():
    """Send OTP to current registered email for identity verification."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    if not user_id:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    try:
        _issue_otp(user_id)
    except DeliveryError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 502
    EMAIL_CHANGE_STATE[session_id] = {
        "identity_verified": False,
        "new_email": None,
        "expires_at": datetime.now() + timedelta(minutes=EMAIL_CHANGE_EXPIRY_MINUTES)
    }
    return jsonify({'success': True, 'message': 'OTP sent to your current email'})


@app.route('/api/account/change-email/verify-identity', methods=['POST'])
def verify_change_email_identity():
    """Verify identity using account PIN or OTP sent to current email."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]

    data = request.get_json(silent=True) or {}
    method = (data.get('method') or '').strip().lower()

    if method == 'pin':
        pin = _normalize_pin(data.get('pin'))
        # If the session is already PIN-verified, allow flow without forcing another PIN entry.
        # Otherwise require PIN and verify against the account.
        if not get_session_pin_verified(session_id):
            if not pin:
                return jsonify({'success': False, 'message': 'PIN required'}), 400
            if not db.verify_pin(user_id, pin):
                return jsonify({'success': False, 'message': 'Incorrect PIN'}), 403
    elif method == 'otp_old':
        otp = _normalize_pin(data.get('otp'))
        if not otp:
            return jsonify({'success': False, 'message': 'OTP required'}), 400
        stored_otp = _get_valid_otp(user_id)
        if not stored_otp or stored_otp != otp:
            return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401
    else:
        return jsonify({'success': False, 'message': 'Invalid verification method'}), 400

    EMAIL_CHANGE_STATE[session_id] = {
        "identity_verified": True,
        "new_email": None,
        "expires_at": datetime.now() + timedelta(minutes=EMAIL_CHANGE_EXPIRY_MINUTES)
    }
    return jsonify({'success': True, 'identity_verified': True})


@app.route('/api/account/change-email/request-new-otp', methods=['POST'])
def request_new_email_otp():
    """Send OTP to new email after identity verification."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]

    state = _get_email_change_state(session_id)
    if not state or not state.get("identity_verified"):
        return jsonify({'success': False, 'message': 'Please verify your identity first'}), 403

    data = request.get_json(silent=True) or {}
    new_email = _normalize_email(data.get('new_email', ''))
    if not new_email:
        return jsonify({'success': False, 'message': 'Valid new email required'}), 400
    if new_email == user_id:
        return jsonify({'success': False, 'message': 'New email must be different'}), 400
    if db.user_exists(new_email):
        return jsonify({'success': False, 'message': 'Email already in use'}), 409

    try:
        _issue_otp(new_email)
    except DeliveryError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 502
    EMAIL_CHANGE_STATE[session_id] = {
        "identity_verified": True,
        "new_email": new_email,
        "expires_at": datetime.now() + timedelta(minutes=EMAIL_CHANGE_EXPIRY_MINUTES)
    }
    return jsonify({'success': True, 'message': 'OTP sent to new email'})


@app.route('/api/account/change-email/confirm', methods=['POST'])
def confirm_change_email():
    """Confirm OTP sent to new email and update account email."""
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]

    state = _get_email_change_state(session_id)
    if not state or not state.get("identity_verified"):
        return jsonify({'success': False, 'message': 'Please verify your identity first'}), 403

    data = request.get_json(silent=True) or {}
    new_email = _normalize_email(data.get('new_email', ''))
    otp = _normalize_pin(data.get('otp'))
    pending_email = state.get("new_email")

    if not new_email or not otp:
        return jsonify({'success': False, 'message': 'New email and OTP required'}), 400
    if not pending_email or pending_email != new_email:
        return jsonify({'success': False, 'message': 'Please request OTP for this new email first'}), 400

    stored_otp = _get_valid_otp(new_email)
    if not stored_otp or stored_otp != otp:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 401

    success, msg = db.update_user_id(user_id, new_email)
    if not success:
        return jsonify({'success': False, 'message': msg or 'Failed to update email'}), 400

    # Keep session active but force re-verify PIN for private sections.
    db.save_app_session(session_id, new_email, pin_verified=False, expiry_minutes=SESSION_EXPIRY_MINUTES)
    OTP_STORAGE.pop(user_id, None)
    OTP_STORAGE.pop(new_email, None)
    EMAIL_CHANGE_STATE.pop(session_id, None)
    return jsonify({'success': True, 'user_id': new_email, 'message': 'Email updated successfully'})


@app.route('/api/auth/logout-all', methods=['POST'])
def logout_all():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    db.end_all_user_sessions(user_id)
    return jsonify({'success': True})


@app.route('/api/privacy/clear-history', methods=['POST'])
def clear_history():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    try:
        deleted = db.clear_user_conversation_history(user_id)
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/account', methods=['DELETE'])
def delete_account():
    session_id, user_id, err = _require_auth()
    if err:
        return err[0], err[1]
    data = request.get_json(silent=True) or {}
    pin = _normalize_pin(data.get('pin'))
    if not pin or not db.verify_pin(user_id, pin):
        return jsonify({'success': False, 'message': 'Incorrect PIN'}), 403
    try:
        db.delete_user_data(user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    """Create a new independent conversation for the logged-in user."""
    session_id, user_id, err = _require_auth()
    if err:
        return err
    conversation_id = str(uuid.uuid4())
    db.create_conversation(user_id, conversation_id=conversation_id, title="New conversation")
    return jsonify({
        'success': True,
        'conversation_id': conversation_id,
        'title': 'New conversation',
        'created_at': datetime.now().isoformat(),
    })


@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """
    Get user conversation history (PIN REQUIRED).
    
    SECURITY: This endpoint enforces PIN verification at backend level.
    - Session must exist and not be expired
    - User must be logged in
    - PIN must have been verified for this session
    """
    session_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    # Step 1: Validate session exists and not expired
    is_valid, user_id = is_session_valid(session_id)
    if not is_valid:
        return jsonify({'success': False, 'conversations': [], 'message': 'Session expired'}), 401
    
    # Step 2: Check user is logged in
    if not user_id:
        return jsonify({'success': False, 'conversations': [], 'message': 'Not logged in'}), 401
    
    if not get_session_pin_verified(session_id):
        return jsonify({
            'success': False,
            'conversations': [],
            'message': 'PIN verification required. Please verify your PIN to access conversation history.',
            'pin_required': True
        }), 403

    raw_convos = db.get_user_conversations(user_id)
    convos = [
        {
            'conversation_id': c.get('conversation_id'),
            'session_id': c.get('conversation_id'),
            'title': c.get('title', ''),
            'summary': c.get('preview', ''),
            'intent': c.get('intent', ''),
            'date': c.get('updated_at') or c.get('created_at', ''),
            'created_at': c.get('created_at', ''),
            'last_message_at': c.get('last_message_at', ''),
        }
        for c in raw_convos
    ]
    
    return jsonify({
        'success': True,
        'conversations': convos
    })


@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation_by_session(conversation_id):
    """Get full conversation messages for a specific conversation (PIN REQUIRED)."""
    auth_session_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    is_valid, user_id = is_session_valid(auth_session_id)
    if not is_valid or not user_id:
        return jsonify({'success': False, 'messages': [], 'message': 'Session expired or not logged in'}), 401
    if not get_session_pin_verified(auth_session_id):
        return jsonify({'success': False, 'messages': [], 'message': 'PIN verification required', 'pin_required': True}), 403
    raw_messages = db.get_conversation_messages_for_user(conversation_id, user_id, limit=200)
    if raw_messages:
        messages = [
            {
                'role': 'user' if r.get('sender') == 'user' else 'bot',
                'text': r.get('message', ''),
                'intent': r.get('intent', ''),
                'timestamp': r.get('timestamp', ''),
            }
            for r in raw_messages
        ]
        return jsonify({'success': True, 'conversation_id': conversation_id, 'session_id': conversation_id, 'messages': messages})

    raw = db.get_conversation_history_for_user(conversation_id, user_id, limit=100)
    messages = [
        {'summary': r.get('summary', ''), 'intent': r.get('intent', ''), 'timestamp': r.get('timestamp', '')}
        for r in raw
    ]
    return jsonify({'success': True, 'conversation_id': conversation_id, 'session_id': conversation_id, 'messages': messages})


@app.route('/api/analytics/global', methods=['GET'])
def global_analytics():
    """Get global analytics (no authentication required)"""
    try:
        stats = db.get_global_analytics()
        trends = db.get_global_trends(days=7)
        return jsonify({
            'success': True,
            **stats,
            'trend_data': trends.get('trend_data', [])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analytics/global/trends', methods=['GET'])
def global_trends():
    """Get global trend data for graphs (messages/day, crisis/day)"""
    try:
        trends = db.get_global_trends(days=7)
        return jsonify({'success': True, **trends})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analytics/user', methods=['GET'])
def user_analytics():
    """
    Get user-specific analytics (PIN REQUIRED).
    
    SECURITY: This endpoint enforces PIN verification at backend level.
    - Session must exist and not be expired
    - User must be logged in
    - PIN must have been verified for this session
    """
    session_id = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    # Step 1: Validate session exists and not expired
    is_valid, user_id = is_session_valid(session_id)
    if not is_valid:
        return jsonify({'success': False, 'message': 'Session expired. Please login again.'}), 401
    
    # Step 2: Check user is logged in
    if not user_id:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    if not get_session_pin_verified(session_id):
        return jsonify({
            'success': False,
            'message': 'PIN verification required. Please verify your PIN to access personal analytics.'
        }), 403

    try:
        stats = db.get_user_analytics(user_id)
        trends = db.get_user_trends(user_id, days=7)
        return jsonify({
            'success': True,
            **stats,
            'trend_data': trends.get('trend_data', [])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback on a message. Validates message belongs to user if session provided."""
    data = request.get_json(silent=True) or {}
    message_id = data.get('message_id')
    rating = data.get('rating')
    session_id = request.headers.get('Authorization', '').replace('Bearer ', '')

    user_id = None
    if session_id:
        is_valid, uid = is_session_valid(session_id)
        if is_valid and uid:
            user_id = uid

    success, err = db.save_feedback(message_id, rating, user_id)
    if success:
        if QUALITY_MONITOR_ENABLED and message_id and rating is not None:
            try:
                intent = data.get('intent', 'general')
                quality_monitor.record_feedback(intent, 1 if rating > 0 else -1)
            except Exception:
                pass
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err or 'Failed to save feedback'}), 400


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/', methods=['GET'])
def serve_ui():
    return send_from_directory(UI_DIR, "index.html")

@app.route('/<path:path>')
def serve_static_files(path):
    return send_from_directory(UI_DIR, path)
import os

if __name__ == '__main__':
    logger.info("Starting Serenity backend...")
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config["DEBUG"])
