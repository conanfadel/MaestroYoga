"""Public single-session booking checkout."""

from __future__ import annotations

import json

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_commerce_book_routes(router: APIRouter) -> None:
    @router.post("/public/book")
    def public_book(
        request: _s.Request,
        center_id: int = _s.Form(...),
        session_id: int = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        if _s._is_ip_blocked(db, request):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="ip_blocked")
        public_user = _s._current_public_user(request, db)
        if not public_user:
            return _s._public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
        if _s._is_email_verification_required() and not public_user.email_verified:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
                status_code=303,
            )

        center = _s.get_center_or_404(db, center_id)

        if _s.is_sqlite:
            db.execute(_s.text("BEGIN IMMEDIATE"))

        yoga_session_query = db.query(_s.models.YogaSession).filter(_s.models.YogaSession.id == session_id)
        if not _s.is_sqlite:
            yoga_session_query = yoga_session_query.with_for_update()
        yoga_session = yoga_session_query.first()
        if not yoga_session or yoga_session.center_id != center_id:
            raise _s.HTTPException(status_code=404, detail="Session not found")
        if not _s.yoga_session_still_on_public_schedule(yoga_session):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="session_ended")
        if not _s.yoga_session_accepts_new_public_booking(yoga_session):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="session_started")

        room_query = db.query(_s.models.Room).filter(_s.models.Room.id == yoga_session.room_id)
        if not _s.is_sqlite:
            room_query = room_query.with_for_update()
        room = room_query.first()
        if not room:
            return _s.RedirectResponse(
                url=f"/index?center_id={center_id}&msg=full",
                status_code=303,
            )
        available_spots = max(0, int(room.capacity or 0) - _s.count_active_bookings(db, yoga_session.id))
        if available_spots <= 0:
            return _s.RedirectResponse(
                url=f"/index?center_id={center_id}&msg=full",
                status_code=303,
            )

        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)

        duplicate = (
            db.query(_s.models.Booking)
            .filter(
                _s.models.Booking.session_id == session_id,
                _s.models.Booking.client_id == client.id,
                _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
            )
            .first()
        )
        if duplicate:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="duplicate")

        provider, payment_cfg_msg = _s.resolve_public_payment_provider()
        if payment_cfg_msg or provider is None:
            return _s.redirect_public_index_with_params(center_id=center_id, msg=payment_cfg_msg or "payment_provider_config")

        amount = float(_s.discount_pricing.session_public_checkout_amount(yoga_session))
        booking, payment_row, booking_error = _s.create_pending_single_booking_payment(
            db=db,
            models_module=_s.models,
            center_id=center_id,
            session_id=session_id,
            client_id=client.id,
            amount=amount,
            payment_method="public_checkout",
            utcnow_fn=_s.utcnow_naive,
            integrity_error_cls=_s.IntegrityError,
        )
        if booking_error:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="duplicate")
        assert booking is not None and payment_row is not None

        base = _s._public_base(request)

        if _s.payment_provider_supports_hosted_checkout(provider):
            checkout_url, hosted_error = _s.process_hosted_single_booking_checkout(
                db=db,
                provider=provider,
                booking=booking,
                payment_row=payment_row,
                amount=amount,
                center_id=center_id,
                client_id=client.id,
                center_name=center.name,
                session_title=yoga_session.title,
                session_starts_at=yoga_session.starts_at,
                session_duration_minutes=yoga_session.duration_minutes,
                base_url=base,
                fmt_dt_fn=_s._fmt_dt,
                request=request,
                log_security_event_fn=_s.log_security_event,
                session_id=session_id,
                billing_email=(public_user.email or "").strip() or None,
            )
            if hosted_error:
                return _s.redirect_public_index_with_params(center_id=center_id, msg=hosted_error)
            assert checkout_url
            return _s.RedirectResponse(url=checkout_url, status_code=303)

        _s.process_mock_single_booking_checkout(
            db=db,
            provider=provider,
            booking=booking,
            payment_row=payment_row,
            amount=amount,
            center_id=center_id,
            client_id=client.id,
        )

        return _s.redirect_public_index_paid_mock(center_id=center_id, booking_id=booking.id)

    @router.post("/public/book-plan-session")
    def public_book_plan_session(
        request: _s.Request,
        center_id: int = _s.Form(...),
        session_id: int = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        """حجز جلسة ضمن حصة اشتراك بحد جلسات (بدون دفع منفصل)."""
        if _s._is_ip_blocked(db, request):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="ip_blocked")
        public_user = _s._current_public_user(request, db)
        if not public_user:
            return _s._public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
        if _s._is_email_verification_required() and not public_user.email_verified:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
                status_code=303,
            )

        _s.get_center_or_404(db, center_id)

        if _s.is_sqlite:
            db.execute(_s.text("BEGIN IMMEDIATE"))

        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)
        ok, code = _s.confirm_public_plan_session_booking(
            db,
            center_id=center_id,
            session_id=session_id,
            client=client,
            models_module=_s.models,
            utcnow_fn=_s.utcnow_naive,
            count_active_bookings_fn=_s.count_active_bookings,
            integrity_error_cls=_s.IntegrityError,
        )
        if ok:
            _s.log_security_event(
                "public_plan_session_book",
                request,
                "success",
                email=public_user.email,
                details={"center_id": center_id, "session_id": session_id, "client_id": client.id},
            )
            return _s.redirect_public_index_with_params(center_id=center_id, msg=code)
        _s.log_security_event(
            "public_plan_session_book",
            request,
            "blocked",
            email=public_user.email,
            details={"center_id": center_id, "session_id": session_id, "reason": code},
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg=code)

    @router.post("/public/book-plan-sessions")
    def public_book_plan_sessions(
        request: _s.Request,
        center_id: int = _s.Form(...),
        session_ids_json: str = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        """حجز عدة جلسات ضمن حصة الخطة في طلب واحد (بعد التأكيد في الواجهة)."""
        if _s._is_ip_blocked(db, request):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="ip_blocked")
        public_user = _s._current_public_user(request, db)
        if not public_user:
            return _s._public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
        if _s._is_email_verification_required() and not public_user.email_verified:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
                status_code=303,
            )

        _s.get_center_or_404(db, center_id)

        session_ids: list[int] = []
        try:
            parsed = json.loads(session_ids_json or "[]")
            if not isinstance(parsed, list):
                raise ValueError("not a list")
            session_ids = [int(x) for x in parsed]
        except (ValueError, TypeError, json.JSONDecodeError):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="plan_sessions_batch_invalid")

        if _s.is_sqlite:
            db.execute(_s.text("BEGIN IMMEDIATE"))

        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)
        ok, code = _s.confirm_public_plan_sessions_booking(
            db,
            center_id=center_id,
            session_ids=session_ids,
            client=client,
            models_module=_s.models,
            utcnow_fn=_s.utcnow_naive,
            count_active_bookings_fn=_s.count_active_bookings,
            integrity_error_cls=_s.IntegrityError,
        )
        if ok:
            _s.log_security_event(
                "public_plan_sessions_book",
                request,
                "success",
                email=public_user.email,
                details={
                    "center_id": center_id,
                    "session_ids": session_ids,
                    "client_id": client.id,
                    "msg": code,
                },
            )
            return _s.redirect_public_index_with_params(center_id=center_id, msg=code)
        _s.log_security_event(
            "public_plan_sessions_book",
            request,
            "blocked",
            email=public_user.email,
            details={"center_id": center_id, "session_ids": session_ids, "reason": code},
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg=code)

    @router.post("/public/cancel-plan-session")
    def public_cancel_plan_session(
        request: _s.Request,
        center_id: int = _s.Form(...),
        session_id: int = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        """إلغاء جلسة كانت محجوزة ضمن حصة الخطة (قبل بدء الجلسة)."""
        if _s._is_ip_blocked(db, request):
            return _s.redirect_public_index_with_params(center_id=center_id, msg="ip_blocked")
        public_user = _s._current_public_user(request, db)
        if not public_user:
            return _s._public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
        if _s._is_email_verification_required() and not public_user.email_verified:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
                status_code=303,
            )

        _s.get_center_or_404(db, center_id)

        if _s.is_sqlite:
            db.execute(_s.text("BEGIN IMMEDIATE"))

        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)
        ok, code = _s.cancel_public_plan_session_booking(
            db,
            center_id=center_id,
            session_id=session_id,
            client=client,
            models_module=_s.models,
            utcnow_fn=_s.utcnow_naive,
        )
        if ok:
            _s.log_security_event(
                "public_plan_session_cancel",
                request,
                "success",
                email=public_user.email,
                details={"center_id": center_id, "session_id": session_id, "client_id": client.id},
            )
            return _s.redirect_public_index_with_params(center_id=center_id, msg=code)
        _s.log_security_event(
            "public_plan_session_cancel",
            request,
            "blocked",
            email=public_user.email,
            details={"center_id": center_id, "session_id": session_id, "reason": code},
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg=code)
