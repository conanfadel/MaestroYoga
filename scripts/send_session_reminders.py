"""إرسال تذكيرات بريدية قبل الجلسات — شغّله دورياً (cron كل ساعة).

مثال:
  python scripts/send_session_reminders.py
  SESSION_REMINDER_HOURS=24 python scripts/send_session_reminders.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import SessionLocal
from backend.app.session_reminders import dispatch_session_reminder_emails


def main() -> None:
    hours = float(os.getenv("SESSION_REMINDER_HOURS", "24"))
    window = float(os.getenv("SESSION_REMINDER_WINDOW_MINUTES", "45"))
    db = SessionLocal()
    try:
        stats = dispatch_session_reminder_emails(db, hours_before=hours, window_minutes=window)
    finally:
        db.close()
    print("session_reminders", stats)


if __name__ == "__main__":
    main()
