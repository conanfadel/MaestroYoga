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
