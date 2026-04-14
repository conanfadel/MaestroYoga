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
    private const val KEY_EMAIL = "login_email"
    private const val KEY_PASSWORD = "login_password"

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

    fun setLoginCredentials(email: String, password: String) {
        prefs?.edit()
            ?.putString(KEY_EMAIL, email)
            ?.putString(KEY_PASSWORD, password)
            ?.apply()
    }

    fun getLoginCredentials(): Pair<String, String>? {
        val email = prefs?.getString(KEY_EMAIL, null)
        val password = prefs?.getString(KEY_PASSWORD, null)
        if (email.isNullOrBlank() || password.isNullOrBlank()) return null
        return email to password
    }

    fun clearAll() {
        prefs?.edit()
            ?.remove(KEY_ACCESS)
            ?.remove(KEY_EMAIL)
            ?.remove(KEY_PASSWORD)
            ?.apply()
    }
}
