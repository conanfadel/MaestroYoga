import csv
import io
import json
from html import escape as html_escape
from collections import defaultdict
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, case, func, nullslast, or_
from sqlalchemy.orm import Session

from . import models
from .booking_utils import ACTIVE_BOOKING_STATUSES, spots_available
from .bootstrap import DEMO_CENTER_NAME, ensure_demo_data, ensure_demo_news_posts
from .database import get_db
from .loyalty import (
    LOYALTY_REWARD_MAX_LEN,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_thresholds,
    validate_loyalty_threshold_triple,
)
from .mailer import (
    feedback_destination_email,
    queue_email_verification_email,
    queue_password_reset_email,
    send_mail_with_attachments,
    validate_mailer_settings,
)
from .payments import StripePaymentProvider, get_payment_provider
from .rate_limiter import rate_limiter
from .request_ip import get_client_ip
from .security_audit import log_security_event
from .security import (
    create_access_token,
    create_public_access_token,
    create_public_email_verification_token,
    create_public_email_verify_flash_token,
    create_public_password_reset_token,
    decode_public_email_verification_token,
    decode_public_email_verify_flash_token,
    decode_public_password_reset_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
    hash_password,
    require_roles_cookie_or_bearer,
    verify_password,
)
from .tenant_utils import require_user_center_id
from .time_utils import utcnow_naive
from .web_shared import (
    _cookie_secure_flag,
    _fmt_dt,
    _is_email_verification_required,
    _is_strong_public_password,
    _is_truthy_env,
    _normalize_phone_with_country,
    _plan_duration_days,
    _public_base,
    _sanitize_next_url,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
    _url_with_params,
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(tags=["web"])
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

# Admin security policy defaults.
ADMIN_IP_BLOCK_DEFAULT_MINUTES = 60
ADMIN_IP_BLOCK_MAX_MINUTES = 10080

# Admin query parameter keys.
ADMIN_QP_ROOM_SORT = "room_sort"
ADMIN_QP_PUBLIC_USER_Q = "public_user_q"
ADMIN_QP_PUBLIC_USER_STATUS = "public_user_status"
ADMIN_QP_PUBLIC_USER_VERIFIED = "public_user_verified"
ADMIN_QP_PUBLIC_USER_PAGE = "public_user_page"
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
        "section-rooms",
        "section-plans",
        "section-public-users",
        "section-sessions",
        "section-faq",
        "section-security",
        "section-center-posts",
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
ADMIN_MSG_SECURITY_OWNER_ONLY = "security_owner_only"
ADMIN_MSG_CENTER_POST_SAVED = "center_post_saved"
ADMIN_MSG_CENTER_POST_DELETED = "center_post_deleted"
ADMIN_MSG_CENTER_POST_NOT_FOUND = "center_post_not_found"
ADMIN_MSG_CENTER_POST_INVALID = "center_post_invalid"

CENTER_LOGO_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "centers"
CENTER_POST_UPLOAD_DIR = CENTER_LOGO_UPLOAD_DIR / "posts"
APP_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
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
    ADMIN_MSG_SECURITY_OWNER_ONLY: ("قسم الأمان والتصدير الحساس متاح لمالك المركز فقط.", "warn"),
    ADMIN_MSG_CENTER_POST_SAVED: ("تم حفظ المنشور بنجاح.", "info"),
    ADMIN_MSG_CENTER_POST_DELETED: ("تم حذف المنشور.", "info"),
    ADMIN_MSG_CENTER_POST_NOT_FOUND: ("المنشور غير موجود أو لا يتبع مركزك.", "warn"),
    ADMIN_MSG_CENTER_POST_INVALID: ("بيانات المنشور غير صالحة أو الصورة غير مقبولة.", "warn"),
}


def _current_public_user(request: Request, db: Session) -> models.PublicUser | None:
    token = request.cookies.get(PUBLIC_COOKIE_NAME)
    if not token:
        return None
    try:
        return get_public_user_from_token_string(token, db)
    except HTTPException:
        return None


def _public_user_from_verify_flash_token(db: Session, vk: str) -> models.PublicUser | None:
    vk_value = (vk or "").strip()
    if not vk_value:
        return None
    try:
        payload = decode_public_email_verify_flash_token(vk_value)
    except HTTPException:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.is_deleted or not user.is_active:
        return None
    if user.email.lower() != email:
        return None
    if not user.email_verified:
        return None
    return user


def _build_verify_url(request: Request, user: models.PublicUser, next_url: str = "/index?center_id=1") -> str:
    token = create_public_email_verification_token(user.id, user.email)
    safe_next = _sanitize_next_url(next_url)
    query = urlencode({"token": token, "next": safe_next})
    return f"{_public_base(request)}/public/verify-email?{query}"


def _build_reset_url(request: Request, user: models.PublicUser) -> str:
    token = create_public_password_reset_token(user.id, user.email)
    query = urlencode({"token": token})
    return f"{_public_base(request)}/public/reset-password?{query}"


def _request_key(request: Request, prefix: str, identity: str = "") -> str:
    client_ip = get_client_ip(request)
    scope = identity.strip().lower() if identity else client_ip
    return f"{prefix}:{scope}"


def _client_ip(request: Request) -> str:
    return get_client_ip(request)


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
    return _active_block_for_ip(db, _client_ip(request)) is not None


def _delete_center_logo_files(center_id: int) -> None:
    if not CENTER_LOGO_UPLOAD_DIR.is_dir():
        return
    for path in CENTER_LOGO_UPLOAD_DIR.glob(f"center_{center_id}.*"):
        path.unlink(missing_ok=True)


def _delete_center_hero_files(center_id: int) -> None:
    if not CENTER_LOGO_UPLOAD_DIR.is_dir():
        return
    for path in CENTER_LOGO_UPLOAD_DIR.glob(f"center_{center_id}_hero.*"):
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


def _public_login_redirect(next_url: str = "/index?center_id=1", msg: str | None = None) -> RedirectResponse:
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
    if user.role not in ("center_owner", "center_staff", "trainer"):
        return None
    return user


def _get_public_user_or_redirect(
    db: Session,
    public_user_id: int,
    scroll_y: str,
    *,
    allow_deleted: bool = False,
    return_section: str | None = None,
) -> tuple[models.PublicUser | None, RedirectResponse | None]:
    row = db.get(models.PublicUser, public_user_id)
    if not row:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    if not allow_deleted and row.is_deleted:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    return row, None


PUBLIC_USER_BULK_ACTIONS = frozenset(
    {
        "activate",
        "deactivate",
        "verify",
        "unverify",
        "resend_verification",
        "soft_delete",
        "restore",
    }
)


def _apply_public_user_bulk_action(action_key: str, row: models.PublicUser, request: Request) -> tuple[int, int]:
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
        ok, _ = _queue_verify_email_for_user(request, row)
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
    return updated, queued


def _analytics_context(page_name: str, **extra: str) -> dict:
    data = {
        "ga4_measurement_id": GA4_MEASUREMENT_ID,
        "analytics_enabled": bool(GA4_MEASUREMENT_ID),
        "analytics_page_name": page_name,
    }
    data.update(extra)
    return data


def _queue_verify_email_for_user(request: Request, user: models.PublicUser, next_url: str = "/index?center_id=1") -> tuple[bool, str]:
    verify_url = _build_verify_url(request, user, next_url=next_url)
    return queue_email_verification_email(user.email, verify_url, full_name=user.full_name)


def _soft_delete_public_user(row: models.PublicUser) -> tuple[str, str]:
    original_email = row.email
    original_phone = row.phone or ""
    tombstone = f"deleted+{row.id}+{int(utcnow_naive().timestamp())}@maestroyoga.local"
    row.email = tombstone
    row.phone = None
    row.is_active = False
    row.email_verified = False
    row.is_deleted = True
    row.deleted_at = utcnow_naive()
    return original_email, original_phone


def _preview_text(text: str | None, max_len: int = 100) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


@router.get("/index", response_class=HTMLResponse)
def public_index(
    request: Request,
    center_id: int = 1,
    payment: str | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
):
    public_user = _current_public_user(request, db)
    center = db.get(models.Center, center_id)
    if not center:
        # Keep web pages usable even on a fresh DB.
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    if center.name == DEMO_CENTER_NAME:
        ensure_demo_news_posts(db, center.id)

    _clear_center_branding_urls_if_files_missing(db, center)

    sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == center_id)
        .order_by(models.YogaSession.starts_at.asc())
        .all()
    )
    room_ids = sorted({s.room_id for s in sessions if s.room_id is not None})
    rooms_by_id = {}
    if room_ids:
        rooms_by_id = {
            r.id: r
            for r in db.query(models.Room).filter(models.Room.center_id == center_id, models.Room.id.in_(room_ids)).all()
        }
    rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "spots_available": spots_available(db, s),
            }
        )

    plans = (
        db.query(models.SubscriptionPlan)
        .filter(
            models.SubscriptionPlan.center_id == center_id,
            models.SubscriptionPlan.is_active.is_(True),
        )
        .order_by(models.SubscriptionPlan.price.asc())
        .all()
    )
    faq_items = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == center_id, models.FAQItem.is_active.is_(True))
        .order_by(models.FAQItem.sort_order.asc(), models.FAQItem.created_at.asc())
        .all()
    )
    pinned_post = (
        db.query(models.CenterPost)
        .filter(
            models.CenterPost.center_id == center_id,
            models.CenterPost.is_published.is_(True),
            models.CenterPost.is_pinned.is_(True),
        )
        .order_by(nullslast(models.CenterPost.published_at.desc()), models.CenterPost.id.desc())
        .first()
    )
    total_published_posts = (
        db.query(func.count(models.CenterPost.id))
        .filter(
            models.CenterPost.center_id == center_id,
            models.CenterPost.is_published.is_(True),
        )
        .scalar()
        or 0
    )
    recent_posts_q = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.center_id == center_id, models.CenterPost.is_published.is_(True))
        .order_by(nullslast(models.CenterPost.published_at.desc()), models.CenterPost.id.desc())
        .limit(24)
        .all()
    )
    pinned_public_post = None
    if pinned_post:
        sum_full = (pinned_post.summary or "").strip()
        pinned_public_post = {
            "id": pinned_post.id,
            "title": pinned_post.title,
            "post_type": pinned_post.post_type,
            "type_label": CENTER_POST_TYPE_LABELS.get(pinned_post.post_type, pinned_post.post_type),
            "summary": sum_full,
            "summary_short": _preview_text(sum_full, 100),
            "cover_image_url": pinned_post.cover_image_url,
            "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
        }
    loyalty_ctx: dict = {}
    if public_user:
        loyalty_ctx = loyalty_context_for_count(
            count_confirmed_sessions_for_public_user(db, center_id, public_user),
            center=center,
        )

    public_posts_teasers: list[dict] = []
    news_ticker_items: list[dict[str, str]] = []
    if pinned_post:
        news_ticker_items.append(
            {
                "title": (pinned_post.title or "").strip(),
                "type_label": CENTER_POST_TYPE_LABELS.get(pinned_post.post_type, pinned_post.post_type),
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
            }
        )
    for p in recent_posts_q:
        if pinned_post and p.id == pinned_post.id:
            continue
        if len(public_posts_teasers) < 3:
            sum_full = (p.summary or "").strip()
            public_posts_teasers.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "post_type": p.post_type,
                    "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                    "summary": _preview_text(sum_full, 120),
                    "cover_image_url": p.cover_image_url,
                    "published_at_display": _fmt_dt(p.published_at) if p.published_at else "",
                    "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                }
            )
        if len(news_ticker_items) < 14:
            tl = (p.title or "").strip()
            if tl:
                news_ticker_items.append(
                    {
                        "title": tl,
                        "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                        "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                    }
                )
        if len(public_posts_teasers) >= 3 and len(news_ticker_items) >= 14:
            break

    num_news_on_index = (1 if pinned_public_post else 0) + len(public_posts_teasers)
    public_news_has_more = total_published_posts > num_news_on_index
    public_news_list_url = _url_with_params("/news", center_id=str(center_id))
    plan_labels = {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "center": center,
            "center_id": center_id,
            "sessions": rows,
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "plan_type": p.plan_type,
                    "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
                    "duration_days": _plan_duration_days(p.plan_type),
                    "price": p.price,
                    "session_limit": p.session_limit,
                }
                for p in plans
            ],
            "payment": payment,
            "msg": msg,
            "public_user": public_user,
            "faq_items": faq_items,
            "pinned_public_post": pinned_public_post,
            "public_posts_teasers": public_posts_teasers,
            "news_ticker_items": news_ticker_items,
            "public_news_has_more": public_news_has_more,
            "public_news_list_url": public_news_list_url,
            "loyalty_program_rows": loyalty_program_table_rows(center),
            "feedback_enabled": bool(feedback_destination_email()) and validate_mailer_settings()[0],
            **loyalty_ctx,
            **_analytics_context("index", center_id=str(center_id)),
        },
    )


