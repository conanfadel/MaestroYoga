"""Shared helpers for web UI routes (public + admin)."""
import io
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..mailer import queue_email_verification_email
from ..request_ip import get_client_ip
from ..security import (
    create_public_email_verification_token,
    create_public_password_reset_token,
    decode_public_email_verify_flash_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
)
from ..time_utils import utcnow_naive
from ..web_shared import (
    PUBLIC_INDEX_DEFAULT_PATH,
    _public_base,
    _sanitize_next_url,
    _url_with_params,
)
from .constants import *

__all__ = [
    "ADMIN_FLASH_MESSAGES",
    "_resolved_path_under_static",
    "_clear_center_branding_urls_if_files_missing",
    "_current_public_user",
    "_public_user_from_verify_flash_token",
    "_build_verify_url",
    "_build_reset_url",
    "_request_key",
    "_active_block_for_ip",
    "_is_ip_blocked",
    "_unlink_center_uploads",
    "_sanitize_center_post_remote_image_url",
    "_parse_center_post_gallery_remote_urls",
    "_delete_center_post_disk_files",
    "_unlink_static_url_file",
    "_sanitize_admin_return_section",
    "_admin_redirect",
    "_parse_optional_date_str",
    "_trainer_forbidden_redirect",
    "_security_owner_forbidden_redirect",
    "_admin_login_redirect",
    "_require_admin_user_or_redirect",
    "_public_login_redirect",
    "_admin_user_from_request",
    "_get_public_user_or_redirect",
    "_apply_public_user_bulk_action",
    "_analytics_context",
    "_queue_verify_email_for_user",
    "_soft_delete_public_user",
    "_preview_text",
    "_public_account_phone_prefill",
    "_admin_user_for_data_export",
    "_utf8_bom_csv_content",
    "_optional_non_negative_int_form",
]


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


def _build_verify_url(request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH) -> str:
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


def _queue_verify_email_for_user(request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH) -> tuple[bool, str]:
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


def _utf8_bom_csv_content(output: io.StringIO) -> str:
    """BOM لعرض UTF-8 بشكل صحيح في Excel."""
    return "\ufeff" + output.getvalue()


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
