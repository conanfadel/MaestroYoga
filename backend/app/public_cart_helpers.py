import json
import logging

from .checkout_status_urls import build_checkout_status_url
from .discount_pricing import session_public_checkout_amount
from .public_session_visibility import (
    yoga_session_accepts_new_public_booking,
    yoga_session_still_on_public_schedule,
)

logger = logging.getLogger(__name__)


def parse_cart_session_ids(
    cart_json: str,
    *,
    max_sessions: int,
) -> tuple[list[int], str | None]:
    try:
        raw_items = json.loads(cart_json)
    except (json.JSONDecodeError, TypeError):
        return [], "cart_invalid"
    if not isinstance(raw_items, list) or not raw_items:
        return [], "cart_empty"

    session_ids: list[int] = []
    for item in raw_items:
        if not isinstance(item, dict):
            return [], "cart_invalid"
        if item.get("type") != "session":
            return [], "cart_invalid"
        sid = item.get("session_id")
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
        return [], "cart_empty"
    if len(session_ids) > max_sessions:
        return [], "cart_too_many"
    return session_ids, None


def build_cart_booking_bundle(
    *,
    db,
    models_module,
    session_ids: list[int],
    center_id: int,
    client_id: int,
    active_booking_statuses,
    spots_available_fn,
    utcnow_fn,
) -> tuple[list[tuple[object, object, object]], str | None]:
    bundle: list[tuple[object, object, object]] = []
    for session_id in session_ids:
        yoga_session = db.get(models_module.YogaSession, session_id)
        if not yoga_session or yoga_session.center_id != center_id:
            return [], "cart_invalid"
        if not yoga_session_still_on_public_schedule(yoga_session, now=utcnow_fn()):
            return [], "cart_session_ended"
        if not yoga_session_accepts_new_public_booking(yoga_session, now=utcnow_fn()):
            return [], "cart_session_started"
        if spots_available_fn(db, yoga_session) <= 0:
            return [], "cart_session_full"

        duplicate = (
            db.query(models_module.Booking)
            .filter(
                models_module.Booking.session_id == session_id,
                models_module.Booking.client_id == client_id,
                models_module.Booking.status.in_(active_booking_statuses),
            )
            .first()
        )
        if duplicate:
            return [], "duplicate"

        booking = models_module.Booking(
            center_id=center_id,
            session_id=session_id,
            client_id=client_id,
            status="pending_payment",
        )
        db.add(booking)
        db.flush()

        payment_row = models_module.Payment(
            center_id=center_id,
            client_id=client_id,
            booking_id=booking.id,
            amount=float(session_public_checkout_amount(yoga_session, now=utcnow_fn())),
            currency="SAR",
            payment_method="public_cart_checkout",
            status="pending",
            created_at=utcnow_fn(),
        )
        db.add(payment_row)
        db.flush()
        bundle.append((booking, payment_row, yoga_session))
    return bundle, None


def process_hosted_cart_checkout(
    *,
    db,
    provider,
    bundle: list[tuple[object, object, object]],
    center_name: str,
    center_id: int,
    client_id: int,
    base_url: str,
    fmt_dt_fn,
    request,
    log_security_event_fn,
    billing_email: str | None = None,
) -> tuple[str | None, str | None]:
    line_specs = [
        (
            float(session_public_checkout_amount(yoga_session)),
            f"حجز جلسة — {yoga_session.title}"[:120],
            f"{center_name} · {fmt_dt_fn(yoga_session.starts_at)} · {yoga_session.duration_minutes} دقيقة"[:500],
        )
        for _, _, yoga_session in bundle
    ]
    payment_ids_meta = ",".join(str(payment.id) for _, payment, _ in bundle)
    cart_payment_ids = [int(payment.id) for _, payment, _ in bundle]
    idem = f"cart-{payment_ids_meta.replace(',', '-')}"[:255]
    prov_name = type(provider).__name__
    try:
        provider_result = provider.create_checkout_session_multi_line(
            currency="sar",
            line_specs=line_specs,
            metadata={
                "payment_ids": payment_ids_meta,
                "center_id": str(center_id),
                "client_id": str(client_id),
                "cart": "1",
            },
            success_url=build_checkout_status_url(base_url, center_id, cart_payment_ids),
            cancel_url=build_checkout_status_url(
                base_url, center_id, cart_payment_ids, result="cancelled"
            ),
            idempotency_key=idem,
            billing_email=billing_email,
        )
    except Exception as exc:
        logger.exception(
            "hosted cart checkout failed center_id=%s provider=%s",
            center_id,
            prov_name,
        )
        for booking, payment, _ in bundle:
            booking.status = "cancelled"
            payment.status = "failed"
        db.commit()
        log_security_event_fn(
            "public_cart_checkout",
            request,
            "payment_checkout_failed",
            details={"error": str(exc)[:200], "center_id": center_id, "provider": prov_name},
        )
        return None, "payment_checkout_failed"

    provider_ref = provider_result.provider_ref
    checkout_url = provider_result.checkout_url or ""
    if not provider_ref or not checkout_url:
        for booking, payment, _ in bundle:
            booking.status = "cancelled"
            payment.status = "failed"
        db.commit()
        return None, "payment_checkout_no_url"

    for _, payment, _ in bundle:
        payment.provider_ref = provider_ref
    db.commit()
    return checkout_url, None


