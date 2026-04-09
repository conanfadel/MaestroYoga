"""Shared web UI state: templates, constants, and helper functions (no HTTP routes)."""

import copy
import csv
import io
import json
from html import escape as html_escape
from collections import defaultdict
from datetime import date, datetime, timedelta
import os
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

from .. import models, schemas
from ..rbac import admin_ui_flags, user_has_permission
from ..role_definitions import (
    ASSIGNABLE_BY_CENTER_OWNER,
    CENTER_ADMIN_LOGIN_ROLES,
    PERMISSION_CATALOG,
    STAFF_ROLE_CATALOG,
    STAFF_ROLE_UI_SECTIONS_HINT,
    handbook_matrix_rows,
    permission_catalog_grouped_for_custom_staff,
)
from ..booking_utils import ACTIVE_BOOKING_STATUSES, count_active_bookings, spots_available
from ..bootstrap import DEMO_CENTER_NAME, ensure_demo_data, ensure_demo_news_posts, should_auto_seed_demo_data
from ..admin_report_helpers import (
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
from ..admin_export_helpers import (
    admin_user_for_export_permission,
    build_bookings_csv_content,
    build_payments_csv_content,
    build_security_events_filtered_query,
    build_security_events_csv_content,
    clients_new_returning_for_range,
)
from ..public_center_helpers import get_center_or_404, get_seeded_center_or_404, resolve_public_center_or_404
from ..database import get_db, is_sqlite
from ..loyalty import (
    LOYALTY_REWARD_MAX_LEN,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_thresholds,
    validate_loyalty_threshold_triple,
)
from ..mailer import (
    feedback_destination_email,
    queue_account_delete_confirmation_email,
    queue_password_reset_email,
    send_mail_with_attachments,
    validate_mailer_settings,
)
from ..payments import get_payment_provider, payment_provider_supports_hosted_checkout
from ..public_account_helpers import build_account_delete_confirm_url, public_account_phone_prefill
from ..public_auth_helpers import (
    build_reset_url,
    build_verify_url,
    public_user_from_verify_flash_token,
    queue_verify_email_for_user,
)
from ..public_auth_flow_helpers import (
    is_public_account_delete_request_rate_limited,
    is_public_forgot_password_rate_limited,
    is_public_resend_verification_rate_limited,
    is_public_reset_password_rate_limited,
    reset_password_validation_error,
    resolve_public_account_delete_confirmation,
    resolve_public_email_verification,
    sanitize_public_token,
)
from ..public_cart_helpers import (
    create_pending_single_booking_payment,
    build_cart_booking_bundle,
    parse_cart_session_ids,
    process_hosted_cart_checkout,
    process_hosted_single_booking_checkout,
    process_mock_single_booking_checkout,
    process_mock_cart_checkout,
)
from ..public_client_helpers import get_or_sync_public_client
from ..public_content_version import compute_public_center_content_version
from ..public_feedback_helpers import (
    feedback_send_result_message,
    is_valid_feedback_contact_name,
    is_valid_feedback_email,
    is_valid_feedback_message,
    prepare_feedback_submission,
)
from ..public_news_helpers import (
    apply_public_news_filters_and_sort,
    build_public_news_index_meta,
    build_public_news_filter_options,
    build_public_news_list_rows,
    build_public_posts_blocks,
    index_preconnect_origins,
    preview_text,
)
from ..public_index_data_helpers import build_public_index_template_context, load_public_index_data
from ..public_loyalty_helpers import build_public_loyalty_context
from ..public_plan_helpers import build_public_plan_rows, default_plan_labels
from ..public_redirect_helpers import (
    redirect_public_index_paid_mock,
    redirect_public_index_with_msg,
    redirect_public_index_with_params,
)
from ..public_register_helpers import (
    build_post_login_redirect_url,
    build_post_register_redirect_url,
    is_public_login_rate_limited,
    is_public_register_rate_limited,
    set_public_auth_cookie,
    upsert_public_user_for_register,
)
from ..public_sessions_helpers import build_public_session_rows
from ..public_subscribe_helpers import (
    create_pending_subscription_payment,
    get_active_center_plan_or_404,
    process_hosted_subscription_checkout,
    process_mock_subscription_checkout,
)
from ..rate_limiter import rate_limiter
from ..request_ip import get_client_ip
from ..security_audit import log_security_event
from ..security import (
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
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import (
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

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))
templates.env.globals["PUBLIC_INDEX_DEFAULT_PATH"] = PUBLIC_INDEX_DEFAULT_PATH

PUBLIC_COOKIE_NAME = "public_access_token"
MAX_LOCKOUT_SECONDS = int(os.getenv("RATE_LIMIT_MAX_LOCKOUT_SECONDS", "900"))
MAX_PUBLIC_CART_SESSIONS = int(os.getenv("MAX_PUBLIC_CART_SESSIONS", "8"))
GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "").strip()
PUBLIC_FEEDBACK_MAX_IMAGES = int(os.getenv("PUBLIC_FEEDBACK_MAX_IMAGES", "4"))
PUBLIC_FEEDBACK_MAX_IMAGE_BYTES = int(os.getenv("PUBLIC_FEEDBACK_MAX_IMAGE_BYTES", str(3 * 1024 * 1024)))
PUBLIC_FEEDBACK_ALLOWED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)
PUBLIC_FEEDBACK_CATEGORY_LABELS = {
    "problem": "مشكلة تقنية",
    "complaint": "شكوى",
    "suggestion": "اقتراح",
}

