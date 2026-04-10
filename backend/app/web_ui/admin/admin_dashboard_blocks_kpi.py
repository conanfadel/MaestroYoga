"""KPI counts, revenue chart, ops rows, and aggregate stats for the admin dashboard."""

from __future__ import annotations

from .admin_dashboard_blocks_kpi_aggregates import (
    aggregate_paid_revenue_and_public_user_stats,
    fetch_admin_login_audit_rows,
)
from .admin_dashboard_blocks_kpi_counts import AdminKpiCounts, fetch_admin_kpi_counts
from .admin_dashboard_blocks_kpi_revenue_ops import (
    build_ops_rows_and_schedule_conflicts,
    build_revenue_7d_bars,
)

__all__ = [
    "AdminKpiCounts",
    "aggregate_paid_revenue_and_public_user_stats",
    "build_ops_rows_and_schedule_conflicts",
    "build_revenue_7d_bars",
    "fetch_admin_kpi_counts",
    "fetch_admin_login_audit_rows",
]
