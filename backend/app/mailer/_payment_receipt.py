"""بريد تأكيد بعد نجاح الدفع (نص + HTML + مرفق تقويم اختياري)."""

from __future__ import annotations

from ._core_send import send_mail_with_attachments


def deliver_payment_success_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> tuple[bool, str]:
    return send_mail_with_attachments(
        to_email,
        subject,
        body,
        html_body=html_body,
        attachments=attachments or [],
    )
