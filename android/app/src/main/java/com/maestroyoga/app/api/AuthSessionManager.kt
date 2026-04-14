package com.maestroyoga.app.api

import retrofit2.HttpException

/**
 * Handles one-shot auto re-login when access token expires.
 */
object AuthSessionManager {
    suspend fun refreshTokenIfPossibleOn401(error: Exception): Boolean {
        if (error !is HttpException || error.code() != 401) return false
        val refresh = TokenStore.getRefreshToken() ?: return false
        return try {
            val token = NetworkModule.authApi().refresh(RefreshTokenRequest(refreshToken = refresh))
            TokenStore.setAccessToken(token.accessToken)
            TokenStore.setRefreshToken(token.refreshToken)
            true
        } catch (_: Exception) {
            TokenStore.clearAll()
            false
        }
    }
}