@router.post("/public/feedback")
async def public_feedback_submit(
    request: Request,
    center_id: int = Form(1),
    category: str = Form(...),
    message: str = Form(...),
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    """إرسال مشكلة / شكوى / اقتراح من الواجهة العامة إلى بريد الإدارة (مع صور اختيارية)."""
    pu = _current_public_user(request, db)
    if not pu:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_auth_required"),
            status_code=303,
        )

    dest = feedback_destination_email()
    ok_cfg, _why = validate_mailer_settings()
    if not dest or not ok_cfg:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_unavailable"),
            status_code=303,
        )

    cat_key = (category or "").strip().lower()
    if cat_key not in PUBLIC_FEEDBACK_CATEGORY_LABELS:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    msg_text = (message or "").strip()
    if len(msg_text) < 3 or len(msg_text) > 8000:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    name_sub = (contact_name or "").strip()
    if len(name_sub) < 2 or len(name_sub) > 200:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )
    phone_sub = (contact_phone or "").strip()[:40]

    ce = (pu.email or "").strip().lower()
    if not ce or "@" not in ce or len(ce) > 254:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    fb_key = _request_key(request, "public_feedback", f"{center_id}")
    if not rate_limiter.allow(fb_key, limit=5, window_seconds=3600, lockout_seconds=120, max_lockout_seconds=MAX_LOCKOUT_SECONDS):
        log_security_event("public_feedback", request, "rate_limited", email=ce or None)
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_rate_limited"),
            status_code=303,
        )

    attachments: list[tuple[str, bytes, str]] = []
    upload_list = images if images else []
    for uf in upload_list:
        if not uf.filename:
            continue
        ct = (uf.content_type or "").split(";")[0].strip().lower()
        if ct not in PUBLIC_FEEDBACK_ALLOWED_IMAGE_TYPES:
            return RedirectResponse(
                url=_url_with_params("/index", center_id=str(center_id), msg="feedback_bad_image"),
                status_code=303,
            )
        raw = await uf.read()
        if len(raw) > PUBLIC_FEEDBACK_MAX_IMAGE_BYTES:
            return RedirectResponse(
                url=_url_with_params("/index", center_id=str(center_id), msg="feedback_image_too_large"),
                status_code=303,
            )
        if len(attachments) >= PUBLIC_FEEDBACK_MAX_IMAGES:
            break
        safe_name = os.path.basename(uf.filename or "image.jpg")[:180]
        attachments.append((safe_name, raw, ct))

    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    cat_label = PUBLIC_FEEDBACK_CATEGORY_LABELS[cat_key]
    ip = get_client_ip(request)
    subject = f"{app_name} — {center.name} — {cat_label}"
    body_lines = [
        f"المركز: {center.name} (center_id={center_id})",
        f"التصنيف: {cat_label}",
        f"الاسم: {name_sub}",
        f"الجوال: {phone_sub or '—'}",
        f"البريد (من حساب المستخدم): {ce}",
        "",
        "النص:",
        msg_text,
        "",
        f"عنوان IP: {ip}",
    ]
    body = "\n".join(body_lines)
    html_body = (
        f"<div dir='rtl' style='font-family:Tahoma,Arial,sans-serif;line-height:1.6'>"
        f"<p><strong>المركز:</strong> {html_escape(center.name)}</p>"
        f"<p><strong>التصنيف:</strong> {html_escape(cat_label)}</p>"
        f"<p><strong>الاسم:</strong> {html_escape(name_sub)}</p>"
        f"<p><strong>الجوال:</strong> {html_escape(phone_sub or '—')}</p>"
        f"<p><strong>البريد:</strong> {html_escape(ce)}</p>"
        f"<p><strong>النص:</strong></p><pre style='white-space:pre-wrap'>{html_escape(msg_text)}</pre>"
        f"<p><strong>IP:</strong> {html_escape(ip)}</p>"
        f"</div>"
    )

    sent_ok, send_reason = send_mail_with_attachments(
        dest,
        subject,
        body,
        html_body=html_body,
        attachments=attachments or None,
    )
    if not sent_ok:
        log_security_event(
            "public_feedback",
            request,
            "send_failed",
            email=ce or None,
            details={"reason": send_reason[:400]},
        )
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )
    log_security_event("public_feedback", request, "success", email=ce or None)
    return RedirectResponse(
        url=_url_with_params("/index", center_id=str(center_id), msg="feedback_sent"),
        status_code=303,
    )


@router.get("/news", response_class=HTMLResponse)
def public_news_list(
    request: Request,
    center_id: int = 1,
    filter_type: str | None = Query(None, alias="type", description="تصفية حسب نوع المنشور"),
    sort: str = Query("newest", description="newest | oldest | recent"),
    db: Session = Depends(get_db),
):
    center = db.get(models.Center, center_id)
    if not center:
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    if center.name == DEMO_CENTER_NAME:
        ensure_demo_news_posts(db, center.id)
    _clear_center_branding_urls_if_files_missing(db, center)

    type_key = (filter_type or "").strip().lower()
    if type_key and type_key not in CENTER_POST_TYPES:
        type_key = ""
    sort_key = (sort or "newest").strip().lower()
    if sort_key not in NEWS_LIST_SORT_MODES:
        sort_key = "newest"

    q = db.query(models.CenterPost).filter(
        models.CenterPost.center_id == center_id,
        models.CenterPost.is_published.is_(True),
    )
    if type_key:
        q = q.filter(models.CenterPost.post_type == type_key)

    if sort_key == "oldest":
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            nullslast(models.CenterPost.published_at.asc()),
            models.CenterPost.id.asc(),
        )
    elif sort_key == "recent":
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            models.CenterPost.created_at.desc(),
            models.CenterPost.id.desc(),
        )
    else:
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            nullslast(models.CenterPost.published_at.desc()),
            models.CenterPost.id.desc(),
        )

    posts = q.all()
    news_rows = []
    for p in posts:
        sum_full = (p.summary or "").strip()
        news_rows.append(
            {
                "title": p.title,
                "post_type": p.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                "summary": _preview_text(sum_full, 180),
                "published_at_display": _fmt_dt(p.published_at) if p.published_at else "",
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                "cover_image_url": p.cover_image_url,
                "is_pinned": bool(p.is_pinned),
            }
        )

    post_type_filter_options = [("", "كل الأنواع")] + [(k, CENTER_POST_TYPE_LABELS[k]) for k in sorted(CENTER_POST_TYPES)]
    sort_filter_options = [
        ("newest", "الأحدث نشراً"),
        ("oldest", "الأقدم نشراً"),
        ("recent", "آخر إضافة"),
    ]

    return templates.TemplateResponse(
        request,
        "public_news_list.html",
        {
            "center": center,
            "center_id": center_id,
            "news_rows": news_rows,
            "news_type_filter": type_key,
            "news_sort": sort_key,
            "post_type_filter_options": post_type_filter_options,
            "sort_filter_options": sort_filter_options,
            "index_url": _url_with_params("/index", center_id=str(center_id)),
            **_analytics_context("public_news_list", center_id=str(center_id)),
        },
    )


@router.get("/post", response_class=HTMLResponse)
def public_post_detail(
    request: Request,
    center_id: int,
    post_id: int,
    db: Session = Depends(get_db),
):
    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    post = db.get(models.CenterPost, post_id)
    if not post or post.center_id != center_id or not post.is_published:
        raise HTTPException(status_code=404, detail="Post not found")
    _clear_center_branding_urls_if_files_missing(db, center)
    imgs = (
        db.query(models.CenterPostImage)
        .filter(models.CenterPostImage.post_id == post.id)
        .order_by(models.CenterPostImage.sort_order.asc(), models.CenterPostImage.id.asc())
        .all()
    )
    gallery = [{"id": i.id, "url": i.image_url} for i in imgs]
    public_user = _current_public_user(request, db)
    loyalty_ctx: dict = {}
    if public_user:
        loyalty_ctx = loyalty_context_for_count(
            count_confirmed_sessions_for_public_user(db, center_id, public_user),
            center=center,
        )
    return templates.TemplateResponse(
        request,
        "post_detail.html",
        {
            "center": center,
            "center_id": center_id,
            "public_user": public_user,
            **loyalty_ctx,
            "post": {
                "id": post.id,
                "title": post.title,
                "post_type": post.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(post.post_type, post.post_type),
                "summary": post.summary or "",
                "body": post.body or "",
                "cover_image_url": post.cover_image_url,
                "published_at_display": _fmt_dt(post.published_at) if post.published_at else "",
            },
            "gallery": gallery,
            "index_url": _url_with_params("/index", center_id=str(center_id)),
            **_analytics_context("post", center_id=str(center_id), post_id=str(post_id)),
        },
    )


@router.post("/public/book")
def public_book(
    request: Request,
    center_id: int = Form(...),
    session_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != center_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if spots_available(db, yoga_session) <= 0:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=full",
            status_code=303,
        )

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    duplicate = (
        db.query(models.Booking)
        .filter(
            models.Booking.session_id == session_id,
            models.Booking.client_id == client.id,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .first()
    )
    if duplicate:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=duplicate",
            status_code=303,
        )

    booking = models.Booking(
        center_id=center_id,
        session_id=session_id,
        client_id=client.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()

    amount = float(yoga_session.price_drop_in)
    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=booking.id,
        amount=amount,
        currency="SAR",
        payment_method="public_checkout",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)

    provider = get_payment_provider()
    base = _public_base(request)

    if isinstance(provider, StripePaymentProvider):
        try:
            provider_result = provider.create_checkout_session(
                amount=amount,
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "booking_id": str(booking.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled",
                line_item_name=f"حجز جلسة — {yoga_session.title}"[:120],
                line_item_description=f"{center.name} · {_fmt_dt(yoga_session.starts_at)} · {yoga_session.duration_minutes} دقيقة"[
                    :500
                ],
            )
        except Exception as exc:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            log_security_event(
                "public_book",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "session_id": session_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_no_url",
                status_code=303,
            )
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=amount,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client.id, "booking_id": booking.id},
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    booking.status = "confirmed"
    db.commit()

    return RedirectResponse(
        url=f"/index?center_id={center_id}&msg=paid_mock&booking_id={booking.id}",
        status_code=303,
    )


