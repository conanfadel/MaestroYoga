"""Admin dashboard main HTML page (GET /admin)."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_dashboard_routes(router: APIRouter) -> None:
    """Large dashboard view."""

    @router.get("/admin", response_class=_s.HTMLResponse)
    def admin_dashboard(
        request: _s.Request,
        msg: str | None = None,
        room_sort: str = "id_asc",
        public_user_q: str = "",
        public_user_status: str = "active",
        public_user_verified: str = "all",
        public_user_page: int = 1,
        trash_page: int = 1,
        trash_q: str = "",
        sessions_page: int = 1,
        payments_page: int = 1,
        audit_event_type: str = "",
        audit_status: str = "",
        audit_email: str = "",
        audit_ip: str = "",
        audit_page: int = 1,
        payment_date_from: str = "",
        payment_date_to: str = "",
        post_edit: int = 0,
        center_posts_page: int = 1,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        cid = _s.require_user_center_id(user)
        center = db.get(_s.models.Center, cid)
        if center:
            if center.name == _s.DEMO_CENTER_NAME:
                _s.ensure_demo_news_posts(db, center.id)
            _s._clear_center_branding_urls_if_files_missing(db, center)
        room_sort_key = (room_sort or "id_asc").strip().lower()
        room_ordering = {
            "id_asc": (_s.models.Room.id.asc(),),
            "name": (_s.models.Room.name.asc(), _s.models.Room.id.asc()),
            "newest": (_s.models.Room.id._s.desc(),),
            "capacity_desc": (_s.models.Room.capacity._s.desc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
            "capacity_asc": (_s.models.Room.capacity.asc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
        }
        if room_sort_key in {"sessions_desc", "sessions_asc"}:
            session_count_order = (
                _s.func.count(_s.models.YogaSession.id)._s.desc()
                if room_sort_key == "sessions_desc"
                else _s.func.count(_s.models.YogaSession.id).asc()
            )
            rooms = (
                db.query(_s.models.Room)
                .outerjoin(
                    _s.models.YogaSession,
                    _s.and_(
                        _s.models.YogaSession.room_id == _s.models.Room.id,
                        _s.models.YogaSession.center_id == cid,
                    ),
                )
                .filter(_s.models.Room.center_id == cid)
                .group_by(_s.models.Room.id)
                .order_by(session_count_order, _s.models.Room.name.asc(), _s.models.Room.id.asc())
                .all()
            )
        else:
            room_order_by = room_ordering.get(room_sort_key, room_ordering["id_asc"])
            rooms = (
                db.query(_s.models.Room)
                .filter(_s.models.Room.center_id == cid)
                .order_by(*room_order_by)
                .all()
            )
        plans = (
            db.query(_s.models.SubscriptionPlan)
            .filter(_s.models.SubscriptionPlan.center_id == cid)
            .order_by(_s.models.SubscriptionPlan.price.asc())
            .all()
        )
        rooms_by_id = {r.id: r for r in rooms}
    
        def _normalize_page(page_value: int, total_items: int, page_size: int) -> tuple[int, int, int]:
            safe_page = max(1, int(page_value or 1))
            total_pages = max(1, (total_items + page_size - 1) // page_size)
            if safe_page > total_pages:
                safe_page = total_pages
            offset = (safe_page - 1) * page_size
            return safe_page, total_pages, offset
    
        sessions_page_size = _s.ADMIN_SESSIONS_PAGE_SIZE
        sessions_base_query = db.query(_s.models.YogaSession).filter(_s.models.YogaSession.center_id == cid)
        sessions_total = sessions_base_query.order_by(None).count()
        safe_sessions_page, sessions_total_pages, sessions_offset = _normalize_page(
            sessions_page,
            sessions_total,
            sessions_page_size,
        )
        sessions = (
            sessions_base_query.order_by(_s.models.YogaSession.starts_at._s.desc())
            .offset(sessions_offset)
            .limit(sessions_page_size)
            .all()
        )
        session_ids_page = [int(s.id) for s in sessions]
        spots_by_session_page = _s._spots_available_map(db, cid, session_ids_page)
        faqs = (
            db.query(_s.models.FAQItem)
            .filter(_s.models.FAQItem.center_id == cid)
            .order_by(_s.models.FAQItem.sort_order.asc(), _s.models.FAQItem.created_at.asc())
            .all()
        )
        public_users_query = _s._public_users_query_for_center(db, cid)
        q = public_user_q.strip()
        if q:
            public_users_query = public_users_query.filter(
                _s.or_(
                    _s.models.PublicUser.full_name.ilike(f"%{q}%"),
                    _s.models.PublicUser.email.ilike(f"%{q}%"),
                    _s.models.PublicUser.phone.ilike(f"%{q}%"),
                )
            )
        status_key = public_user_status.strip().lower() or "active"
        if status_key == "deleted":
            public_users_query = public_users_query.filter(_s.models.PublicUser.is_deleted.is_(True))
        elif status_key == "inactive":
            public_users_query = public_users_query.filter(
                _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(False)
            )
        else:
            public_users_query = public_users_query.filter(
                _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(True)
            )
        verified_key = public_user_verified.strip().lower()
        if verified_key == "verified":
            public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(True))
        elif verified_key == "unverified":
            public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(False))
        public_users_page_size = _s.ADMIN_PUBLIC_USERS_PAGE_SIZE
        public_users_total = public_users_query.order_by(None).count()
        safe_public_user_page, public_users_total_pages, public_users_offset = _normalize_page(
            public_user_page,
            public_users_total,
            public_users_page_size,
        )
        public_users = (
            public_users_query.order_by(_s.models.PublicUser.created_at._s.desc())
            .offset(public_users_offset)
            .limit(public_users_page_size)
            .all()
        )
        trash_q_s = trash_q.strip()
        trash_base = _s._public_users_query_for_center(db, cid).filter(_s.models.PublicUser.is_deleted.is_(True))
        if trash_q_s:
            trash_base = trash_base.filter(
                _s.or_(
                    _s.models.PublicUser.full_name.ilike(f"%{trash_q_s}%"),
                    _s.models.PublicUser.email.ilike(f"%{trash_q_s}%"),
                )
            )
        trash_total = trash_base.order_by(None).count()
        safe_trash_page, trash_total_pages, trash_offset = _normalize_page(
            trash_page,
            trash_total,
            public_users_page_size,
        )
        trash_users_list = (
            trash_base.order_by(_s.models.PublicUser.deleted_at._s.desc(), _s.models.PublicUser.id._s.desc())
            .offset(trash_offset)
            .limit(public_users_page_size)
            .all()
        )
        session_rows = []
        level_labels = {
            "beginner": "مبتدئ",
            "intermediate": "متوسط",
            "advanced": "متقدم",
        }
        now_for_sessions = _s.utcnow_naive()
        for s in sessions:
            room = rooms_by_id.get(s.room_id)
            session_rows.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "trainer_name": s.trainer_name,
                    "level": s.level,
                    "level_label": level_labels.get(s.level, s.level),
                    "starts_at": s.starts_at,
                    "starts_at_display": _s._fmt_dt(s.starts_at),
                    "duration_minutes": s.duration_minutes,
                    "price_drop_in": s.price_drop_in,
                    "room_name": room.name if room else "-",
                    "room_id": s.room_id,
                    "spots_available": spots_by_session_page.get(int(s.id), 0),
                    "capacity": room.capacity if room else 0,
                    "is_past": bool(s.starts_at < now_for_sessions),
                }
            )
        plan_labels = {
            "weekly": "أسبوعي",
            "monthly": "شهري",
            "yearly": "سنوي",
        }
        plan_rows = [
            {
                "id": p.id,
                "name": p.name,
                "plan_type": p.plan_type,
                "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
                "price": p.price,
                "session_limit": p.session_limit,
                "is_active": p.is_active,
            }
            for p in plans
        ]
    
        today = _s.utcnow_naive().date()
        tomorrow_d = today + _s.timedelta(days=1)
        now_na = _s.utcnow_naive()
        payment_from_dt = _s._parse_optional_date_str(payment_date_from)
        payment_to_dt = _s._parse_optional_date_str(payment_date_to)
    
        sessions_today_no_bookings = (
            db.query(_s.models.YogaSession.id)
            .outerjoin(
                _s.models.Booking,
                _s.and_(
                    _s.models.Booking.session_id == _s.models.YogaSession.id,
                    _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
                ),
            )
            .filter(
                _s.models.YogaSession.center_id == cid,
                _s.func.date(_s.models.YogaSession.starts_at) == today,
            )
            .group_by(_s.models.YogaSession.id)
            .having(_s.func.count(_s.models.Booking.id) == 0)
            .count()
        )
        subs_expiring_7d = (
            db.query(_s.models.ClientSubscription)
            .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
            .filter(
                _s.models.Client.center_id == cid,
                _s.models.ClientSubscription.status == "active",
                _s.models.ClientSubscription.end_date >= now_na,
                _s.models.ClientSubscription.end_date <= now_na + _s.timedelta(days=7),
            )
            .count()
        )
        pending_cutoff = now_na - _s.timedelta(days=8)
        pending_payments_stale_8d = int(
            db.query(_s.func.count(_s.models.Payment.id))
            .filter(
                _s.models.Payment.center_id == cid,
                _s.models.Payment.status.in_(("pending", "pending_payment")),
                _s.func.coalesce(_s.models.Payment.created_at, _s.models.Payment.paid_at) <= pending_cutoff,
            )
            .scalar()
            or 0
        )
        failed_payments_7d = int(
            db.query(_s.func.count(_s.models.Payment.id))
            .filter(
                _s.models.Payment.center_id == cid,
                _s.models.Payment.status == "failed",
                _s.func.date(_s.models.Payment.paid_at) >= today - _s.timedelta(days=7),
                _s.func.date(_s.models.Payment.paid_at) <= today,
            )
            .scalar()
            or 0
        )
        sessions_scheduled_today = int(
            db.query(_s.func.count(_s.models.YogaSession.id))
            .filter(_s.models.YogaSession.center_id == cid, _s.func.date(_s.models.YogaSession.starts_at) == today)
            .scalar()
            or 0
        )
        bookings_active_today = int(
            db.query(_s.func.count(_s.models.Booking.id))
            .join(_s.models.YogaSession, _s.models.YogaSession.id == _s.models.Booking.session_id)
            .filter(
                _s.models.YogaSession.center_id == cid,
                _s.func.date(_s.models.YogaSession.starts_at) == today,
                _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
            )
            .scalar()
            or 0
        )
        public_users_unverified_count = (
            _s._public_users_query_for_center(db, cid)
            .filter(
                _s.models.PublicUser.is_deleted.is_(False),
                _s.models.PublicUser.is_active.is_(True),
                _s.models.PublicUser.email_verified.is_(False),
            )
            .count()
        )
    
        revenue_7d_bars: list[dict[str, _s.Any]] = []
        max_rev_7d = 0.01
        rev_start = today - _s.timedelta(days=6)
        revenue_7d_rows = (
            db.query(_s.func.date(_s.models.Payment.paid_at).label("day"), _s.func.coalesce(_s.func.sum(_s.models.Payment.amount), 0.0))
            .filter(
                _s.models.Payment.center_id == cid,
                _s.models.Payment.status == "paid",
                _s.func.date(_s.models.Payment.paid_at) >= rev_start,
                _s.func.date(_s.models.Payment.paid_at) <= today,
            )
            .group_by(_s.func.date(_s.models.Payment.paid_at))
            .all()
        )
        revenue_by_day = {str(day): float(total or 0.0) for day, total in revenue_7d_rows}
        for i in range(6, -1, -1):
            d = today - _s.timedelta(days=i)
            amt = revenue_by_day.get(d.isoformat(), 0.0)
            revenue_7d_bars.append({"date_iso": d.isoformat(), "amount": amt, "label": f"{d.day}/{d.month}"})
            max_rev_7d = max(max_rev_7d, amt)
        for bar in revenue_7d_bars:
            bar["bar_pct"] = int(round(100 * float(bar["amount"]) / max_rev_7d)) if max_rev_7d > 0 else 0
    
        ops_sessions_q = (
            db.query(_s.models.YogaSession)
            .filter(
                _s.models.YogaSession.center_id == cid,
                _s.or_(
                    _s.func.date(_s.models.YogaSession.starts_at) == today,
                    _s.func.date(_s.models.YogaSession.starts_at) == tomorrow_d,
                ),
            )
            .order_by(_s.models.YogaSession.starts_at.asc())
            .limit(36)
            .all()
        )
        ops_spots = _s._spots_available_map(db, cid, [int(s.id) for s in ops_sessions_q])
        ops_today_rows: list[dict[str, str | int]] = []
        ops_tomorrow_rows: list[dict[str, str | int]] = []
        for s in ops_sessions_q:
            room = rooms_by_id.get(s.room_id)
            row = {
                "id": s.id,
                "title": s.title,
                "trainer": s.trainer_name,
                "room": room.name if room else "-",
                "starts": _s._fmt_dt(s.starts_at),
                "spots": ops_spots.get(int(s.id), 0),
                "capacity": room.capacity if room else 0,
            }
            if s.starts_at.date() == today:
                ops_today_rows.append(row)
            elif s.starts_at.date() == tomorrow_d:
                ops_tomorrow_rows.append(row)
    
        window_start = now_na - _s.timedelta(hours=6)
        future_for_conflicts = (
            db.query(_s.models.YogaSession)
            .filter(_s.models.YogaSession.center_id == cid, _s.models.YogaSession.starts_at >= window_start)
            .order_by(_s.models.YogaSession.room_id, _s.models.YogaSession.starts_at)
            .all()
        )
        by_room_sessions: dict[int, list[_s.models.YogaSession]] = _s.defaultdict(list)
        for s in future_for_conflicts:
            by_room_sessions[s.room_id].append(s)
        schedule_conflicts: list[dict[str, str | int]] = []
        for rid, lst in by_room_sessions.items():
            lst.sort(key=lambda x: x.starts_at)
            for i in range(len(lst) - 1):
                a, b = lst[i], lst[i + 1]
                end_a = a.starts_at + _s.timedelta(minutes=int(a.duration_minutes or 0))
                if end_a > b.starts_at:
                    schedule_conflicts.append(
                        {
                            "room_name": (rooms_by_id.get(rid).name if rooms_by_id.get(rid) else f"غرفة #{rid}"),
                            "a_id": a.id,
                            "a_title": a.title,
                            "a_start": _s._fmt_dt(a.starts_at),
                            "b_id": b.id,
                            "b_title": b.title,
                            "b_start": _s._fmt_dt(b.starts_at),
                        }
                    )
    
        admin_login_audit_rows = [
            {
                "created_at_display": _s._fmt_dt(ev.created_at),
                "status": ev.status,
                "email": ev.email or "-",
                "ip": ev.ip or "-",
            }
            for ev in db.query(_s.models.SecurityAuditEvent)
            .filter(_s.models.SecurityAuditEvent.event_type == "admin_login")
            .order_by(_s.models.SecurityAuditEvent.created_at._s.desc())
            .limit(20)
            .all()
        ]
    
        recent_public_cutoff = _s.utcnow_naive() - _s.timedelta(days=7)
        paid_revenue_total, paid_revenue_today = (
            db.query(
                _s.func.coalesce(
                    _s.func.sum(
                        _s.case(
                            (_s.models.Payment.status == "paid", _s.models.Payment.amount),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
                _s.func.coalesce(
                    _s.func.sum(
                        _s.case(
                            (
                                _s.and_(
                                    _s.models.Payment.status == "paid",
                                    _s.func.date(_s.models.Payment.paid_at) == today,
                                ),
                                _s.models.Payment.amount,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
            )
            .filter(_s.models.Payment.center_id == cid)
            .one()
        )
        scoped_public_users = _s._public_users_query_for_center(db, cid).subquery()
        public_users_count, public_users_deleted_count, public_users_new_7d = (
            db.query(
                _s.func.count(scoped_public_users.c.id),
                _s.func.coalesce(
                    _s.func.sum(_s.case((scoped_public_users.c.is_deleted.is_(True), 1), else_=0)),
                    0,
                ),
                _s.func.coalesce(
                    _s.func.sum(
                        _s.case(
                            (
                                _s.and_(
                                    scoped_public_users.c.created_at >= recent_public_cutoff,
                                    scoped_public_users.c.is_deleted.is_(False),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).one()
        )
        dashboard = {
            "rooms_count": len(rooms),
            "sessions_count": sessions_total,
            "bookings_count": db.query(_s.models.Booking).filter(_s.models.Booking.center_id == cid).count(),
            "clients_count": db.query(_s.models.Client).filter(_s.models.Client.center_id == cid).count(),
            "active_plans_count": sum(1 for p in plans if p.is_active),
            "active_subscriptions_count": (
                db.query(_s.models.ClientSubscription)
                .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
                .filter(
                    _s.models.Client.center_id == cid,
                    _s.models.ClientSubscription.status == "active",
                )
                .count()
            ),
            "revenue_total": float(paid_revenue_total or 0.0),
            "revenue_today": float(paid_revenue_today or 0.0),
            "public_users_count": int(public_users_count) - int(public_users_deleted_count),
            "public_users_deleted_count": int(public_users_deleted_count),
            "public_users_new_7d": int(public_users_new_7d),
        }
        payments_page_size = _s.ADMIN_PAYMENTS_PAGE_SIZE
        payments_base_query = db.query(_s.models.Payment).filter(_s.models.Payment.center_id == cid)
        if payment_from_dt:
            payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) >= payment_from_dt)
        if payment_to_dt:
            payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) <= payment_to_dt)
        payments_total = payments_base_query.order_by(None).count()
        safe_payments_page, payments_total_pages, payments_offset = _normalize_page(
            payments_page,
            payments_total,
            payments_page_size,
        )
        recent_payments = (
            payments_base_query.order_by(_s.models.Payment.paid_at._s.desc())
            .offset(payments_offset)
            .limit(payments_page_size)
            .all()
        )
        client_ids = [p.client_id for p in recent_payments]
        clients_by_id = {
            c.id: c
            for c in db.query(_s.models.Client).filter(_s.models.Client.id.in_(client_ids)).all()
        }
        status_labels = {
            "paid": "مدفوع",
            "pending": "قيد الانتظار",
            "failed": "فشل",
        }
        payment_rows = []
        for pay in recent_payments:
            client = clients_by_id.get(pay.client_id)
            payment_rows.append(
                {
                    "id": pay.id,
                    "client_name": client.full_name if client else f"عميل #{pay.client_id}",
                    "payment_method": pay.payment_method,
                    "amount": pay.amount,
                    "currency": pay.currency,
                    "status": pay.status,
                    "status_label": status_labels.get(pay.status, pay.status),
                    "paid_at_display": _s._fmt_dt(pay.paid_at),
                }
            )
        loyalty_by_email = _s.loyalty_confirmed_counts_by_email_lower(db, cid)
        public_user_rows = []
        for u in public_users:
            cnt = loyalty_by_email.get((u.email or "").lower(), 0)
            lt = _s.loyalty_context_for_count(cnt, center=center)
            public_user_rows.append(
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "phone": _s._phone_admin_display(u.phone),
                    "is_active": u.is_active,
                    "email_verified": u.email_verified,
                    "is_deleted": bool(u.is_deleted),
                    "created_at_display": _s._fmt_dt(u.created_at),
                    "loyalty_confirmed_count": cnt,
                    "loyalty_tier": lt["loyalty_tier"],
                    "loyalty_tier_label": lt["loyalty_tier_label"],
                }
            )
        trash_user_rows = []
        for u in trash_users_list:
            cnt = loyalty_by_email.get((u.email or "").lower(), 0)
            lt = _s.loyalty_context_for_count(cnt, center=center)
            trash_user_rows.append(
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                    "phone": _s._phone_admin_display(u.phone),
                    "deleted_at_display": _s._fmt_dt(u.deleted_at),
                    "created_at_display": _s._fmt_dt(u.created_at),
                    "loyalty_confirmed_count": cnt,
                    "loyalty_tier": lt["loyalty_tier"],
                    "loyalty_tier_label": lt["loyalty_tier_label"],
                }
            )
        faq_rows = [
            {
                "id": f.id,
                "question": f.question,
                "answer": f.answer,
                "sort_order": f.sort_order,
                "is_active": f.is_active,
            }
            for f in faqs
        ]
    
        audit_query = db.query(_s.models.SecurityAuditEvent)
        if audit_event_type.strip():
            audit_query = audit_query.filter(_s.models.SecurityAuditEvent.event_type == audit_event_type.strip())
        if audit_status.strip():
            audit_query = audit_query.filter(_s.models.SecurityAuditEvent.status == audit_status.strip())
        if audit_email.strip():
            audit_query = audit_query.filter(_s.models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%"))
        if audit_ip.strip():
            audit_query = audit_query.filter(_s.models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))
    
        audit_page_size = _s.ADMIN_SECURITY_AUDIT_PAGE_SIZE
        security_events_total = audit_query.order_by(None).count()
        safe_audit_page, security_events_total_pages, security_events_offset = _normalize_page(
            audit_page,
            security_events_total,
            audit_page_size,
        )
        security_events = (
            audit_query.order_by(_s.models.SecurityAuditEvent.created_at._s.desc())
            .offset(security_events_offset)
            .limit(audit_page_size)
            .all()
        )
        security_event_rows = [
            {
                "id": ev.id,
                "event_type": ev.event_type,
                "status": ev.status,
                "email": ev.email or "-",
                "ip": ev.ip or "-",
                "path": ev.path or "-",
                "details": ev.details_json or "{}",
                "created_at_display": _s._fmt_dt(ev.created_at),
            }
            for ev in security_events
        ]
        high_risk_since = _s.utcnow_naive() - _s.timedelta(hours=24)
        failed_logins_24h = (
            db.query(_s.models.SecurityAuditEvent)
            .filter(
                _s.models.SecurityAuditEvent.event_type == "public_login",
                _s.models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
                _s.models.SecurityAuditEvent.created_at >= high_risk_since,
            )
            .count()
        )
        suspicious_ips = (
            db.query(_s.models.SecurityAuditEvent.ip, _s.func.count(_s.models.SecurityAuditEvent.id).label("hits"))
            .filter(
                _s.models.SecurityAuditEvent.event_type == "public_login",
                _s.models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
                _s.models.SecurityAuditEvent.created_at >= high_risk_since,
            )
            .group_by(_s.models.SecurityAuditEvent.ip)
            .having(_s.func.count(_s.models.SecurityAuditEvent.id) >= 5)
            .order_by(_s.func.count(_s.models.SecurityAuditEvent.id)._s.desc())
            .limit(5)
            .all()
        )
        blocked_ips = (
            db.query(_s.models.BlockedIP)
            .filter(
                _s.models.BlockedIP.is_active.is_(True),
                _s.or_(_s.models.BlockedIP.blocked_until.is_(None), _s.models.BlockedIP.blocked_until > _s.utcnow_naive()),
            )
            .order_by(_s.models.BlockedIP.created_at._s.desc())
            .limit(20)
            .all()
        )
    
        def _risk_level(hits: int) -> str:
            if hits >= 12:
                return "high"
            if hits >= 5:
                return "medium"
            return "low"
    
        security_summary = {
            "failed_logins_24h": failed_logins_24h,
            "suspicious_ips": [
                {"ip": ip or "-", "hits": int(hits), "risk_level": _risk_level(int(hits))}
                for ip, hits in suspicious_ips
            ],
            "blocked_ips": [
                {
                    "ip": b.ip,
                    "reason": b.reason or "-",
                    "blocked_until": _s._fmt_dt(b.blocked_until) if b.blocked_until else "دائم",
                }
                for b in blocked_ips
            ],
        }
        block_history_events = (
            db.query(_s.models.SecurityAuditEvent)
            .filter(_s.models.SecurityAuditEvent.event_type.in_(["admin_ip_block", "admin_ip_unblock"]))
            .order_by(_s.models.SecurityAuditEvent.created_at._s.desc())
            .limit(120)
            .all()
        )
        block_history_rows = []
        for ev in block_history_events:
            details = {}
            if ev.details_json:
                try:
                    details = _s.json.loads(ev.details_json)
                except (TypeError, ValueError):
                    details = {}
            block_history_rows.append(
                {
                    "id": ev.id,
                    "created_at_display": _s._fmt_dt(ev.created_at),
                    "event_type": ev.event_type,
                    "status": ev.status,
                    "admin_email": ev.email or "-",
                    "target_ip": details.get("target_ip", "-"),
                    "minutes": details.get("minutes", "-"),
                    "reason": details.get("reason", "-"),
                }
            )
        security_export_url = _s._url_with_params(
            "/admin/security/export/_s.csv",
            audit_event_type=audit_event_type,
            audit_status=audit_status,
            audit_email=audit_email,
            audit_ip=audit_ip,
        )
        admin_flash = None
        if msg:
            flash_data = _s.ADMIN_FLASH_MESSAGES.get(msg)
            if flash_data:
                text, level = flash_data
                admin_flash = {"text": text, "level": level}
    
        base_admin_params = {
            _s.ADMIN_QP_ROOM_SORT: room_sort,
            _s.ADMIN_QP_PUBLIC_USER_Q: public_user_q,
            _s.ADMIN_QP_PUBLIC_USER_STATUS: public_user_status,
            _s.ADMIN_QP_PUBLIC_USER_VERIFIED: public_user_verified,
            _s.ADMIN_QP_PUBLIC_USER_PAGE: str(safe_public_user_page),
            _s.ADMIN_QP_TRASH_PAGE: str(safe_trash_page),
            _s.ADMIN_QP_TRASH_Q: trash_q,
            _s.ADMIN_QP_SESSIONS_PAGE: str(safe_sessions_page),
            _s.ADMIN_QP_PAYMENTS_PAGE: str(safe_payments_page),
            _s.ADMIN_QP_AUDIT_EVENT_TYPE: audit_event_type,
            _s.ADMIN_QP_AUDIT_STATUS: audit_status,
            _s.ADMIN_QP_AUDIT_EMAIL: audit_email,
            _s.ADMIN_QP_AUDIT_IP: audit_ip,
            _s.ADMIN_QP_AUDIT_PAGE: str(safe_audit_page),
            _s.ADMIN_QP_PAYMENT_DATE_FROM: (payment_date_from or "").strip()[:32],
            _s.ADMIN_QP_PAYMENT_DATE_TO: (payment_date_to or "").strip()[:32],
            "center_posts_page": str(max(1, int(center_posts_page or 1))),
        }
    
        def _admin_page_url(**overrides: str) -> str:
            params = dict(base_admin_params)
            for k, v in overrides.items():
                params[k] = v
            return _s._url_with_params("/admin", **params)
    
        public_users_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_PUBLIC_USER_PAGE: str(max(1, safe_public_user_page - 1))})
        public_users_page_next_url = _admin_page_url(
            **{_s.ADMIN_QP_PUBLIC_USER_PAGE: str(min(public_users_total_pages, safe_public_user_page + 1))}
        )
        security_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_AUDIT_PAGE: str(max(1, safe_audit_page - 1))})
        security_page_next_url = _admin_page_url(
            **{_s.ADMIN_QP_AUDIT_PAGE: str(min(security_events_total_pages, safe_audit_page + 1))}
        )
        sessions_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_SESSIONS_PAGE: str(max(1, safe_sessions_page - 1))})
        sessions_page_next_url = _admin_page_url(
            **{_s.ADMIN_QP_SESSIONS_PAGE: str(min(sessions_total_pages, safe_sessions_page + 1))}
        )
        payments_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_PAYMENTS_PAGE: str(max(1, safe_payments_page - 1))})
        payments_page_next_url = _admin_page_url(
            **{_s.ADMIN_QP_PAYMENTS_PAGE: str(min(payments_total_pages, safe_payments_page + 1))}
        )
        trash_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_TRASH_PAGE: str(max(1, safe_trash_page - 1))})
        trash_page_next_url = _admin_page_url(
            **{_s.ADMIN_QP_TRASH_PAGE: str(min(trash_total_pages, safe_trash_page + 1))}
        )
    
        safe_post_edit = max(0, int(post_edit or 0))
        center_posts_page_size = _s.ADMIN_CENTER_POSTS_PAGE_SIZE
        center_posts_base_query = (
            db.query(_s.models.CenterPost)
            .filter(_s.models.CenterPost.center_id == cid)
            .order_by(_s.models.CenterPost.updated_at._s.desc())
        )
        center_posts_total = center_posts_base_query.order_by(None).count()
        safe_center_posts_page, center_posts_total_pages, center_posts_offset = _normalize_page(
            center_posts_page,
            center_posts_total,
            center_posts_page_size,
        )
        center_posts_all = (
            center_posts_base_query
            .offset(center_posts_offset)
            .limit(center_posts_page_size)
            .all()
        )
        center_posts_page_prev_url = _admin_page_url(
            **{"center_posts_page": str(max(1, safe_center_posts_page - 1))}
        )
        center_posts_page_next_url = _admin_page_url(
            **{"center_posts_page": str(min(center_posts_total_pages, safe_center_posts_page + 1))}
        )
        center_post_ids_page = [int(cp.id) for cp in center_posts_all]
        center_post_gallery_counts = {
            int(pid): int(cnt)
            for pid, cnt in (
                db.query(_s.models.CenterPostImage.post_id, _s.func.count(_s.models.CenterPostImage.id))
                .filter(_s.models.CenterPostImage.post_id.in_(center_post_ids_page))
                .group_by(_s.models.CenterPostImage.post_id)
                .all()
            )
        } if center_post_ids_page else {}
    
        def _post_admin_edit_url(edit_id: int) -> str:
            return _admin_page_url(**{_s.ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"
    
        center_post_admin_rows: list[dict[str, str | int | bool]] = []
        for cp in center_posts_all:
            center_post_admin_rows.append(
                {
                    "id": cp.id,
                    "title": cp.title,
                    "post_type": cp.post_type,
                    "type_label": _s.CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                    "is_published": cp.is_published,
                    "is_pinned": cp.is_pinned,
                    "updated_display": _s._fmt_dt(cp.updated_at),
                    "gallery_count": center_post_gallery_counts.get(int(cp.id), 0),
                    "public_url": _s._url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                    if cp.is_published
                    else "",
                    "edit_url": _post_admin_edit_url(cp.id),
                }
            )
    
        editing_post: dict[str, _s.Any] | None = None
        if safe_post_edit:
            ep = db.get(_s.models.CenterPost, safe_post_edit)
            if ep and ep.center_id == cid:
                gi = sorted(ep.images, key=lambda x: (x.sort_order, x.id))
                editing_post = {
                    "id": ep.id,
                    "title": ep.title,
                    "summary": ep.summary or "",
                    "body": ep.body or "",
                    "post_type": ep.post_type,
                    "is_pinned": ep.is_pinned,
                    "is_published": ep.is_published,
                    "cover_image_url": ep.cover_image_url or "",
                    "gallery": [{"id": g.id, "url": g.image_url} for g in gi],
                }
    
        center_post_type_choices = [
            {"value": k, "label": v} for k, v in sorted(_s.CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
        ]
    
        dash_home = _admin_page_url()
        admin_insights: list[dict[str, str]] = []
        if sessions_today_no_bookings:
            admin_insights.append(
                {
                    "label": f"جلسات اليوم بلا حجوزات نشطة: {sessions_today_no_bookings}",
                    "href": f"{dash_home}#section-sessions",
                    "kind": "warn",
                }
            )
        if subs_expiring_7d:
            admin_insights.append(
                {
                    "label": f"اشتراكات تنتهي خلال 7 أيام: {subs_expiring_7d}",
                    "href": f"{dash_home}#section-plans",
                    "kind": "info",
                }
            )
        if public_users_unverified_count:
            admin_insights.append(
                {
                    "label": f"مستخدمون غير موثّقين (عام): {public_users_unverified_count}",
                    "href": f"{dash_home}#section-public-users",
                    "kind": "info",
                }
            )
        if schedule_conflicts:
            admin_insights.append(
                {
                    "label": f"تضارب جدولة في نفس الغرفة: {len(schedule_conflicts)}",
                    "href": f"{dash_home}#section-sessions",
                    "kind": "warn",
                }
            )
        if pending_payments_stale_8d:
            admin_insights.append(
                {
                    "label": f"معلّقات قديمة (+8 أيام): {pending_payments_stale_8d}",
                    "href": "/admin/reports/health",
                    "kind": "warn",
                }
            )
        if failed_payments_7d:
            admin_insights.append(
                {
                    "label": f"مدفوعات فاشلة في آخر 7 أيام: {failed_payments_7d}",
                    "href": "/admin/reports/health",
                    "kind": "warn",
                }
            )
    
        morning_brief = {
            "sessions_today": sessions_scheduled_today,
            "bookings_today": bookings_active_today,
            "revenue_today": float(paid_revenue_today or 0),
            "pending_stale_8d": pending_payments_stale_8d,
            "failed_7d": failed_payments_7d,
            "subs_expiring_7d": subs_expiring_7d,
        }
    
        export_pay_params: dict[str, str] = {}
        pf = (payment_date_from or "").strip()[:32]
        pt = (payment_date_to or "").strip()[:32]
        if pf:
            export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_FROM] = pf
        if pt:
            export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_TO] = pt
        data_export_urls = {
            "clients": "/admin/export/clients._s.csv",
            "bookings": "/admin/export/bookings._s.csv",
            "payments": _s._url_with_params("/admin/export/payments._s.csv", **export_pay_params)
            if export_pay_params
            else "/admin/export/payments._s.csv",
        }
    
        _env_b, _env_s, _env_g = _s.loyalty_thresholds()
        _eff_b, _eff_s, _eff_g = _s.effective_loyalty_thresholds(center)
        loyalty_admin = {
            "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
            "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
        }
    
        index_page_cfg = _s.merge_index_page_config(center) if center else _s._default_index_page_config()
    
        return _s.templates.TemplateResponse(
            request,
            "admin.html",
            {
                "user": user,
                "center": center,
                "index_page": index_page_cfg,
                "msg": msg,
                "admin_flash": admin_flash,
                "dashboard": dashboard,
                "rooms": rooms,
                "plans": plan_rows,
                "sessions": session_rows,
                "recent_payments": payment_rows,
                "public_users": public_user_rows,
                "faq_items": faq_rows,
                "security_events": security_event_rows,
                "security_summary": security_summary,
                "security_export_url": security_export_url,
                "block_history": block_history_rows,
                "security_filters": {
                    "event_type": audit_event_type,
                    "status": audit_status,
                    "email": audit_email,
                    "ip": audit_ip,
                },
                "public_user_filters": {
                    "q": public_user_q,
                    "status": status_key,
                    "verified": verified_key or "all",
                },
                "public_user_pagination": {
                    "page": safe_public_user_page,
                    "page_size": public_users_page_size,
                    "total": public_users_total,
                    "total_pages": public_users_total_pages,
                    "has_prev": safe_public_user_page > 1,
                    "has_next": safe_public_user_page < public_users_total_pages,
                    "prev_url": public_users_page_prev_url,
                    "next_url": public_users_page_next_url,
                },
                "trash_users": trash_user_rows,
                "trash_filters": {"q": trash_q},
                "trash_pagination": {
                    "page": safe_trash_page,
                    "page_size": public_users_page_size,
                    "total": trash_total,
                    "total_pages": trash_total_pages,
                    "has_prev": safe_trash_page > 1,
                    "has_next": safe_trash_page < trash_total_pages,
                    "prev_url": trash_page_prev_url,
                    "next_url": trash_page_next_url,
                },
                "security_pagination": {
                    "page": safe_audit_page,
                    "page_size": audit_page_size,
                    "total": security_events_total,
                    "total_pages": security_events_total_pages,
                    "has_prev": safe_audit_page > 1,
                    "has_next": safe_audit_page < security_events_total_pages,
                    "prev_url": security_page_prev_url,
                    "next_url": security_page_next_url,
                },
                "sessions_pagination": {
                    "page": safe_sessions_page,
                    "page_size": sessions_page_size,
                    "total": sessions_total,
                    "total_pages": sessions_total_pages,
                    "has_prev": safe_sessions_page > 1,
                    "has_next": safe_sessions_page < sessions_total_pages,
                    "prev_url": sessions_page_prev_url,
                    "next_url": sessions_page_next_url,
                },
                "payments_pagination": {
                    "page": safe_payments_page,
                    "page_size": payments_page_size,
                    "total": payments_total,
                    "total_pages": payments_total_pages,
                    "has_prev": safe_payments_page > 1,
                    "has_next": safe_payments_page < payments_total_pages,
                    "prev_url": payments_page_prev_url,
                    "next_url": payments_page_next_url,
                },
                "center_posts_pagination": {
                    "page": safe_center_posts_page,
                    "page_size": center_posts_page_size,
                    "total": center_posts_total,
                    "total_pages": center_posts_total_pages,
                    "has_prev": safe_center_posts_page > 1,
                    "has_next": safe_center_posts_page < center_posts_total_pages,
                    "prev_url": center_posts_page_prev_url,
                    "next_url": center_posts_page_next_url,
                },
                "room_filters": {
                    "sort": (
                        room_sort_key
                        if room_sort_key in room_ordering or room_sort_key in {"sessions_desc", "sessions_asc"}
                        else "id_asc"
                    ),
                },
                "center_id": cid,
                "admin_public_index_url": _s._url_with_params("/index", center_id=str(cid)),
                "admin_insights": admin_insights,
                "morning_brief": morning_brief,
                "revenue_7d_bars": revenue_7d_bars,
                "ops_today_rows": ops_today_rows,
                "ops_tomorrow_rows": ops_tomorrow_rows,
                "schedule_conflicts": schedule_conflicts,
                "admin_login_audit_rows": admin_login_audit_rows,
                "data_export_urls": data_export_urls,
                "payment_date_from_value": pf,
                "payment_date_to_value": pt,
                "loyalty_admin": loyalty_admin,
                **_s.admin_ui_flags(user),
                "permission_catalog": _s.PERMISSION_CATALOG,
                "assignable_staff_roles": tuple(
                    r for r in _s.STAFF_ROLE_CATALOG if r["id"] in _s.ASSIGNABLE_BY_CENTER_OWNER
                ),
                "staff_role_sections_hints_json": _s.json.dumps(_s.STAFF_ROLE_UI_SECTIONS_HINT, ensure_ascii=False),
                "staff_permission_groups": _s.permission_catalog_grouped_for_custom_staff(),
                "role_permission_matrix": _s.handbook_matrix_rows(),
                "center_post_admin_rows": center_post_admin_rows,
                "editing_post": editing_post,
                "center_post_type_choices": center_post_type_choices,
                "post_edit_id": safe_post_edit,
                "perm_report_sessions": (
                    _s.user_has_permission(user, "sessions.manage")
                    or _s.user_has_permission(user, "reports.financial")
                    or _s.user_has_permission(user, "dashboard.view")
                ),
                "perm_report_revenue": (
                    _s.user_has_permission(user, "payments.records")
                    or _s.user_has_permission(user, "reports.financial")
                    or _s.user_has_permission(user, "dashboard.financial")
                ),
            },
        )
