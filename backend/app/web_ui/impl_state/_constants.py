"""Constants and admin flash message map for web UI impl_state."""

from __future__ import annotations

import os

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
        "section-training-management",
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
ADMIN_MSG_TRAINING_EXERCISE_ADDED = "training_exercise_added"
ADMIN_MSG_TRAINING_EXERCISE_DELETED = "training_exercise_deleted"
ADMIN_MSG_TRAINING_EXERCISE_INVALID = "training_exercise_invalid"
ADMIN_MSG_TRAINING_EXERCISE_NOT_FOUND = "training_exercise_not_found"
ADMIN_MSG_TRAINING_ASSIGNMENT_CREATED = "training_assignment_created"
ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID = "training_assignment_invalid"
ADMIN_MSG_TRAINING_ASSIGNMENT_NOT_FOUND = "training_assignment_not_found"
ADMIN_MSG_TRAINING_ASSIGNMENT_CANCELLED = "training_assignment_cancelled"
ADMIN_MSG_TRAINING_MEDICAL_PROFILE_SAVED = "training_medical_profile_saved"
ADMIN_MSG_TRAINING_MEDICAL_HISTORY_ADDED = "training_medical_history_added"
ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID = "training_medical_history_invalid"
ADMIN_MSG_TRAINING_MEDICAL_HISTORY_DELETED = "training_medical_history_deleted"

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
    ADMIN_MSG_CENTER_BRANDING_UPDATED: ("تم حفظ هوية المركز (الشعار، غلاف الصفحة، عنوان البطاقة، التلميح) في الواجهة العامة.", "info"),
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
    ADMIN_MSG_TRAINING_EXERCISE_ADDED: ("تمت إضافة التمرين بنجاح.", "info"),
    ADMIN_MSG_TRAINING_EXERCISE_DELETED: ("تم حذف التمرين.", "info"),
    ADMIN_MSG_TRAINING_EXERCISE_INVALID: ("اسم التمرين مطلوب. تحقق من البيانات ثم أعد المحاولة.", "warn"),
    ADMIN_MSG_TRAINING_EXERCISE_NOT_FOUND: ("تعذر العثور على التمرين المطلوب أو لا يتبع مركزك.", "warn"),
    ADMIN_MSG_TRAINING_ASSIGNMENT_CREATED: ("تم إرسال التمارين للمتدرب بنجاح وربطها برقم اشتراكه.", "info"),
    ADMIN_MSG_TRAINING_ASSIGNMENT_INVALID: ("تعذر إرسال التمارين. تحقق من المتدرب والتمارين والبيانات المدخلة.", "warn"),
    ADMIN_MSG_TRAINING_ASSIGNMENT_NOT_FOUND: ("خطة التمارين المطلوبة غير موجودة أو لا تتبع مركزك.", "warn"),
    ADMIN_MSG_TRAINING_ASSIGNMENT_CANCELLED: ("تم إيقاف خطة التمارين للمتدرب.", "info"),
    ADMIN_MSG_TRAINING_MEDICAL_PROFILE_SAVED: ("تم حفظ الملف الطبي للمتدرب.", "info"),
    ADMIN_MSG_TRAINING_MEDICAL_HISTORY_ADDED: ("تمت إضافة سجل مرضي جديد لملف المتدرب.", "info"),
    ADMIN_MSG_TRAINING_MEDICAL_HISTORY_INVALID: ("بيانات السجل المرضي غير مكتملة أو غير صالحة.", "warn"),
    ADMIN_MSG_TRAINING_MEDICAL_HISTORY_DELETED: ("تم حذف السجل المرضي.", "info"),
    "report_settings_saved": ("تم حفظ أهداف التقارير وإعدادات الضريبة والبريد.", "info"),
    "digest_email_sent": ("تم إرسال الملخص إلى البريد المحدد.", "info"),
    "digest_email_failed": ("تعذر إرسال البريد. تحقق من SMTP والعنوان.", "warn"),
}
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
INDEX_PAGE_MAX_JSON_CHARS = 120_000
