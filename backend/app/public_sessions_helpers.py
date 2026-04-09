from datetime import timedelta

from . import models
from .web_shared import _fmt_dt_weekday_ar


def build_public_session_rows(
    sessions: list[models.YogaSession],
    rooms_by_id: dict[int, models.Room],
    spots_by_session: dict[int, int],
) -> list[dict]:
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    rows: list[dict] = []
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        starts = s.starts_at
        dur = int(s.duration_minutes or 0)
        ends = (starts + timedelta(minutes=dur)) if starts else None
        rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt_weekday_ar(s.starts_at),
                "starts_at_iso": starts.isoformat() if starts else "",
                "ends_at_iso": ends.isoformat() if ends else "",
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "spots_available": spots_by_session.get(int(s.id), 0),
            }
        )
    return rows
