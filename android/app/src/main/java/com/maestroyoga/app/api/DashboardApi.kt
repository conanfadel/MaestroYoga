package com.maestroyoga.app.api

import retrofit2.http.GET

interface DashboardApi {
    @GET("api/v1/dashboard/summary")
    suspend fun summary(): DashboardSummaryDto
}
