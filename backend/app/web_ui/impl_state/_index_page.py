"""Public index SEO strings and nested index page JSON config merge/build."""

from __future__ import annotations

import copy
import json
from typing import Any

from ... import models


def _index_seo_title(center: models.Center) -> str:
    tag = (center.brand_tagline or "").strip()
    if tag:
        if len(tag) > 52:
            tag = tag[:51].rstrip() + "…"
        return f"{center.name} — {tag} | Maestro Yoga"
    return f"حجز جلسات يوغا — {center.name} | Maestro Yoga"


def _index_meta_description(center: models.Center, session_count: int, plan_count: int) -> str:
    parts: list[str] = []
    t = (center.brand_tagline or "").strip()
    if t:
        parts.append(t + "،")
    city = (center.city or "").strip()
    core = f"احجز جلسات يوغا أو اشتراكًا في {center.name}"
    if city:
        core += f" ({city})"
    parts.append(core + ". دفع إلكتروني آمن، وتصفية الجلسات بالمستوى والسعر.")
    if session_count > 0:
        parts.append(f"يعرض الموقع {session_count} جلسة للحجز.")
    elif plan_count > 0:
        parts.append("تصفّح باقات الاشتراك المتاحة.")
    out = " ".join(parts)
    return out if len(out) <= 320 else out[:319].rstrip() + "…"


def _default_index_page_config() -> dict[str, Any]:
    return {
        "trust_bar": {
            "show": True,
            "payment_text": "دفع إلكتروني آمن",
            "trainers_text": "مدربون بمستويات واضحة",
            "show_session_count": True,
            "show_city": True,
            "refund_link_text": "سياسة الإلغاء والاسترداد",
        },
        "hero_chips": {
            "show": True,
            "c1": "جلسات يومية",
            "c2": "مدربون محترفون",
            "c3": "دفع إلكتروني آمن",
        },
        "product_clarity": {
            "show": False,
            "dropin_title": "جلسة بالحصة (دروب إن)",
            "dropin_body": "ادفع ثمن جلسة واحدة واختر الموعد من الجدول أدناه — مناسب للتجربة أو المرونة.",
            "plan_title": "اشتراك أسبوعي أو شهري أو سنوي",
            "plan_body": (
                'وفّر التكلفة عند الالتزام بمجموعة جلسات ضمن باقة من قسم '
                '<a href="#plans-section">مقارنة الاشتراكات</a> في العمود الجانبي.'
            ),
            "note": (
                'في كل طلب يمكن إضافة <strong>إما جلسات فقط أو خطة اشتراك واحدة</strong> '
                "— لا يُدمج النوعان في دفعة واحدة."
            ),
        },
        "team_strip": {
            "show": False,
            "text": "جلسات لمستويات <strong>مبتدئ ومتوسط ومتقدم</strong> — يحدد المدرب والجدول ما يناسبك عند الحجز.",
        },
        "services_block": {
            "show": True,
            "title": "خدماتنا",
            "intro": "نقدّم في مركزنا مجموعة من الخدمات لتناسب احتياجاتك.",
            "items": [
                {
                    "title": "جلسات يوغا جماعية",
                    "body": "جلسات بمستويات متعددة مع مدربين معتمدين.",
                },
                {
                    "title": "حصص خاصة",
                    "body": "تدريب فردي أو لمجموعات صغيرة حسب الطلب.",
                },
                {
                    "title": "ورش وبرامج خاصة",
                    "body": "فعاليات وورش دورية — تابع الجدول والإعلانات في المركز.",
                },
            ],
        },
        "loyalty_block": {
            "show": True,
            "title": "برنامج المكافآت والولاء",
            "lead": (
                "اجمع <strong>جلساتاً مؤكدة</strong> في هذا المركز (بعد إتمام الحجز والدفع) لتنتقل بين مستويات "
                "الأوسمة والمكافآت. يحدّد المركز نصوص المكافآت من لوحة الإدارة."
            ),
        },
        "news_ticker": {"show": True},
        "steps": {
            "show": True,
            "s1": "اختر الجلسة أو الخطة المناسبة.",
            "s2": "سجّل الدخول وفعّل بريدك الإلكتروني.",
            "s3": "راجع السلة وأكمل الطلب منها.",
        },
        "plans_section": {
            "show": True,
            "heading": "مقارنة الاشتراكات (أسبوعي / شهري / سنوي)",
        },
        "testimonials": {
            "show": True,
            "t1": '"تجربة ممتازة وتنظيم احترافي للجلسات." <span class="small">— سارة</span>',
            "t2": '"الاشتراك الشهري ساعدني على الالتزام بالرياضة." <span class="small">— نورة</span>',
            "t3": '"الدفع والحجز سهل جدًا من الجوال." <span class="small">— ريم</span>',
        },
        "faq_section": {"show": True, "heading": "أسئلة شائعة"},
        "refund": {
            "show": True,
            "title": "الإلغاء والاسترداد",
            "p1": (
                "تفاصيل إلغاء الحجز أو الاشتراك واسترداد المبالغ تُحدّدها <strong>إدارة {name}</strong> "
                "وفق سياسة المركز وسياسة مزوّد الدفع. راجع الشروط مع المركز عند الحاجة."
            ),
            "p2": (
                "عند إلغاء عملية دفع إلكتروني من بوابة الدفع يمكنك إعادة المحاولة من السلة. "
                "لأي استفسار تواصل مباشرة مع المركز قبل أو بعد الحجز."
            ),
        },
    }


