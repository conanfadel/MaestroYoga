"""Public subscription checkout."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_subscribe_routes(router: APIRouter) -> None:
    """POST /public/subscribe."""

    @router.post("/public/subscribe")
    def public_subscribe(
        request: _s.Request,
        center_id: int = _s.Form(...),
        plan_id: int = _s.Form(...),
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
        plan = _s.get_active_center_plan_or_404(
            db=db,
            models_module=_s.models,
            center_id=center_id,
            plan_id=plan_id,
        )
    
        client = _s.get_or_sync_public_client(db, center_id=center_id, public_user=public_user)

        provider, payment_cfg_msg = _s.resolve_public_payment_provider()
        if payment_cfg_msg or provider is None:
            return _s.redirect_public_index_with_params(center_id=center_id, msg=payment_cfg_msg or "payment_provider_config")

        subscription, payment_row = _s.create_pending_subscription_payment(
            db=db,
            models_module=_s.models,
            center_id=center_id,
            client_id=client.id,
            plan=plan,
            utcnow_fn=_s.utcnow_naive,
            plan_duration_days_fn=_s._plan_duration_days,
        )

        base = _s._public_base(request)
        if _s.payment_provider_supports_hosted_checkout(provider):
            checkout_url, hosted_error = _s.process_hosted_subscription_checkout(
                db=db,
                provider=provider,
                payment_row=payment_row,
                subscription=subscription,
                center_id=center_id,
                client_id=client.id,
                plan=plan,
                center_name=center.name,
                base_url=base,
                request=request,
                log_security_event_fn=_s.log_security_event,
            )
            if hosted_error:
                return _s.redirect_public_index_with_params(center_id=center_id, msg=hosted_error)
            assert checkout_url
            return _s.RedirectResponse(url=checkout_url, status_code=303)
    
        _s.process_mock_subscription_checkout(
            db=db,
            provider=provider,
            payment_row=payment_row,
            subscription=subscription,
            center_id=center_id,
            client_id=client.id,
            plan_id=plan.id,
            amount=float(plan.price),
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg="subscribed_mock")
