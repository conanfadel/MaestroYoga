"""Stable permission ids and catalog rows for UI / RBAC."""

from __future__ import annotations

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
