"""Security audit listing, summaries, and block history for the admin dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks_pagination import normalize_admin_list_page


@dataclass(frozen=True)
class SecurityAuditBundle:
    security_event_rows: list[dict[str, Any]]
    security_summary: dict[str, Any]
    block_history_rows: list[dict[str, Any]]
    security_export_url: str
    safe_audit_page: int
    security_events_total: int
    security_events_total_pages: int
    audit_page_size: int


def _risk_level(hits: int) -> str:
    if hits >= 12:
        return "high"
    if hits >= 5:
        return "medium"
    return "low"


def load_security_audit_bundle(
    db: _s.Session,
    *,
    audit_event_type: str,
    audit_status: str,
    audit_email: str,
    audit_ip: str,
    audit_page: int,
) -> SecurityAuditBundle:
    audit_query = db.query(_s.models.SecurityAuditEvent)
    if audit_event_type.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        audit_query = audit_query.filter(
            _s.models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%")
        )
    if audit_ip.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))

    audit_page_size = _s.ADMIN_SECURITY_AUDIT_PAGE_SIZE
    security_events_total = audit_query.order_by(None).count()
    safe_audit_page, security_events_total_pages, security_events_offset = normalize_admin_list_page(
        audit_page,
        security_events_total,
        audit_page_size,
    )
    security_events = (
        audit_query.order_by(_s.models.SecurityAuditEvent.created_at.desc())
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
        .order_by(_s.func.count(_s.models.SecurityAuditEvent.id).desc())
        .limit(5)
        .all()
    )
    blocked_ips = (
        db.query(_s.models.BlockedIP)
        .filter(
            _s.models.BlockedIP.is_active.is_(True),
            _s.or_(_s.models.BlockedIP.blocked_until.is_(None), _s.models.BlockedIP.blocked_until > _s.utcnow_naive()),
        )
        .order_by(_s.models.BlockedIP.created_at.desc())
        .limit(20)
        .all()
    )

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
        .order_by(_s.models.SecurityAuditEvent.created_at.desc())
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
        "/admin/security/export/csv",
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
    )
    return SecurityAuditBundle(
        security_event_rows=security_event_rows,
        security_summary=security_summary,
        block_history_rows=block_history_rows,
        security_export_url=security_export_url,
        safe_audit_page=safe_audit_page,
        security_events_total=security_events_total,
        security_events_total_pages=security_events_total_pages,
        audit_page_size=audit_page_size,
    )
