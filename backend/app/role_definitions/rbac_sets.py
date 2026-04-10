"""Frozensets: assignable roles, login roles, custom-staff permission allow-list."""

from __future__ import annotations

from .permissions_catalog import ALL_PERMISSION_KEYS

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
