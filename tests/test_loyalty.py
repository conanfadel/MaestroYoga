import os
from datetime import datetime

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.loyalty import (
    LOYALTY_TIER_BRONZE,
    LOYALTY_TIER_GOLD,
    LOYALTY_TIER_NONE,
    LOYALTY_TIER_SILVER,
    count_confirmed_sessions_for_public_user,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_tier_for_confirmed_count,
)


def test_loyalty_tier_for_confirmed_count_defaults(monkeypatch):
    monkeypatch.delenv("LOYALTY_BRONZE_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_SILVER_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_GOLD_MIN_CONFIRMED", raising=False)
    assert loyalty_tier_for_confirmed_count(0) == LOYALTY_TIER_NONE
    assert loyalty_tier_for_confirmed_count(1) == LOYALTY_TIER_BRONZE
    assert loyalty_tier_for_confirmed_count(5) == LOYALTY_TIER_BRONZE
    assert loyalty_tier_for_confirmed_count(6) == LOYALTY_TIER_SILVER
    assert loyalty_tier_for_confirmed_count(19) == LOYALTY_TIER_SILVER
    assert loyalty_tier_for_confirmed_count(20) == LOYALTY_TIER_GOLD


def test_loyalty_context_gold_has_no_next(monkeypatch):
    monkeypatch.delenv("LOYALTY_GOLD_MIN_CONFIRMED", raising=False)
    ctx = loyalty_context_for_count(50)
    assert ctx["loyalty_tier"] == LOYALTY_TIER_GOLD
    assert ctx["loyalty_sessions_to_next"] is None


def test_count_confirmed_sessions_matches_client_email():
    db = SessionLocal()
    center_id = None
    try:
        center = models.Center(name=f"Loyalty Test Center {os.getpid()}")
        db.add(center)
        db.flush()
        center_id = center.id
        room = models.Room(center_id=center.id, name="R1", capacity=10)
        db.add(room)
        db.flush()
        sess = models.YogaSession(
            center_id=center.id,
            room_id=room.id,
            title="S1",
            trainer_name="T",
            level="beginner",
            starts_at=datetime(2026, 6, 1, 10, 0, 0),
            duration_minutes=60,
            price_drop_in=50.0,
        )
        db.add(sess)
        db.flush()
        client = models.Client(
            center_id=center.id,
            full_name="LC",
            email="loyalty_count_test@example.com",
            phone="+966501112233",
        )
        db.add(client)
        db.flush()
        for _ in range(3):
            db.add(
                models.Booking(
                    center_id=center.id,
                    session_id=sess.id,
                    client_id=client.id,
                    status="confirmed",
                )
            )
        db.add(
            models.Booking(
                center_id=center.id,
                session_id=sess.id,
                client_id=client.id,
                status="cancelled",
            )
        )
        pu = models.PublicUser(
            full_name="LC",
            email="loyalty_count_test@example.com",
            phone="+966501112233",
            password_hash="x",
            email_verified=True,
            is_active=True,
            is_deleted=False,
        )
        db.add(pu)
        db.commit()
        db.refresh(pu)

        n = count_confirmed_sessions_for_public_user(db, center.id, pu)
        assert n == 3
        m = loyalty_confirmed_counts_by_email_lower(db, center.id)
        assert m.get("loyalty_count_test@example.com") == 3
    finally:
        if center_id is not None:
            db.query(models.Booking).filter(models.Booking.center_id == center_id).delete()
            db.query(models.YogaSession).filter(models.YogaSession.center_id == center_id).delete()
            db.query(models.Client).filter(models.Client.center_id == center_id).delete()
            db.query(models.Room).filter(models.Room.center_id == center_id).delete()
            db.query(models.Center).filter(models.Center.id == center_id).delete()
        db.query(models.PublicUser).filter(models.PublicUser.email == "loyalty_count_test@example.com").delete()
        db.commit()
        db.close()
