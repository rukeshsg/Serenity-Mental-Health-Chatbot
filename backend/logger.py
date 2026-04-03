from datetime import datetime, timedelta
import os

from backend.data.database_manager import get_database_manager

LOG_FILE = "intent_log.txt"
DAYS_LIMIT = 16


def save_intent(intent, confidence=None, user_id=None, session_id=None):
    """Save intent to the legacy file log and the analytics DB log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} | {intent}\n"

    clean_old_logs()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

    try:
        get_database_manager().save_intent_log(
            intent=intent,
            confidence=confidence,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        # Keep the file log resilient even if DB logging is unavailable.
        pass


def clean_old_logs():
    """Remove logs older than the retention window."""
    if not os.path.exists(LOG_FILE):
        return

    valid_lines = []
    cutoff_date = datetime.now() - timedelta(days=DAYS_LIMIT)

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        try:
            timestamp_str, intent = line.strip().split(" | ")
            log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

            if log_time >= cutoff_date:
                valid_lines.append(line)
        except Exception:
            continue

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.writelines(valid_lines)


def get_recent_intents():
    """Get recent intents for pattern awareness."""
    if not os.path.exists(LOG_FILE):
        return []

    clean_old_logs()

    intents = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f.readlines():
            try:
                _, intent = line.strip().split(" | ")
                intents.append(intent)
            except Exception:
                continue

    return intents