@router.post("/public/cart/checkout")
def public_cart_checkout(
    request: Request,
    center_id: int = Form(...),
    cart_json: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    try:
        raw_items = json.loads(cart_json)
    except (json.JSONDecodeError, TypeError):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
    if not isinstance(raw_items, list) or not raw_items:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_empty", status_code=303)

    session_ids: list[int] = []
    for it in raw_items:
        if not isinstance(it, dict):
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        if it.get("type") != "session":
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        sid = it.get("session_id")
        if isinstance(sid, str) and sid.strip().isdigit():
            session_ids.append(int(sid.strip()))
        elif isinstance(sid, int):
            session_ids.append(sid)
    seen: set[int] = set()
    deduped: list[int] = []
    for sid in session_ids:
        if sid not in seen:
            seen.add(sid)
            deduped.append(sid)
    session_ids = deduped
    if not session_ids:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_empty", status_code=303)
    if len(session_ids) > MAX_PUBLIC_CART_SESSIONS:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_too_many", status_code=303)

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    bundle: list[tuple[models.Booking, models.Payment, models.YogaSession]] = []
    for session_id in session_ids:
        yoga_session = db.get(models.YogaSession, session_id)
        if not yoga_session or yoga_session.center_id != center_id:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        if spots_available(db, yoga_session) <= 0:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_session_full", status_code=303)
        duplicate = (
            db.query(models.Booking)
            .filter(
                models.Booking.session_id == session_id,
                models.Booking.client_id == client.id,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .first()
        )
        if duplicate:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=duplicate", status_code=303)
        booking = models.Booking(
            center_id=center_id,
            session_id=session_id,
            client_id=client.id,
            status="pending_payment",
        )
        db.add(booking)
        db.flush()
        amount = float(yoga_session.price_drop_in)
        payment_row = models.Payment(
            center_id=center_id,
            client_id=client.id,
            booking_id=booking.id,
            amount=amount,
            currency="SAR",
            payment_method="public_cart_checkout",
            status="pending",
        )
        db.add(payment_row)
        db.flush()
        bundle.append((booking, payment_row, yoga_session))

    db.commit()

    provider = get_payment_provider()
    base = _public_base(request)

    if isinstance(provider, StripePaymentProvider):
        line_specs = [
            (
                float(ys.price_drop_in),
                f"حجز جلسة — {ys.title}"[:120],
                f"{center.name} · {_fmt_dt(ys.starts_at)} · {ys.duration_minutes} دقيقة"[:500],
            )
            for _, _, ys in bundle
        ]
        payment_ids_meta = ",".join(str(p.id) for _, p, _ in bundle)
        try:
            provider_result = provider.create_checkout_session_multi_line(
                currency="sar",
                line_specs=line_specs,
                metadata={
                    "payment_ids": payment_ids_meta,
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                    "cart": "1",
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled",
            )
        except Exception as exc:
            for bk, pay, _ in bundle:
                bk.status = "cancelled"
                pay.status = "failed"
            db.commit()
            log_security_event(
                "public_cart_checkout",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id},
            )
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_error", status_code=303)

        pref = provider_result.provider_ref
        checkout_url = provider_result.checkout_url or ""
        if not pref or not checkout_url:
            for bk, pay, _ in bundle:
                bk.status = "cancelled"
                pay.status = "failed"
            db.commit()
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_no_url", status_code=303)
        for _, pay, _ in bundle:
            pay.provider_ref = pref
        db.commit()
        return RedirectResponse(url=checkout_url, status_code=303)

    total = sum(float(ys.price_drop_in) for _, _, ys in bundle)
    provider_result = provider.charge(
        amount=total,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client.id, "cart": "1"},
    )
    pref = provider_result.provider_ref
    for bk, pay, _ in bundle:
        pay.provider_ref = pref
        if provider_result.status == "paid":
            pay.status = "paid"
            bk.status = "confirmed"
        else:
            pay.status = "failed"
            bk.status = "cancelled"
    db.commit()
    first_bid = bundle[0][0].id if bundle else ""
    return RedirectResponse(
        url=f"/index?center_id={center_id}&msg=paid_mock&booking_id={first_bid}",
        status_code=303,
    )


@router.get("/public/register", response_class=HTMLResponse)
def public_register_page(request: Request, next: str = "/index?center_id=1"):
    safe_next = _sanitize_next_url(request.query_params.get("next") or next)
    return templates.TemplateResponse(
        request,
        "public_register.html",
        {"next": safe_next, **_analytics_context("public_register")},
    )


@router.post("/public/register")
def public_register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    country_code: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    email_normalized = email.lower().strip()
    full_name_normalized = full_name.strip()
    phone_normalized = _normalize_phone_with_country(country_code, phone)
    if (
        not full_name_normalized
        or not email_normalized
        or not password.strip()
        or not phone.strip()
        or not country_code.strip()
    ):
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="required_fields", next=safe_next),
            status_code=303,
        )
    if phone_normalized is None:
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="invalid_phone", next=safe_next),
            status_code=303,
        )
    register_key = _request_key(request, "public_register", email_normalized)
    if not rate_limiter.allow(
        register_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_register", request, "rate_limited", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="rate_limited", next=safe_next),
            status_code=303,
        )
    exists = db.query(models.PublicUser).filter(models.PublicUser.email == email_normalized).first()
    if exists and not exists.is_deleted:
        log_security_event("public_register", request, "already_exists", email=email_normalized)
        return _public_login_redirect(msg="account_exists")
    phone_exists = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.phone == phone_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if phone_exists:
        log_security_event("public_register", request, "phone_already_exists", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="phone_exists", next=safe_next),
            status_code=303,
        )
    if not _is_strong_public_password(password):
        log_security_event("public_register", request, "weak_password", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="weak_password", next=safe_next),
            status_code=303,
        )

    if exists and exists.is_deleted:
        user = exists
        user.full_name = full_name_normalized
        user.email = email_normalized
        user.phone = phone_normalized
        user.password_hash = hash_password(password)
        user.email_verified = not _is_email_verification_required()
        user.verification_sent_at = utcnow_naive()
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        status_label = "restored"
    else:
        user = models.PublicUser(
            full_name=full_name_normalized,
            email=email_normalized,
            phone=phone_normalized,
            password_hash=hash_password(password),
            email_verified=not _is_email_verification_required(),
            verification_sent_at=utcnow_naive(),
            is_active=True,
            is_deleted=False,
        )
        db.add(user)
        status_label = "created"
    db.commit()
    db.refresh(user)

    queued, mail_info = (True, "verification_bypassed")
    if _is_email_verification_required():
        queued, mail_info = _queue_verify_email_for_user(request, user, next_url=safe_next)
    if not queued:
        log_security_event(
            "public_register",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200], "state": status_label},
        )
    else:
        log_security_event(
            "public_register",
            request,
            "success",
            email=user.email,
            details={"mail_status": "queued", "state": status_label},
        )
    token = create_public_access_token(user.id)
    if _is_email_verification_required():
        next_msg = "registered" if queued else "mail_failed"
        vp_params: dict[str, str] = {"msg": next_msg, "next": safe_next}
        if not queued:
            why = public_mail_fail_why_token(mail_info)
            if why:
                vp_params["why"] = why
        response = RedirectResponse(
            url=_url_with_params("/public/verify-pending", **vp_params),
            status_code=303,
        )
    else:
        sep = "&" if "?" in safe_next else "?"
        response = RedirectResponse(url=f"{safe_next}{sep}msg=registered_no_verify", status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/public/login", response_class=HTMLResponse)
def public_login_page(request: Request, next: str = "/index?center_id=1"):
    return templates.TemplateResponse(request, "public_login.html", {"next": next, **_analytics_context("public_login")})


@router.post("/public/login")
def public_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    email_normalized = email.lower().strip()
    login_key = _request_key(request, "public_login", email_normalized)
    if not rate_limiter.allow(
        login_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_login", request, "rate_limited", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="rate_limited")
    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        log_security_event("public_login", request, "invalid_credentials", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="invalid_credentials")
    if not user.is_active:
        log_security_event("public_login", request, "inactive", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="inactive")

    token = create_public_access_token(user.id)
    if _is_email_verification_required() and not user.email_verified:
        response = RedirectResponse(url=_url_with_params("/public/verify-pending", next=safe_next), status_code=303)
    else:
        response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    log_security_event(
        "public_login",
        request,
        "success",
        email=user.email,
        details={"email_verified": user.email_verified},
    )
    return response


@router.get("/public/logout")
def public_logout():
    # Request object is not required for logout, so this event is not logged here.
    response = RedirectResponse(url="/index?center_id=1&msg=logged_out", status_code=303)
    response.delete_cookie(PUBLIC_COOKIE_NAME)
    return response


def _public_account_phone_prefill(user: models.PublicUser) -> tuple[str, str]:
    """(country_code, local_digits) for account form; default +966 if unknown."""
    raw = (user.phone or "").strip()
    if not raw:
        return "+966", ""
    for prefix in ("+966", "+971", "+965", "+973", "+974", "+968", "+20"):
        if raw.startswith(prefix):
            return prefix, raw[len(prefix) :].lstrip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return "+966", digits


@router.get("/public/account", response_class=HTMLResponse)
def public_account_page(request: Request, next: str = "/index?center_id=1", db: Session = Depends(get_db)):
    safe_next = _sanitize_next_url(request.query_params.get("next") or next)
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    cc, phone_local = _public_account_phone_prefill(user)
    try:
        center_id_loyalty = int(public_center_id_str_from_next(safe_next))
    except ValueError:
        center_id_loyalty = 1
    center_loyalty = db.get(models.Center, center_id_loyalty)
    loyalty_ctx = loyalty_context_for_count(
        count_confirmed_sessions_for_public_user(db, center_id_loyalty, user),
        center=center_loyalty,
    )
    return templates.TemplateResponse(
        request,
        "public_account.html",
        {
            "next": safe_next,
            "user": user,
            "country_code": cc,
            "phone_local": phone_local,
            "loyalty_program_rows": loyalty_program_table_rows(center_loyalty),
            **loyalty_ctx,
            **_analytics_context("public_account"),
        },
    )


@router.post("/public/account")
def public_account_update(
    request: Request,
    full_name: str = Form(...),
    country_code: str = Form(...),
    phone: str = Form(...),
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    full_name_n = full_name.strip()
    if not full_name_n or not phone.strip() or not country_code.strip():
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="required_fields", next=safe_next),
            status_code=303,
        )
    phone_n = _normalize_phone_with_country(country_code, phone)
    if phone_n is None:
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="invalid_phone", next=safe_next),
            status_code=303,
        )
    other = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.phone == phone_n,
            models.PublicUser.is_deleted.is_(False),
            models.PublicUser.id != user.id,
        )
        .first()
    )
    if other:
        log_security_event(
            "public_account_update",
            request,
            "phone_conflict",
            email=user.email,
            details={"public_user_id": user.id},
        )
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="phone_exists", next=safe_next),
            status_code=303,
        )
    user.full_name = full_name_n
    user.phone = phone_n
    db.commit()
    log_security_event(
        "public_account_update",
        request,
        "success",
        email=user.email,
        details={"public_user_id": user.id},
    )
    return RedirectResponse(
        url=_url_with_params("/public/account", msg="saved", next=safe_next),
        status_code=303,
    )


@router.get("/public/verify-pending", response_class=HTMLResponse)
def public_verify_pending(request: Request, next: str = "/index?center_id=1", db: Session = Depends(get_db)):
    safe_next = _sanitize_next_url(next)
    msg_param = (request.query_params.get("msg") or "").strip()
    vk_param = (request.query_params.get("vk") or "").strip()
    flash_user = _public_user_from_verify_flash_token(db, vk_param) if msg_param == "email_verified" else None
    user = _current_public_user(request, db)
    if msg_param == "email_verified":
        target: models.PublicUser | None = None
        if flash_user:
            target = flash_user
        elif user and user.email_verified:
            target = user
        if target:
            index_url = public_index_url_from_next(safe_next, msg="email_verified")
            fn = (target.full_name or "").strip().split()
            user_first_name = fn[0] if fn else ""
            response = templates.TemplateResponse(
                request,
                "public_verify_pending.html",
                {
                    "next": safe_next,
                    "user": target,
                    "show_dev_verify_link": False,
                    "dev_verify_url": "",
                    "show_email_verified_success": True,
                    "index_url": index_url,
                    "user_first_name": user_first_name,
                    **_analytics_context("public_verify_pending"),
                },
            )
            if (not user) or user.id != target.id:
                response.set_cookie(
                    key=PUBLIC_COOKIE_NAME,
                    value=create_public_access_token(target.id),
                    httponly=True,
                    samesite="lax",
                    secure=_cookie_secure_flag(request),
                    max_age=60 * 60 * 24 * 7,
                )
            return response
    if not user:
        return _public_login_redirect(next_url=safe_next)
    if not _is_email_verification_required():
        return RedirectResponse(url=public_index_url_from_next(safe_next), status_code=303)
    if user.email_verified:
        return RedirectResponse(url=public_index_url_from_next(safe_next), status_code=303)
    show_dev_verify_link = _is_truthy_env(os.getenv("SHOW_DEV_VERIFY_LINK"))
    dev_verify_url = _build_verify_url(request, user, next_url=safe_next) if show_dev_verify_link else ""
    return templates.TemplateResponse(
        request,
        "public_verify_pending.html",
        {
            "next": safe_next,
            "user": user,
            "show_dev_verify_link": show_dev_verify_link,
            "dev_verify_url": dev_verify_url,
            "show_email_verified_success": False,
            **_analytics_context("public_verify_pending"),
        },
    )


