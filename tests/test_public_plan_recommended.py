"""Tests for automatic subscription plan recommendation (lowest daily price)."""

from backend.app.public_plan_helpers import recommended_plan_id_by_daily_price


def test_recommended_is_none_when_only_one_plan():
    assert (
        recommended_plan_id_by_daily_price(
            [{"id": 1, "duration_days": 30, "price": 100.0}],
        )
        is None
    )


def test_recommended_picks_lowest_price_per_day():
    rows = [
        {"id": 1, "duration_days": 7, "price": 70.0},
        {"id": 2, "duration_days": 30, "price": 400.0},
        {"id": 3, "duration_days": 365, "price": 2000.0},
    ]
    assert recommended_plan_id_by_daily_price(rows) == 3


def test_recommended_tie_breaks_by_longer_duration():
    rows = [
        {"id": 10, "duration_days": 30, "price": 300.0},
        {"id": 20, "duration_days": 365, "price": 3650.0},
    ]
    assert recommended_plan_id_by_daily_price(rows) == 20

