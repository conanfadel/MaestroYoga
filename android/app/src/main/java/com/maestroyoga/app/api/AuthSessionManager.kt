package com.maestroyoga.app.api

import retrofit2.HttpException

/**
 * Handles one-shot auto re-login when access token expires.
 */
object AuthSessionManager {
    suspend fun refreshTokenIfPossibleOn401(error: Exception): Boolean {
        if (error !is HttpException || error.code() != 401) return false
        val creds = TokenStore.getLoginCredentials() ?: return false
        return try {
            val token = NetworkModule.authApi().login(
                LoginRequest(
                    email = creds.first,
                    password = creds.second,
                ),
            )
            TokenStore.setAccessToken(token.accessToken)
            true
        } catch (_: Exception) {
            TokenStore.clearAll()
            false
        }
    }
}
