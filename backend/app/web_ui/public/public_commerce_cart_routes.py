"""Public multi-session cart checkout."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_commerce_cart_routes(router: APIRouter) -> None:
    @router.post("/public/cart/checkout")
    def public_cart_checkout(
        request: _s.Request,
        center_id: int = _s.Form(...),
        cart_json: str = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        if _s._is_ip_blocked(db, request):
            return _s.redirect_public_index_with_msg(center_id=center_id, msg="ip_blocked")
        public_user = _s._current_public_user(request, db)
        if not public_user:
            return _s._public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
        if _s._is_email_verification_required() and not public_user.email_verified:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
                status_code=303,
            )

        session_ids, cart_error = _s.parse_cart_session_ids(cart_json, max_sessions=_s.MAX_PUBLIC_CART_SESSIONS)
        if cart_error:
            return _s.redirect_public_index_with_msg(center_id=center_id, msg=cart_error)

        center = _s.get_center_or_404(db, center_id)

        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)

        bundle, bundle_error = _s.build_cart_booking_bundle(
            db=db,
            models_module=_s.models,
            session_ids=session_ids,
            center_id=center_id,
            client_id=client.id,
            active_booking_statuses=_s.ACTIVE_BOOKING_STATUSES,
            spots_available_fn=_s.spots_available,
            utcnow_fn=_s.utcnow_naive,
        )
        if bundle_error:
            return _s.redirect_public_index_with_msg(center_id=center_id, msg=bundle_error)

        db.commit()

        provider = _s.get_payment_provider()
        base = _s._public_base(request)

        if _s.payment_provider_supports_hosted_checkout(provider):
            checkout_url, hosted_error = _s.process_hosted_cart_checkout(
                db=db,
                provider=provider,
                bundle=bundle,
                center_name=center.name,
                center_id=center_id,
                client_id=client.id,
                base_url=base,
                fmt_dt_fn=_s._fmt_dt,
                request=request,
                log_security_event_fn=_s.log_security_event,
            )
            if hosted_error:
                return _s.redirect_public_index_with_msg(center_id=center_id, msg=hosted_error)
            assert checkout_url
            return _s.RedirectResponse(url=checkout_url, status_code=303)

        first_bid = _s.process_mock_cart_checkout(
            db=db,
            provider=provider,
            bundle=bundle,
            center_id=center_id,
            client_id=client.id,
        )
        return _s.redirect_public_index_paid_mock(center_id=center_id, booking_id=first_bid)
