"""قواعد صارمة لظهور الجلسات في الواجهة العامة ولقبول حجز الزائر.

- **عرض في الجدول العام:** تُعرض فقط الجلسة التي لم ينتهِ وقتها المجدول (بداية + المدة).
- **قبول حجز/دفع جديد:** لا يُقبل إلا إذا لم يحن **وقت البدء** بعد (لا حجز بعد انطلاق الجلسة).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from . import models
from .time_utils import utcnow_naive

_MAX_REASONABLE_DURATION_MINUTES = 24 * 60


def _max_lookback_days() -> int:
    raw = os.getenv("PUBLIC_SESSION_LIST_LOOKBACK_DAYS", "2").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 2
    return max(0, min(n, 30))


def yoga_session_end_naive(session: models.YogaSession) -> datetime:
    """نهاية الجلسة المجدولة (بداية + duration) بتوقيت الخادم نفسه المستخدم في بقية التطبيق."""
    starts = session.starts_at
    if starts is None:
        return utcnow_naive()
    dur = int(session.duration_minutes or 0)
    dur = min(max(dur, 0), _MAX_REASONABLE_DURATION_MINUTES)
    return starts + timedelta(minutes=dur)


def yoga_session_still_on_public_schedule(session: models.YogaSession, *, now: datetime | None = None) -> bool:
    """تُعرض في /index إذا لم ينتهِ وقت الجلسة بعد (قد تكون «جارية»)."""
    now = now or utcnow_naive()
    return yoga_session_end_naive(session) > now


def yoga_session_accepts_new_public_booking(session: models.YogaSession, *, now: datetime | None = None) -> bool:
    """حجز زائر جديد: فقط قبل وقت البدء المجدول (صارم)."""
    now = now or utcnow_naive()
    if session.starts_at is None:
        return False
    return session.starts_at > now


def public_schedule_query_lower_bound_starts_at(*, now: datetime | None = None) -> datetime:
    """حد أدنى لـ starts_at في الاستعلام لتقليل الصفوف قبل التصفية النهائية."""
    now = now or utcnow_naive()
    return now - timedelta(days=_max_lookback_days())


def filter_sessions_for_public_index(
    sessions: list[models.YogaSession],
    *,
    now: datetime | None = None,
) -> list[models.YogaSession]:
    """إزالة الجلسات التي انتهى وقتها من القائمة المعروضة للزائر."""
    now = now or utcnow_naive()
    return [s for s in sessions if yoga_session_still_on_public_schedule(s, now=now)]
