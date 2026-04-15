from .web_shared import _plan_duration_days


def default_plan_labels() -> dict[str, str]:
    return {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }


def build_public_plan_rows(plans: list, *, plan_labels: dict[str, str]) -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
            "duration_days": _plan_duration_days(p.plan_type),
            "price": p.price,
            "session_limit": p.session_limit,
        }
        for p in plans
    ]


def recommended_plan_id_by_daily_price(plan_rows: list[dict]) -> int | None:
    """Pick the plan with the lowest price per day (price / duration_days).

    When two plans tie on daily rate, the longer duration wins (e.g. yearly over monthly).
    With fewer than two plans, returns None so the UI does not show a comparative badge.
    """
    if len(plan_rows) < 2:
        return None
    best: tuple[float, float, int] | None = None
    for p in plan_rows:
        raw_id = p.get("id")
        if raw_id is None:
            continue
        d = int(p.get("duration_days") or 0)
        if d <= 0:
            d = 1
        price = float(p.get("price") or 0.0)
        score = price / float(d)
        pid = int(raw_id)
        cand = (score, -float(d), pid)
        if best is None or cand < best:
            best = cand
    return best[2] if best else None
