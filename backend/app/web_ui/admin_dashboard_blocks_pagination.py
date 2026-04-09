"""Shared list pagination for admin dashboard tables."""

from __future__ import annotations


def normalize_admin_list_page(page_value: int, total_items: int, page_size: int) -> tuple[int, int, int]:
    safe_page = max(1, int(page_value or 1))
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if safe_page > total_pages:
        safe_page = total_pages
    offset = (safe_page - 1) * page_size
    return safe_page, total_pages, offset
