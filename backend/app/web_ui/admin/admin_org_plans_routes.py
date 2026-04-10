"""Admin org: subscription plans CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_org_plans_routes(router: APIRouter) -> None:
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
