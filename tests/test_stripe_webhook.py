"""تكامل أساسي لـ Stripe webhook (مع استبدال التحقق من التوقيع في الاختبار)."""

from backend.app import models
from backend.app.bootstrap import ensure_demo_data
from backend.app.database import SessionLocal
from backend.app.payments import StripePaymentProvider


def test_stripe_webhook_checkout_completed_marks_payment_paid(client, monkeypatch):
    db = SessionLocal()
    center = ensure_demo_data(db)
    client_row = db.query(models.Client).filter(models.Client.center_id == center.id).first()
    assert client_row is not None
    pay = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=None,
        amount=10.0,
        currency="SAR",
        payment_method="stripe",
        status="pending",
    )
    db.add(pay)
    db.commit()
    db.refresh(pay)
    pid = pay.id
    db.close()

    def fake_construct(_payload: bytes, _sig: str) -> dict:
        return {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_pytest",
                    "metadata": {"payment_id": str(pid)},
                }
            },
        }

    monkeypatch.setattr(StripePaymentProvider, "construct_event", staticmethod(fake_construct))
    r = client.post("/payments/webhook/stripe", content=b"{}", headers={"Stripe-Signature": "t=1,v1=abc"})
    assert r.status_code == 200
    assert r.json().get("received") is True

    db = SessionLocal()
    p = db.get(models.Payment, pid)
    assert p is not None
    assert p.status == "paid"
    db.close()


def test_stripe_webhook_checkout_expired_marks_payment_failed(client, monkeypatch):
    db = SessionLocal()
    center = ensure_demo_data(db)
    client_row = db.query(models.Client).filter(models.Client.center_id == center.id).first()
    assert client_row is not None
    pay = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=None,
        amount=5.0,
        currency="SAR",
        payment_method="stripe",
        status="pending",
    )
    db.add(pay)
    db.commit()
    db.refresh(pay)
    pid = pay.id
    db.close()

    def fake_construct(_payload: bytes, _sig: str) -> dict:
        return {
            "type": "checkout.session.expired",
            "data": {
                "object": {
                    "id": "cs_expired_pytest",
                    "metadata": {"payment_id": str(pid)},
                }
            },
        }

    monkeypatch.setattr(StripePaymentProvider, "construct_event", staticmethod(fake_construct))
    r = client.post("/payments/webhook/stripe", content=b"{}", headers={"Stripe-Signature": "t=1,v1=abc"})
    assert r.status_code == 200

    db = SessionLocal()
    p = db.get(models.Payment, pid)
    assert p is not None
    assert p.status == "failed"
    db.close()
