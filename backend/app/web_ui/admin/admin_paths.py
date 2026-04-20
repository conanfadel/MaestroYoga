"""Base URL paths for split admin UI (accordion sections live on different list pages)."""

from __future__ import annotations

ADMIN_PATH_DASHBOARD = "/admin/dashboard"
ADMIN_PATH_USERS = "/admin/users"
ADMIN_PATH_TRAINING = "/admin/training"
ADMIN_PATH_SETTINGS = "/admin/settings"

ADMIN_DEFAULT_HOME = ADMIN_PATH_DASHBOARD

# Accordion id -> GET base path (hash added by templates / redirects)
ADMIN_SECTION_BASE_PATHS: dict[str, str] = {
    "section-branding": ADMIN_PATH_SETTINGS,
    "section-index-page": ADMIN_PATH_SETTINGS,
    "section-center-posts": ADMIN_PATH_SETTINGS,
    "section-faq": ADMIN_PATH_SETTINGS,
    "section-staff-invite": ADMIN_PATH_SETTINGS,
    "section-staff-roles": ADMIN_PATH_SETTINGS,
    # Backward-compatible alias: loyalty lives under users section UI.
    "section-loyalty": ADMIN_PATH_USERS,
    "section-rooms": ADMIN_PATH_DASHBOARD,
    "section-plans": ADMIN_PATH_DASHBOARD,
    "section-sessions": ADMIN_PATH_DASHBOARD,
    "section-reports": ADMIN_PATH_DASHBOARD,
    "section-security": ADMIN_PATH_DASHBOARD,
    "section-public-users": ADMIN_PATH_USERS,
    "section-public-users-trash": ADMIN_PATH_USERS,
    "section-training-management": ADMIN_PATH_TRAINING,
}


def admin_base_path_for_return_section(section_id: str | None) -> str:
    sid = (section_id or "").strip()
    if not sid:
        return ADMIN_DEFAULT_HOME
    return ADMIN_SECTION_BASE_PATHS.get(sid, ADMIN_DEFAULT_HOME)


def admin_section_paths_for_template() -> dict[str, str]:
    return dict(ADMIN_SECTION_BASE_PATHS)
