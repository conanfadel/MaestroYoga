package com.maestroyoga.app.api

import com.maestroyoga.app.BuildConfig
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.UUID
import java.util.concurrent.TimeUnit

object NetworkModule {

    private val logging: HttpLoggingInterceptor =
        HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }

    fun okHttp(): OkHttpClient =
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor(logging)
            .addInterceptor { chain ->
                val req = chain.request().newBuilder()
                    .header("Accept", "application/json")
                    .header("X-App-Version", BuildConfig.VERSION_NAME)
                    .header("X-Request-ID", UUID.randomUUID().toString())
                    .build()
                chain.proceed(req)
            }
            .build()

    fun retrofit(client: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

    fun metaApi(): MetaApi = retrofit(okHttp()).create(MetaApi::class.java)
}
