package com.maestroyoga.app.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @GET("api/v1/auth/me")
    suspend fun me(): UserDto
}