# Admin dashboard pagination tuning.
ADMIN_SESSIONS_PAGE_SIZE = 50
ADMIN_PUBLIC_USERS_PAGE_SIZE = 50
ADMIN_SECURITY_AUDIT_PAGE_SIZE = 50
ADMIN_PAYMENTS_PAGE_SIZE = 20
ADMIN_CENTER_POSTS_PAGE_SIZE = 20

# Admin security policy defaults.
ADMIN_IP_BLOCK_DEFAULT_MINUTES = 60
ADMIN_IP_BLOCK_MAX_MINUTES = 10080

# Admin query parameter keys.
ADMIN_QP_ROOM_SORT = "room_sort"
ADMIN_QP_PUBLIC_USER_Q = "public_user_q"
ADMIN_QP_PUBLIC_USER_STATUS = "public_user_status"
ADMIN_QP_PUBLIC_USER_VERIFIED = "public_user_verified"
ADMIN_QP_PUBLIC_USER_PAGE = "public_user_page"
ADMIN_QP_TRASH_PAGE = "trash_page"
ADMIN_QP_TRASH_Q = "trash_q"
ADMIN_QP_SESSIONS_PAGE = "sessions_page"
ADMIN_QP_PAYMENTS_PAGE = "payments_page"
ADMIN_QP_AUDIT_EVENT_TYPE = "audit_event_type"
ADMIN_QP_AUDIT_STATUS = "audit_status"
ADMIN_QP_AUDIT_EMAIL = "audit_email"
ADMIN_QP_AUDIT_IP = "audit_ip"
ADMIN_QP_AUDIT_PAGE = "audit_page"
ADMIN_QP_PAYMENT_DATE_FROM = "payment_date_from"
ADMIN_QP_PAYMENT_DATE_TO = "payment_date_to"
ADMIN_QP_POST_EDIT = "post_edit"

ALLOWED_ADMIN_RETURN_SECTIONS = frozenset(
    {
        "section-branding",
        "section-index-page",
        "section-rooms",
        "section-plans",
        "section-public-users",
        "section-public-users-trash",
        "section-sessions",
        "section-faq",
        "section-security",
        "section-center-posts",
        "section-loyalty",
        "section-staff-invite",
        "section-staff-roles",
        "section-reports",
    }
)

