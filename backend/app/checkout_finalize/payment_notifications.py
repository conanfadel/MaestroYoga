"""بريد تأكيد ومستند تقويم بعد أول تأكيد دفع ناجح."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import timedelta
from html import escape
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..mailer import queue_payment_success_email
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)


def _ics_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _ics_dt(dt: Any) -> str:
    if dt is None:
        return utcnow_naive().strftime("%Y%m%dT%H%M%S")
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%Y%m%dT%H%M%S")


def build_bookings_calendar_ics(
    *,
    center_name: str,
    booking_sessions: list[tuple[models.Booking, models.YogaSession]],
) -> bytes:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MaestroYoga//payment-receipt//AR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    now = utcnow_naive()
    for booking, session in booking_sessions:
        start = session.starts_at
        end = start + timedelta(minutes=int(session.duration_minutes or 60))
        uid = f"maestro-booking-{booking.id}@payment"
        title = _ics_escape(f"{center_name} — {session.title}")
        desc = _ics_escape(f"حجز مؤكّد · {session.trainer_name} · {session.level}")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{_ics_dt(now)}",
                f"DTSTART:{_ics_dt(start)}",
                f"DTEND:{_ics_dt(end)}",
                f"SUMMARY:{title}",
                f"DESCRIPTION:{desc}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _public_index_url(center_id: int) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return f"/index?center_id={center_id}"
    return f"{base}/index?center_id={center_id}"


def dispatch_payment_success_notifications(
    db: Session,
    *,
    newly_paid_payments: list[models.Payment],
    subscription_prev_status: str | None,
    subscription: models.ClientSubscription | None,
) -> None:
    if os.getenv("DISABLE_PAYMENT_SUCCESS_EMAIL", "").strip().lower() in ("1", "true", "yes"):
        return

    sub_just_active = bool(
        subscription
        and subscription_prev_status == "pending"
        and subscription.status == "active"
    )
    if not newly_paid_payments and not sub_just_active:
        return

    by_client: dict[int, list[models.Payment]] = defaultdict(list)
    for p in newly_paid_payments:
        by_client[int(p.client_id)].append(p)
    if sub_just_active and subscription:
        cid = int(subscription.client_id)
        if cid not in by_client:
            by_client[cid] = []

    for client_id, pays in by_client.items():
        client = db.get(models.Client, client_id)
        if not client or not (client.email or "").strip():
            continue
        to_email = (client.email or "").strip()
        center_id = int(client.center_id)
        center = db.get(models.Center, center_id)
        center_name = center.name if center else "المركز"
        index_url = _public_index_url(center_id)

        plain: list[str] = [
            f"مرحبًا {client.full_name}،",
            "",
            "تم استلام دفعك وتأكيد طلبك في Maestro Yoga.",
            f"رابط صفحة المركز: {index_url}",
            "",
        ]
        html: list[str] = [
            f"<p>مرحبًا <strong>{escape(client.full_name)}</strong>،</p>",
            "<p>تم استلام دفعك وتأكيد طلبك.</p>",
            f'<p><a href="{index_url}">العودة إلى صفحة الحجز</a></p>',
            "<ul>",
        ]

        booking_rows: list[tuple[models.Booking, models.YogaSession]] = []
        for pay in pays:
            if not pay.booking_id:
                continue
            booking = db.get(models.Booking, pay.booking_id)
            if not booking or booking.status != "confirmed":
                continue
            session = db.get(models.YogaSession, booking.session_id)
            if not session:
                continue
            booking_rows.append((booking, session))
            line = (
                f"- حجز: {session.title} — يبدأ {session.starts_at} — المبلغ {pay.amount:g} {pay.currency}"
            )
            plain.append(line)
            html.append(
                "<li>"
                f"<strong>{escape(session.title)}</strong> — {escape(str(session.starts_at))} — "
                f"{pay.amount:g} {escape(pay.currency)}"
                "</li>"
            )

        if sub_just_active and subscription and int(subscription.client_id) == client_id:
            plan = db.get(models.SubscriptionPlan, subscription.plan_id)
            pname = plan.name if plan else "الباقة"
            plain.extend(
                [
                    "",
                    f"تم تفعيل الاشتراك: {pname}",
                    f"صالح حتى: {subscription.end_date}",
                ]
            )
            html.append(
                "<li><strong>اشتراك مفعّل</strong> — "
                f"{escape(pname)} — ينتهي {escape(str(subscription.end_date))}</li>"
            )

        plain.extend(
            [
                "",
                "برنامج الولاء: تُحتسب الجلسات المؤكّدة عند الحضور؛ راجع صفحة المركز لمعرفة مستواك والمكافآت.",
                "",
                "سياسة مختصرة: لتغيير الموعد أو الاستفسار عن الاسترداد، تواصل مع إدارة المركز مباشرة.",
                "",
                "شكرًا لثقتك،",
                center_name,
            ]
        )
        html.append("</ul>")
        html.append(
            "<p style=\"color:#555;font-size:0.95em;\">"
            "الولاء: تُحدَّث المستويات وفق الجلسات المؤكّدة عند الحضور. "
            "للاسترداد أو تغيير الموعد، راسل إدارة المركز."
            "</p>"
        )

        attachments: list[tuple[str, bytes, str]] = []
        if booking_rows:
            mp = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
            if mp not in {"http_relay", "apps_script"}:
                try:
                    ics = build_bookings_calendar_ics(center_name=center_name, booking_sessions=booking_rows)
                    attachments.append(("bookings.ics", ics, "text/calendar"))
                except Exception as exc:
                    logger.warning("ics build failed: %s", exc)

        subject = f"تأكيد الدفع — {center_name}"
        queue_payment_success_email(
            to_email=to_email,
            subject=subject,
            body="\n".join(plain),
            html_body="".join(html),
            attachments=attachments or None,
        )
