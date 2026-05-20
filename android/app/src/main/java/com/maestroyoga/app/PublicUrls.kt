package com.maestroyoga.app

import android.net.Uri

/** روابط واجهة العملاء المشتقة من إعدادات Gradle. */
object PublicUrls {
    private val base: String = BuildConfig.API_BASE_URL
    val home: String = BuildConfig.PUBLIC_HOME_URL

    private val homeNextPath: String
        get() {
            val path = Uri.parse(home).path?.trim().orEmpty().ifBlank { "/index" }
            val query = Uri.parse(home).query
            return if (query.isNullOrBlank()) path else "$path?$query"
        }

    val login: String
        get() = base + "public/login?next=" + Uri.encode(homeNextPath)

    val register: String
        get() = base + "public/register?next=" + Uri.encode(homeNextPath)

    val account: String
        get() = base + "public/account?next=" + Uri.encode(homeNextPath)
}
