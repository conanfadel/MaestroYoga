from datetime import timedelta

from sqlalchemy.orm import Session

from . import models
from .security import hash_password
from .time_utils import utcnow_naive

DEMO_OWNER_EMAIL = "owner@maestroyoga.local"
DEMO_OWNER_PASSWORD = "Admin@12345"
DEMO_CENTER_NAME = "Maestro Yoga Center"
DEFAULT_FAQS: list[tuple[str, str]] = [
    ("هل يمكن الإلغاء؟", "نعم، حسب سياسة المركز قبل وقت الجلسة."),
    ("هل يلزم توثيق البريد؟", "نعم، لإتمام الحجز والاشتراك وحماية الحساب."),
    ("ما طرق الدفع؟", "بطاقات إلكترونية عبر بوابة دفع آمنة."),
]


def _seed_default_faqs(center_id: int) -> list[models.FAQItem]:
    return [
        models.FAQItem(
            center_id=center_id,
            question=question,
            answer=answer,
            sort_order=index,
            is_active=True,
        )
        for index, (question, answer) in enumerate(DEFAULT_FAQS, start=1)
    ]


def ensure_demo_data(db: Session) -> models.Center:
    center = db.query(models.Center).filter(models.Center.name == DEMO_CENTER_NAME).first()
    if not center:
        center = models.Center(name=DEMO_CENTER_NAME, city="Riyadh")
        db.add(center)
        db.flush()

        room_1 = models.Room(center_id=center.id, name="Zen Hall", capacity=20)
        room_2 = models.Room(center_id=center.id, name="Flow Room", capacity=14)
        db.add_all([room_1, room_2])
        db.flush()

        db.add_all(
            [
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك أسبوعي",
                    plan_type="weekly",
                    price=99.0,
                    session_limit=4,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك شهري",
                    plan_type="monthly",
                    price=299.0,
                    session_limit=12,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك سنوي",
                    plan_type="yearly",
                    price=2990.0,
                    session_limit=180,
                ),
            ]
        )

        starts = utcnow_naive().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
        db.add_all(
            [
                models.YogaSession(
                    center_id=center.id,
                    room_id=room_1.id,
                    title="Morning Flow",
                    trainer_name="Maya",
                    level="beginner",
                    starts_at=starts,
                    duration_minutes=60,
                    price_drop_in=60.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=room_2.id,
                    title="Power Yoga",
                    trainer_name="Nora",
                    level="intermediate",
                    starts_at=starts + timedelta(hours=2),
                    duration_minutes=75,
                    price_drop_in=80.0,
                ),
            ]
        )
        db.add_all(_seed_default_faqs(center.id))
        db.commit()
        db.refresh(center)

    # Ensure default public plans exist even for previously initialized databases.
    existing_plan_types = {
        p.plan_type
        for p in db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.center_id == center.id).all()
    }
    missing_defaults = []
    if "weekly" not in existing_plan_types:
        missing_defaults.append(
            models.SubscriptionPlan(
                center_id=center.id,
                name="اشتراك أسبوعي",
                plan_type="weekly",
                price=99.0,
                session_limit=4,
            )
        )
    if "monthly" not in existing_plan_types:
        missing_defaults.append(
            models.SubscriptionPlan(
                center_id=center.id,
                name="اشتراك شهري",
                plan_type="monthly",
                price=299.0,
                session_limit=12,
            )
        )
    if "yearly" not in existing_plan_types:
        missing_defaults.append(
            models.SubscriptionPlan(
                center_id=center.id,
                name="اشتراك سنوي",
                plan_type="yearly",
                price=2990.0,
                session_limit=180,
            )
        )
    if missing_defaults:
        db.add_all(missing_defaults)
        db.commit()

    faq_count = db.query(models.FAQItem).filter(models.FAQItem.center_id == center.id).count()
    if faq_count == 0:
        db.add_all(_seed_default_faqs(center.id))
        db.commit()

    owner = db.query(models.User).filter(models.User.email == DEMO_OWNER_EMAIL).first()
    if not owner:
        db.add(
            models.User(
                center_id=center.id,
                full_name="Center Owner",
                email=DEMO_OWNER_EMAIL,
                password_hash=hash_password(DEMO_OWNER_PASSWORD),
                role="center_owner",
                is_active=True,
            )
        )
        db.commit()

    return center
