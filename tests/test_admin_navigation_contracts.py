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
NAV_ANCHOR_OPEN_RE = re.compile(r"<a\s([^>]+)>([^<]+)</a>", re.IGNORECASE)
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
    files = (
        PARTIALS_DIR / "admin_nav_macros.html",
        PARTIALS_DIR / "admin_mazer_sidebar.html",
    )
    targets: set[str] = set()
    for path in files:
        targets.update(DATA_TARGET_RE.findall(_read(path)))
    return targets


def _extract_nav_link_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for attrs, label in NAV_ANCHOR_OPEN_RE.findall(_read(path)):
        target_m = re.search(r'\bdata-target="([^"]+)"', attrs, re.IGNORECASE)
        if not target_m:
            continue
        id_m = re.search(r'\bid="([^"]+)"', attrs, re.IGNORECASE)
        anchor_m = re.search(r'\bdata-scroll-anchor="([^"]+)"', attrs, re.IGNORECASE)
        if id_m:
            key = id_m.group(1)
        elif anchor_m:
            key = f"{target_m.group(1)}|{anchor_m.group(1)}"
        else:
            key = target_m.group(1)
        clean = re.sub(r"\s+", " ", label.strip())
        if key in labels and labels[key] != clean:
            raise AssertionError(f"conflicting labels for {key!r} in {path.name}: {labels[key]!r} vs {clean!r}")
        labels[key] = clean
    return labels


def _extract_security_scroll_anchors() -> set[str]:
    nav_html = _read(PARTIALS_DIR / "admin_nav_macros.html") + "\n" + _read(PARTIALS_DIR / "admin_mazer_sidebar.html")
    return set(SCROLL_ANCHOR_RE.findall(nav_html))


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


def test_sidebar_and_tab_nav_labels_match():
    sidebar_labels = _extract_nav_link_labels(PARTIALS_DIR / "admin_mazer_sidebar.html")
    tabs_labels = _extract_nav_link_labels(PARTIALS_DIR / "admin_nav_macros.html")

    def _paired_id(link_id: str) -> str | None:
        if link_id.startswith("mazer-tab-"):
            return "tab-" + link_id[len("mazer-tab-") :]
        if link_id.startswith("tab-"):
            return "mazer-tab-" + link_id[len("tab-") :]
        return None

    shared = sorted(
        sid
        for sid in sidebar_labels
        if sid in tabs_labels or (_paired_id(sid) and _paired_id(sid) in tabs_labels)
    )
    mismatched: list[str] = []
    for sid in shared:
        tid = sid if sid in tabs_labels else _paired_id(sid)
        assert tid is not None
        if sidebar_labels[sid] != tabs_labels[tid]:
            mismatched.append(f"{sid}/{tid}")
    assert not mismatched, "label mismatch for: " + ", ".join(
        f"{pair} (sidebar={sidebar_labels[pair.split('/')[0]]!r}, tabs={tabs_labels[pair.split('/')[1]]!r})"
        for pair in mismatched
    )


def test_admin_same_page_section_tabs_do_not_reload():
    html = _read(TEMPLATES_DIR / "admin_base.html")
    assert "window.location.reload()" not in html, (
        "section tab navigation should use activateAdminSection without full page reload"
    )


def test_security_anchor_links_match_dashboard_blocks():
    anchors = _extract_security_scroll_anchors()
    dashboard_ids = _extract_dashboard_div_ids()
    missing = sorted(anchor for anchor in anchors if anchor not in dashboard_ids)
    assert not missing, f"security data-scroll-anchor values missing in dashboard section: {missing}"