@router.post("/public/resend-verification")
def public_resend_verification(
    request: Request,
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    resend_key = _request_key(request, "public_resend_verify")
    if not rate_limiter.allow(
        resend_key,
        limit=6,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_resend_verification", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="rate_limited", next=safe_next),
            status_code=303,
        )
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    now = utcnow_naive()
    if user.verification_sent_at and (now - user.verification_sent_at).total_seconds() < 60:
        log_security_event("public_resend_verification", request, "too_soon", email=user.email)
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="resend_too_soon", next=safe_next),
            status_code=303,
        )
    user.verification_sent_at = now
    db.commit()
    queued, mail_info = _queue_verify_email_for_user(request, user, next_url=safe_next)
    if not queued:
        log_security_event(
            "public_resend_verification",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200]},
        )
        why = public_mail_fail_why_token(mail_info)
        vp = {"msg": "mail_failed", "next": safe_next}
        if why:
            vp["why"] = why
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", **vp),
            status_code=303,
        )
    log_security_event(
        "public_resend_verification",
        request,
        "success",
        email=user.email,
        details={"mail_status": "queued"},
    )
    return RedirectResponse(
        url=_url_with_params("/public/verify-pending", msg="resent", next=safe_next),
        status_code=303,
    )


@router.get("/public/verify-email")
def public_verify_email(
    request: Request,
    token: str = "",
    next: str = "/index?center_id=1",
    db: Session = Depends(get_db),
):
    token_value = token.strip().strip("<>").strip('"').strip("'")
    safe_next = _sanitize_next_url(next)
    if not token_value:
        return RedirectResponse(url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next), status_code=303)
    try:
        payload = decode_public_email_verification_token(token_value)
    except HTTPException:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="expired_link", next=safe_next),
            status_code=303,
        )
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    session_token = create_public_access_token(user.id)
    flash_token = create_public_email_verify_flash_token(user.id, user.email)
    response = RedirectResponse(
        url=_url_with_params("/public/verify-pending", msg="email_verified", next=safe_next, vk=flash_token),
        status_code=303,
    )
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    log_security_event(
        "public_verify_email",
        request,
        "success",
        email=user.email,
        details={"public_user_id": user.id},
    )
    return response


@router.get("/public/forgot-password", response_class=HTMLResponse)
def public_forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "public_forgot_password.html", _analytics_context("public_forgot_password"))


@router.post("/public/forgot-password")
def public_forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    email_normalized = email.lower().strip()
    forgot_key = _request_key(request, "public_forgot_password", email_normalized)
    if not rate_limiter.allow(
        forgot_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_forgot_password", request, "rate_limited", email=email_normalized)
        return RedirectResponse(url="/public/forgot-password?msg=rate_limited", status_code=303)

    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    mail_sent = False
    if user and user.is_active:
        reset_url = _build_reset_url(request, user)
        mail_sent, mail_info = queue_password_reset_email(user.email, reset_url, full_name=user.full_name)
        if not mail_sent:
            log_security_event(
                "public_forgot_password",
                request,
                "mail_failed",
                email=email_normalized,
                details={"mail_error": mail_info[:200]},
            )
    log_security_event("public_forgot_password", request, "accepted", email=email_normalized)
    # Keep response neutral, but surface delivery issue when sending fails for an existing account.
    if user and user.is_active and not mail_sent:
        why = public_mail_fail_why_token(mail_info)
        fp = {"msg": "mail_failed"}
        if why:
            fp["why"] = why
        return RedirectResponse(
            url=_url_with_params("/public/forgot-password", **fp),
            status_code=303,
        )
    return RedirectResponse(url="/public/forgot-password?msg=sent", status_code=303)


@router.get("/public/reset-password", response_class=HTMLResponse)
def public_reset_password_page(request: Request, token: str | None = None):
    raw = (token or "").strip()
    token_valid = False
    if raw:
        try:
            decode_public_password_reset_token(raw)
            token_valid = True
        except HTTPException:
            token_valid = False
    return templates.TemplateResponse(
        request,
        "public_reset_password.html",
        {
            "token": raw if token_valid else "",
            "reset_token_missing": not raw,
            "reset_token_invalid": bool(raw) and not token_valid,
            **_analytics_context("public_reset_password"),
        },
    )


@router.post("/public/reset-password")
def public_reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    reset_key = _request_key(request, "public_reset_password")
    if not rate_limiter.allow(
        reset_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_reset_password", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="rate_limited"),
            status_code=303,
        )
    if not _is_strong_public_password(password):
        log_security_event("public_reset_password", request, "weak_password")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="weak_password"),
            status_code=303,
        )
    if password != confirm_password:
        log_security_event("public_reset_password", request, "password_mismatch")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="password_mismatch"),
            status_code=303,
        )

    try:
        payload = decode_public_password_reset_token(token)
        user_id = int(payload.get("sub"))
    except (HTTPException, TypeError, ValueError):
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")

    user.password_hash = hash_password(password)
    user.is_active = True
    db.commit()
    log_security_event("public_reset_password", request, "success", email=user.email)
    return _public_login_redirect(msg="password_reset_success")


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    # Ensure there is at least one admin-capable user in fresh installs.
    ensure_demo_data(db)
    return templates.TemplateResponse(request, "admin_login.html", {})


@router.post("/admin/login")
def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = (email or "").strip().lower()
    user = db.query(models.User).filter(models.User.email == email_norm).first()
    if not user or not verify_password(password, user.password_hash):
        log_security_event(
            "admin_login",
            request,
            "invalid_credentials",
            email=email_norm,
        )
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
    if user.role not in ("center_owner", "center_staff", "trainer"):
        log_security_event(
            "admin_login",
            request,
            "forbidden_role",
            email=user.email,
        )
        return RedirectResponse(url="/admin/login?error=role", status_code=303)

    log_security_event("admin_login", request, "success", email=user.email)
    token = create_access_token(user.id)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 12,
    )
    return response


