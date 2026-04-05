package com.maestroyoga.app.api

import retrofit2.http.GET

interface MetaApi {
    @GET("api/v1/meta")
    suspend fun meta(): MetaResponse
}
