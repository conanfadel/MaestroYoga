"""Queries and template dict for the admin revenue HTML report."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from .. import models
from ..admin_report_helpers import (
    effective_vat_percent_for_center,
    payment_method_label_ar,
    report_previous_period_range,
    vat_inclusive_breakdown,
)
from ..time_utils import utcnow_naive
from ..web_shared import _fmt_dt, _url_with_params


def build_revenue_report_template_context(
    *,
    db: Session,
    cid: int,
    center: models.Center | None,
    d0: date,
    d1: date,
    period: str,
    range_label: str | None,
    range_err: str | None,
    date_from: str,
    date_to: str,
    admin_qp_payment_date_from: str,
    admin_qp_payment_date_to: str,
) -> dict[str, Any]:
    vat_pct = effective_vat_percent_for_center(center=center)

    base_pf = [
        models.Payment.center_id == cid,
        func.date(models.Payment.paid_at) >= d0,
        func.date(models.Payment.paid_at) <= d1,
    ]
    paid_total = float(
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(*base_pf, models.Payment.status == "paid")
        .scalar()
        or 0.0
    )
    vat_breakdown = vat_inclusive_breakdown(paid_total, vat_pct)
    paid_count = (
        db.query(func.count(models.Payment.id)).filter(*base_pf, models.Payment.status == "paid").scalar()
        or 0
    )
    p0, p1, prev_period_label = report_previous_period_range(d0, d1)
    prev_pf = [
        models.Payment.center_id == cid,
        func.date(models.Payment.paid_at) >= p0,
        func.date(models.Payment.paid_at) <= p1,
    ]
    prev_paid_total = float(
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(*prev_pf, models.Payment.status == "paid")
        .scalar()
        or 0.0
    )
    prev_paid_count = int(
        db.query(func.count(models.Payment.id)).filter(*prev_pf, models.Payment.status == "paid").scalar() or 0
    )
    paid_delta_pct = (
        round(100.0 * (paid_total - prev_paid_total) / prev_paid_total, 1)
        if prev_paid_total > 0
        else None
    )
    count_delta = int(paid_count - prev_paid_count)

    by_day = (
        db.query(
            func.date(models.Payment.paid_at).label("d"),
            func.coalesce(func.sum(models.Payment.amount), 0.0),
        )
        .filter(*base_pf, models.Payment.status == "paid")
        .group_by(func.date(models.Payment.paid_at))
        .order_by(func.date(models.Payment.paid_at).asc())
        .all()
    )
    by_method = (
        db.query(
            models.Payment.payment_method,
            func.count(models.Payment.id),
            func.coalesce(func.sum(models.Payment.amount), 0.0),
        )
        .filter(*base_pf, models.Payment.status == "paid")
        .group_by(models.Payment.payment_method)
        .all()
    )
    by_status = (
        db.query(
            models.Payment.status,
            func.count(models.Payment.id),
            func.coalesce(func.sum(models.Payment.amount), 0.0),
        )
        .filter(*base_pf)
        .group_by(models.Payment.status)
        .all()
    )
    sub_cond = models.Payment.payment_method.like("subscription_%")
    cat_session_count, cat_session_amount, cat_sub_count, cat_sub_amount, cat_other_count, cat_other_amount = (
        db.query(
            func.coalesce(
                func.sum(case((and_(~sub_cond, models.Payment.booking_id.is_not(None)), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(~sub_cond, models.Payment.booking_id.is_not(None)),
                            models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            func.coalesce(func.sum(case((sub_cond, 1), else_=0)), 0),
            func.coalesce(func.sum(case((sub_cond, models.Payment.amount), else_=0.0)), 0.0),
            func.coalesce(
                func.sum(case((and_(~sub_cond, models.Payment.booking_id.is_(None)), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(~sub_cond, models.Payment.booking_id.is_(None)),
                            models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        )
        .filter(*base_pf, models.Payment.status == "paid")
        .one()
    )
    cat_session = {"count": int(cat_session_count or 0), "amount": float(cat_session_amount or 0.0)}
    cat_sub = {"count": int(cat_sub_count or 0), "amount": float(cat_sub_amount or 0.0)}
    cat_other = {"count": int(cat_other_count or 0), "amount": float(cat_other_amount or 0.0)}
    product_rows = [
        {"label": "حجز جلسة (مرتبط بحجز)", **cat_session},
        {"label": "اشتراك / باقة", **cat_sub},
        {"label": "أخرى (بدون ربط حجز)", **cat_other},
    ]

    status_counts: dict[str, tuple[int, float]] = {}
    for st, c, a in by_status:
        status_counts[st] = (int(c), float(a or 0))
    paid_n = status_counts.get("paid", (0, 0.0))[0]
    failed_n = status_counts.get("failed", (0, 0.0))[0]
    pend_n = status_counts.get("pending", (0, 0.0))[0] + status_counts.get("pending_payment", (0, 0.0))[0]
    terminal_n = paid_n + failed_n + pend_n
    success_rate_pct = round(100.0 * paid_n / terminal_n, 1) if terminal_n else 0.0

    now = utcnow_naive()
    anchor = func.coalesce(models.Payment.created_at, models.Payment.paid_at, now)
    cutoff_1d = now - timedelta(days=1)
    cutoff_7d = now - timedelta(days=7)
    (
        pending_open_count,
        pending_total_amt,
        p01_n,
        p01_amt,
        p27_n,
        p27_amt,
        p8p_n,
        p8p_amt,
    ) = (
        db.query(
            func.count(models.Payment.id),
            func.coalesce(func.sum(models.Payment.amount), 0.0),
            func.coalesce(func.sum(case((anchor >= cutoff_1d, 1), else_=0)), 0),
            func.coalesce(func.sum(case((anchor >= cutoff_1d, models.Payment.amount), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((and_(anchor < cutoff_1d, anchor >= cutoff_7d), 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((and_(anchor < cutoff_1d, anchor >= cutoff_7d), models.Payment.amount), else_=0.0)),
                0.0,
            ),
            func.coalesce(func.sum(case((anchor < cutoff_7d, 1), else_=0)), 0),
            func.coalesce(func.sum(case((anchor < cutoff_7d, models.Payment.amount), else_=0.0)), 0.0),
        )
        .filter(
            models.Payment.center_id == cid,
            models.Payment.status.in_(("pending", "pending_payment")),
        )
        .one()
    )
    pend_age_buckets = {
        "0_1": {"n": int(p01_n or 0), "amt": float(p01_amt or 0.0)},
        "2_7": {"n": int(p27_n or 0), "amt": float(p27_amt or 0.0)},
        "8p": {"n": int(p8p_n or 0), "amt": float(p8p_amt or 0.0)},
    }
    pending_total_amt = float(pending_total_amt or 0.0)
    pending_open_count = int(pending_open_count or 0)

    refund_count, refund_sum = (
        db.query(
            func.count(models.Payment.id),
            func.coalesce(func.sum(models.Payment.amount), 0.0),
        )
        .filter(*base_pf, models.Payment.status == "refunded")
        .one()
    )
    refund_count = int(refund_count or 0)
    refund_sum = float(refund_sum or 0.0)

    revenue_goal_pct: float | None = None
    monthly_rev_goal = float(center.monthly_revenue_goal) if center and center.monthly_revenue_goal is not None else None
    if monthly_rev_goal and monthly_rev_goal > 0 and (period or "").strip().lower() == "month":
        revenue_goal_pct = round(100.0 * paid_total / monthly_rev_goal, 1)

    day_rows = [{"d": row[0], "amount": float(row[1] or 0)} for row in by_day]
    method_rows = [
        {
            "method": payment_method_label_ar(m),
            "method_id": m or "",
            "count": int(c),
            "amount": float(a or 0),
        }
        for m, c, a in by_method
    ]
    status_labels = {
        "paid": "مدفوع",
        "pending": "معلّق",
        "pending_payment": "بانتظار الدفع",
        "failed": "فاشل",
        "refunded": "مسترد",
    }
    status_rows = [
        {
            "status": status_labels.get(st, st),
            "status_id": st,
            "count": int(c),
            "amount": float(a or 0),
        }
        for st, c, a in by_status
    ]
    revenue_charts_json = json.dumps(
        {
            "daily": {
                "labels": [str(r["d"]) for r in day_rows],
                "data": [r["amount"] for r in day_rows],
            },
            "methods": {
                "labels": [r["method"][:28] for r in method_rows],
                "data": [r["amount"] for r in method_rows],
            },
        },
        ensure_ascii=False,
    )
    export_q = _url_with_params(
        "/admin/export/payments.csv",
        **{
            admin_qp_payment_date_from: d0.isoformat(),
            admin_qp_payment_date_to: d1.isoformat(),
        },
    )

    return {
        "center": center,
        "range_label": range_label or "الفترة",
        "range_error": range_err,
        "period": (period or "today").strip().lower(),
        "date_from_val": (date_from or "")[:10],
        "date_to_val": (date_to or "")[:10],
        "paid_total": paid_total,
        "paid_count": int(paid_count),
        "prev_period_label": prev_period_label,
        "prev_paid_total": prev_paid_total,
        "prev_paid_count": prev_paid_count,
        "paid_delta_pct": paid_delta_pct,
        "count_delta": count_delta,
        "vat_rate_percent": vat_pct,
        "vat_net": vat_breakdown["net"],
        "vat_amount": vat_breakdown["vat"],
        "product_rows": product_rows,
        "success_rate_pct": success_rate_pct,
        "pending_total_amt": pending_total_amt,
        "pending_open_count": pending_open_count,
        "pend_age_buckets": pend_age_buckets,
        "day_rows": day_rows,
        "method_rows": method_rows,
        "status_rows": status_rows,
        "revenue_charts_json": revenue_charts_json,
        "export_payments_csv_url": export_q,
        "refund_count": refund_count,
        "refund_sum": refund_sum,
        "revenue_goal_pct": revenue_goal_pct,
        "monthly_revenue_goal": monthly_rev_goal,
        "generated_at": _fmt_dt(utcnow_naive()),
    }
