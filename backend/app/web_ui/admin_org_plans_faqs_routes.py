"""Admin org: Plans and FAQ CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_plans_faqs_routes(router: APIRouter) -> None:
    """Plans and FAQ CRUD."""

    @router.post("/admin/plans")
    def admin_create_plan(
        name: str = _s.Form(...),
        plan_type: str = _s.Form(...),
        price: float = _s.Form(...),
        session_limit: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        if plan_type not in ("weekly", "monthly", "yearly"):
            raise _s.HTTPException(status_code=400, detail="Invalid plan type")
        if price < 0:
            raise _s.HTTPException(status_code=400, detail="Price must be non-negative")
        parsed_session_limit = None
        if session_limit.strip():
            try:
                parsed_session_limit = int(session_limit)
            except ValueError:
                raise _s.HTTPException(status_code=400, detail="Session limit must be an integer")
            if parsed_session_limit <= 0:
                parsed_session_limit = None
        plan = _s.models.SubscriptionPlan(
            center_id=cid,
            name=name,
            plan_type=plan_type,
            price=price,
            session_limit=parsed_session_limit,
            is_active=True,
        )
        db.add(plan)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/update-name")
    def admin_update_plan_name(
        plan_id: int = _s.Form(...),
        name: str = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
        new_name = name.strip()
        if not new_name:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_NAME_INVALID, scroll_y, return_section)
        plan.name = new_name
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/update-details")
    def admin_update_plan_details(
        plan_id: int = _s.Form(...),
        plan_type: str = _s.Form(...),
        price: float = _s.Form(...),
        session_limit: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
    
        plan_type_clean = plan_type.strip().lower()
        if plan_type_clean not in ("weekly", "monthly", "yearly"):
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
        if price < 0:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    
        parsed_session_limit = None
        if session_limit.strip():
            try:
                parsed_session_limit = int(session_limit)
            except ValueError:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
            if parsed_session_limit <= 0:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    
        plan.plan_type = plan_type_clean
        plan.price = float(price)
        plan.session_limit = parsed_session_limit
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/delete")
    def admin_delete_plan(
        plan_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
        has_subscriptions = db.query(_s.models.ClientSubscription).filter(_s.models.ClientSubscription.plan_id == plan_id).first()
        if has_subscriptions:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS, scroll_y, return_section)
        db.delete(plan)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DELETED, scroll_y, return_section)
    
    
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
