"""RBAC: صلاحيات فعّالة حسب users.role."""

from __future__ import annotations

from . import models
from .role_definitions import (
    ALL_PERMISSION_KEYS,
    custom_permissions_from_json,
    permissions_for_role,
)


def permissions_for_user(user: models.User) -> frozenset[str]:
    if user.role == "center_owner":
        return ALL_PERMISSION_KEYS
    if user.role == "custom_staff":
        return custom_permissions_from_json(getattr(user, "permissions_json", None))
    return permissions_for_role(user.role)


def user_has_permission(user: models.User, permission_id: str) -> bool:
    return permission_id in permissions_for_user(user)


def user_has_all_permissions(user: models.User, permission_ids: tuple[str, ...]) -> bool:
    p = permissions_for_user(user)
    return all(x in p for x in permission_ids)


def user_has_any_permission(user: models.User, permission_ids: tuple[str, ...]) -> bool:
    if not permission_ids:
        return True
    p = permissions_for_user(user)
    return any(x in p for x in permission_ids)


def admin_ui_flags(user: models.User) -> dict[str, bool | str]:
    """مفاتيح جاهزة لقوالب لوحة الإدارة (admin_base وما يمتد منه)."""
    p = permissions_for_user(user)
    role = user.role or ""
    use_trainer_layout = role == "trainer"

    perm_site_cluster = any(
        x in p
        for x in (
            "center.settings.edit",
            "content.index",
            "content.posts",
            "content.faq",
        )
    )
    perm_ops_cluster = any(
        x in p for x in ("rooms.manage", "sessions.manage", "plans.manage", "payments.records", "reports.financial")
    )
    perm_clients_cluster = any(x in p for x in ("public_users.manage", "loyalty.manage", "clients.manage"))

    perm_reports_hub = not use_trainer_layout

    return {
        "use_trainer_layout": use_trainer_layout,
        "perm_site_cluster": perm_site_cluster,
        "perm_ops_cluster": perm_ops_cluster,
        "perm_clients_cluster": perm_clients_cluster,
        "perm_reports_hub": perm_reports_hub,
        "perm_training_management": ("sessions.manage" in p),
        "perm_dashboard": "dashboard.view" in p,
        "perm_dashboard_financial": "dashboard.financial" in p,
        "perm_reminder_card": "sessions.manage" in p or "public_users.manage" in p,
        "perm_branding": "center.settings.edit" in p,
        "perm_index": "content.index" in p,
        "perm_posts": "content.posts" in p,
        "perm_faq": "content.faq" in p,
        "perm_rooms_manage": "rooms.manage" in p,
        "perm_sessions_manage": "sessions.manage" in p,
        "perm_plans": "plans.manage" in p,
        "perm_loyalty": "loyalty.manage" in p,
        "perm_public_users": "public_users.manage" in p,
        "perm_security": "security.audit" in p,
        "perm_exports_clients": "exports.clients" in p,
        "perm_exports_bookings": "exports.bookings" in p,
        "perm_exports_payments": "exports.payments" in p,
        "perm_payments_section": ("payments.records" in p or "sessions.manage" in p or "reports.financial" in p),
        "show_admin_sessions_area": (
            ("sessions.manage" in p)
            or (role == "trainer")
            or (("payments.records" in p) and ("exports.payments" in p))
        ),
        "show_staff_roles_handbook": role == "center_owner",
        "show_security_section": "security.audit" in p,
        "is_center_owner": role == "center_owner",
        "staff_invite_perm": "staff.invite" in p,
    }