@router.get("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    msg: str | None = None,
    room_sort: str = "id_asc",
    public_user_q: str = "",
    public_user_status: str = "active",
    public_user_verified: str = "all",
    public_user_page: int = 1,
    sessions_page: int = 1,
    payments_page: int = 1,
    audit_event_type: str = "",
    audit_status: str = "",
    audit_email: str = "",
    audit_ip: str = "",
    audit_page: int = 1,
    payment_date_from: str = "",
    payment_date_to: str = "",
    post_edit: int = 0,
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if center:
        if center.name == DEMO_CENTER_NAME:
            ensure_demo_news_posts(db, center.id)
        _clear_center_branding_urls_if_files_missing(db, center)
    room_sort_key = (room_sort or "id_asc").strip().lower()
    room_ordering = {
        "id_asc": (models.Room.id.asc(),),
        "name": (models.Room.name.asc(), models.Room.id.asc()),
        "newest": (models.Room.id.desc(),),
        "capacity_desc": (models.Room.capacity.desc(), models.Room.name.asc(), models.Room.id.asc()),
        "capacity_asc": (models.Room.capacity.asc(), models.Room.name.asc(), models.Room.id.asc()),
    }
    if room_sort_key in {"sessions_desc", "sessions_asc"}:
        session_count_order = (
            func.count(models.YogaSession.id).desc()
            if room_sort_key == "sessions_desc"
            else func.count(models.YogaSession.id).asc()
        )
        rooms = (
            db.query(models.Room)
            .outerjoin(
                models.YogaSession,
                and_(
                    models.YogaSession.room_id == models.Room.id,
                    models.YogaSession.center_id == cid,
                ),
            )
            .filter(models.Room.center_id == cid)
            .group_by(models.Room.id)
            .order_by(session_count_order, models.Room.name.asc(), models.Room.id.asc())
            .all()
        )
    else:
        room_order_by = room_ordering.get(room_sort_key, room_ordering["id_asc"])
        rooms = (
            db.query(models.Room)
            .filter(models.Room.center_id == cid)
            .order_by(*room_order_by)
            .all()
        )
    plans = (
        db.query(models.SubscriptionPlan)
        .filter(models.SubscriptionPlan.center_id == cid)
        .order_by(models.SubscriptionPlan.price.asc())
        .all()
    )
    rooms_by_id = {r.id: r for r in rooms}

    def _normalize_page(page_value: int, total_items: int, page_size: int) -> tuple[int, int, int]:
        safe_page = max(1, int(page_value or 1))
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        if safe_page > total_pages:
            safe_page = total_pages
        offset = (safe_page - 1) * page_size
        return safe_page, total_pages, offset

    sessions_page_size = ADMIN_SESSIONS_PAGE_SIZE
    sessions_base_query = db.query(models.YogaSession).filter(models.YogaSession.center_id == cid)
    sessions_total = sessions_base_query.order_by(None).count()
    safe_sessions_page, sessions_total_pages, sessions_offset = _normalize_page(
        sessions_page,
        sessions_total,
        sessions_page_size,
    )
    sessions = (
        sessions_base_query.order_by(models.YogaSession.starts_at.desc())
        .offset(sessions_offset)
        .limit(sessions_page_size)
        .all()
    )
    faqs = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == cid)
        .order_by(models.FAQItem.sort_order.asc(), models.FAQItem.created_at.asc())
        .all()
    )
    public_users_query = db.query(models.PublicUser)
    q = public_user_q.strip()
    if q:
        public_users_query = public_users_query.filter(
            or_(
                models.PublicUser.full_name.ilike(f"%{q}%"),
                models.PublicUser.email.ilike(f"%{q}%"),
                models.PublicUser.phone.ilike(f"%{q}%"),
            )
        )
    status_key = public_user_status.strip().lower() or "active"
    if status_key == "deleted":
        public_users_query = public_users_query.filter(models.PublicUser.is_deleted.is_(True))
    elif status_key == "inactive":
        public_users_query = public_users_query.filter(
            models.PublicUser.is_deleted.is_(False), models.PublicUser.is_active.is_(False)
        )
    else:
        public_users_query = public_users_query.filter(
            models.PublicUser.is_deleted.is_(False), models.PublicUser.is_active.is_(True)
        )
    verified_key = public_user_verified.strip().lower()
    if verified_key == "verified":
        public_users_query = public_users_query.filter(models.PublicUser.email_verified.is_(True))
    elif verified_key == "unverified":
        public_users_query = public_users_query.filter(models.PublicUser.email_verified.is_(False))
    public_users_page_size = ADMIN_PUBLIC_USERS_PAGE_SIZE
    public_users_total = public_users_query.order_by(None).count()
    safe_public_user_page, public_users_total_pages, public_users_offset = _normalize_page(
        public_user_page,
        public_users_total,
        public_users_page_size,
    )
    public_users = (
        public_users_query.order_by(models.PublicUser.created_at.desc())
        .offset(public_users_offset)
        .limit(public_users_page_size)
        .all()
    )
    session_rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        session_rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "room_id": s.room_id,
                "spots_available": spots_available(db, s),
                "capacity": room.capacity if room else 0,
            }
        )
    plan_labels = {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }
    plan_rows = [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
            "price": p.price,
            "session_limit": p.session_limit,
            "is_active": p.is_active,
        }
        for p in plans
    ]

    today = utcnow_naive().date()
    tomorrow_d = today + timedelta(days=1)
    now_na = utcnow_naive()
    payment_from_dt = _parse_optional_date_str(payment_date_from)
    payment_to_dt = _parse_optional_date_str(payment_date_to)

    sessions_today_no_bookings = (
        db.query(models.YogaSession.id)
        .outerjoin(
            models.Booking,
            and_(
                models.Booking.session_id == models.YogaSession.id,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            ),
        )
        .filter(
            models.YogaSession.center_id == cid,
            func.date(models.YogaSession.starts_at) == today,
        )
        .group_by(models.YogaSession.id)
        .having(func.count(models.Booking.id) == 0)
        .count()
    )
    subs_expiring_7d = (
        db.query(models.ClientSubscription)
        .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
        .filter(
            models.Client.center_id == cid,
            models.ClientSubscription.status == "active",
            models.ClientSubscription.end_date >= now_na,
            models.ClientSubscription.end_date <= now_na + timedelta(days=7),
        )
        .count()
    )
    public_users_unverified_count = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.is_deleted.is_(False),
            models.PublicUser.is_active.is_(True),
            models.PublicUser.email_verified.is_(False),
        )
        .count()
    )

    revenue_7d_bars: list[dict[str, Any]] = []
    max_rev_7d = 0.01
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        amt = float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "paid",
                func.date(models.Payment.paid_at) == d,
            )
            .scalar()
            or 0.0
        )
        revenue_7d_bars.append({"date_iso": d.isoformat(), "amount": amt, "label": f"{d.day}/{d.month}"})
        max_rev_7d = max(max_rev_7d, amt)
    for bar in revenue_7d_bars:
        bar["bar_pct"] = int(round(100 * float(bar["amount"]) / max_rev_7d)) if max_rev_7d > 0 else 0

    ops_sessions_q = (
        db.query(models.YogaSession)
        .filter(
            models.YogaSession.center_id == cid,
            or_(
                func.date(models.YogaSession.starts_at) == today,
                func.date(models.YogaSession.starts_at) == tomorrow_d,
            ),
        )
        .order_by(models.YogaSession.starts_at.asc())
        .limit(36)
        .all()
    )
    ops_today_rows: list[dict[str, str | int]] = []
    ops_tomorrow_rows: list[dict[str, str | int]] = []
    for s in ops_sessions_q:
        room = rooms_by_id.get(s.room_id)
        row = {
            "id": s.id,
            "title": s.title,
            "trainer": s.trainer_name,
            "room": room.name if room else "-",
            "starts": _fmt_dt(s.starts_at),
            "spots": spots_available(db, s),
            "capacity": room.capacity if room else 0,
        }
        if s.starts_at.date() == today:
            ops_today_rows.append(row)
        elif s.starts_at.date() == tomorrow_d:
            ops_tomorrow_rows.append(row)

    window_start = now_na - timedelta(hours=6)
    future_for_conflicts = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.starts_at >= window_start)
        .order_by(models.YogaSession.room_id, models.YogaSession.starts_at)
        .all()
    )
    by_room_sessions: dict[int, list[models.YogaSession]] = defaultdict(list)
    for s in future_for_conflicts:
        by_room_sessions[s.room_id].append(s)
    schedule_conflicts: list[dict[str, str | int]] = []
    for rid, lst in by_room_sessions.items():
        lst.sort(key=lambda x: x.starts_at)
        for i in range(len(lst) - 1):
            a, b = lst[i], lst[i + 1]
            end_a = a.starts_at + timedelta(minutes=int(a.duration_minutes or 0))
            if end_a > b.starts_at:
                schedule_conflicts.append(
                    {
                        "room_name": (rooms_by_id.get(rid).name if rooms_by_id.get(rid) else f"غرفة #{rid}"),
                        "a_id": a.id,
                        "a_title": a.title,
                        "a_start": _fmt_dt(a.starts_at),
                        "b_id": b.id,
                        "b_title": b.title,
                        "b_start": _fmt_dt(b.starts_at),
                    }
                )

    admin_login_audit_rows = [
        {
            "created_at_display": _fmt_dt(ev.created_at),
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
        }
        for ev in db.query(models.SecurityAuditEvent)
        .filter(models.SecurityAuditEvent.event_type == "admin_login")
        .order_by(models.SecurityAuditEvent.created_at.desc())
        .limit(20)
        .all()
    ]

    recent_public_cutoff = utcnow_naive() - timedelta(days=7)
    paid_revenue_total, paid_revenue_today = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (models.Payment.status == "paid", models.Payment.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Payment.status == "paid",
                                func.date(models.Payment.paid_at) == today,
                            ),
                            models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        )
        .filter(models.Payment.center_id == cid)
        .one()
    )
    public_users_count, public_users_deleted_count, public_users_new_7d = (
        db.query(
            func.count(models.PublicUser.id),
            func.coalesce(
                func.sum(case((models.PublicUser.is_deleted.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.PublicUser.created_at >= recent_public_cutoff,
                                models.PublicUser.is_deleted.is_(False),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).one()
    )
    dashboard = {
        "rooms_count": len(rooms),
        "sessions_count": sessions_total,
        "bookings_count": db.query(models.Booking).filter(models.Booking.center_id == cid).count(),
        "clients_count": db.query(models.Client).filter(models.Client.center_id == cid).count(),
        "active_plans_count": sum(1 for p in plans if p.is_active),
        "active_subscriptions_count": (
            db.query(models.ClientSubscription)
            .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
            .filter(
                models.Client.center_id == cid,
                models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(paid_revenue_total or 0.0),
        "revenue_today": float(paid_revenue_today or 0.0),
        "public_users_count": int(public_users_count) - int(public_users_deleted_count),
        "public_users_deleted_count": int(public_users_deleted_count),
        "public_users_new_7d": int(public_users_new_7d),
    }
    payments_page_size = ADMIN_PAYMENTS_PAGE_SIZE
    payments_base_query = db.query(models.Payment).filter(models.Payment.center_id == cid)
    if payment_from_dt:
        payments_base_query = payments_base_query.filter(func.date(models.Payment.paid_at) >= payment_from_dt)
    if payment_to_dt:
        payments_base_query = payments_base_query.filter(func.date(models.Payment.paid_at) <= payment_to_dt)
    payments_total = payments_base_query.order_by(None).count()
    safe_payments_page, payments_total_pages, payments_offset = _normalize_page(
        payments_page,
        payments_total,
        payments_page_size,
    )
    recent_payments = (
        payments_base_query.order_by(models.Payment.paid_at.desc())
        .offset(payments_offset)
        .limit(payments_page_size)
        .all()
    )
    client_ids = [p.client_id for p in recent_payments]
    clients_by_id = {
        c.id: c
        for c in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all()
    }
    status_labels = {
        "paid": "مدفوع",
        "pending": "قيد الانتظار",
        "failed": "فشل",
    }
    payment_rows = []
    for pay in recent_payments:
        client = clients_by_id.get(pay.client_id)
        payment_rows.append(
            {
                "id": pay.id,
                "client_name": client.full_name if client else f"عميل #{pay.client_id}",
                "payment_method": pay.payment_method,
                "amount": pay.amount,
                "currency": pay.currency,
                "status": pay.status,
                "status_label": status_labels.get(pay.status, pay.status),
                "paid_at_display": _fmt_dt(pay.paid_at),
            }
        )
    loyalty_by_email = loyalty_confirmed_counts_by_email_lower(db, cid)
    public_user_rows = []
    for u in public_users:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = loyalty_context_for_count(cnt, center=center)
        public_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone or "-",
                "is_active": u.is_active,
                "email_verified": u.email_verified,
                "is_deleted": bool(u.is_deleted),
                "deleted_at_display": _fmt_dt(u.deleted_at),
                "created_at_display": _fmt_dt(u.created_at),
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
    faq_rows = [
        {
            "id": f.id,
            "question": f.question,
            "answer": f.answer,
            "sort_order": f.sort_order,
            "is_active": f.is_active,
        }
        for f in faqs
    ]

    audit_query = db.query(models.SecurityAuditEvent)
    if audit_event_type.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%"))
    if audit_ip.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))

    audit_page_size = ADMIN_SECURITY_AUDIT_PAGE_SIZE
    security_events_total = audit_query.order_by(None).count()
    safe_audit_page, security_events_total_pages, security_events_offset = _normalize_page(
        audit_page,
        security_events_total,
        audit_page_size,
    )
    security_events = (
        audit_query.order_by(models.SecurityAuditEvent.created_at.desc())
        .offset(security_events_offset)
        .limit(audit_page_size)
        .all()
    )
    security_event_rows = [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
            "path": ev.path or "-",
            "details": ev.details_json or "{}",
            "created_at_display": _fmt_dt(ev.created_at),
        }
        for ev in security_events
    ]
    high_risk_since = utcnow_naive() - timedelta(hours=24)
    failed_logins_24h = (
        db.query(models.SecurityAuditEvent)
        .filter(
            models.SecurityAuditEvent.event_type == "public_login",
            models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .count()
    )
    suspicious_ips = (
        db.query(models.SecurityAuditEvent.ip, func.count(models.SecurityAuditEvent.id).label("hits"))
        .filter(
            models.SecurityAuditEvent.event_type == "public_login",
            models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .group_by(models.SecurityAuditEvent.ip)
        .having(func.count(models.SecurityAuditEvent.id) >= 5)
        .order_by(func.count(models.SecurityAuditEvent.id).desc())
        .limit(5)
        .all()
    )
    blocked_ips = (
        db.query(models.BlockedIP)
        .filter(
            models.BlockedIP.is_active.is_(True),
            or_(models.BlockedIP.blocked_until.is_(None), models.BlockedIP.blocked_until > utcnow_naive()),
        )
        .order_by(models.BlockedIP.created_at.desc())
        .limit(20)
        .all()
    )

    def _risk_level(hits: int) -> str:
        if hits >= 12:
            return "high"
        if hits >= 5:
            return "medium"
        return "low"

    security_summary = {
        "failed_logins_24h": failed_logins_24h,
        "suspicious_ips": [
            {"ip": ip or "-", "hits": int(hits), "risk_level": _risk_level(int(hits))}
            for ip, hits in suspicious_ips
        ],
        "blocked_ips": [
            {
                "ip": b.ip,
                "reason": b.reason or "-",
                "blocked_until": _fmt_dt(b.blocked_until) if b.blocked_until else "دائم",
            }
            for b in blocked_ips
        ],
    }
    block_history_events = (
        db.query(models.SecurityAuditEvent)
        .filter(models.SecurityAuditEvent.event_type.in_(["admin_ip_block", "admin_ip_unblock"]))
        .order_by(models.SecurityAuditEvent.created_at.desc())
        .limit(120)
        .all()
    )
    block_history_rows = []
    for ev in block_history_events:
        details = {}
        if ev.details_json:
            try:
                details = json.loads(ev.details_json)
            except (TypeError, ValueError):
                details = {}
        block_history_rows.append(
            {
                "id": ev.id,
                "created_at_display": _fmt_dt(ev.created_at),
                "event_type": ev.event_type,
                "status": ev.status,
                "admin_email": ev.email or "-",
                "target_ip": details.get("target_ip", "-"),
                "minutes": details.get("minutes", "-"),
                "reason": details.get("reason", "-"),
            }
        )
    security_export_url = _url_with_params(
        "/admin/security/export/csv",
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
    )
    admin_flash = None
    if msg:
        flash_data = ADMIN_FLASH_MESSAGES.get(msg)
        if flash_data:
            text, level = flash_data
            admin_flash = {"text": text, "level": level}

    base_admin_params = {
        ADMIN_QP_ROOM_SORT: room_sort,
        ADMIN_QP_PUBLIC_USER_Q: public_user_q,
        ADMIN_QP_PUBLIC_USER_STATUS: public_user_status,
        ADMIN_QP_PUBLIC_USER_VERIFIED: public_user_verified,
        ADMIN_QP_PUBLIC_USER_PAGE: str(safe_public_user_page),
        ADMIN_QP_SESSIONS_PAGE: str(safe_sessions_page),
        ADMIN_QP_PAYMENTS_PAGE: str(safe_payments_page),
        ADMIN_QP_AUDIT_EVENT_TYPE: audit_event_type,
        ADMIN_QP_AUDIT_STATUS: audit_status,
        ADMIN_QP_AUDIT_EMAIL: audit_email,
        ADMIN_QP_AUDIT_IP: audit_ip,
        ADMIN_QP_AUDIT_PAGE: str(safe_audit_page),
        ADMIN_QP_PAYMENT_DATE_FROM: (payment_date_from or "").strip()[:32],
        ADMIN_QP_PAYMENT_DATE_TO: (payment_date_to or "").strip()[:32],
    }

    def _admin_page_url(**overrides: str) -> str:
        params = dict(base_admin_params)
        for k, v in overrides.items():
            params[k] = v
        return _url_with_params("/admin", **params)

    public_users_page_prev_url = _admin_page_url(**{ADMIN_QP_PUBLIC_USER_PAGE: str(max(1, safe_public_user_page - 1))})
    public_users_page_next_url = _admin_page_url(
        **{ADMIN_QP_PUBLIC_USER_PAGE: str(min(public_users_total_pages, safe_public_user_page + 1))}
    )
    security_page_prev_url = _admin_page_url(**{ADMIN_QP_AUDIT_PAGE: str(max(1, safe_audit_page - 1))})
    security_page_next_url = _admin_page_url(
        **{ADMIN_QP_AUDIT_PAGE: str(min(security_events_total_pages, safe_audit_page + 1))}
    )
    sessions_page_prev_url = _admin_page_url(**{ADMIN_QP_SESSIONS_PAGE: str(max(1, safe_sessions_page - 1))})
    sessions_page_next_url = _admin_page_url(
        **{ADMIN_QP_SESSIONS_PAGE: str(min(sessions_total_pages, safe_sessions_page + 1))}
    )
    payments_page_prev_url = _admin_page_url(**{ADMIN_QP_PAYMENTS_PAGE: str(max(1, safe_payments_page - 1))})
    payments_page_next_url = _admin_page_url(
        **{ADMIN_QP_PAYMENTS_PAGE: str(min(payments_total_pages, safe_payments_page + 1))}
    )

    safe_post_edit = max(0, int(post_edit or 0))
    center_posts_all = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.center_id == cid)
        .order_by(models.CenterPost.updated_at.desc())
        .all()
    )

    def _post_admin_edit_url(edit_id: int) -> str:
        return _admin_page_url(**{ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"

    center_post_admin_rows: list[dict[str, str | int | bool]] = []
    for cp in center_posts_all:
        center_post_admin_rows.append(
            {
                "id": cp.id,
                "title": cp.title,
                "post_type": cp.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                "is_published": cp.is_published,
                "is_pinned": cp.is_pinned,
                "updated_display": _fmt_dt(cp.updated_at),
                "gallery_count": len(cp.images),
                "public_url": _url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                if cp.is_published
                else "",
                "edit_url": _post_admin_edit_url(cp.id),
            }
        )

    editing_post: dict[str, Any] | None = None
    if safe_post_edit:
        ep = db.get(models.CenterPost, safe_post_edit)
        if ep and ep.center_id == cid:
            gi = sorted(ep.images, key=lambda x: (x.sort_order, x.id))
            editing_post = {
                "id": ep.id,
                "title": ep.title,
                "summary": ep.summary or "",
                "body": ep.body or "",
                "post_type": ep.post_type,
                "is_pinned": ep.is_pinned,
                "is_published": ep.is_published,
                "cover_image_url": ep.cover_image_url or "",
                "gallery": [{"id": g.id, "url": g.image_url} for g in gi],
            }

    center_post_type_choices = [
        {"value": k, "label": v} for k, v in sorted(CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
    ]

    dash_home = _admin_page_url()
    admin_insights: list[dict[str, str]] = []
    if sessions_today_no_bookings:
        admin_insights.append(
            {
                "label": f"جلسات اليوم بلا حجوزات نشطة: {sessions_today_no_bookings}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )
    if subs_expiring_7d:
        admin_insights.append(
            {
                "label": f"اشتراكات تنتهي خلال 7 أيام: {subs_expiring_7d}",
                "href": f"{dash_home}#section-plans",
                "kind": "info",
            }
        )
    if public_users_unverified_count:
        admin_insights.append(
            {
                "label": f"مستخدمو جمهور غير موثّقين (عام): {public_users_unverified_count}",
                "href": f"{dash_home}#section-public-users",
                "kind": "info",
            }
        )
    if schedule_conflicts:
        admin_insights.append(
            {
                "label": f"تضارب جدولة في نفس الغرفة: {len(schedule_conflicts)}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )

    export_pay_params: dict[str, str] = {}
    pf = (payment_date_from or "").strip()[:32]
    pt = (payment_date_to or "").strip()[:32]
    if pf:
        export_pay_params[ADMIN_QP_PAYMENT_DATE_FROM] = pf
    if pt:
        export_pay_params[ADMIN_QP_PAYMENT_DATE_TO] = pt
    data_export_urls = {
        "clients": "/admin/export/clients.csv",
        "bookings": "/admin/export/bookings.csv",
        "payments": _url_with_params("/admin/export/payments.csv", **export_pay_params)
        if export_pay_params
        else "/admin/export/payments.csv",
    }

    _env_b, _env_s, _env_g = loyalty_thresholds()
    _eff_b, _eff_s, _eff_g = effective_loyalty_thresholds(center)
    loyalty_admin = {
        "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
        "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
    }

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "center": center,
            "msg": msg,
            "admin_flash": admin_flash,
            "dashboard": dashboard,
            "rooms": rooms,
            "plans": plan_rows,
            "sessions": session_rows,
            "recent_payments": payment_rows,
            "public_users": public_user_rows,
            "faq_items": faq_rows,
            "security_events": security_event_rows,
            "security_summary": security_summary,
            "security_export_url": security_export_url,
            "block_history": block_history_rows,
            "security_filters": {
                "event_type": audit_event_type,
                "status": audit_status,
                "email": audit_email,
                "ip": audit_ip,
            },
            "public_user_filters": {
                "q": public_user_q,
                "status": status_key,
                "verified": verified_key or "all",
            },
            "public_user_pagination": {
                "page": safe_public_user_page,
                "page_size": public_users_page_size,
                "total": public_users_total,
                "total_pages": public_users_total_pages,
                "has_prev": safe_public_user_page > 1,
                "has_next": safe_public_user_page < public_users_total_pages,
                "prev_url": public_users_page_prev_url,
                "next_url": public_users_page_next_url,
            },
            "security_pagination": {
                "page": safe_audit_page,
                "page_size": audit_page_size,
                "total": security_events_total,
                "total_pages": security_events_total_pages,
                "has_prev": safe_audit_page > 1,
                "has_next": safe_audit_page < security_events_total_pages,
                "prev_url": security_page_prev_url,
                "next_url": security_page_next_url,
            },
            "sessions_pagination": {
                "page": safe_sessions_page,
                "page_size": sessions_page_size,
                "total": sessions_total,
                "total_pages": sessions_total_pages,
                "has_prev": safe_sessions_page > 1,
                "has_next": safe_sessions_page < sessions_total_pages,
                "prev_url": sessions_page_prev_url,
                "next_url": sessions_page_next_url,
            },
            "payments_pagination": {
                "page": safe_payments_page,
                "page_size": payments_page_size,
                "total": payments_total,
                "total_pages": payments_total_pages,
                "has_prev": safe_payments_page > 1,
                "has_next": safe_payments_page < payments_total_pages,
                "prev_url": payments_page_prev_url,
                "next_url": payments_page_next_url,
            },
            "room_filters": {
                "sort": (
                    room_sort_key
                    if room_sort_key in room_ordering or room_sort_key in {"sessions_desc", "sessions_asc"}
                    else "id_asc"
                ),
            },
            "center_id": cid,
            "admin_public_index_url": _url_with_params("/index", center_id=str(cid)),
            "admin_insights": admin_insights,
            "revenue_7d_bars": revenue_7d_bars,
            "ops_today_rows": ops_today_rows,
            "ops_tomorrow_rows": ops_tomorrow_rows,
            "schedule_conflicts": schedule_conflicts,
            "admin_login_audit_rows": admin_login_audit_rows,
            "data_export_urls": data_export_urls,
            "payment_date_from_value": pf,
            "payment_date_to_value": pt,
            "loyalty_admin": loyalty_admin,
            "is_trainer": user.role == "trainer",
            "is_center_owner": user.role == "center_owner",
            "show_security_section": user.role == "center_owner",
            "center_post_admin_rows": center_post_admin_rows,
            "editing_post": editing_post,
            "center_post_type_choices": center_post_type_choices,
            "post_edit_id": safe_post_edit,
        },
    )


def _admin_user_for_data_export(
    request: Request, db: Session
) -> tuple[models.User | None, RedirectResponse | None]:
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return None, redirect
    assert user is not None
    if user.role == "trainer":
        return None, _trainer_forbidden_redirect()
    return user, None


@router.get("/admin/export/clients.csv")
def export_clients_csv(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    rows = (
        db.query(models.Client)
        .filter(models.Client.center_id == cid)
        .order_by(models.Client.created_at.desc())
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "full_name", "email", "phone", "created_at"])
    for c in rows:
        writer.writerow(
            [
                c.id,
                c.full_name,
                c.email,
                c.phone or "",
                c.created_at.isoformat() if c.created_at else "",
            ]
        )
    content = "\ufeff" + output.getvalue()
    output.close()
    fn = f"clients_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/admin/export/bookings.csv")
def export_bookings_csv(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    q = (
        db.query(models.Booking, models.YogaSession, models.Client)
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .join(models.Client, models.Client.id == models.Booking.client_id)
        .filter(models.Booking.center_id == cid)
        .order_by(models.Booking.booked_at.desc())
        .limit(50_000)
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "booking_id",
            "status",
            "booked_at",
            "session_id",
            "session_title",
            "session_starts_at",
            "client_id",
            "client_name",
            "client_email",
        ]
    )
    for bk, sess, cl in q:
        writer.writerow(
            [
                bk.id,
                bk.status,
                bk.booked_at.isoformat() if bk.booked_at else "",
                sess.id,
                sess.title,
                sess.starts_at.isoformat() if sess.starts_at else "",
                cl.id,
                cl.full_name,
                cl.email,
            ]
        )
    content = "\ufeff" + output.getvalue()
    output.close()
    fn = f"bookings_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/admin/export/payments.csv")
def export_payments_csv(
    request: Request,
    payment_date_from: str = "",
    payment_date_to: str = "",
    db: Session = Depends(get_db),
):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    pq = db.query(models.Payment).filter(models.Payment.center_id == cid)
    pdf = _parse_optional_date_str(payment_date_from)
    pdt = _parse_optional_date_str(payment_date_to)
    if pdf:
        pq = pq.filter(func.date(models.Payment.paid_at) >= pdf)
    if pdt:
        pq = pq.filter(func.date(models.Payment.paid_at) <= pdt)
    rows = pq.order_by(models.Payment.paid_at.desc()).limit(50_000).all()
    client_ids = list({p.client_id for p in rows})
    clients_map = {
        c.id: c
        for c in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all()
    } if client_ids else {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["payment_id", "client_id", "client_name", "amount", "currency", "status", "method", "paid_at", "booking_id"]
    )
    for p in rows:
        cl = clients_map.get(p.client_id)
        writer.writerow(
            [
                p.id,
                p.client_id,
                cl.full_name if cl else "",
                p.amount,
                p.currency,
                p.status,
                p.payment_method,
                p.paid_at.isoformat() if p.paid_at else "",
                p.booking_id or "",
            ]
        )
    content = "\ufeff" + output.getvalue()
    output.close()
    fn = f"payments_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/admin/security/export/csv")
def export_security_events_csv(
    request: Request,
    audit_event_type: str = "",
    audit_status: str = "",
    audit_email: str = "",
    audit_ip: str = "",
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect()

    query = db.query(models.SecurityAuditEvent)
    if audit_event_type.strip():
        query = query.filter(models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        query = query.filter(models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        query = query.filter(models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%"))
    if audit_ip.strip():
        query = query.filter(models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))
    events = query.order_by(models.SecurityAuditEvent.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "event_type", "status", "email", "ip", "path", "details_json"])
    for ev in events:
        writer.writerow(
            [
                ev.id,
                ev.created_at.isoformat() if ev.created_at else "",
                ev.event_type,
                ev.status,
                ev.email or "",
                ev.ip or "",
                ev.path or "",
                ev.details_json or "",
            ]
        )
    filename = f"security_audit_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    content = output.getvalue()
    output.close()
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/admin/security/ip-block")
def admin_block_ip(
    request: Request,
    ip: str = Form(...),
    minutes: int = Form(ADMIN_IP_BLOCK_DEFAULT_MINUTES),
    reason: str = Form("manual_block"),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect(return_section)

    target_ip = ip.strip()
    if not target_ip:
        return _admin_redirect(ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
    if minutes <= 0:
        minutes = ADMIN_IP_BLOCK_DEFAULT_MINUTES
    if minutes > ADMIN_IP_BLOCK_MAX_MINUTES:
        minutes = ADMIN_IP_BLOCK_MAX_MINUTES
    blocked_until = utcnow_naive() + timedelta(minutes=minutes)

    row = db.query(models.BlockedIP).filter(models.BlockedIP.ip == target_ip).first()
    if not row:
        row = models.BlockedIP(
            ip=target_ip,
            reason=reason[:255],
            blocked_until=blocked_until,
            is_active=True,
        )
        db.add(row)
    else:
        row.reason = reason[:255]
        row.blocked_until = blocked_until
        row.is_active = True
    db.commit()
    log_security_event(
        "admin_ip_block",
        request,
        "success",
        email=user.email,
        details={"target_ip": target_ip, "minutes": minutes, "reason": reason[:255]},
    )
    return _admin_redirect(ADMIN_MSG_IP_BLOCKED, return_section=return_section)


@router.post("/admin/security/ip-unblock")
def admin_unblock_ip(
    request: Request,
    ip: str = Form(...),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect(return_section)
    target_ip = ip.strip()
    if not target_ip:
        return _admin_redirect(ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
    row = db.query(models.BlockedIP).filter(models.BlockedIP.ip == target_ip).first()
    if not row:
        return _admin_redirect(ADMIN_MSG_IP_UNBLOCK_NOT_FOUND, return_section=return_section)
    row.is_active = False
    db.commit()
    log_security_event(
        "admin_ip_unblock",
        request,
        "success",
        email=user.email,
        details={"target_ip": target_ip, "reason": "manual_unblock"},
    )
    return _admin_redirect(ADMIN_MSG_IP_UNBLOCKED, return_section=return_section)


@router.post("/admin/public-users/toggle-active")
def admin_toggle_public_user_active(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    row.is_active = not row.is_active
    db.commit()
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)


@router.post("/admin/public-users/toggle-verified")
def admin_toggle_public_user_verified(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    row.email_verified = not row.email_verified
    db.commit()
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)


@router.post("/admin/public-users/delete")
def admin_delete_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    deleted_email, deleted_phone = _soft_delete_public_user(row)
    db.commit()
    log_security_event(
        "admin_public_user_delete",
        request,
        "success",
        email=user.email,
        details={
            "deleted_public_user_id": public_user_id,
            "deleted_email": deleted_email,
            "deleted_phone": deleted_phone,
            "mode": "soft_delete",
        },
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_DELETED, scroll_y, return_section)


@router.post("/admin/public-users/resend-verification")
def admin_resend_public_user_verification(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    if row.email_verified:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_ALREADY_VERIFIED, scroll_y, return_section)

    queued, mail_info = _queue_verify_email_for_user(request, row)
    if not queued:
        log_security_event(
            "admin_public_user_resend_verification",
            request,
            "mail_failed",
            email=admin_user.email,
            details={
                "target_user_id": row.id,
                "target_email": row.email,
                "mail_error": mail_info[:200],
            },
        )
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)

    row.verification_sent_at = utcnow_naive()
    db.commit()
    log_security_event(
        "admin_public_user_resend_verification",
        request,
        "success",
        email=admin_user.email,
        details={"target_user_id": row.id, "target_email": row.email, "mail_status": "queued"},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_RESENT, scroll_y, return_section)


@router.post("/admin/public-users/restore")
def admin_restore_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(
        db, public_user_id, scroll_y, allow_deleted=True, return_section=return_section
    )
    if redirect:
        return redirect
    assert row is not None
    if not row.is_deleted:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)
    row.is_deleted = False
    row.deleted_at = None
    row.is_active = True
    db.commit()
    log_security_event(
        "admin_public_user_restore",
        request,
        "success",
        email=admin_user.email,
        details={"restored_public_user_id": row.id, "restored_email": row.email},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_RESTORED, scroll_y, return_section)


@router.post("/admin/public-users/bulk-action")
def admin_public_users_bulk_action(
    request: Request,
    action: str = Form(...),
    public_user_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    ids = sorted(set(public_user_ids))
    if not ids:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_NONE_SELECTED, scroll_y, return_section)
    rows = db.query(models.PublicUser).filter(models.PublicUser.id.in_(ids)).all()
    if not rows:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)

    action_key = action.strip().lower()
    if action_key not in PUBLIC_USER_BULK_ACTIONS:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_BULK_INVALID_ACTION, scroll_y, return_section)
    if action_key == "resend_verification":
        # Fast fail if SMTP settings are invalid.
        sample_ok, _ = validate_mailer_settings()
        if not sample_ok:
            return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)

    updated = 0
    queued = 0
    for row in rows:
        row_updated, row_queued = _apply_public_user_bulk_action(action_key, row, request)
        updated += row_updated
        queued += row_queued
    db.commit()
    log_security_event(
        "admin_public_users_bulk_action",
        request,
        "success",
        email=admin_user.email,
        details={"action": action_key, "selected": len(ids), "updated": updated, "queued": queued},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_BULK_DONE, scroll_y, return_section)


@router.post("/admin/rooms")
def admin_create_room(
    name: str = Form(...),
    capacity: int = Form(10),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = models.Room(center_id=cid, name=name, capacity=capacity)
    db.add(room)
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_CREATED, scroll_y, return_section)


@router.post("/admin/rooms/update")
def admin_update_room(
    room_id: int = Form(...),
    name: str = Form(...),
    capacity: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")
    if capacity <= 0:
        return _admin_redirect(ADMIN_MSG_ROOM_CAPACITY_INVALID, scroll_y, return_section)
    room.name = name.strip() or room.name
    room.capacity = capacity
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_UPDATED, scroll_y, return_section)


@router.post("/admin/rooms/delete")
def admin_delete_room(
    room_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")

    room_sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.room_id == room_id)
        .all()
    )
    if room_sessions:
        session_ids = [s.id for s in room_sessions]
        has_bookings = (
            db.query(models.Booking.id)
            .filter(models.Booking.center_id == cid, models.Booking.session_id.in_(session_ids))
            .first()
        )
        if has_bookings:
            return _admin_redirect(ADMIN_MSG_ROOM_HAS_BOOKINGS, scroll_y, return_section)
        for session in room_sessions:
            db.delete(session)

    db.delete(room)
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_DELETED, scroll_y, return_section)


@router.post("/admin/rooms/delete-bulk")
def admin_delete_rooms_bulk(
    room_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    selected_ids = sorted(set(room_ids))
    if not selected_ids:
        return _admin_redirect(ADMIN_MSG_ROOMS_NONE_SELECTED, scroll_y, return_section)

    rooms = (
        db.query(models.Room)
        .filter(models.Room.center_id == cid, models.Room.id.in_(selected_ids))
        .all()
    )
    if not rooms:
        return _admin_redirect(ADMIN_MSG_ROOMS_NOT_FOUND, scroll_y, return_section)

    room_ids = [r.id for r in rooms]
    all_sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.room_id.in_(room_ids))
        .all()
    )
    sessions_by_room: dict[int, list[models.YogaSession]] = {}
    session_ids: list[int] = []
    for session in all_sessions:
        sessions_by_room.setdefault(session.room_id, []).append(session)
        session_ids.append(session.id)
    booked_session_ids: set[int] = set()
    if session_ids:
        booked_session_ids = {
            sid
            for (sid,) in db.query(models.Booking.session_id)
            .filter(models.Booking.center_id == cid, models.Booking.session_id.in_(session_ids))
            .distinct()
            .all()
        }

    blocked_bookings = 0
    deleted = 0
    for room in rooms:
        room_sessions = sessions_by_room.get(room.id, [])
        if room_sessions:
            if any(s.id in booked_session_ids for s in room_sessions):
                blocked_bookings += 1
                continue
            for session in room_sessions:
                db.delete(session)
        db.delete(room)
        deleted += 1
    db.commit()

    if deleted > 0 and blocked_bookings > 0:
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETED_PARTIAL_BOOKINGS, scroll_y, return_section)
    if deleted > 0:
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETED, scroll_y, return_section)
    if blocked_bookings > 0:
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETE_HAS_BOOKINGS, scroll_y, return_section)
    return _admin_redirect(ADMIN_MSG_ROOMS_DELETE_BLOCKED, scroll_y, return_section)


