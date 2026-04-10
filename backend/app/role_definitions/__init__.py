"""
تعريفات أدوار فريق المركز والصلاحيات المرجعية (للعرض في لوحة المالك ولفحص RBAC).

ملاحظة: القيم المخزّنة في users.role هي مفاتيح إنجليزية ثابتة؛ العناوين العربية للواجهة فقط.
"""

from __future__ import annotations

from .helpers import (
    custom_permissions_from_json,
    handbook_matrix_rows,
    permission_catalog_grouped_for_custom_staff,
)
from .permissions_catalog import ALL_PERMISSION_KEYS, PERMISSION_CATALOG, PERMISSION_IDS
from .rbac_sets import (
    ASSIGNABLE_BY_CENTER_OWNER,
    CENTER_ADMIN_LOGIN_ROLES,
    CUSTOM_STAFF_ALLOWED_PERMISSIONS,
)
from .role_permissions_map import permissions_for_role
from .staff_roles import STAFF_ROLE_CATALOG, STAFF_ROLE_IDS, STAFF_ROLE_UI_SECTIONS_HINT

__all__ = [
    "ALL_PERMISSION_KEYS",
    "ASSIGNABLE_BY_CENTER_OWNER",
    "CENTER_ADMIN_LOGIN_ROLES",
    "CUSTOM_STAFF_ALLOWED_PERMISSIONS",
    "PERMISSION_CATALOG",
    "PERMISSION_IDS",
    "STAFF_ROLE_CATALOG",
    "STAFF_ROLE_IDS",
    "STAFF_ROLE_UI_SECTIONS_HINT",
    "custom_permissions_from_json",
    "handbook_matrix_rows",
    "permission_catalog_grouped_for_custom_staff",
    "permissions_for_role",
]
