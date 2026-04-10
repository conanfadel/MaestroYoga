from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    center_id: int
    clients_count: int
    sessions_count: int
    bookings_count: int
    active_plans_count: int
    revenue_total: float
    revenue_today: float
    pending_payments_count: int
