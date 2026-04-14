package com.maestroyoga.app.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface AuthApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body body: RefreshTokenRequest): TokenResponse

    @POST("api/v1/auth/logout")
    suspend fun logout(@Body body: RefreshTokenRequest): LogoutResponse

    @POST("api/v1/auth/logout/all")
    suspend fun logoutAll(): LogoutResponse

    @GET("api/v1/auth/me")
    suspend fun me(): UserDto
}
