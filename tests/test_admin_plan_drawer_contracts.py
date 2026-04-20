from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRAWER_TEMPLATE = PROJECT_ROOT / "backend" / "templates" / "partials" / "admin_plan_details_drawer.html"
DISCOUNT_TEMPLATE = PROJECT_ROOT / "backend" / "templates" / "partials" / "admin_discount_fields.html"
ADMIN_ENTRY_TS = PROJECT_ROOT / "admin-ui" / "src" / "admin-entry.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plan_drawer_core_dom_hooks_exist():
    html = _read(DRAWER_TEMPLATE)
    required_ids = (
        'id="plan-details-offcanvas-backdrop"',
        'id="plan-details-offcanvas"',
        'id="plan-drawer-close"',
        'id="plan-drawer-plan-id"',
        'id="plan-drawer-type"',
        'id="plan-drawer-list-price"',
        'id="plan-drawer-session-limit"',
        'id="maestro-admin-plans-json"',
    )
    for token in required_ids:
        assert token in html, f"Missing drawer hook: {token}"


def test_plan_drawer_numeric_inputs_remain_number_type():
    html = _read(DRAWER_TEMPLATE)
    assert 'id="plan-drawer-list-price"' in html and 'type="number"' in html
    assert 'id="plan-drawer-session-limit"' in html and 'type="number"' in html


def test_plan_drawer_uses_discount_macro_with_plan_drawer_suffix():
    html = _read(DRAWER_TEMPLATE)
    assert "admin_discount_fields('plan-drawer'" in html


def test_discount_macro_exposes_expected_plan_drawer_ids():
    html = _read(DISCOUNT_TEMPLATE)
    expected_macro_ids = (
        'id="discount-mode-{{ suffix }}"',
        'id="discount-pct-{{ suffix }}"',
        'id="reduced-price-{{ suffix }}"',
        'id="schedule-type-{{ suffix }}"',
        'id="valid-from-{{ suffix }}"',
        'id="valid-until-{{ suffix }}"',
        'id="duration-hours-{{ suffix }}"',
        'data-discount-suffix="{{ suffix }}"',
    )
    for token in expected_macro_ids:
        assert token in html, f"Missing discount macro id contract: {token}"


def test_admin_entry_plan_drawer_selectors_still_present():
    ts = _read(ADMIN_ENTRY_TS)
    selectors = (
        "#plan-details-offcanvas-backdrop",
        "#plan-details-offcanvas",
        "#plan-drawer-close",
        "#plan-drawer-plan-id",
        "#plan-drawer-type",
        "#plan-drawer-list-price",
        "#plan-drawer-session-limit",
        "#discount-mode-plan-drawer",
        "#discount-pct-plan-drawer",
        "#reduced-price-plan-drawer",
        "#schedule-type-plan-drawer",
        "#valid-from-plan-drawer",
        "#valid-until-plan-drawer",
        "#duration-hours-plan-drawer",
        '[data-discount-suffix="plan-drawer"]',
        ".js-plan-drawer-open",
    )
    for selector in selectors:
        assert selector in ts, f"Missing selector in admin-entry contract: {selector}"
