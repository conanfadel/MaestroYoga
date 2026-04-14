package com.maestroyoga.app.api

import com.google.gson.annotations.SerializedName

data class LoginRequest(
    val email: String,
    val password: String,
)

data class TokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String?,
    @SerializedName("token_type") val tokenType: String?,
    val user: UserDto,
)

data class RefreshTokenRequest(
    @SerializedName("refresh_token") val refreshToken: String,
)

data class LogoutResponse(
    val ok: Boolean = true,
)

data class UserDto(
    val id: Int,
    @SerializedName("center_id") val centerId: Int?,
    @SerializedName("full_name") val fullName: String,
    val email: String,
    val role: String,
    @SerializedName("custom_role_label") val customRoleLabel: String?,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("created_at") val createdAt: String,
)