def process_mock_cart_checkout(
    *,
    db,
    provider,
    bundle: list[tuple[object, object, object]],
    center_id: int,
    client_id: int,
) -> str:
    total = sum(float(session_public_checkout_amount(yoga_session)) for _, _, yoga_session in bundle)
    provider_result = provider.charge(
        amount=total,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client_id, "cart": "1"},
    )
    provider_ref = provider_result.provider_ref
    for booking, payment, _ in bundle:
        payment.provider_ref = provider_ref
        if provider_result.status == "paid":
            payment.status = "paid"
            booking.status = "confirmed"
        else:
            payment.status = "failed"
            booking.status = "cancelled"
    db.commit()
    first_booking_id = bundle[0][0].id if bundle else ""
    return str(first_booking_id)


def process_hosted_single_booking_checkout(
    *,
    db,
    provider,
    booking,
    payment_row,
    amount: float,
    center_id: int,
    client_id: int,
    center_name: str,
    session_title: str,
    session_starts_at,
    session_duration_minutes: int,
    base_url: str,
    fmt_dt_fn,
    request,
    log_security_event_fn,
    session_id: int,
    billing_email: str | None = None,
) -> tuple[str | None, str | None]:
    prov_name = type(provider).__name__
    try:
        single_ids = [int(payment_row.id)]
        provider_result = provider.create_checkout_session(
            amount=amount,
            currency="sar",
            metadata={
                "payment_id": str(payment_row.id),
                "booking_id": str(booking.id),
                "center_id": str(center_id),
                "client_id": str(client_id),
            },
            success_url=build_checkout_status_url(base_url, center_id, single_ids),
            cancel_url=build_checkout_status_url(
                base_url, center_id, single_ids, result="cancelled"
            ),
            line_item_name=f"حجز جلسة — {session_title}"[:120],
            line_item_description=f"{center_name} · {fmt_dt_fn(session_starts_at)} · {session_duration_minutes} دقيقة"[:500],
            idempotency_key=f"book-{payment_row.id}"[:255],
            billing_email=billing_email,
        )
    except Exception as exc:
        logger.exception(
            "hosted single booking checkout failed center_id=%s session_id=%s provider=%s",
            center_id,
            session_id,
            prov_name,
        )
        booking.status = "cancelled"
        payment_row.status = "failed"
        db.commit()
        log_security_event_fn(
            "public_book",
            request,
            "payment_checkout_failed",
            details={"error": str(exc)[:200], "center_id": center_id, "session_id": session_id, "provider": prov_name},
        )
        return None, "payment_checkout_failed"

    payment_row.provider_ref = provider_result.provider_ref
    db.commit()
    checkout_url = provider_result.checkout_url or ""
    if not checkout_url:
        booking.status = "cancelled"
        payment_row.status = "failed"
        db.commit()
        return None, "payment_checkout_no_url"
    return checkout_url, None


def process_mock_single_booking_checkout(
    *,
    db,
    provider,
    booking,
    payment_row,
    amount: float,
    center_id: int,
    client_id: int,
) -> None:
    provider_result = provider.charge(
        amount=amount,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client_id, "booking_id": booking.id},
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    booking.status = "confirmed"
    db.commit()


def create_pending_single_booking_payment(
    *,
    db,
    models_module,
    center_id: int,
    session_id: int,
    client_id: int,
    amount: float,
    payment_method: str,
    utcnow_fn,
    integrity_error_cls,
) -> tuple[object | None, object | None, str | None]:
    booking = models_module.Booking(
        center_id=center_id,
        session_id=session_id,
        client_id=client_id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()

    payment_row = models_module.Payment(
        center_id=center_id,
        client_id=client_id,
        booking_id=booking.id,
        amount=amount,
        currency="SAR",
        payment_method=payment_method,
        status="pending",
        created_at=utcnow_fn(),
    )
    db.add(payment_row)
    try:
        db.commit()
    except integrity_error_cls:
        db.rollback()
        return None, None, "duplicate"
    db.refresh(payment_row)
    return booking, payment_row, None
