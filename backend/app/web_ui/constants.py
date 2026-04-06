"""Constants and paths for the web UI package."""
import os
from pathlib import Path

# backend/ (this file lives under backend/app/web_ui/)
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

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
        "section-rooms",
        "section-plans",
        "section-public-users",
        "section-public-users-trash",
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
ADMIN_MSG_SECURITY_OWNER_ONLY = "security_owner_only"
ADMIN_MSG_CENTER_POST_SAVED = "center_post_saved"
ADMIN_MSG_CENTER_POST_DELETED = "center_post_deleted"
ADMIN_MSG_CENTER_POST_NOT_FOUND = "center_post_not_found"
ADMIN_MSG_CENTER_POST_INVALID = "center_post_invalid"

CENTER_LOGO_UPLOAD_DIR = BACKEND_ROOT / "static" / "uploads" / "centers"
CENTER_POST_UPLOAD_DIR = CENTER_LOGO_UPLOAD_DIR / "posts"
APP_STATIC_ROOT = BACKEND_ROOT / "static"
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