# Admin redirect/flash message keys.
ADMIN_MSG_IP_BLOCK_INVALID = "ip_block_invalid"
ADMIN_MSG_IP_BLOCKED = "ip_blocked"
ADMIN_MSG_IP_UNBLOCK_NOT_FOUND = "ip_unblock_not_found"
ADMIN_MSG_IP_UNBLOCKED = "ip_unblocked"
ADMIN_MSG_PUBLIC_USER_NOT_FOUND = "public_user_not_found"
ADMIN_MSG_PUBLIC_USER_UPDATED = "public_user_updated"
ADMIN_MSG_PUBLIC_USER_DELETED = "public_user_deleted"
ADMIN_MSG_PUBLIC_USER_ALREADY_VERIFIED = "public_user_already_verified"
ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED = "public_user_verification_mail_failed"
ADMIN_MSG_PUBLIC_USER_VERIFICATION_RESENT = "public_user_verification_resent"
ADMIN_MSG_PUBLIC_USER_RESTORED = "public_user_restored"
ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETED = "public_user_permanent_deleted"
ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETE_FORBIDDEN = "public_user_permanent_delete_forbidden"
ADMIN_MSG_PUBLIC_USERS_NONE_SELECTED = "public_users_none_selected"
ADMIN_MSG_PUBLIC_USERS_BULK_INVALID_ACTION = "public_users_bulk_invalid_action"
ADMIN_MSG_PUBLIC_USERS_BULK_DONE = "public_users_bulk_done"
ADMIN_MSG_ROOM_CREATED = "room_created"
ADMIN_MSG_ROOM_UPDATED = "room_updated"
ADMIN_MSG_ROOM_DELETED = "room_deleted"
ADMIN_MSG_ROOM_HAS_SESSIONS = "room_has_sessions"
ADMIN_MSG_ROOM_HAS_BOOKINGS = "room_has_bookings"
ADMIN_MSG_ROOM_CAPACITY_INVALID = "room_capacity_invalid"
ADMIN_MSG_ROOMS_NONE_SELECTED = "rooms_none_selected"
ADMIN_MSG_ROOMS_NOT_FOUND = "rooms_not_found"
ADMIN_MSG_ROOMS_DELETED = "rooms_deleted"
ADMIN_MSG_ROOMS_DELETED_PARTIAL = "rooms_deleted_partial"
ADMIN_MSG_ROOMS_DELETED_PARTIAL_BOOKINGS = "rooms_deleted_partial_bookings"
ADMIN_MSG_ROOMS_DELETE_HAS_BOOKINGS = "rooms_delete_has_bookings"
ADMIN_MSG_ROOMS_DELETE_BLOCKED = "rooms_delete_blocked"
ADMIN_MSG_PLAN_CREATED = "plan_created"
ADMIN_MSG_PLAN_UPDATED = "plan_updated"
ADMIN_MSG_PLAN_DELETED = "plan_deleted"
ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS = "plan_has_subscriptions"
ADMIN_MSG_PLAN_NAME_INVALID = "plan_name_invalid"
ADMIN_MSG_PLAN_DETAILS_UPDATED = "plan_details_updated"
ADMIN_MSG_PLAN_DETAILS_INVALID = "plan_details_invalid"
ADMIN_MSG_SESSION_CREATED = "session_created"
ADMIN_MSG_SESSION_DELETED = "session_deleted"
ADMIN_MSG_FAQ_CREATED = "faq_created"
ADMIN_MSG_FAQ_UPDATED = "faq_updated"
ADMIN_MSG_FAQ_DELETED = "faq_deleted"
ADMIN_MSG_FAQ_INVALID = "faq_invalid"
ADMIN_MSG_FAQ_NOT_FOUND = "faq_not_found"
ADMIN_MSG_FAQ_REORDERED = "faq_reordered"
ADMIN_MSG_FAQ_REORDER_INVALID = "faq_reorder_invalid"
ADMIN_MSG_CENTER_BRANDING_UPDATED = "center_branding_updated"
ADMIN_MSG_CENTER_BRANDING_BAD_FILE = "center_branding_bad_file"
ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING = "center_branding_center_missing"
ADMIN_MSG_CENTER_LOYALTY_SAVED = "center_loyalty_saved"
ADMIN_MSG_CENTER_LOYALTY_INVALID = "center_loyalty_invalid"
ADMIN_MSG_CENTER_LOYALTY_BAD_NUMBER = "center_loyalty_bad_number"
ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN = "trainer_admin_forbidden"
ADMIN_MSG_REPORT_FORBIDDEN = "report_forbidden"
ADMIN_MSG_SECURITY_OWNER_ONLY = "security_owner_only"
ADMIN_MSG_CENTER_POST_SAVED = "center_post_saved"
ADMIN_MSG_CENTER_POST_DELETED = "center_post_deleted"
ADMIN_MSG_CENTER_POST_NOT_FOUND = "center_post_not_found"
ADMIN_MSG_CENTER_POST_INVALID = "center_post_invalid"
ADMIN_MSG_CENTER_INDEX_SAVED = "center_index_saved"
ADMIN_MSG_CENTER_INDEX_NAME_INVALID = "center_index_name_invalid"
ADMIN_MSG_CENTER_INDEX_NAME_TAKEN = "center_index_name_taken"
ADMIN_MSG_CENTER_INDEX_TOO_LARGE = "center_index_too_large"
ADMIN_MSG_STAFF_CREATED = "staff_user_created"
ADMIN_MSG_STAFF_EMAIL_EXISTS = "staff_email_exists"
ADMIN_MSG_STAFF_INVALID = "staff_invalid"
ADMIN_MSG_STAFF_NOT_OWNER = "staff_not_owner"

