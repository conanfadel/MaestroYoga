package com.maestroyoga.app

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.maestroyoga.app.api.LoginRequest
import com.maestroyoga.app.api.NetworkModule
import com.maestroyoga.app.api.TokenStore
import com.maestroyoga.app.api.UserDto
import com.maestroyoga.app.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.HttpException
import java.io.IOException

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        TokenStore.init(applicationContext)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.baseUrlLabel.text = getString(R.string.hint_api) + "\n\nBase: " + BuildConfig.API_BASE_URL
        binding.btnRetry.setOnClickListener { loadMeta() }
        binding.btnLogin.setOnClickListener { login() }
        binding.btnLogout.setOnClickListener {
            TokenStore.clear()
            binding.output.text = getString(R.string.msg_logged_out)
        }
        binding.btnOpenDashboard.setOnClickListener {
            startActivity(Intent(this, DashboardActivity::class.java))
        }

        loadMeta()
    }

    private fun loadMeta() {
        binding.output.text = getString(R.string.status_loading)
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) {
                try {
                    val meta = NetworkModule.metaApi().meta()
                    buildString {
                        appendLine("api_version: ${meta.apiVersion}")
                        appendLine("app: ${meta.app}")
                        appendLine("server_version: ${meta.serverVersion}")
                        appendLine("openapi_json: ${meta.openapiJson}")
                        appendLine("docs: ${meta.docs}")
                        meta.clientHint?.let { appendLine("client_hint: $it") }
                        appendLine()
                        append(fetchMeIfLoggedIn())
                    }
                } catch (e: Exception) {
                    mapFriendlyError(e)
                }
            }
            binding.output.text = text
        }
    }

    private fun login() {
        val email = binding.inputEmail.text?.toString()?.trim().orEmpty()
        val password = binding.inputPassword.text?.toString().orEmpty()
        if (email.isEmpty() || password.isEmpty()) {
            binding.output.text = getString(R.string.err_email_password_required)
            return
        }
        binding.output.text = getString(R.string.status_loading)
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) {
                try {
                    val token = NetworkModule.authApi().login(LoginRequest(email, password))
                    TokenStore.setAccessToken(token.accessToken)
                    buildString {
                        appendLine(getString(R.string.msg_login_ok, token.user.email))
                        appendLine()
                        appendLine("GET /api/v1/auth/me:")
                        appendLine(formatUser(NetworkModule.authApi().me()))
                    }
                } catch (e: Exception) {
                    mapFriendlyError(e)
                }
            }
            binding.output.text = text
            if (TokenStore.getAccessToken().isNullOrBlank().not()) {
                startActivity(Intent(this@MainActivity, DashboardActivity::class.java))
            }
        }
    }

    private suspend fun fetchMeIfLoggedIn(): String = withContext(Dispatchers.IO) {
        val token = TokenStore.getAccessToken() ?: return@withContext ""
        if (token.isBlank()) return@withContext ""
        try {
            "GET /api/v1/auth/me:\n" + formatUser(NetworkModule.authApi().me())
        } catch (e: Exception) {
            TokenStore.clear()
            "auth/me failed (token cleared): ${mapFriendlyError(e)}\n"
        }
    }

    private fun mapFriendlyError(e: Exception): String {
        return when (e) {
            is HttpException -> when (e.code()) {
                401 -> getString(R.string.err_unauthorized)
                403 -> getString(R.string.err_forbidden)
                else -> getString(R.string.err_server, e.code())
            }
            is IOException -> getString(R.string.err_network)
            else -> e.message ?: e.javaClass.simpleName
        }
    }

    private fun formatUser(u: UserDto): String = buildString {
        appendLine("id: ${u.id}")
        appendLine("email: ${u.email}")
        appendLine("full_name: ${u.fullName}")
        appendLine("role: ${u.role}")
        u.centerId?.let { appendLine("center_id: $it") }
    }
}
