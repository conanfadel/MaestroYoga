from datetime import timedelta
from fastapi import HTTPException


def create_pending_subscription_payment(
    *,
    db,
    models_module,
    center_id: int,
    client_id: int,
    plan,
    utcnow_fn,
    plan_duration_days_fn,
):
    start_date = utcnow_fn()
    end_date = start_date + timedelta(days=plan_duration_days_fn(plan.plan_type))
    subscription = models_module.ClientSubscription(
        client_id=client_id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        status="pending",
    )
    db.add(subscription)
    db.flush()

    payment_row = models_module.Payment(
        center_id=center_id,
        client_id=client_id,
        booking_id=None,
        amount=float(plan.price),
        currency="SAR",
        payment_method=f"subscription_{plan.plan_type}",
        status="pending",
        created_at=utcnow_fn(),
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)
    db.refresh(subscription)
    return subscription, payment_row


def get_active_center_plan_or_404(
    *,
    db,
    models_module,
    center_id: int,
    plan_id: int,
):
    plan = db.get(models_module.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != center_id or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


def process_hosted_subscription_checkout(
    *,
    db,
    provider,
    payment_row,
    subscription,
    center_id: int,
    client_id: int,
    plan,
    center_name: str,
    base_url: str,
    request,
    log_security_event_fn,
) -> tuple[str | None, str | None]:
    try:
        provider_result = provider.create_checkout_session(
            amount=float(plan.price),
            currency="sar",
            metadata={
                "payment_id": str(payment_row.id),
                "subscription_id": str(subscription.id),
                "center_id": str(center_id),
                "client_id": str(client_id),
                "plan_id": str(plan.id),
            },
            success_url=f"{base_url}/index?center_id={center_id}&payment=success&msg=subscribed",
            cancel_url=f"{base_url}/index?center_id={center_id}&payment=cancelled&msg=subscription_cancelled",
            line_item_name=f"اشتراك — {plan.name}"[:120],
            line_item_description=f"{center_name} · باقة {plan.plan_type}"[:500],
        )
    except Exception as exc:
        payment_row.status = "failed"
        subscription.status = "cancelled"
        db.commit()
        log_security_event_fn(
            "public_subscribe",
            request,
            "stripe_error",
            details={"error": str(exc)[:200], "center_id": center_id, "plan_id": plan.id},
        )
        return None, "stripe_error"

    payment_row.provider_ref = provider_result.provider_ref
    db.commit()
    checkout_url = provider_result.checkout_url or ""
    if not checkout_url:
        payment_row.status = "failed"
        subscription.status = "cancelled"
        db.commit()
        return None, "stripe_no_url"
    return checkout_url, None


def process_mock_subscription_checkout(
    *,
    db,
    provider,
    payment_row,
    subscription,
    center_id: int,
    client_id: int,
    plan_id: int,
    amount: float,
) -> None:
    provider_result = provider.charge(
        amount=amount,
        currency="SAR",
        metadata={
            "center_id": center_id,
            "client_id": client_id,
            "plan_id": plan_id,
            "subscription_id": subscription.id,
        },
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    subscription.status = "active" if provider_result.status == "paid" else "cancelled"
    db.commit()
