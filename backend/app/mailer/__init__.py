"""Email delivery: SMTP, Resend, HTTP relay, and transactional templates."""

from __future__ import annotations

from ._core_send import feedback_destination_email, send_mail_with_attachments
from ._env import MAILER_ASYNC_WORKERS
from ._queue import (
    queue_account_delete_confirmation_email,
    queue_email_verification_email,
    queue_password_reset_email,
    queue_payment_success_email,
    validate_mailer_settings,
)
from ._transactional import (
    send_account_delete_confirmation_email,
    send_email_verification_email,
    send_password_reset_email,
)

__all__ = [
    "MAILER_ASYNC_WORKERS",
    "feedback_destination_email",
    "queue_account_delete_confirmation_email",
    "queue_email_verification_email",
    "queue_password_reset_email",
    "queue_payment_success_email",
    "send_account_delete_confirmation_email",
    "send_email_verification_email",
    "send_mail_with_attachments",
    "send_password_reset_email",
    "validate_mailer_settings",
]
