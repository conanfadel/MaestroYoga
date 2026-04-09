"""Built-in verification, password reset, and account-delete email bodies."""

from __future__ import annotations

import os

from ._core_send import _send_mail
from ._templates import _brand_email_html


def send_email_verification_email(to_email: str, verification_url: str, full_name: str = "") -> tuple[bool, str]:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    recipient_name = full_name.strip() or "there"
    try:
        verify_mins = max(5, int(os.getenv("PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES", "30")))
    except ValueError:
        verify_mins = 30
    foot_note = (
        f"صلاحية الرابط نحو {verify_mins} دقيقة. بعد التأكيد يمكنك إكمال الحجز والدفع. "
        "إذا لم تطلب إنشاء حساب، تجاهل هذه الرسالة."
    )

    subject = f"{app_name} - تأكيد البريد الإلكتروني"
    body = (
        f"مرحبًا بك في {app_name}!\n\n"
        f"افتح الرابط التالي لتأكيد بريدك الإلكتروني:\n{verification_url}\n\n"
        f"{foot_note}\n\n"
        "إذا تعذر الضغط على الرابط، انسخه بالكامل والصقه في المتصفح."
    )
    html_body = _brand_email_html(
        app_name=app_name,
        title="تأكيد البريد الإلكتروني",
        recipient_name=recipient_name,
        intro="اضغط الزر أدناه لتفعيل حسابك. التأكيد مطلوب قبل إتمام حجز الجلسات أو الاشتراكات عند تفعيل خيار التحقق.",
        cta_label="تأكيد البريد",
        cta_url=verification_url,
        foot_note=foot_note,
    )
    return _send_mail(to_email, subject, body, html_body=html_body)


def send_password_reset_email(to_email: str, reset_url: str, full_name: str = "") -> tuple[bool, str]:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    recipient_name = full_name.strip() or "there"
    try:
        reset_mins = max(5, int(os.getenv("PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES", "30")))
    except ValueError:
        reset_mins = 30
    foot_note = (
        f"صلاحية الرابط نحو {reset_mins} دقيقة. إذا انتهت المدة اطلب رابطًا جديدًا من صفحة «نسيت كلمة المرور»."
    )
    subject = f"{app_name} - إعادة تعيين كلمة المرور"
    body = (
        f"استلمنا طلبًا لإعادة تعيين كلمة المرور لحسابك في {app_name}.\n\n"
        f"افتح الرابط التالي للمتابعة:\n{reset_url}\n\n"
        f"{foot_note}\n\n"
        "إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة.\n\n"
        "إذا تعذر الضغط على الرابط، انسخه بالكامل والصقه في المتصفح."
    )
    html_body = _brand_email_html(
        app_name=app_name,
        title="إعادة تعيين كلمة المرور",
        recipient_name=recipient_name,
        intro="استلمنا طلبًا لإعادة تعيين كلمة المرور. استخدم الزر التالي للمتابعة بشكل آمن.",
        cta_label="إعادة تعيين كلمة المرور",
        cta_url=reset_url,
        foot_note=foot_note,
    )
    return _send_mail(to_email, subject, body, html_body=html_body)


def send_account_delete_confirmation_email(to_email: str, confirm_url: str, full_name: str = "") -> tuple[bool, str]:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    recipient_name = full_name.strip() or "there"
    try:
        mins = max(5, int(os.getenv("PUBLIC_ACCOUNT_DELETE_EXPIRES_MINUTES", "30")))
    except ValueError:
        mins = 30
    foot_note = (
        f"صلاحية رابط الحذف نحو {mins} دقيقة. بعد التأكيد سيتم حذف الحساب من الوصول العام فوراً."
    )
    subject = f"{app_name} - تأكيد حذف الحساب"
    body = (
        f"مرحبًا،\n\n"
        f"استلمنا طلبًا لحذف حسابك في {app_name}.\n"
        f"للتأكيد افتح الرابط التالي:\n{confirm_url}\n\n"
        f"{foot_note}\n\n"
        "إذا لم تطلب حذف الحساب، تجاهل هذه الرسالة."
    )
    html_body = _brand_email_html(
        app_name=app_name,
        title="تأكيد حذف الحساب",
        recipient_name=recipient_name,
        intro="وصلك طلب حذف حسابك. لحماية حسابك، لن يتم الحذف إلا بعد الضغط على زر التأكيد من هذه الرسالة.",
        cta_label="تأكيد حذف الحساب",
        cta_url=confirm_url,
        foot_note=foot_note,
    )
    return _send_mail(to_email, subject, body, html_body=html_body)
