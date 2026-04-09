"""Shared web UI state: templates, constants, and helper functions (no HTTP routes)."""

from __future__ import annotations

import copy
import csv
import io
import json
from html import escape as html_escape
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from pydantic import ValidationError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, case, desc, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ... import models, schemas
from ...rbac import admin_ui_flags, user_has_permission
from ...role_definitions import (
    ASSIGNABLE_BY_CENTER_OWNER,
    CENTER_ADMIN_LOGIN_ROLES,
    PERMISSION_CATALOG,
    STAFF_ROLE_CATALOG,
    STAFF_ROLE_UI_SECTIONS_HINT,
    handbook_matrix_rows,
    permission_catalog_grouped_for_custom_staff,
)
from ...booking_utils import ACTIVE_BOOKING_STATUSES, count_active_bookings, spots_available
from ...bootstrap import DEMO_CENTER_NAME, ensure_demo_data, ensure_demo_news_posts, should_auto_seed_demo_data
from ...admin_report_helpers import (
    build_subscription_report_rows,
    can_access_report_kind,
    effective_vat_percent_for_center,
    parse_optional_non_negative_float,
    parse_optional_non_negative_int,
    payment_method_label_ar,
    report_period_to_range,
    report_previous_period_range,
    user_can_report_revenue,
    user_can_report_sessions,
    user_can_report_health,
    utf8_bom_csv_content,
    vat_inclusive_breakdown,
)
from ...admin_export_helpers import (
    admin_user_for_export_permission,
    build_bookings_csv_content,
    build_payments_csv_content,
    build_security_events_filtered_query,
    build_security_events_csv_content,
    clients_new_returning_for_range,
)
from ...public_center_helpers import get_center_or_404, get_seeded_center_or_404, resolve_public_center_or_404
from ...database import get_db, is_sqlite
from ...loyalty import (
    LOYALTY_REWARD_MAX_LEN,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_thresholds,
    validate_loyalty_threshold_triple,
)
from ...mailer import (
    feedback_destination_email,
    queue_account_delete_confirmation_email,
    queue_password_reset_email,
    send_mail_with_attachments,
    validate_mailer_settings,
)
from ...payments import get_payment_provider, payment_provider_supports_hosted_checkout
from ...public_account_helpers import build_account_delete_confirm_url, public_account_phone_prefill
from ...public_auth_helpers import (
    build_reset_url,
    build_verify_url,
    public_user_from_verify_flash_token,
    queue_verify_email_for_user,
)
from ...public_auth_flow_helpers import (
    is_public_account_delete_request_rate_limited,
    is_public_forgot_password_rate_limited,
    is_public_resend_verification_rate_limited,
    is_public_reset_password_rate_limited,
    reset_password_validation_error,
    resolve_public_account_delete_confirmation,
    resolve_public_email_verification,
    sanitize_public_token,
)
from ...public_cart_helpers import (
    create_pending_single_booking_payment,
    build_cart_booking_bundle,
    parse_cart_session_ids,
    process_hosted_cart_checkout,
    process_hosted_single_booking_checkout,
    process_mock_single_booking_checkout,
    process_mock_cart_checkout,
)
from ...public_client_helpers import get_or_sync_public_client
from ...public_content_version import compute_public_center_content_version
from ...public_feedback_helpers import (
    feedback_send_result_message,
    is_valid_feedback_contact_name,
    is_valid_feedback_email,
    is_valid_feedback_message,
    prepare_feedback_submission,
)
from ...public_news_helpers import (
    apply_public_news_filters_and_sort,
    build_public_news_index_meta,
    build_public_news_filter_options,
    build_public_news_list_rows,
    build_public_posts_blocks,
    index_preconnect_origins,
    preview_text,
)
from ...public_index_data_helpers import build_public_index_template_context, load_public_index_data
from ...public_loyalty_helpers import build_public_loyalty_context
from ...public_plan_helpers import build_public_plan_rows, default_plan_labels
from ...public_redirect_helpers import (
    redirect_public_index_paid_mock,
    redirect_public_index_with_msg,
    redirect_public_index_with_params,
)
from ...public_register_helpers import (
    build_post_login_redirect_url,
    build_post_register_redirect_url,
    is_public_login_rate_limited,
    is_public_register_rate_limited,
    set_public_auth_cookie,
    upsert_public_user_for_register,
)
from ...public_sessions_helpers import build_public_session_rows
from ...public_subscribe_helpers import (
    create_pending_subscription_payment,
    get_active_center_plan_or_404,
    process_hosted_subscription_checkout,
    process_mock_subscription_checkout,
)
from ...rate_limiter import rate_limiter
from ...request_ip import get_client_ip
from ...security_audit import log_security_event
from ...security import (
    create_access_token,
    create_public_access_token,
    create_public_email_verify_flash_token,
    decode_public_account_delete_token,
    decode_public_email_verification_token,
    decode_public_password_reset_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
    hash_password,
    require_permissions_cookie_or_bearer,
    verify_password,
)
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import (
    _cookie_secure_flag,
    _fmt_dt,
    _is_email_verification_required,
    _is_strong_public_password,
    _is_truthy_env,
    _normalize_phone_with_country,
    _phone_admin_display,
    _plan_duration_days,
    _public_base,
    _sanitize_next_url,
    PUBLIC_INDEX_DEFAULT_PATH,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
    _url_with_params,
)

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