@router.post("/admin/sessions")
def admin_create_session(
    room_id: int = Form(...),
    title: str = Form(...),
    trainer_name: str = Form(...),
    level: str = Form(...),
    starts_at: str = Form(...),
    duration_minutes: int = Form(60),
    price_drop_in: float = Form(0.0),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff", "trainer")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        start_dt = datetime.fromisoformat(starts_at)
    except ValueError:
        start_dt = datetime.strptime(starts_at, "%Y-%m-%dT%H:%M")

    yoga_session = models.YogaSession(
        center_id=cid,
        room_id=room_id,
        title=title,
        trainer_name=trainer_name,
        level=level,
        starts_at=start_dt,
        duration_minutes=duration_minutes,
        price_drop_in=float(price_drop_in),
    )
    db.add(yoga_session)
    db.commit()
    return _admin_redirect(ADMIN_MSG_SESSION_CREATED, scroll_y, return_section)


@router.post("/admin/sessions/delete")
def admin_delete_session(
    session_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff", "trainer")),
):
    cid = require_user_center_id(user)
    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != cid:
        raise HTTPException(status_code=404, detail="Session not found")

    booking_ids = [b.id for b in db.query(models.Booking).filter(models.Booking.session_id == session_id).all()]
    if booking_ids:
        db.query(models.Payment).filter(models.Payment.booking_id.in_(booking_ids)).delete(
            synchronize_session=False
        )
    db.query(models.Booking).filter(models.Booking.session_id == session_id).delete()
    db.delete(yoga_session)
    db.commit()
    return _admin_redirect(ADMIN_MSG_SESSION_DELETED, scroll_y, return_section)


@router.post("/admin/plans")
def admin_create_plan(
    name: str = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    if plan_type not in ("weekly", "monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid plan type")
    if price < 0:
        raise HTTPException(status_code=400, detail="Price must be non-negative")
    parsed_session_limit = None
    if session_limit.strip():
        try:
            parsed_session_limit = int(session_limit)
        except ValueError:
            raise HTTPException(status_code=400, detail="Session limit must be an integer")
        if parsed_session_limit <= 0:
            parsed_session_limit = None
    plan = models.SubscriptionPlan(
        center_id=cid,
        name=name,
        plan_type=plan_type,
        price=price,
        session_limit=parsed_session_limit,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_CREATED, scroll_y, return_section)


@router.post("/admin/plans/update-name")
def admin_update_plan_name(
    plan_id: int = Form(...),
    name: str = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    new_name = name.strip()
    if not new_name:
        return _admin_redirect(ADMIN_MSG_PLAN_NAME_INVALID, scroll_y, return_section)
    plan.name = new_name
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_UPDATED, scroll_y, return_section)


@router.post("/admin/plans/update-details")
def admin_update_plan_details(
    plan_id: int = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_type_clean = plan_type.strip().lower()
    if plan_type_clean not in ("weekly", "monthly", "yearly"):
        return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    if price < 0:
        return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)

    parsed_session_limit = None
    if session_limit.strip():
        try:
            parsed_session_limit = int(session_limit)
        except ValueError:
            return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
        if parsed_session_limit <= 0:
            return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)

    plan.plan_type = plan_type_clean
    plan.price = float(price)
    plan.session_limit = parsed_session_limit
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_UPDATED, scroll_y, return_section)


