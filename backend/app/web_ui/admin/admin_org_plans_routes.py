"""Admin org: subscription plans CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_org_plans_routes(router: APIRouter) -> None:
    @router.post("/admin/plans")
    def admin_create_plan(
        name: str = _s.Form(...),
        plan_type: str = _s.Form(...),
        list_price: str = _s.Form(...),
        discount_mode: str = _s.Form(default="none"),
        discount_percent: str = _s.Form(default=""),
        reduced_price: str = _s.Form(default=""),
        discount_schedule_type: str = _s.Form(default="always"),
        discount_valid_from: str = _s.Form(default=""),
        discount_valid_until: str = _s.Form(default=""),
        discount_hour_start: str = _s.Form(default=""),
        discount_hour_end: str = _s.Form(default=""),
        session_limit: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        if plan_type not in ("weekly", "monthly", "yearly"):
            raise _s.HTTPException(status_code=400, detail="Invalid plan type")
        parsed_price, perr = _s.discount_pricing.parse_admin_discount_pricing(
            list_price_raw=list_price,
            discount_mode_raw=discount_mode,
            discount_percent_raw=discount_percent,
            reduced_price_raw=reduced_price,
        )
        if perr or not parsed_price:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_PRICING_INVALID, scroll_y, return_section)
        sch, serr = _s.discount_pricing.parse_admin_discount_schedule(
            discount_mode=parsed_price.discount_mode,
            schedule_type_raw=discount_schedule_type,
            valid_from_raw=discount_valid_from,
            valid_until_raw=discount_valid_until,
            hour_start_raw=discount_hour_start,
            hour_end_raw=discount_hour_end,
        )
        if serr or not sch:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_PRICING_INVALID, scroll_y, return_section)
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
            price=float(parsed_price.effective_price),
            list_price=float(parsed_price.list_price),
            discount_mode=parsed_price.discount_mode,
            discount_percent=parsed_price.discount_percent,
            discount_schedule_type=sch.schedule_type,
            discount_valid_from=sch.valid_from,
            discount_valid_until=sch.valid_until,
            discount_hour_start=sch.hour_start,
            discount_hour_end=sch.hour_end,
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
        list_price: str = _s.Form(...),
        discount_mode: str = _s.Form(default="none"),
        discount_percent: str = _s.Form(default=""),
        reduced_price: str = _s.Form(default=""),
        discount_schedule_type: str = _s.Form(default="always"),
        discount_valid_from: str = _s.Form(default=""),
        discount_valid_until: str = _s.Form(default=""),
        discount_hour_start: str = _s.Form(default=""),
        discount_hour_end: str = _s.Form(default=""),
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

        parsed_price, perr = _s.discount_pricing.parse_admin_discount_pricing(
            list_price_raw=list_price,
            discount_mode_raw=discount_mode,
            discount_percent_raw=discount_percent,
            reduced_price_raw=reduced_price,
        )
        if perr or not parsed_price:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_PRICING_INVALID, scroll_y, return_section)
        sch, serr = _s.discount_pricing.parse_admin_discount_schedule(
            discount_mode=parsed_price.discount_mode,
            schedule_type_raw=discount_schedule_type,
            valid_from_raw=discount_valid_from,
            valid_until_raw=discount_valid_until,
            hour_start_raw=discount_hour_start,
            hour_end_raw=discount_hour_end,
        )
        if serr or not sch:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_PRICING_INVALID, scroll_y, return_section)

        parsed_session_limit = None
        if session_limit.strip():
            try:
                parsed_session_limit = int(session_limit)
            except ValueError:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
            if parsed_session_limit <= 0:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)

        plan.plan_type = plan_type_clean
        plan.price = float(parsed_price.effective_price)
        plan.list_price = float(parsed_price.list_price)
        plan.discount_mode = parsed_price.discount_mode
        plan.discount_percent = parsed_price.discount_percent
        plan.discount_schedule_type = sch.schedule_type
        plan.discount_valid_from = sch.valid_from
        plan.discount_valid_until = sch.valid_until
        plan.discount_hour_start = sch.hour_start
        plan.discount_hour_end = sch.hour_end
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
