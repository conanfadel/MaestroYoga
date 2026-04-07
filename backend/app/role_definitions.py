"""
تعريفات أدوار فريق المركز والصلاحيات المرجعية (للعرض في لوحة المالك ولفحص RBAC).

ملاحظة: القيم المخزّنة في users.role هي مفاتيح إنجليزية ثابتة؛ العناوين العربية للواجهة فقط.
"""

from __future__ import annotations

import json
from typing import Any

# --- الصلاحيات (معرّفات مستقرة للكود) ---
PERMISSION_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "center.settings.view",
        "label": "عرض إعدادات المركز",
        "group": "المركز والإعدادات",
    },
    {
        "id": "center.settings.edit",
        "label": "تعديل هوية المركز والغلاف والإعدادات العامة",
        "group": "المركز والإعدادات",
    },
    {
        "id": "billing.manage",
        "label": "إدارة الفوترة والربط المالي الحساس",
        "group": "المركز والإعدادات",
    },
    {
        "id": "integrations.manage",
        "label": "إدارة التكاملات الخارجية",
        "group": "المركز والإعدادات",
    },
    {
        "id": "content.index",
        "label": "تعديل محتوى صفحة الحجز العامة",
        "group": "المحتوى العام",
    },
    {
        "id": "content.posts",
        "label": "أخبار ومنشورات المركز",
        "group": "المحتوى العام",
    },
    {
        "id": "content.faq",
        "label": "الأسئلة الشائعة",
        "group": "المحتوى العام",
    },
    {
        "id": "rooms.manage",
        "label": "إدارة الغرف والسعة",
        "group": "التشغيل",
    },
    {
        "id": "sessions.manage",
        "label": "إدارة الجلسات والجدولة",
        "group": "التشغيل",
    },
    {
        "id": "plans.manage",
        "label": "خطط الاشتراك والأسعار",
        "group": "التشغيل",
    },
    {
        "id": "clients.manage",
        "label": "عملاء المركز (CRM) وواجهة API",
        "group": "العملاء والولاء",
    },
    {
        "id": "loyalty.manage",
        "label": "برنامج الولاء والعتبات",
        "group": "العملاء والولاء",
    },
    {
        "id": "public_users.manage",
        "label": "مستخدمو صفحة الحجز العامة",
        "group": "العملاء والولاء",
    },
    {
        "id": "payments.records",
        "label": "عرض سجلات المدفوعات والعمليات",
        "group": "المالية والتقارير",
    },
    {
        "id": "payments.refund",
        "label": "استرداد أو تعديل مالي حساس",
        "group": "المالية والتقارير",
    },
    {
        "id": "exports.clients",
        "label": "تصدير ملف العملاء (CSV)",
        "group": "المالية والتقارير",
    },
    {
        "id": "exports.bookings",
        "label": "تصدير الحجوزات (CSV)",
        "group": "المالية والتقارير",
    },
    {
        "id": "exports.payments",
        "label": "تصدير المدفوعات (CSV)",
        "group": "المالية والتقارير",
    },
    {
        "id": "reports.operational",
        "label": "تقارير تشغيلية ومؤشرات عامة",
        "group": "المالية والتقارير",
    },
    {
        "id": "reports.financial",
        "label": "تقارير مالية وإيرادات تفصيلية",
        "group": "المالية والتقارير",
    },
    {
        "id": "security.audit",
        "label": "سجل الأمان والتدقيق وحظر العناوين",
        "group": "الأمان والفريق",
    },
    {
        "id": "staff.invite",
        "label": "دعوة أعضاء فريق جدد (حسابات لوحة التحكم)",
        "group": "الأمان والفريق",
    },
    {
        "id": "staff.manage_roles",
        "label": "تعيين الأدوار والصلاحيات للفريق",
        "group": "الأمان والفريق",
    },
    {
        "id": "dashboard.view",
        "label": "لوحة المؤشرات والتنبيهات التشغيلية",
        "group": "المالية والتقارير",
    },
    {
        "id": "dashboard.financial",
        "label": "مؤشرات إيراد ومدفوعات في لوحة التحكم",
        "group": "المالية والتقارير",
    },
    {
        "id": "support.tools",
        "label": "أدوات دعم محدودة (قراءة/مساعدة)",
        "group": "الأمان والفريق",
    },
)

PERMISSION_IDS: tuple[str, ...] = tuple(p["id"] for p in PERMISSION_CATALOG)
ALL_PERMISSION_KEYS: frozenset[str] = frozenset(PERMISSION_IDS)

