package com.maestroyoga.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.maestroyoga.app.databinding.ActivityPublicWebBinding

/**
 * هجين سريع: WebView لواجهة الموقع + شريط تنقل أصلي (حجز، دخول، تسجيل، حسابي).
 */
class PublicWebActivity : AppCompatActivity() {
    private lateinit var binding: ActivityPublicWebBinding
    private val homeUrl: String = PublicUrls.home
    private var suppressBottomNavCallback = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPublicWebBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayShowTitleEnabled(true)

        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.updatePadding(left = bars.left, right = bars.right, bottom = bars.bottom)
            binding.toolbar.updatePadding(top = bars.top)
            insets
        }

        binding.swipeRefresh.setOnRefreshListener { binding.webView.reload() }
        binding.btnRetry.setOnClickListener { loadUrl(homeUrl, clearHistory = true) }

        setupBottomNav(binding.bottomNav)
        setupWebView()

        onBackPressedDispatcher.addCallback(this) {
            if (binding.webView.canGoBack()) {
                binding.webView.goBack()
            } else {
                finish()
            }
        }

        if (savedInstanceState != null) {
            binding.webView.restoreState(savedInstanceState)
        } else {
            val startUrl = intent.getStringExtra(EXTRA_START_URL) ?: homeUrl
            loadUrl(startUrl, clearHistory = true)
            syncBottomNavForUrl(startUrl)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.webView.saveState(outState)
    }

    private fun setupBottomNav(nav: BottomNavigationView) {
        nav.setOnItemSelectedListener { item ->
            if (suppressBottomNavCallback) return@setOnItemSelectedListener true
            val url = when (item.itemId) {
                R.id.nav_home -> PublicUrls.home
                R.id.nav_login -> PublicUrls.login
                R.id.nav_register -> PublicUrls.register
                R.id.nav_account -> PublicUrls.account
                else -> return@setOnItemSelectedListener false
            }
            loadUrl(url, clearHistory = true)
            true
        }
    }

    private fun syncBottomNavForUrl(url: String?) {
        val path = url?.let { Uri.parse(it).path?.lowercase().orEmpty() }.orEmpty()
        val id = when {
            path.contains("/public/register") -> R.id.nav_register
            path.contains("/public/login") -> R.id.nav_login
            path.contains("/public/account") -> R.id.nav_account
            else -> R.id.nav_home
        }
        if (binding.bottomNav.selectedItemId != id) {
            suppressBottomNavCallback = true
            try {
                binding.bottomNav.menu.findItem(id)?.isChecked = true
            } finally {
                suppressBottomNavCallback = false
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(binding.webView, true)

        binding.webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = false
            displayZoomControls = false
            setSupportMultipleWindows(false)
        }
        binding.webView.layoutDirection = View.LAYOUT_DIRECTION_RTL

        binding.webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress in 1..99) {
                    binding.progress.visibility = View.VISIBLE
                    binding.progress.progress = newProgress
                } else {
                    binding.progress.visibility = View.GONE
                }
            }
        }

        binding.webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url?.toString().orEmpty()
                if (url.isBlank()) return false
                if (isSameOrigin(url)) return false
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                return true
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                hideError()
                binding.swipeRefresh.isRefreshing = false
                syncBottomNavForUrl(url)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                binding.swipeRefresh.isRefreshing = false
                binding.progress.visibility = View.GONE
                syncBottomNavForUrl(url)
                val title = view?.title?.trim().orEmpty()
                supportActionBar?.title = if (title.isNotEmpty()) title else getString(R.string.public_web_title)
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (!request.isForMainFrame) return
                showError(getString(R.string.public_web_load_error))
            }
        }
    }

    private fun loadUrl(url: String, clearHistory: Boolean) {
        hideError()
        binding.swipeRefresh.isRefreshing = true
        if (clearHistory) {
            binding.webView.loadUrl(url)
        } else {
            binding.webView.reload()
        }
    }

    private fun showError(message: String) {
        binding.errorText.text = message
        binding.errorPanel.visibility = View.VISIBLE
        binding.swipeRefresh.visibility = View.GONE
        binding.swipeRefresh.isRefreshing = false
        binding.progress.visibility = View.GONE
    }

    private fun hideError() {
        binding.errorPanel.visibility = View.GONE
        binding.swipeRefresh.visibility = View.VISIBLE
    }

    private fun isSameOrigin(url: String): Boolean {
        return try {
            val base = Uri.parse(BuildConfig.API_BASE_URL)
            val target = Uri.parse(url)
            base.host.equals(target.host, ignoreCase = true) &&
                base.scheme.equals(target.scheme, ignoreCase = true)
        } catch (_: Exception) {
            false
        }
    }

    companion object {
        const val EXTRA_START_URL = "extra_start_url"
    }
}
