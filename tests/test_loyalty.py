import os
from datetime import datetime

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.loyalty import (
    DEFAULT_LOYALTY_REWARD_BRONZE,
    LOYALTY_REWARD_MAX_LEN,
    LOYALTY_TIER_BRONZE,
    LOYALTY_TIER_GOLD,
    LOYALTY_TIER_NONE,
    LOYALTY_TIER_SILVER,
    apply_loyalty_cascade,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_reward_text,
    loyalty_tier_for_confirmed_count,
    loyalty_tier_label_ar,
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


def test_apply_loyalty_cascade_bumps_silver_and_gold():
    b, s, g = apply_loyalty_cascade(6, 6, 10)
    assert b == 6 and s == 7 and g == 10
    b2, s2, g2 = apply_loyalty_cascade(6, 8, 8)
    assert b2 == 6 and s2 == 8 and g2 == 9


def test_effective_loyalty_bronze_only_bumps_silver(monkeypatch):
    monkeypatch.delenv("LOYALTY_BRONZE_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_SILVER_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_GOLD_MIN_CONFIRMED", raising=False)
    c = models.Center()
    c.loyalty_bronze_min = 6
    b, s, g = effective_loyalty_thresholds(c)
    assert b == 6 and s == 7


def test_effective_loyalty_thresholds_center_override(monkeypatch):
    monkeypatch.delenv("LOYALTY_SILVER_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_GOLD_MIN_CONFIRMED", raising=False)
    c = models.Center()
    c.loyalty_silver_min = 10
    c.loyalty_gold_min = 35
    b, s, g = effective_loyalty_thresholds(c)
    assert s == 10 and g == 35 and b >= 1 and b < s


def test_loyalty_tier_label_custom_on_center():
    c = models.Center()
    c.loyalty_label_gold = "نجم ذهبي"
    assert loyalty_tier_label_ar(LOYALTY_TIER_GOLD, c) == "نجم ذهبي"


def test_loyalty_reward_text_default_and_override():
    assert loyalty_reward_text(None, "bronze") == DEFAULT_LOYALTY_REWARD_BRONZE
    c = models.Center()
    c.loyalty_reward_bronze = "خصم 10٪ على الجلسة القادمة"
    assert loyalty_reward_text(c, "bronze") == "خصم 10٪ على الجلسة القادمة"
    long_txt = "x" * (LOYALTY_REWARD_MAX_LEN + 50)
    c.loyalty_reward_silver = long_txt
    assert len(loyalty_reward_text(c, "silver")) == LOYALTY_REWARD_MAX_LEN


def test_loyalty_program_table_rows_structure(monkeypatch):
    monkeypatch.delenv("LOYALTY_BRONZE_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_SILVER_MIN_CONFIRMED", raising=False)
    monkeypatch.delenv("LOYALTY_GOLD_MIN_CONFIRMED", raising=False)
    rows = loyalty_program_table_rows(None)
    assert len(rows) == 3
    assert {r["tier_key"] for r in rows} == {"bronze", "silver", "gold"}
    assert all("medal" in r and "label" in r and "range_label" in r and "reward" in r and "row_class" in r for r in rows)
    c = models.Center()
    c.loyalty_bronze_min = 2
    c.loyalty_silver_min = 5
    c.loyalty_gold_min = 10
    rows2 = loyalty_program_table_rows(c)
    assert rows2[0]["range_label"].startswith("من 2")
    assert "10 جلسة" in rows2[2]["range_label"]


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