# --- أنواع المستخدمين (الدور المخزن في users.role) ---
STAFF_ROLE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "center_owner",
        "label": "مالك المركز",
        "description": "صلاحيات كاملة على مركزه، بما فيها الأمان وإدارة أدوار الفريق.",
        "optional": False,
    },
    {
        "id": "center_staff",
        "label": "موظف عام (قديم)",
        "description": "صلاحيات تشغيل واسعة كالسابق؛ لا يدير أدوار الفريق الآخرين.",
        "optional": False,
    },
    {
        "id": "operations_manager",
        "label": "مدير تشغيل",
        "description": "جلسات، حجوزات، عملاء، تقارير تشغيلية؛ بدون إدارة أدوار الفريق أو أعلى صلاحيات الأمان.",
        "optional": False,
    },
    {
        "id": "session_coordinator",
        "label": "منسق جلسات",
        "description": "الجدولة، الغرف، الجلسات، الخطط؛ محدود المحتوى العام ومستخدمي الموقع.",
        "optional": False,
    },
    {
        "id": "reception",
        "label": "استقبال / حجوزات",
        "description": "الجلسات، الحجوزات، مستخدمو الموقع، الولاء؛ بدون تعديل الغرف أو المحتوى التسويقي.",
        "optional": False,
    },
    {
        "id": "content_marketing",
        "label": "محتوى / تسويق",
        "description": "هوية الموقع، صفحة الحجز، الأخبار، الأسئلة؛ بدون بيانات مالية تفصيلية أو تشغيل كامل.",
        "optional": False,
    },
    {
        "id": "support_limited",
        "label": "دعم فني (محدود)",
        "description": "مساعدة المستخدمين وقراءة محدودة؛ بدون تعديل إعدادات حساسة أو مالية.",
        "optional": True,
    },
    {
        "id": "accountant",
        "label": "محاسب / مالية",
        "description": "التقارير المالية، التصدير، المدفوعات؛ بدون تعديل الجدول أو المحتوى.",
        "optional": True,
    },
    {
        "id": "trainer",
        "label": "مدرب",
        "description": "نشر جلساته والغرف المرتبطة بالتشغيل؛ لا يدير مستخدمي الموقع أو المحتوى العام.",
        "optional": False,
    },
    {
        "id": "custom_staff",
        "label": "جديد — دور مخصّص بالصلاحيات",
        "description": "يحدد المالك اسماً عربياً ومجموعة صلاحيات من القائمة.",
        "optional": False,
    },
)

STAFF_ROLE_IDS: frozenset[str] = frozenset(r["id"] for r in STAFF_ROLE_CATALOG)

# نصوص تظهر في لوحة «إضافة عضو فريق» عند اختيار دور جاهز (أقسام لوحة الإدارة المعنيّة)
STAFF_ROLE_UI_SECTIONS_HINT: dict[str, str] = {
    "center_staff": (
        "يصل تقريباً إلى كل أقسام لوحة الإدارة لهذا المركز: لوحة المؤشرات، الهوية وصفحة الحجز، "
        "الغرف والجلسات والخطط، العملاء والولاء والمستخدمون العامّون، المدفوعات والتصدير، الأمان والفريق — "
        "ما عدا تعيين أدوار الفريق الآخرين."
    ),
    "operations_manager": (
        "صلاحياته تغطي: لوحة المؤشرات والتنبيهات، إعدادات المركز (عرض)، الغرف والجلسات وخطط الاشتراك، "
        "عملاء المركز وبرنامج الولاء، عرض سجلات المدفوعات والتقارير التشغيلية وتصدير الحجوزات/العملاء. "
        "لا يصل إلى: دعوة أعضاء فريق جدد، سجل الأمان وحظر العناوين، أو إدارة أدوار الفريق."
    ),
    "session_coordinator": (
        "يركّز على: لوحة المؤشرات، الغرف والجلسات والخطط، العملاء والولاء، عرض المدفوعات والتصدير التشغيلي، "
        "وعرض إعدادات المركز. لا يدير مستخدمي الموقع العامّين بالكامل كقسم الاستقبال، ولا المحتوى التسويقي الكامل."
    ),
    "reception": (
        "صلاحياته في: لوحة المؤشرات، الجلسات والخطط، العملاء والولاء، مستخدمو صفحة الحجز العامة، عرض المدفوعات. "
        "لا يعدّل الغرف ولا المحتوى العام (هوية/صفحة حجز/أخبار) بشكل كامل كدور المحتوى."
    ),
    "content_marketing": (
        "صلاحياته في: لوحة المؤشرات (محدودة)، الهوية وإعدادات المركز الظاهرة، تعديل محتوى صفحة الحجز، "
        "أخبار ومنشورات المركز، والأسئلة الشائعة. لا يصل إلى إدارة الجلسات والغرف التشغيلية الكاملة "
        "ولا التقارير المالية التفصيلية ولا الأمان."
    ),
    "support_limited": (
        "دور مساعد: لوحة المؤشرات، مساعدة مستخدمي الموقع، أدوات دعم محدودة، عرض سجلات المدفوعات (قراءة). "
        "لا يغيّر الجدول ولا الإعدادات الحساسة."
    ),
    "accountant": (
        "صلاحياته في: المؤشرات المالية، التقارير والتصدير، المدفوعات والاسترداد، خطط الاشتراك (للأسعار المرتبطة بالمالية)، "
        "وعرض إعدادات المركز. لا يدير الجلسات اليومية ولا محتوى الموقع التسويقي."
    ),
    "trainer": (
        "واجهة مدرب: لوحة مبسّطة تركّز على الغرف والجلسات ذات الصلة، مع مؤشرات تشغيلية وعرض مدفوعات محدود. "
        "لا يدير مستخدمي الموقع العامّين ولا المحتوى العام للمركز."
    ),
}

