from datetime import datetime, timedelta, timezone

# Saudi Arabia is fixed UTC+03 with no DST.
KSA_TZ = timezone(timedelta(hours=3), name="Asia/Riyadh")


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive_to_ksa(value: datetime) -> datetime:
    """
    Convert a UTC-naive/UTC-aware datetime to KSA local time.

    DB timestamps in this project are stored as UTC-naive; this helper keeps
    storage semantics unchanged and only normalizes display time.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KSA_TZ)