def _deep_merge_index_defaults(defaults: dict[str, Any], saved: Any) -> dict[str, Any]:
    if not isinstance(saved, dict):
        return copy.deepcopy(defaults)
    out: dict[str, Any] = copy.deepcopy(defaults)
    for k, v in saved.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_index_defaults(out[k], v)
        elif k in out:
            out[k] = v
    return out


def merge_index_page_config(center: models.Center) -> dict[str, Any]:
    defaults = _default_index_page_config()
    raw = (getattr(center, "index_config_json", None) or "").strip()
    if not raw:
        return defaults
    try:
        saved = json.loads(raw)
    except json.JSONDecodeError:
        return defaults
    return _deep_merge_index_defaults(defaults, saved)


def _form_str_index(form_data: Any, key: str, max_len: int) -> str:
    v = form_data.get(key)
    if v is None:
        return ""
    if hasattr(v, "read"):
        return ""
    s = str(v).strip()
    return s[:max_len]


def _services_items_from_form(form_data: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for i in range(1, 7):
        title = _form_str_index(form_data, f"svc_{i}_title", 120)
        body = _form_str_index(form_data, f"svc_{i}_body", 500)
        if title or body:
            items.append({"title": title or "خدمة", "body": body})
    return items


def _form_bool01(form_data: Any, key: str, default: bool = True) -> bool:
    v = form_data.get(key)
    if v is None:
        return default
    if hasattr(v, "read"):
        return default
    s = str(v).strip().lower()
    if s in ("0", "false", "off", "no", ""):
        return False
    if s in ("1", "true", "on", "yes"):
        return True
    return default


def _index_config_build_from_form(form_data: Any) -> dict[str, Any]:
    """Build nested config dict from POST fields (see admin form names)."""
    return {
        "trust_bar": {
            "show": _form_bool01(form_data, "trust_show", True),
            "payment_text": _form_str_index(form_data, "trust_payment_text", 160),
            "trainers_text": _form_str_index(form_data, "trust_trainers_text", 160),
            "show_session_count": _form_bool01(form_data, "trust_show_session_count", True),
            "show_city": _form_bool01(form_data, "trust_show_city", True),
            "refund_link_text": _form_str_index(form_data, "trust_refund_link_text", 120),
        },
        "hero_chips": {
            "show": _form_bool01(form_data, "hero_chips_show", True),
            "c1": _form_str_index(form_data, "hero_c1", 80),
            "c2": _form_str_index(form_data, "hero_c2", 80),
            "c3": _form_str_index(form_data, "hero_c3", 80),
        },
        "product_clarity": {
            "show": _form_bool01(form_data, "pc_show", False),
            "dropin_title": _form_str_index(form_data, "pc_dropin_title", 120),
            "dropin_body": _form_str_index(form_data, "pc_dropin_body", 600),
            "plan_title": _form_str_index(form_data, "pc_plan_title", 120),
            "plan_body": _form_str_index(form_data, "pc_plan_body", 1200),
            "note": _form_str_index(form_data, "pc_note", 800),
        },
        "team_strip": {
            "show": _form_bool01(form_data, "team_show", False),
            "text": _form_str_index(form_data, "team_text", 600),
        },
        "services_block": {
            "show": _form_bool01(form_data, "services_show", True),
            "title": _form_str_index(form_data, "services_title", 120),
            "intro": _form_str_index(form_data, "services_intro", 600),
            "items": _services_items_from_form(form_data),
        },
        "loyalty_block": {
            "show": _form_bool01(form_data, "loyalty_block_show", True),
            "title": _form_str_index(form_data, "loyalty_block_title", 120),
            "lead": _form_str_index(form_data, "loyalty_block_lead", 1200),
        },
        "news_ticker": {"show": _form_bool01(form_data, "news_ticker_show", True)},
        "steps": {
            "show": _form_bool01(form_data, "steps_show", True),
            "s1": _form_str_index(form_data, "steps_s1", 220),
            "s2": _form_str_index(form_data, "steps_s2", 220),
            "s3": _form_str_index(form_data, "steps_s3", 220),
        },
        "plans_section": {
            "show": _form_bool01(form_data, "plans_section_show", True),
            "heading": _form_str_index(form_data, "plans_section_heading", 200),
        },
        "testimonials": {
            "show": _form_bool01(form_data, "testimonials_show", True),
            "t1": _form_str_index(form_data, "tm1", 400),
            "t2": _form_str_index(form_data, "tm2", 400),
            "t3": _form_str_index(form_data, "tm3", 400),
        },
        "faq_section": {
            "show": _form_bool01(form_data, "faq_section_show", True),
            "heading": _form_str_index(form_data, "faq_section_heading", 120),
        },
        "refund": {
            "show": _form_bool01(form_data, "refund_show", True),
            "title": _form_str_index(form_data, "refund_title", 120),
            "p1": _form_str_index(form_data, "refund_p1", 2000),
            "p2": _form_str_index(form_data, "refund_p2", 2000),
        },
    }


def _index_refund_p1_rendered(p1_template: str, center_name: str) -> str:
    t = (p1_template or "").strip()
    if not t:
        return ""
    name = (center_name or "").strip() or "المركز"
    return t.replace("{name}", name)