CENTER_LOGO_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "uploads" / "centers"
CENTER_POST_UPLOAD_DIR = CENTER_LOGO_UPLOAD_DIR / "posts"
APP_STATIC_ROOT = Path(__file__).resolve().parent.parent.parent / "static"
CENTER_LOGO_MAX_BYTES = 2 * 1024 * 1024
CENTER_LOGO_ALLOWED_EXT = frozenset({"png", "jpg", "jpeg", "webp", "gif"})
CENTER_POST_MAX_GALLERY = 15
CENTER_POST_MAX_BODY_CHARS = 24_000
CENTER_POST_REMOTE_URL_MAX_LEN = 2048
CENTER_POST_TYPES = frozenset({"news", "announcement", "trip", "competition", "report"})
CENTER_POST_TYPE_LABELS = {
    "news": "خبر",
    "announcement": "إعلان",
    "trip": "رحلة",
    "competition": "مسابقة",
    "report": "تقرير",
}
NEWS_LIST_SORT_MODES = frozenset({"newest", "oldest", "recent"})


def _resolved_path_under_static(public_path: str | None) -> Path | None:
    if not public_path or not isinstance(public_path, str):
        return None
    u = public_path.strip()
    if not u.startswith("/static/"):
        return None
    rel = u[len("/static/") :].strip("/")
    if not rel:
        return None
    parts = rel.split("/")
    if any(p == ".." or p == "" for p in parts):
        return None
    base = APP_STATIC_ROOT.resolve()
    candidate = (base / Path(*parts)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _clear_center_branding_urls_if_files_missing(db: Session, center: models.Center) -> None:
    changed = False
    lp = _resolved_path_under_static(center.logo_url)
    if lp is not None and not lp.is_file():
        center.logo_url = None
        changed = True
    hp = _resolved_path_under_static(center.hero_image_url)
    if hp is not None and not hp.is_file():
        center.hero_image_url = None
        center.hero_show_stock_photo = True
        changed = True
    if changed:
        db.add(center)
        db.commit()

ADMIN_FLASH_MESSAGES: dict[str, tuple[str, str]] = {
    ADMIN_MSG_ROOM_CREATED: ("تمت إضافة الغرفة بنجاح.", "info"),
    ADMIN_MSG_ROOM_UPDATED: ("تم تحديث بيانات الغرفة بنجاح.", "info"),
    ADMIN_MSG_ROOM_DELETED: ("تم حذف الغرفة بنجاح.", "info"),
    ADMIN_MSG_ROOM_HAS_SESSIONS: ("لا يمكن حذف الغرفة لوجود جلسات مرتبطة بها. احذف الجلسات أو غيّر الغرفة أولًا.", "warn"),
    ADMIN_MSG_ROOM_HAS_BOOKINGS: ("تعذر حذف الغرفة لأن جلساتها تحتوي حجوزات. انقل الحجوزات أو احذفها أولًا.", "warn"),
    ADMIN_MSG_ROOMS_NONE_SELECTED: ("اختر غرفة واحدة على الأقل للحذف الجماعي.", "warn"),
    ADMIN_MSG_ROOMS_NOT_FOUND: ("الغرف المحددة غير موجودة.", "warn"),
    ADMIN_MSG_ROOMS_DELETED: ("تم حذف الغرف المحددة بنجاح.", "info"),
    ADMIN_MSG_ROOMS_DELETED_PARTIAL: ("تم حذف بعض الغرف، وتعذر حذف غرف أخرى لوجود جلسات مرتبطة بها.", "warn"),
    ADMIN_MSG_ROOMS_DELETED_PARTIAL_BOOKINGS: ("تم حذف بعض الغرف، وتعذر حذف غرف أخرى لأن جلساتها تحتوي حجوزات.", "warn"),
    ADMIN_MSG_ROOMS_DELETE_HAS_BOOKINGS: ("تعذر حذف الغرف المحددة لأن جلساتها تحتوي حجوزات.", "warn"),
    ADMIN_MSG_ROOMS_DELETE_BLOCKED: ("تعذر حذف الغرف المحددة لوجود جلسات مرتبطة بها.", "warn"),
    ADMIN_MSG_ROOM_CAPACITY_INVALID: ("سعة الغرفة يجب أن تكون أكبر من صفر.", "warn"),
    ADMIN_MSG_PLAN_CREATED: ("تمت إضافة خطة الاشتراك.", "info"),
    ADMIN_MSG_PLAN_UPDATED: ("تم تعديل اسم خطة الاشتراك.", "info"),
    ADMIN_MSG_PLAN_DELETED: ("تم حذف خطة الاشتراك.", "info"),
    ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS: ("لا يمكن حذف الخطة لوجود اشتراكات مرتبطة بها.", "warn"),
    ADMIN_MSG_PLAN_NAME_INVALID: ("اسم الخطة لا يمكن أن يكون فارغًا.", "warn"),
    ADMIN_MSG_PLAN_DETAILS_UPDATED: ("تم تحديث نوع الخطة والسعر وحد الجلسات بنجاح.", "info"),
    ADMIN_MSG_PLAN_DETAILS_INVALID: ("بيانات الخطة غير صالحة. تحقق من النوع/السعر/حد الجلسات.", "warn"),
    ADMIN_MSG_SESSION_CREATED: ("تمت إضافة الجلسة بنجاح.", "info"),
    ADMIN_MSG_SESSION_DELETED: ("تم حذف الجلسة بنجاح.", "info"),
    ADMIN_MSG_IP_BLOCKED: ("تم حظر الـ IP مؤقتًا.", "warn"),
    ADMIN_MSG_IP_UNBLOCKED: ("تم فك حظر الـ IP.", "info"),
    ADMIN_MSG_IP_UNBLOCK_NOT_FOUND: ("تعذر العثور على الـ IP لفك الحظر.", "warn"),
    ADMIN_MSG_IP_BLOCK_INVALID: ("قيمة IP غير صالحة.", "warn"),
    ADMIN_MSG_PUBLIC_USER_UPDATED: ("تم تحديث حالة المستخدم بنجاح.", "info"),
    ADMIN_MSG_PUBLIC_USER_NOT_FOUND: ("تعذر العثور على المستخدم المطلوب.", "warn"),
    ADMIN_MSG_PUBLIC_USER_DELETED: ("تم حذف المستخدم بنجاح.", "info"),
    ADMIN_MSG_PUBLIC_USER_VERIFICATION_RESENT: ("تم إرسال رابط التحقق للمستخدم بنجاح.", "info"),
    ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED: ("تعذر إرسال رابط التحقق. تحقق من إعدادات SMTP.", "warn"),
    ADMIN_MSG_PUBLIC_USER_ALREADY_VERIFIED: ("هذا المستخدم موثق بالفعل.", "warn"),
    ADMIN_MSG_PUBLIC_USER_RESTORED: ("تمت استعادة المستخدم بنجاح.", "info"),
    ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETED: ("تم حذف المستخدم نهائياً من قاعدة البيانات.", "info"),
    ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETE_FORBIDDEN: (
        "الحذف النهائي متاح فقط للحسابات في سلة المحذوفات (محذوفة Soft مسبقاً).",
        "warn",
    ),
    ADMIN_MSG_PUBLIC_USERS_NONE_SELECTED: ("اختر مستخدمًا واحدًا على الأقل لتنفيذ العملية الجماعية.", "warn"),
    ADMIN_MSG_PUBLIC_USERS_BULK_INVALID_ACTION: ("الإجراء الجماعي غير صالح.", "warn"),
    ADMIN_MSG_PUBLIC_USERS_BULK_DONE: ("تم تنفيذ العملية الجماعية على المستخدمين المحددين.", "info"),
    ADMIN_MSG_FAQ_CREATED: ("تمت إضافة السؤال الشائع بنجاح.", "info"),
    ADMIN_MSG_FAQ_UPDATED: ("تم تحديث السؤال الشائع بنجاح.", "info"),
    ADMIN_MSG_FAQ_DELETED: ("تم حذف السؤال الشائع بنجاح.", "info"),
    ADMIN_MSG_FAQ_INVALID: ("بيانات السؤال الشائع غير صالحة.", "warn"),
    ADMIN_MSG_FAQ_NOT_FOUND: ("تعذر العثور على السؤال المطلوب.", "warn"),
    ADMIN_MSG_FAQ_REORDERED: ("تم حفظ ترتيب الأسئلة الشائعة بنجاح.", "info"),
    ADMIN_MSG_FAQ_REORDER_INVALID: ("تعذر حفظ ترتيب الأسئلة. تحقق من القائمة ثم أعد المحاولة.", "warn"),
    ADMIN_MSG_CENTER_BRANDING_UPDATED: ("تم حفظ هوية المركز (الشعار، غلاف الصفحة، التلميح) في الواجهة العامة.", "info"),
    ADMIN_MSG_CENTER_BRANDING_BAD_FILE: ("إحدى الصور غير مقبولة. استخدم PNG أو JPG أو WebP أو GIF بحجم أقل من 2 ميجابايت لكل ملف.", "warn"),
    ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING: ("تعذر العثور على بيانات المركز المرتبطة بحسابك.", "warn"),
    ADMIN_MSG_CENTER_LOYALTY_SAVED: ("تم حفظ إعدادات برنامج الولاء.", "info"),
    ADMIN_MSG_CENTER_LOYALTY_INVALID: ("إعدادات الولاء غير صالحة. يجب أن تكون عتبة البرونزي أقل من الفضي، والفضي أقل من الذهبي.", "warn"),
    ADMIN_MSG_CENTER_LOYALTY_BAD_NUMBER: ("أدخل أرقاماً صحيحة فقط لعتبات الجلسات، أو اترك الحقل فارغاً لاستخدام الافتراضي.", "warn"),
    ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN: ("هذا الإجراء غير متاح لدور المدرب. يمكنك إدارة الجلسات من قسم «الجلسات والمدفوعات» فقط.", "warn"),
    ADMIN_MSG_REPORT_FORBIDDEN: ("لا تملك صلاحية عرض هذا التقرير.", "warn"),
    ADMIN_MSG_SECURITY_OWNER_ONLY: ("قسم الأمان والتصدير الحساس متاح لمالك المركز فقط.", "warn"),
    ADMIN_MSG_CENTER_POST_SAVED: ("تم حفظ المنشور بنجاح.", "info"),
    ADMIN_MSG_CENTER_POST_DELETED: ("تم حذف المنشور.", "info"),
    ADMIN_MSG_CENTER_POST_NOT_FOUND: ("المنشور غير موجود أو لا يتبع مركزك.", "warn"),
    ADMIN_MSG_CENTER_POST_INVALID: ("بيانات المنشور غير صالحة أو الصورة غير مقبولة.", "warn"),
    ADMIN_MSG_CENTER_INDEX_SAVED: ("تم حفظ محتوى صفحة الحجز واسم المركز.", "info"),
    ADMIN_MSG_CENTER_INDEX_NAME_INVALID: ("اسم المركز مطلوب ولا يمكن أن يكون فارغًا.", "warn"),
    ADMIN_MSG_CENTER_INDEX_NAME_TAKEN: ("هذا الاسم مستخدم لمركز آخر. اختر اسمًا مختلفًا.", "warn"),
    ADMIN_MSG_CENTER_INDEX_TOO_LARGE: ("حجم نصوص صفحة الحجز كبير جدًا. قلّل طول بعض الحقول ثم أعد المحاولة.", "warn"),
    ADMIN_MSG_STAFF_CREATED: ("تم إنشاء حساب عضو الفريق. يمكنه تسجيل الدخول من صفحة تسجيل الدخول للإدارة.", "info"),
    ADMIN_MSG_STAFF_EMAIL_EXISTS: ("هذا البريد مسجّل مسبقاً. استخدم بريداً آخر أو تحقق من الحسابات الحالية.", "warn"),
    ADMIN_MSG_STAFF_INVALID: ("تعذر إنشاء الحساب: تحقق من الاسم والبريد وكلمة المرور (8 أحرف على الأقل) والدور.", "warn"),
    ADMIN_MSG_STAFF_NOT_OWNER: ("إضافة أعضاء الفريق متاحة لمالك المركز فقط.", "warn"),
    "report_settings_saved": ("تم حفظ أهداف التقارير وإعدادات الضريبة والبريد.", "info"),
    "digest_email_sent": ("تم إرسال الملخص إلى البريد المحدد.", "info"),
    "digest_email_failed": ("تعذر إرسال البريد. تحقق من SMTP والعنوان.", "warn"),
}


def _current_public_user(request: Request, db: Session) -> models.PublicUser | None:
    token = request.cookies.get(PUBLIC_COOKIE_NAME)
    if not token:
        return None
    try:
        return get_public_user_from_token_string(token, db)
    except HTTPException:
        return None


def _request_key(request: Request, prefix: str, identity: str = "") -> str:
    client_ip = get_client_ip(request)
    scope = identity.strip().lower() if identity else client_ip
    return f"{prefix}:{scope}"


def _active_block_for_ip(db: Session, ip: str) -> models.BlockedIP | None:
    now = utcnow_naive()
    return (
        db.query(models.BlockedIP)
        .filter(
            models.BlockedIP.ip == ip,
            models.BlockedIP.is_active.is_(True),
            or_(models.BlockedIP.blocked_until.is_(None), models.BlockedIP.blocked_until > now),
        )
        .order_by(models.BlockedIP.created_at.desc())
        .first()
    )


def _is_ip_blocked(db: Session, request: Request) -> bool:
    return _active_block_for_ip(db, get_client_ip(request)) is not None


def _unlink_center_uploads(glob_pattern: str) -> None:
    if not CENTER_LOGO_UPLOAD_DIR.is_dir():
        return
    for path in CENTER_LOGO_UPLOAD_DIR.glob(glob_pattern):
        path.unlink(missing_ok=True)


def _sanitize_center_post_remote_image_url(raw: str | None) -> str | None:
    """يقبل فقط http/https لعرضها في المتصفح (بدون تنزيل من الخادم)."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > CENTER_POST_REMOTE_URL_MAX_LEN:
        return None
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    return s


def _parse_center_post_gallery_remote_urls(blob: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in (blob or "").splitlines():
        for part in line.split(","):
            u = _sanitize_center_post_remote_image_url(part)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _delete_center_post_disk_files(center_id: int, post_id: int) -> None:
    if not CENTER_POST_UPLOAD_DIR.is_dir():
        return
    prefix = f"center_{center_id}_post_{post_id}_"
    for path in CENTER_POST_UPLOAD_DIR.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            path.unlink(missing_ok=True)


def _unlink_static_url_file(public_url: str | None) -> None:
    p = _resolved_path_under_static(public_url)
    if p and p.is_file():
        p.unlink(missing_ok=True)


def _sanitize_admin_return_section(raw: str | None) -> str | None:
    s = (raw or "").strip()
    return s if s in ALLOWED_ADMIN_RETURN_SECTIONS else None


def _admin_redirect(
    msg: str | None = None,
    scroll_y: str | None = None,
    return_section: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {}
    if msg:
        params["msg"] = msg
    if scroll_y:
        try:
            parsed = int(float(scroll_y))
            if parsed >= 0:
                params["scroll_y"] = str(parsed)
        except (TypeError, ValueError):
            pass
    url = "/admin"
    if params:
        url = f"{url}?{urlencode(params)}"
    sec = _sanitize_admin_return_section(return_section)
    if sec:
        url = f"{url}#{sec}"
    return RedirectResponse(url=url, status_code=303)


def _parse_optional_date_str(value: str | None) -> date | None:
    s = (value or "").strip()[:10]
    if len(s) < 8:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _trainer_forbidden_redirect(return_section: str | None = None) -> RedirectResponse:
    return _admin_redirect(
        ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN,
        scroll_y=None,
        return_section=return_section,
    )


def _security_owner_forbidden_redirect(return_section: str | None = None) -> RedirectResponse:
    return _admin_redirect(
        ADMIN_MSG_SECURITY_OWNER_ONLY,
        scroll_y=None,
        return_section=return_section,
    )


def _admin_login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=303)


def _require_admin_user_or_redirect(
    request: Request, db: Session
) -> tuple[models.User | None, RedirectResponse | None]:
    user = _admin_user_from_request(request, db)
    if not user:
        return None, _admin_login_redirect()
    return user, None


def _public_login_redirect(next_url: str = PUBLIC_INDEX_DEFAULT_PATH, msg: str | None = None) -> RedirectResponse:
    safe_next = _sanitize_next_url(next_url)
    return RedirectResponse(url=_url_with_params("/public/login", next=safe_next, msg=msg), status_code=303)


def _admin_user_from_request(request: Request, db: Session) -> models.User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        user = get_user_from_token_string(token, db)
    except HTTPException:
        return None
    if user.role not in CENTER_ADMIN_LOGIN_ROLES:
        return None
    return user


def _get_public_user_or_redirect(
    db: Session,
    center_id: int,
    public_user_id: int,
    scroll_y: str,
    *,
    allow_deleted: bool = False,
    return_section: str | None = None,
) -> tuple[models.PublicUser | None, RedirectResponse | None]:
    row = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.id == public_user_id,
            db.query(models.Client.id)
            .filter(
                models.Client.center_id == center_id,
                func.lower(models.Client.email) == func.lower(models.PublicUser.email),
            )
            .exists(),
        )
        .first()
    )
    if not row:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    if not allow_deleted and row.is_deleted:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    return row, None


def _public_users_query_for_center(db: Session, center_id: int):
    return db.query(models.PublicUser).filter(
        db.query(models.Client.id)
        .filter(
            models.Client.center_id == center_id,
            func.lower(models.Client.email) == func.lower(models.PublicUser.email),
        )
        .exists()
    )


def _ensure_client_for_public_register(db: Session, user: models.PublicUser, next_url: str) -> None:
    """Create or refresh a Client row for the center in ``next`` so the user appears in admin public-user lists."""
    cid_str = public_center_id_str_from_next(next_url)
    try:
        center_id = int(cid_str)
    except (ValueError, TypeError):
        return
    if not db.get(models.Center, center_id):
        return
    existing = (
        db.query(models.Client)
        .filter(
            models.Client.center_id == center_id,
            func.lower(models.Client.email) == func.lower(user.email),
        )
        .first()
    )
    if existing:
        existing.full_name = user.full_name
        if user.phone:
            existing.phone = user.phone
        return
    db.add(
        models.Client(
            center_id=center_id,
            full_name=user.full_name,
            email=user.email.lower(),
            phone=user.phone,
        )
    )


def _spots_available_map(db: Session, center_id: int, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}
    sessions = (
        db.query(models.YogaSession.id, models.YogaSession.room_id)
        .filter(models.YogaSession.center_id == center_id, models.YogaSession.id.in_(session_ids))
        .all()
    )
    if not sessions:
        return {}
    room_ids = sorted({rid for _, rid in sessions if rid is not None})
    rooms = (
        db.query(models.Room.id, models.Room.capacity)
        .filter(models.Room.center_id == center_id, models.Room.id.in_(room_ids))
        .all()
        if room_ids
        else []
    )
    capacity_by_room = {int(rid): int(cap or 0) for rid, cap in rooms}
    booking_counts = {
        int(sid): int(cnt)
        for sid, cnt in (
            db.query(models.Booking.session_id, func.count(models.Booking.id))
            .filter(
                models.Booking.session_id.in_(session_ids),
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .group_by(models.Booking.session_id)
            .all()
        )
    }
    out: dict[int, int] = {}
    for sid, rid in sessions:
        cap = capacity_by_room.get(int(rid), 0) if rid is not None else 0
        active = booking_counts.get(int(sid), 0)
        out[int(sid)] = max(0, cap - active)
    return out


PUBLIC_USER_BULK_ACTIONS = frozenset(
    {
        "activate",
        "deactivate",
        "verify",
        "unverify",
        "resend_verification",
        "soft_delete",
        "restore",
        "permanent_delete",
    }
)


def _apply_public_user_bulk_action(
    db: Session, action_key: str, row: models.PublicUser, request: Request
) -> tuple[int, int]:
    updated = 0
    queued = 0
    if action_key == "activate" and not row.is_deleted:
        row.is_active = True
        updated = 1
    elif action_key == "deactivate" and not row.is_deleted:
        row.is_active = False
        updated = 1
    elif action_key == "verify" and not row.is_deleted:
        row.email_verified = True
        updated = 1
    elif action_key == "unverify" and not row.is_deleted:
        row.email_verified = False
        updated = 1
    elif action_key == "resend_verification" and (not row.is_deleted) and (not row.email_verified):
        ok, _ = queue_verify_email_for_user(request, row)
        if ok:
            row.verification_sent_at = utcnow_naive()
            queued = 1
    elif action_key == "soft_delete" and not row.is_deleted:
        _soft_delete_public_user(row)
        updated = 1
    elif action_key == "restore" and row.is_deleted:
        row.is_deleted = False
        row.deleted_at = None
        row.is_active = True
        updated = 1
    elif action_key == "permanent_delete" and row.is_deleted:
        db.delete(row)
        updated = 1
    return updated, queued


def _analytics_context(page_name: str, **extra: str) -> dict:
    data = {
        "ga4_measurement_id": GA4_MEASUREMENT_ID,
        "analytics_enabled": bool(GA4_MEASUREMENT_ID),
        "analytics_page_name": page_name,
    }
    data.update(extra)
    return data


def _soft_delete_public_user(row: models.PublicUser) -> tuple[str, str]:
    original_email = row.email
    original_phone = row.phone or ""
    tombstone = f"deleted+{row.id}+{int(utcnow_naive().timestamp())}@maestroyoga.local"
    row.email = tombstone
    row.phone = None
    row.is_active = False
    row.email_verified = False
    row.is_deleted = True
    if row.deleted_at is None:
        row.deleted_at = utcnow_naive()
    return original_email, original_phone


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


INDEX_PAGE_MAX_JSON_CHARS = 120_000


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
            "show": True,
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
            "show": True,
            "text": "جلسات لمستويات <strong>مبتدئ ومتوسط ومتقدم</strong> — يحدد المدرب والجدول ما يناسبك عند الحجز.",
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
        "faq_teaser": {
            "show": True,
            "title": "أسئلة سريعة قبل الحجز",
            "more_text": "عرض كل الأسئلة الشائعة ←",
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
            "show": _form_bool01(form_data, "pc_show", True),
            "dropin_title": _form_str_index(form_data, "pc_dropin_title", 120),
            "dropin_body": _form_str_index(form_data, "pc_dropin_body", 600),
            "plan_title": _form_str_index(form_data, "pc_plan_title", 120),
            "plan_body": _form_str_index(form_data, "pc_plan_body", 1200),
            "note": _form_str_index(form_data, "pc_note", 800),
        },
        "team_strip": {
            "show": _form_bool01(form_data, "team_show", True),
            "text": _form_str_index(form_data, "team_text", 600),
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
        "faq_teaser": {
            "show": _form_bool01(form_data, "faq_teaser_show", True),
            "title": _form_str_index(form_data, "faq_teaser_title", 160),
            "more_text": _form_str_index(form_data, "faq_teaser_more", 120),
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

