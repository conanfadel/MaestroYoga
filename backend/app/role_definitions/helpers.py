"""JSON parsing for custom_staff and UI grouping / handbook matrix."""

from __future__ import annotations

import json
from typing import Any

from .permissions_catalog import PERMISSION_CATALOG
from .rbac_sets import CUSTOM_STAFF_ALLOWED_PERMISSIONS
from .role_permissions_map import permissions_for_role
from .staff_roles import STAFF_ROLE_CATALOG


def custom_permissions_from_json(raw: str | None) -> frozenset[str]:
    """صلاحيات مستخدم بدور custom_staff من عمود JSON."""
    if not raw or not str(raw).strip():
        return frozenset()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(x for x in data if isinstance(x, str) and x in CUSTOM_STAFF_ALLOWED_PERMISSIONS)


def permission_catalog_grouped_for_custom_staff() -> list[dict[str, Any]]:
    """مجموعات الصلاحيات لعرض خانات الاختيار عند إنشاء دور مخصّص."""
    by: dict[str, list[dict[str, str]]] = {}
    for p in PERMISSION_CATALOG:
        pid = p["id"]
        if pid not in CUSTOM_STAFF_ALLOWED_PERMISSIONS:
            continue
        g = p["group"]
        by.setdefault(g, []).append({"id": pid, "label": p["label"]})
    return [{"group": g, "perms": by[g]} for g in sorted(by.keys())]


def handbook_matrix_rows() -> list[dict[str, Any]]:
    """صفوف جدول المرجعية: كل دور مع خلايا ✓/— لكل صلاحية بالترتيب."""
    perm_ids = [p["id"] for p in PERMISSION_CATALOG]
    rows: list[dict[str, Any]] = []
    for role in STAFF_ROLE_CATALOG:
        rid = role["id"]
        granted = permissions_for_role(rid)
        rows.append(
            {
                "role_id": rid,
                "role_label": role["label"],
                "role_description": role["description"],
                "optional": bool(role.get("optional")),
                "cells": [pid in granted for pid in perm_ids],
            }
        )
    return rows
