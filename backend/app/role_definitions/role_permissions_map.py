"""Role → default permission set (RBAC source for built-in roles)."""

from __future__ import annotations

from .permissions_catalog import ALL_PERMISSION_KEYS

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
