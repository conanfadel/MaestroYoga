package com.maestroyoga.app.api

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Stores the staff JWT in encrypted preferences (never in plain SharedPreferences).
 */
object TokenStore {

    private const val PREFS_NAME = "maestro_auth_enc"
    private const val KEY_ACCESS = "access_token"
    private const val KEY_REFRESH = "refresh_token"

    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        if (prefs != null) return
        val app = context.applicationContext
        val masterKey = MasterKey.Builder(app)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        prefs = EncryptedSharedPreferences.create(
            app,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    fun getAccessToken(): String? = prefs?.getString(KEY_ACCESS, null)

    fun setAccessToken(token: String?) {
        val e = prefs?.edit() ?: return
        if (token.isNullOrBlank()) {
            e.remove(KEY_ACCESS)
        } else {
            e.putString(KEY_ACCESS, token)
        }
        e.apply()
    }

    fun clear() {
        prefs?.edit()?.remove(KEY_ACCESS)?.apply()
    }

    fun setRefreshToken(token: String?) {
        prefs?.edit()
            ?.putString(KEY_REFRESH, token)
            ?.apply()
    }

    fun getRefreshToken(): String? = prefs?.getString(KEY_REFRESH, null)

    fun clearAll() {
        prefs?.edit()
            ?.remove(KEY_ACCESS)
            ?.remove(KEY_REFRESH)
            ?.apply()
    }
}
