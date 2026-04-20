from __future__ import annotations

import re
from pathlib import Path

from backend.app.web_ui.admin.admin_paths import ADMIN_SECTION_BASE_PATHS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "backend" / "templates"
PARTIALS_DIR = TEMPLATES_DIR / "partials"

SECTION_ID_RE = re.compile(r'<section[^>]*\bid="([^"]+)"', re.IGNORECASE)
DATA_TARGET_RE = re.compile(r'\bdata-target="([^"]+)"')
SCROLL_ANCHOR_RE = re.compile(r'\bdata-scroll-anchor="([^"]+)"')
DIV_ID_RE = re.compile(r'<div[^>]*\bid="([^"]+)"', re.IGNORECASE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section_ids() -> set[str]:
    files = (
        PARTIALS_DIR / "admin_page_dashboard_sections.html",
        PARTIALS_DIR / "admin_page_settings_sections.html",
        PARTIALS_DIR / "admin_page_users_sections.html",
        PARTIALS_DIR / "admin_page_training_sections.html",
    )
    ids: set[str] = set()
    for path in files:
        ids.update(SECTION_ID_RE.findall(_read(path)))
    return ids


def _extract_data_targets() -> set[str]:
    # مصدر واحد: الماكرو يعرّف كل data-target لأنماط التبويب والشريط الجانبي.
    return set(DATA_TARGET_RE.findall(_read(PARTIALS_DIR / "admin_nav_macros.html")))


def _extract_security_scroll_anchors() -> set[str]:
    return set(SCROLL_ANCHOR_RE.findall(_read(PARTIALS_DIR / "admin_nav_macros.html")))


def _extract_dashboard_div_ids() -> set[str]:
    dashboard_html = _read(PARTIALS_DIR / "admin_page_dashboard_sections.html")
    return set(DIV_ID_RE.findall(dashboard_html))


def test_admin_data_targets_have_backing_sections():
    section_ids = _extract_section_ids()
    data_targets = _extract_data_targets()
    missing = sorted(target for target in data_targets if target not in section_ids)
    assert not missing, f"data-target references missing section ids: {missing}"


def test_admin_section_paths_cover_all_targets():
    data_targets = _extract_data_targets()
    mapping_keys = set(ADMIN_SECTION_BASE_PATHS.keys())
    missing_in_mapping = sorted(target for target in data_targets if target not in mapping_keys)
    assert not missing_in_mapping, f"data-target ids missing from ADMIN_SECTION_BASE_PATHS: {missing_in_mapping}"


def test_admin_section_paths_do_not_reference_deleted_sections():
    section_ids = _extract_section_ids()
    mapping_keys = set(ADMIN_SECTION_BASE_PATHS.keys())
    stale = sorted(section_id for section_id in mapping_keys if section_id not in section_ids)
    assert not stale, f"ADMIN_SECTION_BASE_PATHS has ids without matching <section>: {stale}"


def test_security_anchor_links_match_dashboard_blocks():
    anchors = _extract_security_scroll_anchors()
    dashboard_ids = _extract_dashboard_div_ids()
    missing = sorted(anchor for anchor in anchors if anchor not in dashboard_ids)
    assert not missing, f"security data-scroll-anchor values missing in dashboard section: {missing}"
