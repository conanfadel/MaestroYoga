"""Shared web UI state: templates, constants, and helper functions (no HTTP routes)."""

from __future__ import annotations

from ._bindings import *
from ._constants import *
from ._files_center import (
    _clear_center_branding_urls_if_files_missing,
    _delete_center_post_disk_files,
    _parse_center_post_gallery_remote_urls,
    _resolved_path_under_static,
    _sanitize_center_post_remote_image_url,
    _unlink_center_uploads,
    _unlink_static_url_file,
)
from ._guards_redirects import (
    _active_block_for_ip,
    _admin_login_redirect,
    _admin_redirect,
    _admin_user_from_request,
    _current_public_user,
    _get_public_user_or_redirect,
    _is_ip_blocked,
    _parse_optional_date_str,
    _public_login_redirect,
    _request_key,
    _require_admin_user_or_redirect,
    _sanitize_admin_return_section,
    _security_owner_forbidden_redirect,
    _trainer_forbidden_redirect,
)
from ._index_page import (
    _deep_merge_index_defaults,
    _default_index_page_config,
    _form_bool01,
    _form_str_index,
    _index_config_build_from_form,
    _index_meta_description,
    _index_refund_p1_rendered,
    _index_seo_title,
    merge_index_page_config,
)
from ._paths import (
    APP_STATIC_ROOT,
    BACKEND_ROOT,
    CENTER_LOGO_UPLOAD_DIR,
    CENTER_POST_UPLOAD_DIR,
    TEMPLATES_DIR,
)
from ._public_users_ops import (
    _analytics_context,
    _apply_public_user_bulk_action,
    _ensure_client_for_public_register,
    _public_users_query_for_center,
    _soft_delete_public_user,
    _spots_available_map,
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["PUBLIC_INDEX_DEFAULT_PATH"] = PUBLIC_INDEX_DEFAULT_PATH
