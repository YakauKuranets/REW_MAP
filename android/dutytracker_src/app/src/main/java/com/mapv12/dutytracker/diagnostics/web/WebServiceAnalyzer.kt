package com.mapv12.dutytracker.diagnostics.web

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Анализирует веб-сервисы на открытых портах.
 * Определяет тип сервера, наличие заголовков и страницы входа.
 */
class WebServiceAnalyzer {

    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .followRedirects(false)
        .build()

    data class WebServiceInfo(
        val port: Int,
        val url: String,
        val statusCode: Int,
        val serverHeader: String?,
        val title: String?,
        val authRequired: Boolean
    )

    /**
     * Выполняет HTTP-запрос к указанному порту и собирает информацию.
     * @param ip целевой IP
     * @param port порт для проверки
     * @return информация о веб-сервисе или null, если не удалось подключиться
     */
    suspend fun analyze(ip: String, port: Int): WebServiceInfo? = withContext(Dispatchers.IO) {
        val url = when (port) {
            443, 8443 -> "https://$ip:$port"
            else -> "http://$ip:$port"
        }
        val request = Request.Builder().url(url).build()
        try {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string()
                val title = extractTitle(body)
                val authRequired = response.code == 401 || response.code == 403
                WebServiceInfo(
                    port = port,
                    url = url,
                    statusCode = response.code,
                    serverHeader = response.header("Server"),
                    title = title,
                    authRequired = authRequired
                )
            }
        } catch (_: Exception) {
            null
        }
    }

    fun toEntity(ip: String, info: WebServiceInfo): WebServiceEntity {
        return WebServiceEntity(
            ip = ip,
            port = info.port,
            url = info.url,
            statusCode = info.statusCode,
            serverHeader = info.serverHeader,
            title = info.title,
            authRequired = info.authRequired
        )
    }

    private fun extractTitle(html: String?): String? {
        if (html == null) return null
        val regex = "<title>(.*?)</title>".toRegex(RegexOption.IGNORE_CASE)
        return regex.find(html)?.groupValues?.get(1)
    }
}
