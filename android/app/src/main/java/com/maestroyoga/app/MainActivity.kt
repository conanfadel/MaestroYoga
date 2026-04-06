package com.maestroyoga.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.maestroyoga.app.api.NetworkModule
import com.maestroyoga.app.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.baseUrlLabel.text = getString(R.string.hint_api) + "\n\nBase: " + BuildConfig.API_BASE_URL

        binding.btnRetry.setOnClickListener { loadMeta() }
        binding.btnOpenDocs.setOnClickListener {
            val base = BuildConfig.API_BASE_URL.trimEnd('/')
            val url = "$base/docs"
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
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
                    }
                } catch (e: Exception) {
                    e.stackTraceToString()
                }
            }
            binding.output.text = text
        }
    }
}