@router.post("/admin/plans/delete")
def admin_delete_plan(
    plan_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    has_subscriptions = db.query(models.ClientSubscription).filter(models.ClientSubscription.plan_id == plan_id).first()
    if has_subscriptions:
        return _admin_redirect(ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS, scroll_y, return_section)
    db.delete(plan)
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_DELETED, scroll_y, return_section)


@router.post("/admin/faqs")
def admin_create_faq(
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect(ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
    row = models.FAQItem(
        center_id=cid,
        question=q,
        answer=a,
        sort_order=max(0, int(sort_order)),
        is_active=is_active in {"1", "true", "on", "yes"},
    )
    db.add(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_CREATED, scroll_y, return_section)


@router.post("/admin/faqs/update")
def admin_update_faq(
    faq_id: int = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect(ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
    row.question = q
    row.answer = a
    row.sort_order = max(0, int(sort_order))
    row.is_active = is_active in {"1", "true", "on", "yes"}
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_UPDATED, scroll_y, return_section)


@router.post("/admin/faqs/delete")
def admin_delete_faq(
    faq_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
    db.delete(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_DELETED, scroll_y, return_section)


@router.post("/admin/faqs/reorder")
def admin_reorder_faqs(
    ordered_ids_csv: str = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    raw = [x.strip() for x in ordered_ids_csv.split(",") if x.strip()]
    if not raw:
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    try:
        ids = [int(x) for x in raw]
    except ValueError:
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    unique_ids = list(dict.fromkeys(ids))
    rows = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == cid, models.FAQItem.id.in_(unique_ids))
        .all()
    )
    if len(rows) != len(unique_ids):
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    row_by_id = {r.id: r for r in rows}
    for idx, faq_id in enumerate(unique_ids, start=1):
        row_by_id[faq_id].sort_order = idx
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_REORDERED, scroll_y, return_section)


def _truthy_form_flag(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}


def _optional_non_negative_int_form(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = int(s)
    except ValueError:
        raise ValueError("nan")
    if v < 0:
        raise ValueError("neg")
    return v


@router.post("/admin/center/loyalty")
def admin_center_loyalty(
    request: Request,
    loyalty_bronze_min: str = Form(""),
    loyalty_silver_min: str = Form(""),
    loyalty_gold_min: str = Form(""),
    loyalty_label_bronze: str = Form(""),
    loyalty_label_silver: str = Form(""),
    loyalty_label_gold: str = Form(""),
    loyalty_reward_bronze: str = Form(""),
    loyalty_reward_silver: str = Form(""),
    loyalty_reward_gold: str = Form(""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if not center:
        return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
    try:
        pb = _optional_non_negative_int_form(loyalty_bronze_min)
        ps = _optional_non_negative_int_form(loyalty_silver_min)
        pg = _optional_non_negative_int_form(loyalty_gold_min)
    except ValueError:
        return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_BAD_NUMBER, scroll_y, return_section)

    prospective = models.Center()
    prospective.loyalty_bronze_min = pb
    prospective.loyalty_silver_min = ps
    prospective.loyalty_gold_min = pg
    b, s, g = effective_loyalty_thresholds(prospective)
    err = validate_loyalty_threshold_triple(b, s, g)
    if err:
        return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_INVALID, scroll_y, return_section)

    def _lbl(x: str) -> str | None:
        t = (x or "").strip()[:64]
        return t or None

    def _reward(x: str) -> str | None:
        t = (x or "").strip()[:LOYALTY_REWARD_MAX_LEN]
        return t or None

    center.loyalty_bronze_min = pb
    center.loyalty_silver_min = ps
    center.loyalty_gold_min = pg
    center.loyalty_label_bronze = _lbl(loyalty_label_bronze)
    center.loyalty_label_silver = _lbl(loyalty_label_silver)
    center.loyalty_label_gold = _lbl(loyalty_label_gold)
    center.loyalty_reward_bronze = _reward(loyalty_reward_bronze)
    center.loyalty_reward_silver = _reward(loyalty_reward_silver)
    center.loyalty_reward_gold = _reward(loyalty_reward_gold)
    db.commit()
    log_security_event(
        "admin_center_loyalty",
        request,
        "success",
        email=user.email,
        details={"center_id": cid, "thresholds": [b, s, g]},
    )
    return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_SAVED, scroll_y, return_section)


@router.post("/admin/center/branding")
async def admin_center_branding(
    brand_tagline: str = Form(""),
    remove_logo: str = Form(""),
    remove_hero: str = Form(""),
    restore_hero_stock: str = Form(""),
    hero_gradient_only: str = Form(""),
    logo: UploadFile | None = File(default=None),
    hero: UploadFile | None = File(default=None),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if not center:
        return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
    had_custom_hero = bool(center.hero_image_url)

    logo_raw = (logo.filename or "").strip() if logo else ""
    logo_ext: str | None = None
    logo_bytes: bytes | None = None
    if logo and logo_raw:
        ext = logo_raw.rsplit(".", 1)[-1].lower() if "." in logo_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        body = await logo.read()
        if not body or len(body) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        logo_ext = ext
        logo_bytes = body

    hero_raw = (hero.filename or "").strip() if hero else ""
    hero_ext: str | None = None
    hero_bytes: bytes | None = None
    if hero and hero_raw:
        ext = hero_raw.rsplit(".", 1)[-1].lower() if "." in hero_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        body = await hero.read()
        if not body or len(body) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        hero_ext = ext
        hero_bytes = body

    tag = brand_tagline.strip()[:500]
    center.brand_tagline = tag if tag else None

    remove = _truthy_form_flag(remove_logo)
    remove_h = _truthy_form_flag(remove_hero)
    restore_stock = _truthy_form_flag(restore_hero_stock)
    gradient_only = _truthy_form_flag(hero_gradient_only)

    if logo_ext is not None and logo_bytes is not None:
        CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _delete_center_logo_files(cid)
        dest = CENTER_LOGO_UPLOAD_DIR / f"center_{cid}.{logo_ext}"
        dest.write_bytes(logo_bytes)
        center.logo_url = f"/static/uploads/centers/center_{cid}.{logo_ext}"
    elif remove:
        _delete_center_logo_files(cid)
        center.logo_url = None

    if restore_stock:
        _delete_center_hero_files(cid)
        center.hero_image_url = None
        center.hero_show_stock_photo = True
    elif hero_ext is not None and hero_bytes is not None:
        CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _delete_center_hero_files(cid)
        dest = CENTER_LOGO_UPLOAD_DIR / f"center_{cid}_hero.{hero_ext}"
        dest.write_bytes(hero_bytes)
        center.hero_image_url = f"/static/uploads/centers/center_{cid}_hero.{hero_ext}"
        center.hero_show_stock_photo = False
    elif remove_h:
        _delete_center_hero_files(cid)
        center.hero_image_url = None
        center.hero_show_stock_photo = False
    elif gradient_only and not had_custom_hero:
        center.hero_show_stock_photo = False

    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_UPDATED, scroll_y, return_section)


@router.post("/admin/center/posts/save")
async def admin_save_center_post(
    request: Request,
    title: str = Form(...),
    post_type: str = Form(...),
    summary: str = Form(""),
    body: str = Form(""),
    post_id: str = Form(""),
    is_pinned: str = Form(""),
    is_published: str = Form(""),
    remove_cover: str = Form(""),
    remove_image_ids: str = Form(""),
    cover_remote_url: str = Form(""),
    gallery_remote_urls: str = Form(""),
    cover: UploadFile | None = File(None),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    ptype = (post_type or "").strip().lower()
    if ptype not in CENTER_POST_TYPES:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
    ttl = (title or "").strip()
    if not ttl or len(ttl) > 220:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
    summ = (summary or "").strip()[:600]
    bod = (body or "").strip()
    if len(bod) > CENTER_POST_MAX_BODY_CHARS:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)

    pid = 0
    if (post_id or "").strip().isdigit():
        pid = int(post_id.strip())
    row: models.CenterPost | None = None
    if pid:
        row = db.get(models.CenterPost, pid)
        if not row or row.center_id != cid:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
    else:
        row = models.CenterPost(center_id=cid, post_type=ptype, title=ttl)
        db.add(row)
        db.flush()

    row.post_type = ptype
    row.title = ttl
    row.summary = summ if summ else None
    row.body = bod if bod else None
    row.is_pinned = _truthy_form_flag(is_pinned)
    row.is_published = _truthy_form_flag(is_published)
    if row.is_published and row.published_at is None:
        row.published_at = utcnow_naive()
    row.updated_at = utcnow_naive()

    if row.is_pinned:
        db.query(models.CenterPost).filter(
            models.CenterPost.center_id == cid,
            models.CenterPost.id != row.id,
        ).update({models.CenterPost.is_pinned: False})

    if _truthy_form_flag(remove_cover) and row.cover_image_url:
        _unlink_static_url_file(row.cover_image_url)
        row.cover_image_url = None

    cover_raw = (cover.filename or "").strip() if cover else ""
    if cover and cover_raw:
        ext = cover_raw.rsplit(".", 1)[-1].lower() if "." in cover_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        cbody = await cover.read()
        if not cbody or len(cbody) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        if row.cover_image_url:
            _unlink_static_url_file(row.cover_image_url)
        CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_cover.{ext}"
        dest.write_bytes(cbody)
        row.cover_image_url = f"/static/uploads/centers/posts/{dest.name}"

    cover_remote_raw = (cover_remote_url or "").strip()
    if cover_remote_raw and not (cover and cover_raw):
        sanitized_remote = _sanitize_center_post_remote_image_url(cover_remote_raw)
        if not sanitized_remote:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        if row.cover_image_url and row.cover_image_url != sanitized_remote:
            _unlink_static_url_file(row.cover_image_url)
        row.cover_image_url = sanitized_remote

    for part in (remove_image_ids or "").replace(" ", "").split(","):
        if not part.isdigit():
            continue
        img_id = int(part)
        img_row = db.get(models.CenterPostImage, img_id)
        if not img_row or img_row.post_id != row.id:
            continue
        _unlink_static_url_file(img_row.image_url)
        db.delete(img_row)

    form = await request.form()
    gallery_files = [
        f
        for f in form.getlist("gallery")
        if hasattr(f, "filename") and (getattr(f, "filename", None) or "").strip()
    ]
    current_n = (
        db.query(models.CenterPostImage)
        .filter(models.CenterPostImage.post_id == row.id)
        .count()
    )
    max_sort = (
        db.query(func.coalesce(func.max(models.CenterPostImage.sort_order), 0))
        .filter(models.CenterPostImage.post_id == row.id)
        .scalar()
    )
    next_order = int(max_sort or 0)

    for gf in gallery_files:
        if current_n >= CENTER_POST_MAX_GALLERY:
            break
        gname = (gf.filename or "").strip()
        ext = gname.rsplit(".", 1)[-1].lower() if "." in gname else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        gbody = await gf.read()
        if not gbody or len(gbody) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        next_order += 1
        CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_gallery_{next_order}_{utcnow_naive().timestamp():.0f}.{ext}"
        dest.write_bytes(gbody)
        db.add(
            models.CenterPostImage(
                post_id=row.id,
                image_url=f"/static/uploads/centers/posts/{dest.name}",
                sort_order=next_order,
            )
        )
        current_n += 1

    for remote_g in _parse_center_post_gallery_remote_urls(gallery_remote_urls):
        if current_n >= CENTER_POST_MAX_GALLERY:
            break
        next_order += 1
        db.add(
            models.CenterPostImage(
                post_id=row.id,
                image_url=remote_g,
                sort_order=next_order,
            )
        )
        current_n += 1

    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_POST_SAVED, scroll_y, return_section)


@router.post("/admin/center/posts/delete")
def admin_delete_center_post(
    post_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.CenterPost, post_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
    _delete_center_post_disk_files(cid, row.id)
    db.delete(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_POST_DELETED, scroll_y, return_section)


@router.post("/public/subscribe")
def public_subscribe(
    request: Request,
    center_id: int = Form(...),
    plan_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != center_id or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    start_date = utcnow_naive()
    end_date = start_date + timedelta(days=_plan_duration_days(plan.plan_type))
    subscription = models.ClientSubscription(
        client_id=client.id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        status="pending",
    )
    db.add(subscription)
    db.flush()

    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=None,
        amount=float(plan.price),
        currency="SAR",
        payment_method=f"subscription_{plan.plan_type}",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)
    db.refresh(subscription)

    provider = get_payment_provider()
    base = _public_base(request)
    if isinstance(provider, StripePaymentProvider):
        try:
            provider_result = provider.create_checkout_session(
                amount=float(plan.price),
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "subscription_id": str(subscription.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                    "plan_id": str(plan.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success&msg=subscribed",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled&msg=subscription_cancelled",
                line_item_name=f"اشتراك — {plan.name}"[:120],
                line_item_description=f"{center.name} · باقة {plan.plan_type}"[:500],
            )
        except Exception as exc:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            log_security_event(
                "public_subscribe",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "plan_id": plan_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_no_url", status_code=303)
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=float(plan.price),
        currency="SAR",
        metadata={
            "center_id": center_id,
            "client_id": client.id,
            "plan_id": plan.id,
            "subscription_id": subscription.id,
        },
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    subscription.status = "active" if provider_result.status == "paid" else "cancelled"
    db.commit()
    return RedirectResponse(url=f"/index?center_id={center_id}&msg=subscribed_mock", status_code=303)
