"""
Database Manager for SQLite storage.
====================================
ADVANCEchatbot: PBKDF2 PIN hashing, session persistence, feedback validation.
- Summary-based history (NOT raw messages)
- PIN verification with PBKDF2 (salt + 100k iterations)
- App sessions persisted in SQLite
"""

import sqlite3
import os
import hashlib
import secrets
import json
import re
import uuid
from datetime import datetime, timedelta

# PBKDF2 constants for PIN hashing
PIN_SALT_BYTES = 16
PIN_ITERATIONS = 100_000
PIN_HASH_NAME = "sha256"

def _default_db_path():
    """Store DB in project root for consistent location."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "mental_health.db")


class DatabaseManager:
    def __init__(self, db_path=None):
        self.db_path = db_path or _default_db_path()
        self.init_db()

    def init_db(self):
        """Initialize database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table with PBKDF2 PIN hash (salt:hex:hash)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                username TEXT,
                gender TEXT,
                pin_hash TEXT,
                pin_salt TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        if 'username' not in user_columns:
            cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
        if 'gender' not in user_columns:
            cursor.execute('ALTER TABLE users ADD COLUMN gender TEXT')
        if 'pin_salt' not in user_columns:
            cursor.execute('ALTER TABLE users ADD COLUMN pin_salt TEXT')
        
        # Messages table (SUMMARY-BASED only - per UI_EXECUTION_PLAN_HYBRID)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                conversation_id TEXT,
                summary TEXT,
                intent TEXT,
                crisis_level INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                first_intent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                intent TEXT,
                confidence REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS intent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                session_id TEXT,
                intent TEXT NOT NULL,
                confidence REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sessions table (DB-backed, supports guests)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                pin_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        try:
            cursor.execute('SELECT pin_verified FROM sessions LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute('ALTER TABLE sessions ADD COLUMN pin_verified INTEGER DEFAULT 0')
        try:
            cursor.execute('SELECT user_id FROM sessions LIMIT 1')
        except sqlite3.OperationalError:
            pass
        
        # Feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages (id)
            )
        ''')
        
        # Global analytics (aggregated only)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analytics_global (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_messages INTEGER DEFAULT 0,
                total_sessions INTEGER DEFAULT 0,
                crisis_count INTEGER DEFAULT 0,
                intent_counts TEXT
            )
        ''')
        
        # Migration: Add crisis_level column if it doesn't exist
        try:
            cursor.execute('SELECT crisis_level FROM messages LIMIT 1')
        except:
            cursor.execute('ALTER TABLE messages ADD COLUMN crisis_level INTEGER DEFAULT 0')
        try:
            cursor.execute('SELECT confidence FROM messages LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute('ALTER TABLE messages ADD COLUMN confidence REAL DEFAULT 0')
        try:
            cursor.execute('SELECT conversation_id FROM messages LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute('ALTER TABLE messages ADD COLUMN conversation_id TEXT')
        cursor.execute("UPDATE messages SET conversation_id = session_id WHERE conversation_id IS NULL OR trim(conversation_id) = ''")

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_session ON messages(user_id, session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_conversation ON messages(user_id, conversation_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_time ON conversation_messages(conversation_id, timestamp ASC)')

        # Emergency support contact (optional safety feature)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emergency_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                contact_number TEXT,
                relationship TEXT,
                enabled INTEGER DEFAULT 0,
                consent_enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # User settings (crisis helpline, appearance)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                crisis_helpline_enabled INTEGER DEFAULT 1,
                dark_mode INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Emergency notification log (max 1 per day per user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emergency_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()

    # ============ USER MANAGEMENT ============
    
    def _hash_pin_pbkdf2(self, pin: str, salt: bytes = None) -> tuple:
        """Hash PIN with PBKDF2. Returns (salt_hex, hash_hex)."""
        if salt is None:
            salt = secrets.token_bytes(PIN_SALT_BYTES)
        key = hashlib.pbkdf2_hmac(
            PIN_HASH_NAME, pin.encode("utf-8"), salt, PIN_ITERATIONS
        )
        return (salt.hex(), key.hex())

    def _verify_pin_pbkdf2(self, pin: str, salt_hex: str, stored_hash: str) -> bool:
        """Verify PIN against stored PBKDF2 hash."""
        if not stored_hash:
            return False
        try:
            salt = bytes.fromhex(salt_hex)
        except (ValueError, TypeError):
            return False
        _, computed = self._hash_pin_pbkdf2(pin, salt)
        return secrets.compare_digest(computed, stored_hash)

    def create_user(self, user_id, pin, username=None, gender=None):
        """Create new user with PBKDF2 PIN hash."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        salt_hex, pin_hash = self._hash_pin_pbkdf2(pin)

        try:
            cursor.execute('''
                INSERT INTO users (user_id, username, gender, pin_hash, pin_salt)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, (username or "").strip(), (gender or "").strip().lower(), pin_hash, salt_hex))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        finally:
            conn.close()

        return success

    def verify_pin(self, user_id, pin):
        """Verify user PIN. Supports PBKDF2 (new) and SHA-256 (legacy) for migration."""
        if not user_id or not pin:
            return False
        uid = str(user_id).strip()
        pin = str(pin).strip()
        if len(pin) < 4:
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Case-insensitive lookup to handle legacy/mixed-case user IDs in older rows.
        cursor.execute('''
            SELECT pin_hash, pin_salt
            FROM users
            WHERE lower(trim(user_id)) = lower(trim(?))
            LIMIT 1
        ''', (uid,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False

        stored_hash, pin_salt = row[0], row[1] if len(row) > 1 else None

        if not stored_hash:
            return False

        if pin_salt:
            return self._verify_pin_pbkdf2(pin, pin_salt, stored_hash)

        legacy_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
        return secrets.compare_digest(legacy_hash, stored_hash)

    def user_has_pin(self, user_id):
        """Check whether user exists and has a stored PIN hash."""
        if not user_id:
            return False
        uid = str(user_id).strip()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pin_hash
            FROM users
            WHERE lower(trim(user_id)) = lower(trim(?))
            LIMIT 1
        ''', (uid,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False
        return bool(row[0])

    def user_exists(self, user_id):
        """Check if user exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_user_profile(self, user_id):
        """Get username/email profile for a user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, gender, created_at, last_seen
            FROM users
            WHERE lower(trim(user_id)) = lower(trim(?))
            LIMIT 1
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        username = (row[1] or "").strip()
        gender = (row[2] or "").strip().lower()
        return {
            "user_id": row[0],
            "username": username,
            "gender": gender,
            "created_at": row[3],
            "last_seen": row[4],
        }

    def update_username(self, user_id, username):
        """Update account username."""
        cleaned = (username or "").strip()
        if len(cleaned) < 2 or len(cleaned) > 40:
            return False, "Username must be 2-40 characters"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET username = ?, last_seen = CURRENT_TIMESTAMP
            WHERE lower(trim(user_id)) = lower(trim(?))
        ''', (cleaned, user_id))
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        if not updated:
            return False, "Account not found"
        return True, None

    def update_gender(self, user_id, gender):
        """Update account gender."""
        cleaned = (gender or "").strip().lower()
        if cleaned not in {"", "male", "female", "prefer_not_to_say"}:
            return False, "Gender must be male, female, or prefer_not_to_say"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET gender = ?, last_seen = CURRENT_TIMESTAMP
            WHERE lower(trim(user_id)) = lower(trim(?))
        ''', (cleaned, user_id))
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        if not updated:
            return False, "Account not found"
        return True, None

    # ============ MESSAGE & SUMMARY STORAGE ============

    def _normalize_title_words(self, text, max_words=5):
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if not cleaned:
            return ""
        cleaned = re.sub(r"[^\w\s'-]", "", cleaned, flags=re.UNICODE).strip()
        words = [word for word in cleaned.split(" ") if word]
        if not words:
            return ""
        return " ".join(words[:max_words]).strip()

    def _title_needs_refresh(self, title):
        cleaned = re.sub(r"\s+", " ", (title or "").strip())
        if not cleaned or cleaned == "New conversation":
            return True
        lowered = cleaned.lower()
        if lowered.startswith("user:") or "| bot:" in lowered:
            return True
        if len(cleaned.split()) > 5:
            return True
        if len(cleaned) > 40:
            return True
        return False

    def _title_matches_first_message(self, title, first_message):
        normalized_title = self._normalize_title_words(title, max_words=5).lower()
        normalized_first_message = self._normalize_title_words(first_message, max_words=5).lower()
        return bool(normalized_title and normalized_first_message and normalized_title == normalized_first_message)

    def _generate_conversation_title(self, first_message="", intent=""):
        """Generate a short conversation title from the first message or detected intent."""
        text = (first_message or "").strip()
        normalized = text.lower()
        normalized_intent = (intent or "").strip().lower()

        keyword_titles = [
            (("hurt myself", "harm myself", "kill myself", "end my life", "suicid"), "Need Emotional Support"),
            (("exam", "exams", "test", "study", "studying"), "Exam Stress Help"),
            (("cant start", "can't start", "cant even start", "can't even start", "cannot start", "dont know what to do", "don't know what to do", "stuck"), "Lack of Motivation"),
            (("confused", "confusing", "idk", "i dont know", "i don't know", "weird"), "Feeling Confused"),
            (("stress", "stressed", "overwhelmed", "pressure"), "Managing Stress"),
            (("anxious", "anxiety", "panic", "panicking"), "Anxiety Support"),
            (("sad", "low", "empty", "down"), "Feeling Low"),
            (("happy", "better", "good", "proud", "well"), "Feeling Happy"),
        ]

        for patterns, title in keyword_titles:
            if any(pattern in normalized for pattern in patterns):
                return title

        intent_titles = {
            "self_harm": "Need Emotional Support",
            "crisis": "Need Emotional Support",
            "stress": "Managing Stress",
            "anxiety": "Anxiety Support",
            "sadness": "Feeling Low",
            "depression": "Feeling Low",
            "anger": "Managing Frustration",
            "fear": "Working Through Fear",
            "abuse": "Safety Support",
            "distress": "Emotional Support",
            "third_person": "Concern For Someone",
            "greeting": "Starting A Chat",
        }
        if normalized_intent in intent_titles:
            return intent_titles[normalized_intent]

        shortened = self._normalize_title_words(text, max_words=5)
        if not shortened:
            return "New conversation"
        return shortened[:60]

    def _extract_user_text_from_summary(self, summary):
        text = (summary or "").strip()
        if not text:
            return ""
        match = re.search(r"User:\s*(.*?)\s*\|\s*Bot:", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip().rstrip(".")
        cleaned = re.sub(r"^\s*User:\s*", "", text, flags=re.IGNORECASE).strip()
        return cleaned.rstrip(".")

    def _backfill_missing_message_confidence(self, user_id=None, limit=500):
        """
        Backfill old message rows that predate confidence storage by re-running the
        intent model on the stored user-side summary text.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        params = []
        filters = ['(confidence IS NULL OR confidence <= 0)']
        if user_id:
            filters.append('user_id = ?')
            params.append(user_id)
        where_clause = " AND ".join(filters)
        cursor.execute(f'''
            SELECT id, summary
            FROM messages
            WHERE {where_clause}
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (*params, limit))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return 0

        try:
            from backend.models.intent_engine_bilstm import predict_intent as runtime_predict_intent
        except Exception:
            from backend.models.fallback_intent_engine import predict_intent as runtime_predict_intent

        updates = []
        for message_id, summary in rows:
            user_text = self._extract_user_text_from_summary(summary)
            if not user_text:
                continue
            try:
                _, confidence = runtime_predict_intent(user_text)
                normalized_confidence = max(0.0, min(1.0, float(confidence)))
            except Exception:
                continue
            updates.append((normalized_confidence, message_id))

        if not updates:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany('''
            UPDATE messages
            SET confidence = ?
            WHERE id = ?
        ''', updates)
        conn.commit()
        conn.close()
        return len(updates)

    def create_conversation(self, user_id, conversation_id=None, title=None, first_intent=None):
        """Create a new conversation row and return the conversation id."""
        conversation_id = (conversation_id or str(uuid.uuid4())).strip()
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR IGNORE INTO conversations (conversation_id, user_id, title, first_intent, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            conversation_id,
            user_id,
            (title or "New conversation").strip(),
            (first_intent or "").strip(),
            now,
            now,
        ))
        conn.commit()
        conn.close()
        return conversation_id

    def ensure_conversation(self, user_id, conversation_id, first_message="", intent=""):
        """Create or backfill a conversation and title if needed."""
        conv_id = (conversation_id or "").strip() or str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            SELECT title, first_intent
            FROM conversations
            WHERE conversation_id = ? AND user_id = ?
            LIMIT 1
        ''', (conv_id, user_id))
        row = cursor.fetchone()
        generated_title = self._generate_conversation_title(first_message, intent)
        if row is None:
            cursor.execute('''
                INSERT INTO conversations (conversation_id, user_id, title, first_intent, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                conv_id,
                user_id,
                generated_title,
                (intent or "").strip(),
                now,
                now,
            ))
        else:
            existing_title = (row[0] or "").strip()
            existing_intent = (row[1] or "").strip()
            should_refresh_title = (
                self._title_needs_refresh(existing_title)
                or (
                    first_message
                    and self._title_matches_first_message(existing_title, first_message)
                    and generated_title != existing_title
                )
            )
            updated_title = generated_title if should_refresh_title else existing_title
            updated_intent = existing_intent or (intent or "").strip()
            cursor.execute('''
                UPDATE conversations
                SET title = ?, first_intent = ?, updated_at = ?
                WHERE conversation_id = ? AND user_id = ?
            ''', (updated_title, updated_intent, now, conv_id, user_id))
        conn.commit()
        conn.close()
        return conv_id

    def save_conversation_message(self, user_id, conversation_id, sender, message, intent=None, confidence=0):
        """Persist a single raw chat message under a conversation."""
        if not user_id or not conversation_id or not sender or not str(message or "").strip():
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        normalized_confidence = 0.0
        try:
            normalized_confidence = max(0.0, min(1.0, float(confidence or 0)))
        except (TypeError, ValueError):
            normalized_confidence = 0.0
        cursor.execute('''
            INSERT INTO conversation_messages (conversation_id, user_id, sender, message, intent, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            conversation_id,
            user_id,
            sender,
            str(message).strip(),
            (intent or "").strip(),
            normalized_confidence,
            now,
        ))
        cursor.execute('''
            UPDATE conversations
            SET updated_at = ?
            WHERE conversation_id = ? AND user_id = ?
        ''', (now, conversation_id, user_id))
        conn.commit()
        conn.close()

    def save_conversation_turn(self, user_id, conversation_id, user_message, bot_message, intent=None, crisis_level=0, confidence=0):
        """Save a real user/bot exchange plus the legacy summary row for compatibility."""
        conv_id = self.ensure_conversation(user_id, conversation_id, first_message=user_message, intent=intent)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        normalized_confidence = 0.0
        try:
            normalized_confidence = max(0.0, min(1.0, float(confidence or 0)))
        except (TypeError, ValueError):
            normalized_confidence = 0.0

        cursor.execute('''
            UPDATE users
            SET last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO users (user_id, username, gender, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, "", ""))

        user_text = str(user_message or "").strip()
        bot_text = str(bot_message or "").strip()
        if user_text:
            cursor.execute('''
                INSERT INTO conversation_messages (conversation_id, user_id, sender, message, intent, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (conv_id, user_id, 'user', user_text, (intent or "").strip(), normalized_confidence, now))
        if bot_text:
            cursor.execute('''
                INSERT INTO conversation_messages (conversation_id, user_id, sender, message, intent, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (conv_id, user_id, 'bot', bot_text, (intent or "").strip(), normalized_confidence, now))

        summary = f"User: {user_text[:50]}{'...' if len(user_text) > 50 else ''} | Bot: {bot_text[:50]}{'...' if len(bot_text) > 50 else ''}"
        cursor.execute('''
            INSERT INTO messages (user_id, session_id, conversation_id, summary, intent, crisis_level, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            conv_id,
            conv_id,
            summary,
            (intent or "").strip(),
            int(crisis_level or 0),
            normalized_confidence,
            now,
        ))

        cursor.execute('''
            UPDATE conversations
            SET updated_at = ?
            WHERE conversation_id = ? AND user_id = ?
        ''', (now, conv_id, user_id))

        conn.commit()
        conn.close()
        return conv_id
    
    def save_message_summary(self, user_id, session_id, summary, intent, crisis_level=0, confidence=0, conversation_id=None):
        """
        Save AI-generated summary (NOT raw messages).
        Per UI_EXECUTION_PLAN_HYBRID: Summary-based memory only.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update user's last_seen without overwriting existing PIN hash
        cursor.execute('''
            UPDATE users
            SET last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))

        # Create user row only if it doesn't exist
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO users (user_id, username, gender, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, "", ""))
        
        # Save summary (not raw message)
        cursor.execute('''
            INSERT INTO messages (user_id, session_id, conversation_id, summary, intent, crisis_level, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, session_id, conversation_id or session_id, summary, intent, crisis_level, confidence or 0))
        
        conn.commit()
        conn.close()

    def save_intent_log(self, intent, confidence=None, user_id=None, session_id=None):
        """Persist intent/confidence for analytics and debugging."""
        if not intent:
            return

        normalized_confidence = None
        if confidence is not None:
            try:
                normalized_confidence = float(confidence)
            except (TypeError, ValueError):
                normalized_confidence = None
            else:
                normalized_confidence = max(0.0, min(1.0, normalized_confidence))

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO intent_logs (user_id, session_id, intent, confidence)
            VALUES (?, ?, ?, ?)
        ''', (
            str(user_id).strip() if user_id else None,
            str(session_id).strip() if session_id else None,
            str(intent).strip(),
            normalized_confidence,
        ))
        conn.commit()
        conn.close()

    def _compute_ratio(self, numerator, denominator):
        try:
            numerator_value = float(numerator or 0)
            denominator_value = float(denominator or 0)
        except (TypeError, ValueError):
            return 0.0
        if denominator_value <= 0:
            return 0.0
        return max(0.0, min(1.0, numerator_value / denominator_value))

    def _get_average_confidence(self, user_id=None, days=None):
        """
        Get average model confidence as a true per-message average.

        Priority:
        1. Stored message confidence scores (preferred for analytics)
        2. Intent logs as a fallback when historical message rows are missing scores

        Missing rows count against coverage so a single logged 1.0 score cannot
        incorrectly inflate the whole dashboard to 100%.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        filters = []
        params = []
        if user_id:
            filters.append('user_id = ?')
            params.append(user_id)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            filters.append('timestamp >= ?')
            params.append(cutoff)

        base_where = f" WHERE {' AND '.join(filters)}" if filters else ""

        cursor.execute(f'''
            SELECT COUNT(*)
            FROM messages
            {base_where}
        ''', tuple(params))
        total_messages = cursor.fetchone()[0] or 0

        message_conf_filters = list(filters)
        message_conf_params = list(params)
        message_conf_filters.extend(['confidence IS NOT NULL', 'confidence > 0'])
        message_conf_where = f" WHERE {' AND '.join(message_conf_filters)}" if message_conf_filters else ""
        cursor.execute(f'''
            SELECT COUNT(*), COALESCE(SUM(confidence), 0)
            FROM messages
            {message_conf_where}
        ''', tuple(message_conf_params))
        message_row = cursor.fetchone() or (0, 0)
        scored_message_count = message_row[0] or 0
        scored_message_sum = message_row[1] or 0.0

        if total_messages > 0 and scored_message_count > 0:
            conn.close()
            return self._compute_ratio(scored_message_sum, total_messages)

        log_filters = []
        log_params = []
        if user_id:
            log_filters.append('user_id = ?')
            log_params.append(user_id)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            log_filters.append('timestamp >= ?')
            log_params.append(cutoff)
        log_filters.append('confidence IS NOT NULL')
        log_where = f" WHERE {' AND '.join(log_filters)}" if log_filters else ""
        cursor.execute(f'''
            SELECT COUNT(*), COALESCE(SUM(confidence), 0)
            FROM intent_logs
            {log_where}
        ''', tuple(log_params))
        log_row = cursor.fetchone() or (0, 0)
        log_count = log_row[0] or 0
        log_sum = log_row[1] or 0.0
        conn.close()

        denominator = total_messages or log_count
        return self._compute_ratio(log_sum, denominator)

    def get_conversation_history(self, session_id, limit=50):
        """
        Get SUMMARY-BASED conversation history.
        Returns summaries ordered by timestamp DESC.
        NO raw message replay - per UI_EXECUTION_PLAN_HYBRID requirements.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT session_id, summary, intent, crisis_level, timestamp
            FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (session_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Format as conversation summaries
        results = []
        for row in rows:
            results.append({
                "session_id": row[0],
                "summary": row[1],
                "intent": row[2],
                "crisis_level": row[3],
                "timestamp": row[4]
            })
        
        return results

    def get_conversation_history_for_user(self, session_id, user_id, limit=100):
        """Get conversation history for a session, only if it belongs to the user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, summary, intent, crisis_level, timestamp
            FROM messages
            WHERE session_id = ? AND user_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (session_id, user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [
            {"session_id": r[0], "summary": r[1], "intent": r[2], "crisis_level": r[3], "timestamp": r[4]}
            for r in rows
        ]

    def get_conversation_messages_for_user(self, conversation_id, user_id, limit=200):
        """Get real stored messages for a conversation, only if it belongs to the user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sender, message, intent, confidence, timestamp
            FROM conversation_messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY timestamp ASC, id ASC
            LIMIT ?
        ''', (conversation_id, user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "sender": row[0],
                "message": row[1],
                "intent": row[2],
                "confidence": row[3],
                "timestamp": row[4],
            }
            for row in rows
        ]

    def get_user_conversations(self, user_id, limit=50):
        """Get distinct conversations for the user with title, preview, and timestamps."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                c.conversation_id,
                c.title,
                c.first_intent,
                c.created_at,
                c.updated_at,
                (
                    SELECT cm.message
                    FROM conversation_messages cm
                    WHERE cm.conversation_id = c.conversation_id
                      AND cm.user_id = c.user_id
                      AND cm.sender = 'user'
                    ORDER BY cm.timestamp ASC, cm.id ASC
                    LIMIT 1
                ) AS first_user_message,
                (
                    SELECT cm.message
                    FROM conversation_messages cm
                    WHERE cm.conversation_id = c.conversation_id
                      AND cm.user_id = c.user_id
                    ORDER BY cm.timestamp DESC, cm.id DESC
                    LIMIT 1
                ) AS latest_message
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY datetime(c.updated_at) DESC, c.updated_at DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        conversation_items = []
        for row in rows:
            generated_title = self._generate_conversation_title(row[5] or "", row[2] or "")
            stored_title = (row[1] or "").strip()
            should_refresh_title = (
                self._title_needs_refresh(stored_title)
                or (
                    row[5]
                    and self._title_matches_first_message(stored_title, row[5])
                    and generated_title != stored_title
                )
            )
            display_title = generated_title if should_refresh_title else stored_title
            if display_title != stored_title:
                cursor.execute('''
                    UPDATE conversations
                    SET title = ?
                    WHERE conversation_id = ? AND user_id = ?
                ''', (display_title, row[0], user_id))
            conversation_items.append({
                "conversation_id": row[0],
                "title": display_title,
                "intent": row[2] or "",
                "created_at": row[3],
                "updated_at": row[4],
                "preview": row[5] or row[6] or "",
                "last_message_at": row[4] or row[3],
            })
        conn.commit()

        existing_ids = {item["conversation_id"] for item in conversation_items if item.get("conversation_id")}
        cursor.execute('''
            SELECT session_id, summary, intent, MAX(timestamp) AS last_message_at, MIN(timestamp) AS created_at
            FROM messages
            WHERE user_id = ?
            GROUP BY session_id
            ORDER BY datetime(last_message_at) DESC, last_message_at DESC
            LIMIT ?
        ''', (user_id, limit * 2))
        legacy_rows = cursor.fetchall()
        conn.close()

        for row in legacy_rows:
            session_id = row[0]
            if not session_id or session_id in existing_ids:
                continue
            summary = row[1] or ""
            preview = summary
            user_match = re.search(r"User:\s*([^|]+)", summary, flags=re.IGNORECASE)
            if user_match and user_match.group(1):
                preview = user_match.group(1).strip()
            conversation_items.append({
                "conversation_id": session_id,
                "title": self._generate_conversation_title(preview, row[2] or ""),
                "intent": row[2] or "",
                "created_at": row[4],
                "updated_at": row[3],
                "preview": preview,
                "last_message_at": row[3],
            })

        conversation_items.sort(key=lambda item: item.get("last_message_at") or item.get("created_at") or "", reverse=True)
        return conversation_items[:limit]

    def get_user_sessions(self, user_id, limit=50):
        """Get user's recent chat sessions with summaries (for conversation history)."""
        conversations = self.get_user_conversations(user_id, limit=limit)
        return [
            {
                "session_id": item["conversation_id"],
                "conversation_id": item["conversation_id"],
                "summary": item["preview"],
                "title": item["title"],
                "intent": item["intent"],
                "last_message_at": item["last_message_at"],
            }
            for item in conversations
        ]

    # ============ APP SESSION PERSISTENCE (ADVANCEchatbot) ============

    def save_app_session(self, session_id, user_id, pin_verified=False, expiry_minutes=60 * 24 * 365 * 10):
        """Persist app session to DB."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        expires_at = datetime.now() + timedelta(minutes=expiry_minutes)
        pv = 1 if pin_verified else 0
        uid = user_id if user_id else ""
        cursor.execute('''
            INSERT OR REPLACE INTO sessions (session_id, user_id, pin_verified, last_active, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, uid, pv, datetime.now(), expires_at))
        conn.commit()
        conn.close()

    def get_app_session(self, session_id):
        """Get app session from DB. Returns None if expired or not found."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, pin_verified, expires_at FROM sessions WHERE session_id = ?
        ''', (session_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        user_id, pin_verified, expires_at = row
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) if expires_at else None
        except (ValueError, TypeError):
            exp = None
        if exp is None or datetime.now() > exp:
            self.end_session(session_id)
            return None
        return {
            "user_id": user_id if user_id else None,
            "pin_verified": bool(pin_verified) if pin_verified is not None else False,
            "expires_at": expires_at,
        }

    def refresh_app_session(self, session_id, expiry_minutes=60 * 24 * 365 * 10):
        """Extend session expiry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        expires_at = datetime.now() + timedelta(minutes=expiry_minutes)
        cursor.execute('''
            UPDATE sessions SET last_active = ?, expires_at = ? WHERE session_id = ?
        ''', (datetime.now(), expires_at, session_id))
        conn.commit()
        conn.close()

    def update_app_session_pin_verified(self, session_id, pin_verified=True):
        """Mark session as PIN verified."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        pv = 1 if pin_verified else 0
        cursor.execute('UPDATE sessions SET pin_verified = ? WHERE session_id = ?', (pv, session_id))
        conn.commit()
        conn.close()

    # ============ SESSION MANAGEMENT ============

    def create_session(self, user_id):
        """Create new session with long-lived expiry."""
        session_id = str(uuid.uuid4())
        expiry_minutes = 60 * 24 * 365 * 10
        self.save_app_session(session_id, user_id or "", pin_verified=False, expiry_minutes=expiry_minutes)
        return session_id, datetime.now() + timedelta(minutes=expiry_minutes)

    def validate_session(self, session_id):
        """Validate session - check if exists and not expired."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, expires_at FROM sessions WHERE session_id = ?
        ''', (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False, None, "Session not found"
        
        user_id, expires_at = row
        
        try:
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        except:
            expires_at = datetime.now() - timedelta(minutes=1)  # Force expire
        
        if datetime.now() > expires_at:
            # Session expired - clean up
            self.end_session(session_id)
            return False, None, "Session expired"
        
        return True, user_id, "valid"

    def update_session_activity(self, session_id):
        """Update last active timestamp."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        new_expires = datetime.now() + timedelta(minutes=60 * 24 * 365 * 10)
        
        cursor.execute('''
            UPDATE sessions SET last_active = ?, expires_at = ? WHERE session_id = ?
        ''', (datetime.now(), new_expires, session_id))
        
        conn.commit()
        conn.close()

    def end_session(self, session_id):
        """End a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()

    def end_all_user_sessions(self, user_id):
        """End all sessions for a user (logout from all devices)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

    def clear_user_conversation_history(self, user_id):
        """Delete all messages for user. Returns count of deleted messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM conversation_messages WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM conversations WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
        n = cursor.rowcount
        conn.commit()
        conn.close()
        return n

    # ============ EMERGENCY CONTACTS ============

    def save_emergency_contact(self, user_id, contact_number, relationship, enabled=True, consent_enabled=True):
        """Save or update emergency contact. Only stores if enabled and consent given."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        en = 1 if enabled else 0
        ce = 1 if consent_enabled else 0
        cursor.execute('''
            INSERT INTO emergency_contacts (user_id, contact_number, relationship, enabled, consent_enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                contact_number=excluded.contact_number,
                relationship=excluded.relationship,
                enabled=excluded.enabled,
                consent_enabled=excluded.consent_enabled,
                updated_at=excluded.updated_at
        ''', (user_id, contact_number or "", relationship or "", en, ce, now))
        conn.commit()
        conn.close()

    def get_emergency_contact(self, user_id):
        """Get emergency contact for user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT contact_number, relationship, enabled, consent_enabled
            FROM emergency_contacts WHERE user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "contact_number": row[0] or "",
            "relationship": row[1] or "",
            "enabled": bool(row[2]),
            "consent_enabled": bool(row[3])
        }

    def update_emergency_contact_enabled(self, user_id, enabled):
        """Enable or disable emergency contact feature."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        en = 1 if enabled else 0
        cursor.execute('''
            UPDATE emergency_contacts SET enabled = ?, updated_at = ? WHERE user_id = ?
        ''', (en, datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()

    # ============ USER SETTINGS ============

    def get_user_settings(self, user_id):
        """Get user settings. Creates default if not exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT crisis_helpline_enabled, dark_mode FROM user_settings WHERE user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute('''
                INSERT INTO user_settings (user_id) VALUES (?)
            ''', (user_id,))
            conn.commit()
            conn.close()
            return {"crisis_helpline_enabled": True, "dark_mode": False}
        conn.close()
        return {"crisis_helpline_enabled": bool(row[0]), "dark_mode": bool(row[1])}

    def update_user_settings(self, user_id, crisis_helpline_enabled=None, dark_mode=None):
        """Update user settings."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if crisis_helpline_enabled is not None:
            v = 1 if crisis_helpline_enabled else 0
            cursor.execute('''
                INSERT INTO user_settings (user_id, crisis_helpline_enabled, updated_at)
                VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET
                crisis_helpline_enabled=excluded.crisis_helpline_enabled, updated_at=excluded.updated_at
            ''', (user_id, v, now))
        if dark_mode is not None:
            v = 1 if dark_mode else 0
            cursor.execute('''
                INSERT INTO user_settings (user_id, dark_mode, updated_at)
                VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET
                dark_mode=excluded.dark_mode, updated_at=excluded.updated_at
            ''', (user_id, v, now))
        conn.commit()
        conn.close()

    # ============ EMERGENCY NOTIFICATION (user signals only) ============

    def get_user_crisis_count_recent(self, user_id, hours=24):
        """Count USER crisis events only (exclude third_person)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor.execute('''
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND crisis_level >= 1 AND intent != 'third_person'
            AND timestamp >= ?
        ''', (user_id, cutoff))
        c = cursor.fetchone()[0] or 0
        conn.close()
        return c

    def get_user_safety_count_recent(self, user_id, hours=24):
        """Count USER abuse/safety events (exclude third_person)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor.execute('''
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND intent = 'abuse' AND timestamp >= ?
        ''', (user_id, cutoff))
        c = cursor.fetchone()[0] or 0
        conn.close()
        return c

    def was_emergency_notified_today(self, user_id):
        """Check if we already sent notification today (max 1/day)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('''
            SELECT 1 FROM emergency_notifications
            WHERE user_id = ? AND date(notified_at) = ?
        ''', (user_id, today))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def log_emergency_notification(self, user_id):
        """Log that we sent an emergency notification."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO emergency_notifications (user_id) VALUES (?)
        ''', (user_id,))
        conn.commit()
        conn.close()

    def change_pin(self, user_id, old_pin, new_pin):
        """Change user PIN. Returns (success, error_msg)."""
        if not self.verify_pin(user_id, old_pin):
            return False, "Incorrect current PIN"
        if not new_pin or len(str(new_pin).strip()) < 4 or len(str(new_pin).strip()) > 6:
            return False, "PIN must be 4-6 digits"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        salt_hex, pin_hash = self._hash_pin_pbkdf2(str(new_pin).strip())
        cursor.execute('''
            UPDATE users SET pin_hash = ?, pin_salt = ? WHERE user_id = ?
        ''', (pin_hash, salt_hex, user_id))
        conn.commit()
        conn.close()
        return True, None

    def update_pin_with_otp(self, user_id, new_pin):
        """Set new PIN (after OTP verification). Used for reset."""
        if not new_pin or len(str(new_pin).strip()) < 4 or len(str(new_pin).strip()) > 6:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        salt_hex, pin_hash = self._hash_pin_pbkdf2(str(new_pin).strip())
        cursor.execute('''
            UPDATE users SET pin_hash = ?, pin_salt = ? WHERE user_id = ?
        ''', (pin_hash, salt_hex, user_id))
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    # ============ ANALYTICS ============
    
    def get_global_analytics(self):
        """Get aggregate statistics (no user-level data)."""
        self._backfill_missing_message_confidence()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total messages
        cursor.execute('SELECT COUNT(*) FROM messages')
        total_messages = cursor.fetchone()[0] or 0
        
        # Total sessions (from messages - sessions table may be empty with in-memory app sessions)
        cursor.execute('SELECT COUNT(DISTINCT session_id) FROM messages')
        total_sessions = cursor.fetchone()[0] or 0
        
        # Crisis count
        cursor.execute('SELECT COUNT(*) FROM messages WHERE crisis_level > 0')
        crisis_count = cursor.fetchone()[0] or 0
        
        # Intent distribution
        cursor.execute('''
            SELECT intent, COUNT(*) as count 
            FROM messages 
            GROUP BY intent
        ''')
        intent_rows = cursor.fetchall()
        intent_counts = {row[0]: row[1] for row in intent_rows if row[0]}
        
        conn.close()
        crisis_rate = self._compute_ratio(crisis_count, total_messages)
        avg_confidence = self._get_average_confidence()
        
        return {
            "total_messages": total_messages,
            "total_sessions": total_sessions,
            "crisis_count": crisis_count,
            "crisis_rate": crisis_rate,
            "intent_distribution": intent_counts,
            "avg_confidence": avg_confidence,
            "confidence": avg_confidence,
        }

    def get_global_trends(self, days=7):
        """Get messages per day and crisis per day for the last N days (real DB data)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Build list of last N days
        today = datetime.now().date()
        day_labels = []
        messages_by_day = []
        crisis_by_day = []
        
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            day_str = d.strftime('%Y-%m-%d')
            day_labels.append(d.strftime('%a'))  # Mon, Tue, etc.
            
            cursor.execute('''
                SELECT COUNT(*), SUM(CASE WHEN crisis_level > 0 THEN 1 ELSE 0 END)
                FROM messages
                WHERE date(timestamp) = ?
            ''', (day_str,))
            row = cursor.fetchone()
            messages_by_day.append(row[0] or 0)
            crisis_by_day.append(row[1] or 0)
        
        conn.close()
        
        return {
            "labels": day_labels,
            "trend_data": [
                {"day": day_labels[i], "messages": messages_by_day[i], "crisis": crisis_by_day[i]}
                for i in range(len(day_labels))
            ]
        }

    def get_user_trends(self, user_id, days=7):
        """Get user's messages per day and crisis per day for the last N days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        day_labels = []
        messages_by_day = []
        crisis_by_day = []
        
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            day_str = d.strftime('%Y-%m-%d')
            day_labels.append(d.strftime('%a'))
            
            cursor.execute('''
                SELECT COUNT(*), SUM(CASE WHEN crisis_level > 0 THEN 1 ELSE 0 END)
                FROM messages
                WHERE user_id = ? AND date(timestamp) = ?
            ''', (user_id, day_str))
            row = cursor.fetchone()
            messages_by_day.append(row[0] or 0)
            crisis_by_day.append(row[1] or 0)
        
        conn.close()
        
        return {
            "labels": day_labels,
            "trend_data": [
                {"day": day_labels[i], "messages": messages_by_day[i], "crisis": crisis_by_day[i]}
                for i in range(len(day_labels))
            ]
        }

    def get_user_analytics(self, user_id):
        """Get single-user analytics."""
        self._backfill_missing_message_confidence(user_id=user_id)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total messages
        cursor.execute('SELECT COUNT(*) FROM messages WHERE user_id = ?', (user_id,))
        total_messages = cursor.fetchone()[0] or 0
        
        # Total sessions (from messages - sessions table may be empty with in-memory app sessions)
        cursor.execute('SELECT COUNT(DISTINCT session_id) FROM messages WHERE user_id = ?', (user_id,))
        total_sessions = cursor.fetchone()[0] or 0
        
        # Crisis count
        cursor.execute('SELECT COUNT(*) FROM messages WHERE user_id = ? AND crisis_level > 0', (user_id,))
        crisis_count = cursor.fetchone()[0] or 0
        
        conn.close()
        crisis_rate = self._compute_ratio(crisis_count, total_messages)
        avg_confidence = self._get_average_confidence(user_id=user_id)
        
        return {
            "user_id": user_id,
            "total_messages": total_messages,
            "total_sessions": total_sessions,
            "crisis_count": crisis_count,
            "crisis_rate": crisis_rate,
            "avg_confidence": avg_confidence,
            "confidence": avg_confidence,
            "data_expires_at": None
        }

    # ============ FEEDBACK ============

    def message_belongs_to_user(self, message_id, user_id):
        """Check if message belongs to user (for feedback validation)."""
        if not message_id or not user_id:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM messages WHERE id = ? AND user_id = ?', (message_id, user_id))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def save_feedback(self, message_id, rating, user_id=None):
        """
        Save user feedback. If user_id provided, validates message belongs to user.
        Returns (success: bool, error_msg: str|None)
        """
        if message_id is None:
            return False, "Missing message_id"
        if user_id is not None and not self.message_belongs_to_user(message_id, user_id):
            return False, "Message does not belong to user"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO feedback (message_id, rating)
                VALUES (?, ?)
            ''', (message_id, rating))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    # ============ LEGACY METHODS (for compatibility) ============
    
    def save_message(self, user_id, session_id, message, response=None, intent=None):
        """Legacy method - now saves summary instead of raw message."""
        summary = f"User: {message[:50]}... | Bot: {response[:50]}..." if response else message[:100]
        crisis_level = 0
        self.save_message_summary(user_id, session_id, summary, intent, crisis_level)

    def get_user_history(self, user_id, limit=50):
        """Legacy method - returns conversation summaries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT summary, intent, timestamp 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def delete_user_data(self, user_id):
        """Delete all user data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get message IDs for feedback cleanup
        cursor.execute('SELECT id FROM messages WHERE user_id = ?', (user_id,))
        message_ids = [row[0] for row in cursor.fetchall()]
        
        # Delete feedback
        for msg_id in message_ids:
            cursor.execute('DELETE FROM feedback WHERE message_id = ?', (msg_id,))
        
        # Delete messages
        cursor.execute('DELETE FROM conversation_messages WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM conversations WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
        
        # Delete emergency contacts and related
        cursor.execute('DELETE FROM emergency_contacts WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM emergency_notifications WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))
        
        # Delete sessions
        cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        return True

    def update_user_id(self, old_user_id, new_user_id):
        """
        Change user_id (email) across all related tables.
        Returns (success: bool, message: str|None).
        """
        old_uid = (old_user_id or "").strip()
        new_uid = (new_user_id or "").strip()
        if not old_uid or not new_uid:
            return False, "Both current and new email are required"
        if old_uid == new_uid:
            return False, "New email must be different"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (new_uid,))
            if cursor.fetchone() is not None:
                conn.rollback()
                return False, "An account with this email already exists"

            cursor.execute('UPDATE users SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            if cursor.rowcount == 0:
                conn.rollback()
                return False, "Current account not found"

            cursor.execute('UPDATE conversation_messages SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE conversations SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE messages SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE sessions SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE emergency_contacts SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE emergency_notifications SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))
            cursor.execute('UPDATE user_settings SET user_id = ? WHERE user_id = ?', (new_uid, old_uid))

            conn.commit()
            return True, None
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, "An account with this email already exists"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


# Singleton instance
_db_manager = None

def get_database_manager():
    """Get the database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
