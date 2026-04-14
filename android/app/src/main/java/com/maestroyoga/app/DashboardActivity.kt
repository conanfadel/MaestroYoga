package com.maestroyoga.app

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.maestroyoga.app.api.DashboardSummaryDto
import com.maestroyoga.app.api.AuthSessionManager
import com.maestroyoga.app.api.NetworkModule
import com.maestroyoga.app.api.TokenStore
import com.maestroyoga.app.api.UserDto
import com.maestroyoga.app.databinding.ActivityDashboardBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.HttpException
import java.io.IOException
import java.text.NumberFormat
import java.util.Locale

class DashboardActivity : AppCompatActivity() {
    private lateinit var binding: ActivityDashboardBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnBack.setOnClickListener { finish() }
        binding.btnRefresh.setOnClickListener { loadDashboard() }
        binding.btnLogout.setOnClickListener {
            lifecycleScope.launch {
                withContext(Dispatchers.IO) {
                    AuthSessionManager.remoteLogout()
                }
                finish()
            }
        }

        loadDashboard()
    }

    private fun loadDashboard() {
        binding.output.text = getString(R.string.dashboard_loading)
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) {
                try {
                    val me = NetworkModule.authApi().me()
                    val summary = NetworkModule.dashboardApi().summary()
                    DashboardUiState(
                        error = null,
                        user = me,
                        summary = summary,
                        debug = "GET /api/v1/auth/me + GET /api/v1/dashboard/summary: OK",
                    )
                } catch (e: Exception) {
                    val refreshed = AuthSessionManager.refreshTokenIfPossibleOn401(e)
                    if (refreshed) {
                        return@withContext try {
                            val me = NetworkModule.authApi().me()
                            val summary = NetworkModule.dashboardApi().summary()
                            DashboardUiState(
                                error = null,
                                user = me,
                                summary = summary,
                                debug = "Auto re-login succeeded after 401",
                            )
                        } catch (retryError: Exception) {
                            DashboardUiState(
                                error = mapFriendlyError(retryError),
                                user = null,
                                summary = null,
                                debug = "retry_error=${retryError.javaClass.simpleName}",
                            )
                        }
                    }
                    DashboardUiState(
                        error = mapFriendlyError(e),
                        user = null,
                        summary = null,
                        debug = "error=${e.javaClass.simpleName}",
                    )
                }
            }
            render(text)
        }
    }

    private fun mapFriendlyError(e: Exception): String {
        return when (e) {
            is HttpException -> when (e.code()) {
                401 -> {
                    TokenStore.clearAll()
                    getString(R.string.err_unauthorized)
                }
                403 -> getString(R.string.err_forbidden)
                else -> getString(R.string.err_server, e.code())
            }
            is IOException -> getString(R.string.err_network)
            else -> e.message ?: e.javaClass.simpleName
        }
    }

    private fun render(state: DashboardUiState) {
        if (state.error != null) {
            binding.output.text = state.error
            binding.userInfo.text = state.error
            return
        }
        val u = state.user ?: return
        val s = state.summary ?: return
        binding.userInfo.text = "${getString(R.string.label_user)}: ${u.email} | ${u.role}"
        binding.kpiClients.text = "${getString(R.string.kpi_clients)}: ${formatInt(s.clientsCount)}"
        binding.kpiSessions.text = "${getString(R.string.kpi_sessions)}: ${formatInt(s.sessionsCount)}"
        binding.kpiBookings.text = "${getString(R.string.kpi_bookings)}: ${formatInt(s.bookingsCount)}"
        binding.kpiActivePlans.text = "${getString(R.string.kpi_active_plans)}: ${formatInt(s.activePlansCount)}"
        binding.kpiRevenueTotal.text = "${getString(R.string.kpi_revenue_total)}: ${formatMoney(s.revenueTotal)}"
        binding.kpiRevenueToday.text = "${getString(R.string.kpi_revenue_today)}: ${formatMoney(s.revenueToday)}"
        binding.kpiPendingPayments.text =
            "${getString(R.string.kpi_pending_payments)}: ${formatInt(s.pendingPaymentsCount)}"
        binding.output.text = state.debug
    }

    private fun formatInt(v: Int): String = NumberFormat.getIntegerInstance(Locale("ar")).format(v)

    private fun formatMoney(v: Double): String {
        val nf = NumberFormat.getNumberInstance(Locale("ar"))
        nf.minimumFractionDigits = 2
        nf.maximumFractionDigits = 2
        return nf.format(v)
    }

    private data class DashboardUiState(
        val error: String?,
        val user: UserDto?,
        val summary: DashboardSummaryDto?,
        val debug: String,
    )
}
