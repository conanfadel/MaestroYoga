package com.maestroyoga.app.api

import com.google.gson.annotations.SerializedName

data class DashboardSummaryDto(
    @SerializedName("center_id") val centerId: Int,
    @SerializedName("clients_count") val clientsCount: Int,
    @SerializedName("sessions_count") val sessionsCount: Int,
    @SerializedName("bookings_count") val bookingsCount: Int,
    @SerializedName("active_plans_count") val activePlansCount: Int,
    @SerializedName("revenue_total") val revenueTotal: Double,
    @SerializedName("revenue_today") val revenueToday: Double,
    @SerializedName("pending_payments_count") val pendingPaymentsCount: Int,
)