# صلاحيات يمكن للمالك تضمينها في «دور مخصّص» (يُستبعد إسناد إدارة أدوار الفريق)
CUSTOM_STAFF_ALLOWED_PERMISSIONS: frozenset[str] = ALL_PERMISSION_KEYS - frozenset({"staff.manage_roles"})

# أدوار يمكن للمالك إنشاؤها عبر API (لا يُنشئ مالكاً آخر عبر هذا المسار)
ASSIGNABLE_BY_CENTER_OWNER: frozenset[str] = frozenset(
    {
        "center_staff",
        "operations_manager",
        "session_coordinator",
        "reception",
        "content_marketing",
        "support_limited",
        "accountant",
        "trainer",
        "custom_staff",
    }
)

# أدوار يمكنها تسجيل الدخول إلى /admin (لوحة مركز)
CENTER_ADMIN_LOGIN_ROLES: frozenset[str] = frozenset(
    {
        "center_owner",
        "center_staff",
        "operations_manager",
        "session_coordinator",
        "reception",
        "content_marketing",
        "support_limited",
        "accountant",
        "trainer",
        "custom_staff",
    }
)

# ربط الدور → صلاحيات (المصدر الوحيد لـ RBAC)
_ROLE_PERMISSIONS_RAW: dict[str, frozenset[str]] = {
    "center_owner": ALL_PERMISSION_KEYS,
    "center_staff": ALL_PERMISSION_KEYS - {"staff.manage_roles"},
    "operations_manager": ALL_PERMISSION_KEYS - {"staff.manage_roles"},
    "session_coordinator": frozenset(
        {
            "dashboard.view",
            "dashboard.financial",
            "reports.operational",
            "rooms.manage",
            "sessions.manage",
            "plans.manage",
            "clients.manage",
            "loyalty.manage",
            "payments.records",
            "exports.bookings",
            "exports.clients",
            "center.settings.view",
        }
    ),
    "reception": frozenset(
        {
            "dashboard.view",
            "dashboard.financial",
            "reports.operational",
            "sessions.manage",
            "plans.manage",
            "clients.manage",
            "loyalty.manage",
            "public_users.manage",
            "payments.records",
            "exports.bookings",
            "center.settings.view",
        }
    ),
    "content_marketing": frozenset(
        {
            "dashboard.view",
            "reports.operational",
            "center.settings.view",
            "center.settings.edit",
            "content.index",
            "content.posts",
            "content.faq",
        }
    ),
    "support_limited": frozenset(
        {
            "dashboard.view",
            "reports.operational",
            "public_users.manage",
            "support.tools",
            "payments.records",
            "center.settings.view",
        }
    ),
    "accountant": frozenset(
        {
            "dashboard.view",
            "dashboard.financial",
            "reports.operational",
            "reports.financial",
            "payments.records",
            "payments.refund",
            "exports.clients",
            "exports.bookings",
            "exports.payments",
            "plans.manage",
            "center.settings.view",
        }
    ),
    "trainer": frozenset(
        {
            "dashboard.view",
            "dashboard.financial",
            "reports.operational",
            "rooms.manage",
            "sessions.manage",
            "payments.records",
        }
    ),
    # الصلاحيات الفعلية تُخزَّن في users.permissions_json
    "custom_staff": frozenset(),
}


def permissions_for_role(role: str | None) -> frozenset[str]:
    if not role:
        return frozenset()
    return _ROLE_PERMISSIONS_RAW.get(role, frozenset())


def custom_permissions_from_json(raw: str | None) -> frozenset[str]:
    """صلاحيات مستخدم بدور custom_staff من عمود JSON."""
    if not raw or not str(raw).strip():
        return frozenset()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(x for x in data if isinstance(x, str) and x in CUSTOM_STAFF_ALLOWED_PERMISSIONS)


def permission_catalog_grouped_for_custom_staff() -> list[dict[str, Any]]:
    """مجموعات الصلاحيات لعرض خانات الاختيار عند إنشاء دور مخصّص."""
    by: dict[str, list[dict[str, str]]] = {}
    for p in PERMISSION_CATALOG:
        pid = p["id"]
        if pid not in CUSTOM_STAFF_ALLOWED_PERMISSIONS:
            continue
        g = p["group"]
        by.setdefault(g, []).append({"id": pid, "label": p["label"]})
    return [{"group": g, "perms": by[g]} for g in sorted(by.keys())]


def handbook_matrix_rows() -> list[dict[str, Any]]:
    """صفوف جدول المرجعية: كل دور مع خلايا ✓/— لكل صلاحية بالترتيب."""
    perm_ids = [p["id"] for p in PERMISSION_CATALOG]
    rows: list[dict[str, Any]] = []
    for role in STAFF_ROLE_CATALOG:
        rid = role["id"]
        granted = permissions_for_role(rid)
        rows.append(
            {
                "role_id": rid,
                "role_label": role["label"],
                "role_description": role["description"],
                "optional": bool(role.get("optional")),
                "cells": [pid in granted for pid in perm_ids],
            }
        )
    return rows
