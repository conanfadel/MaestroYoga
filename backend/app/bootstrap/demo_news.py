"""Demo news posts (picsum URLs) and DB sync for a center."""

from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive

# أخبار تجريبية منشورة بصور من الإنترنت (picsum — روابط ثابتة حسب البذرة).
DEMO_NEWS_POSTS: list[dict] = [
    {
        "title": "ورشة التنفس الصباحي الأسبوعية",
        "summary": "جلسة جماعية قبل الدوام لتصفية الذهن وتنشيط الجسم بلطف.",
        "body": (
            "نلتقي كل أحد ٧:٠٠–٧:٤٥ صباحًا في قاعة Zen Hall. "
            "نركز على تقنيات أنفية بسيطة ووضعيات فاتحة للصدر. "
            "للتسجيل: الاستقبال أو رسالة عبر الواجهة العامة بعد تسجيل الدخول."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-01/960/540",
        "gallery": [
            "https://picsum.photos/seed/maestro-news-01a/640/400",
            "https://picsum.photos/seed/maestro-news-01b/640/400",
        ],
        "pinned": True,
    },
    {
        "title": "توسيع ساعات استوديو التأمل",
        "summary": "أصبح بإمكانكم حجز أوقات إضافية مساءً لجلسات التأمل الإرشادي.",
        "body": (
            "اعتبارًا من هذا الأسبوع نفتح خانات جديدة ١٩:٠٠–٢٠:٣٠ في قاعة الاسترخاء. "
            "السعة محدودة؛ ننصح بالحجز المسبق من جدول الجلسات."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-02/960/540",
        "gallery": ["https://picsum.photos/seed/maestro-news-02a/640/400"],
        "pinned": False,
    },
    {
        "title": "لقاء مجتمع اليوغا — أبريل ٢٠٢٦",
        "summary": "لقاء اجتماعي خفيف بعد جلسة مشتركة مع قهوة ونقاش مفتوح.",
        "body": (
            "ندعوكم الجمعة ١٨:٠٠ في استوديو الضوء. "
            "جلسة فينياسا متوسطة ٦٠ دقيقة تليها ساعة للقاء. "
            "الدخول لمن سجّل عبر الحجز فقط."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-03/960/540",
        "gallery": [
            "https://picsum.photos/seed/maestro-news-03a/640/400",
            "https://picsum.photos/seed/maestro-news-03b/640/400",
        ],
        "pinned": False,
    },
    {
        "title": "نصائح أمان في وضعيات الحوض",
        "summary": "مقال قصير من فريق المدربين حول الاستقرار في الوضعيات الواقفة والتوازن.",
        "body": (
            "تجنّب قفل الركبتين بالكامل، وفعّل قوس القدم الخفيف. "
            "استخدم الدعامات عند الحاجة، وأخبر المدربًا عن أي إصابة قديمة. "
            "الاستماع للجسم أهم من عمق الوضعية."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-04/960/540",
        "gallery": ["https://picsum.photos/seed/maestro-news-04a/640/400"],
        "pinned": False,
    },
    {
        "title": "تعرّف على مدربينا الجدد",
        "summary": "انضمّ إلى الفريق مدربان في التدفق البطيء والاستعادة العصبية.",
        "body": (
            "رحبوا معنا بزين وريم؛ حصصهما مُدرَجة في الجدول بلون مميز في الواجهة قريبًا. "
            "جلسة تعارف مجانية لمدة ٣٠ دقيقة يوم الأربعاء القادم للمهتمين."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-05/960/540",
        "gallery": [
            "https://picsum.photos/seed/maestro-news-05a/640/400",
            "https://picsum.photos/seed/maestro-news-05b/640/400",
        ],
        "pinned": False,
    },
    {
        "title": "خصومات باقات الربيع لفترة محدودة",
        "summary": "خصم ١٥٪ على الاشتراك الشهري والسنوي حتى نفاد العدد.",
        "body": (
            "العرض ساري للتسجيل عبر الموقع حتى ٣٠ أبريل أو حتى ٤٠ اشتراكًا، أيهما أسبق. "
            "لا يجمع مع عروض أخرى. التفاصيل في قسم الخطط في الصفحة العامة."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-06/960/540",
        "gallery": ["https://picsum.photos/seed/maestro-news-06a/640/400"],
        "pinned": False,
    },
    {
        "title": "تقرير الرضا: شكرًا لملاحظاتكم",
        "summary": "لخصّنا آراءكم من الاستبيان الأخير وخططنا تحسينات على الجدول والإضاءة.",
        "body": (
            "أبرز الطلبات: أوقات ظهر إضافية، وإضاءة أخف في قاعة التأمل. "
            "نعمل على تعديل الجدول تدريجيًا وسنُعلن التحديثات هنا. "
            "استبيان قصير جديد خلال شهرين — مشاركتكم تصنع الفرق."
        ),
        "cover": "https://picsum.photos/seed/maestro-news-07/960/540",
        "gallery": [
            "https://picsum.photos/seed/maestro-news-07a/640/400",
            "https://picsum.photos/seed/maestro-news-07b/640/400",
        ],
        "pinned": False,
    },
]


def ensure_demo_news_posts(db: Session, center_id: int) -> None:
    """يضيف سبعة أخبارًا منشورة بصور من الإنترنت إذا لم تُنشأ مسبقًا (حسب العنوان)."""
    titles = [p["title"] for p in DEMO_NEWS_POSTS]
    existing = {
        r.title
        for r in db.query(models.CenterPost)
        .filter(
            models.CenterPost.center_id == center_id,
            models.CenterPost.title.in_(titles),
        )
        .all()
    }
    now = utcnow_naive()
    any_added = False
    for spec in DEMO_NEWS_POSTS:
        if spec["title"] in existing:
            continue
        any_added = True
        if spec.get("pinned"):
            db.query(models.CenterPost).filter(models.CenterPost.center_id == center_id).update(
                {models.CenterPost.is_pinned: False}
            )
        post = models.CenterPost(
            center_id=center_id,
            post_type="news",
            title=spec["title"],
            summary=spec["summary"],
            body=spec["body"],
            cover_image_url=spec["cover"],
            is_published=True,
            is_pinned=bool(spec.get("pinned")),
            published_at=now,
            updated_at=now,
        )
        db.add(post)
        db.flush()
        for i, url in enumerate(spec.get("gallery") or [], start=1):
            db.add(
                models.CenterPostImage(
                    post_id=post.id,
                    image_url=url,
                    sort_order=i,
                )
            )
    if any_added:
        db.commit()
