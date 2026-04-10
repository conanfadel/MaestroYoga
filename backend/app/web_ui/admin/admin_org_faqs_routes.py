"""Admin org: FAQ CRUD and reorder."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_org_faqs_routes(router: APIRouter) -> None:
    @router.post("/admin/faqs")
    def admin_create_faq(
        question: str = _s.Form(...),
        answer: str = _s.Form(...),
        sort_order: int = _s.Form(0),
        is_active: str = _s.Form("1"),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        q = question.strip()
        a = answer.strip()
        if not q or not a:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
        row = _s.models.FAQItem(
            center_id=cid,
            question=q,
            answer=a,
            sort_order=max(0, int(sort_order)),
            is_active=is_active in {"1", "true", "on", "yes"},
        )
        db.add(row)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_CREATED, scroll_y, return_section)

    @router.post("/admin/faqs/update")
    def admin_update_faq(
        faq_id: int = _s.Form(...),
        question: str = _s.Form(...),
        answer: str = _s.Form(...),
        sort_order: int = _s.Form(0),
        is_active: str = _s.Form("1"),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.FAQItem, faq_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
        q = question.strip()
        a = answer.strip()
        if not q or not a:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
        row.question = q
        row.answer = a
        row.sort_order = max(0, int(sort_order))
        row.is_active = is_active in {"1", "true", "on", "yes"}
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_UPDATED, scroll_y, return_section)

    @router.post("/admin/faqs/delete")
    def admin_delete_faq(
        faq_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.FAQItem, faq_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
        db.delete(row)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_DELETED, scroll_y, return_section)

    @router.post("/admin/faqs/reorder")
    def admin_reorder_faqs(
        ordered_ids_csv: str = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        raw = [x.strip() for x in ordered_ids_csv.split(",") if x.strip()]
        if not raw:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        try:
            ids = [int(x) for x in raw]
        except ValueError:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        unique_ids = list(dict.fromkeys(ids))
        rows = (
            db.query(_s.models.FAQItem)
            .filter(_s.models.FAQItem.center_id == cid, _s.models.FAQItem.id.in_(unique_ids))
            .all()
        )
        if len(rows) != len(unique_ids):
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        row_by_id = {r.id: r for r in rows}
        for idx, faq_id in enumerate(unique_ids, start=1):
            row_by_id[faq_id].sort_order = idx
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDERED, scroll_y, return_section)
