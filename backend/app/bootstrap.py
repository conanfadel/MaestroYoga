from datetime import timedelta

from sqlalchemy import func
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
    ("هل يوجد موقف سيارات؟", "نعم، مواقف مخصصة لزوار المركز حسب التوفر."),
    ("ما الملابس المناسبة للجلسة؟", "ملابس رياضية مريحة؛ نوفر سجادًا وأدوات دعم أساسية."),
    ("هل يمكن تجميد الاشتراك؟", "حسب نوع الباقة وسياسة المركز؛ راجع الاستقبال أو صفحة الخطة."),
    ("هل توجد حصص للمبتدئين فقط؟", "نعم، جلسات مُعلَّمة كمستوى مبتدئ في الجدول العام."),
    ("كيف أحجز جلسة تجريبية؟", "سجّل الدخول، اختر الجلسة، وأكمل الحجز؛ قد تتوفر عروض للزيارة الأولى."),
    ("ما مدة الجلسة المعتادة؟", "غالبًا 60 دقيقة؛ بعض الأنماط مثل القوة أو الاسترخاء قد تطول قليلًا."),
    ("هل يُسمح بالحضور بدون حجز مسبق؟", "يُفضّل الحجز لضمان المكان؛ الدخول بدون حجز حسب السعة المتبقية."),
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

        seed_rooms = [
            models.Room(center_id=center.id, name="Zen Hall", capacity=20),
            models.Room(center_id=center.id, name="Flow Room", capacity=14),
            models.Room(center_id=center.id, name="قاعة الاسترخاء", capacity=12),
            models.Room(center_id=center.id, name="استوديو الضوء", capacity=18),
            models.Room(center_id=center.id, name="التراس الخارجي", capacity=10),
        ]
        db.add_all(seed_rooms)
        db.flush()
        r1, r2, r3, r4, r5 = seed_rooms

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
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك أسبوعي — مكثف",
                    plan_type="weekly",
                    price=149.0,
                    session_limit=8,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك شهري — بلس",
                    plan_type="monthly",
                    price=399.0,
                    session_limit=20,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="خطة تجربة قصيرة",
                    plan_type="weekly",
                    price=49.0,
                    session_limit=2,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك سنوي — ذهبي",
                    plan_type="yearly",
                    price=3990.0,
                    session_limit=250,
                ),
                models.SubscriptionPlan(
                    center_id=center.id,
                    name="اشتراك شهري — مرن",
                    plan_type="monthly",
                    price=349.0,
                    session_limit=None,
                ),
            ]
        )

        base = utcnow_naive().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
        db.add_all(
            [
                models.YogaSession(
                    center_id=center.id,
                    room_id=r1.id,
                    title="Morning Flow",
                    trainer_name="Maya",
                    level="beginner",
                    starts_at=base,
                    duration_minutes=60,
                    price_drop_in=60.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r2.id,
                    title="Power Yoga",
                    trainer_name="Nora",
                    level="intermediate",
                    starts_at=base + timedelta(hours=2),
                    duration_minutes=75,
                    price_drop_in=80.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r3.id,
                    title="Yin & Restore",
                    trainer_name="Lina",
                    level="beginner",
                    starts_at=base + timedelta(hours=5),
                    duration_minutes=60,
                    price_drop_in=55.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r4.id,
                    title="Vinyasa Link",
                    trainer_name="Omar",
                    level="intermediate",
                    starts_at=base + timedelta(hours=8),
                    duration_minutes=60,
                    price_drop_in=70.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r5.id,
                    title="Sunrise Stretch",
                    trainer_name="Maya",
                    level="advanced",
                    starts_at=base + timedelta(days=1, hours=7),
                    duration_minutes=45,
                    price_drop_in=65.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r1.id,
                    title="Hatha Basics",
                    trainer_name="Sara",
                    level="beginner",
                    starts_at=base + timedelta(days=1, hours=10),
                    duration_minutes=60,
                    price_drop_in=50.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r2.id,
                    title="Core & Balance",
                    trainer_name="Nora",
                    level="intermediate",
                    starts_at=base + timedelta(days=1, hours=18),
                    duration_minutes=50,
                    price_drop_in=75.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r3.id,
                    title="تأمل إرشادي",
                    trainer_name="Lina",
                    level="beginner",
                    starts_at=base + timedelta(days=2, hours=16),
                    duration_minutes=45,
                    price_drop_in=40.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r4.id,
                    title="Evening Flow",
                    trainer_name="Omar",
                    level="beginner",
                    starts_at=base + timedelta(days=2, hours=20),
                    duration_minutes=60,
                    price_drop_in=60.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r1.id,
                    title="Weekend Deep Stretch",
                    trainer_name="Sara",
                    level="intermediate",
                    starts_at=base + timedelta(days=3, hours=10),
                    duration_minutes=90,
                    price_drop_in=85.0,
                ),
                models.YogaSession(
                    center_id=center.id,
                    room_id=r5.id,
                    title="Outdoor Breathwork",
                    trainer_name="Maya",
                    level="intermediate",
                    starts_at=base + timedelta(days=3, hours=17),
                    duration_minutes=55,
                    price_drop_in=72.0,
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
    elif center.name == DEMO_CENTER_NAME:
        existing_q = {
            row.question
            for row in db.query(models.FAQItem).filter(models.FAQItem.center_id == center.id).all()
        }
        max_sort = (
            db.query(func.max(models.FAQItem.sort_order))
            .filter(models.FAQItem.center_id == center.id)
            .scalar()
        )
        next_sort = (max_sort or 0) + 1
        new_faqs: list[models.FAQItem] = []
        for question, answer in DEFAULT_FAQS:
            if question in existing_q:
                continue
            new_faqs.append(
                models.FAQItem(
                    center_id=center.id,
                    question=question,
                    answer=answer,
                    sort_order=next_sort,
                    is_active=True,
                )
            )
            next_sort += 1
        if new_faqs:
            db.add_all(new_faqs)
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
