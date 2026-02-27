package com.mapv12.dutytracker.scanner.wifi

import android.content.Context
import com.mapv12.dutytracker.Config
import com.mapv12.dutytracker.SecureStores
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

class WifiSecurityAuditClient(
    private val context: Context,
    private val apiKey: String? = SecureStores.getAuditApiKey(context)
) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(30, TimeUnit.SECONDS)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun applyAuthHeaders(requestBuilder: Request.Builder) {
        apiKey?.takeIf { it.isNotBlank() }?.let {
            requestBuilder.header("X-API-Key", it)
        }
        SecureStores.getDeviceToken(context)?.takeIf { it.isNotBlank() }?.let {
            requestBuilder.header("X-DEVICE-TOKEN", it)
        }
    }


    fun connectToTaskProgress(token: String, listener: TaskProgressListener): WebSocket? {
        val base = Config.getBaseUrl(context).trim().trimEnd('/')
        val wsUrl = base
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://") + "/ws/task"

        val request = Request.Builder().url(wsUrl).build()
        val ws = client.newWebSocket(request, listener)
        ws.send(token)
        return ws
    }

    suspend fun requestAudit(network: WifiNetworkEntity): AuditStartResponse? = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("ssid", network.ssid)
            put("essid", network.ssid)
            put("bssid", network.bssid)
            // Поддержка новых протоколов аутентификации (WPA3/SAE и др.)
            put("securityType", network.securityType)
            put("rssi", network.rssi)
            put("frequency", network.frequency)
        }

        val url = Config.getBaseUrl(context).trim().trimEnd('/') + "/api/video/wifi/audit/start"
        val requestBuilder = Request.Builder()
            .url(url)
            .post(payload.toString().toRequestBody(jsonMedia))

        applyAuthHeaders(requestBuilder)

        return@withContext runCatching {
            client.newCall(requestBuilder.build()).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) return@use null
                val json = JSONObject(body)
                val taskId = json.optString("taskId").takeIf { it.isNotBlank() } ?: return@use null
                val wsToken = json.optString("wsToken").takeIf { it.isNotBlank() }
                if (!wsToken.isNullOrBlank()) {
                    SecureStores.setWsToken(context, wsToken)
                }
                AuditStartResponse(taskId, json.optInt("estimatedTime", 0), wsToken, json.optString("wsChannel").takeIf { it.isNotBlank() })
            }
        }.getOrNull()
    }




    suspend fun uploadHandshakeFile(
        file: File,
        bssid: String,
        essid: String,
        securityType: String,
        attackType: String = "handshake"
    ): JSONObject? = withContext(Dispatchers.IO) {
        val base = Config.getBaseUrl(context).trim().trimEnd('/')
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", file.name, file.asRequestBody("application/octet-stream".toMediaType()))
            .addFormDataPart("bssid", bssid)
            .addFormDataPart("essid", essid)
            .addFormDataPart("attack_type", attackType)
            .addFormDataPart("security_type", securityType.ifBlank { "WPA2" })
            .build()

        val requestBuilder = Request.Builder()
            .url(base + "/api/video/handshake/upload")
            .post(body)

        applyAuthHeaders(requestBuilder)

        return@withContext runCatching {
            client.newCall(requestBuilder.build()).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val bodyText = resp.body?.string().orEmpty()
                if (bodyText.isBlank()) return@use null
                JSONObject(bodyText)
            }
        }.getOrNull()
    }

    suspend fun getAuditStatus(taskId: String): AuditStatus? = withContext(Dispatchers.IO) {
        val url = Config.getBaseUrl(context).trim().trimEnd('/') + "/api/video/wifi/audit/status/$taskId"
        val requestBuilder = Request.Builder().url(url).get()

        applyAuthHeaders(requestBuilder)

        return@withContext runCatching {
            client.newCall(requestBuilder.build()).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) return@use null
                val json = JSONObject(body)

                val result = if ((json.optString("status").equals("completed", ignoreCase = true))) {
                    SecurityAssessmentResult(
                        isVulnerable = json.optBoolean("isVulnerable", false),
                        vulnerabilityType = json.optString("vulnerabilityType").takeIf { it.isNotBlank() },
                        foundPassword = json.optString("foundPassword").takeIf { it.isNotBlank() },
                        serverReport = json.optString("message").takeIf { it.isNotBlank() }
                    )
                } else null

                AuditStatus(
                    taskId = json.optString("taskId").ifBlank { taskId },
                    status = json.optString("status").ifBlank { "pending" },
                    progress = json.optInt("progress", 0),
                    estimatedTimeSeconds = json.optInt("estimatedTime", 0),
                    result = result
                )
            }
        }.getOrNull()
    }

    suspend fun getAuditResult(taskId: String): WifiAuditResult? {
        val url = Config.getBaseUrl(context).trim().trimEnd('/') + "/api/video/wifi/audit/result/$taskId"
        val requestBuilder = Request.Builder().url(url).get()

        applyAuthHeaders(requestBuilder)

        return runCatching {
            client.newCall(requestBuilder.build()).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) return@use null
                val json = JSONObject(body)
                WifiAuditResult(
                    bssid = json.optString("bssid"),
                    isVulnerable = json.optBoolean("isVulnerable", false),
                    vulnerabilityType = json.optString("vulnerabilityType").takeIf { it.isNotBlank() },
                    foundPassword = json.optString("foundPassword").takeIf { it.isNotBlank() },
                    report = json.optString("report").takeIf { it.isNotBlank() },
                    status = json.optString("status").ifBlank { null },
                    progress = json.optInt("progress", 0),
                    estimatedTime = json.optInt("estimatedTime", 0),
                    message = json.optString("message").ifBlank { null }
                )
            }
        }.getOrNull()
    }
}

data class WifiAuditResult(
    val bssid: String,
    val isVulnerable: Boolean,
    val vulnerabilityType: String?,
    val foundPassword: String?,
    val report: String?,
    val status: String?,
    val progress: Int,
    val estimatedTime: Int,
    val message: String?
)


data class AuditStartResponse(
    val taskId: String,
    val estimatedTime: Int,
    val wsToken: String? = null,
    val wsChannel: String? = null
)


data class AuditStatus(
    val taskId: String,
    val status: String,
    val progress: Int,
    val estimatedTimeSeconds: Int,
    val result: SecurityAssessmentResult? = null
)


class TaskProgressListener(private val onProgress: (current: Int, total: Int, estimated: Int) -> Unit) : WebSocketListener() {
    override fun onMessage(webSocket: WebSocket, text: String) {
        val json = JSONObject(text)
        if (json.optString("type") == "progress") {
            val current = json.optInt("current", 0)
            val total = json.optInt("total", 100)
            val estimated = json.optInt("estimated", json.optInt("estimated_time", -1))
            onProgress(current, total, estimated)
        }
    }
}


fun formatTime(seconds: Int): String {
    return when {
        seconds < 60 -> "$seconds сек"
        seconds < 3600 -> "${seconds / 60} мин ${seconds % 60} сек"
        else -> "${seconds / 3600} ч ${(seconds % 3600) / 60} мин"
    }
}
