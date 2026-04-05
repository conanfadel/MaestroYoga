package com.maestroyoga.app.api

import com.google.gson.annotations.SerializedName

/**
 * يطابق JSON من GET /api/v1/meta على الخادم.
 */
data class MetaResponse(
    @SerializedName("api_version") val apiVersion: String,
    val app: String,
    @SerializedName("server_version") val serverVersion: String,
    @SerializedName("openapi_json") val openapiJson: String,
    val docs: String,
    @SerializedName("client_hint") val clientHint: String? = null,
)
