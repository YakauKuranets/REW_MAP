package com.mapv12.dutytracker

import android.content.Context
import com.mapv12.dutytracker.DeviceInfoStore
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.WebSocketListener
import okhttp3.WebSocket
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/** HTTP error with status code preserved (important for 409 session_inactive handling). */
class ApiHttpException(val statusCode: Int, val responseBody: String) : IOException("HTTP ${'$'}statusCode: ${'$'}responseBody")

/** Thrown when server rejects points because provided session_id is no longer active (HTTP 409). */
class SessionInactiveException(val activeSessionId: String?) : IOException("session_inactive")


interface RealtimeEventListener {
    fun onEvent(event: String, payload: JSONObject)
    fun onFailure(t: Throwable) {}
}

class ApiClient(private val ctx: Context) {
    private val client = OkHttpClient.Builder()
        .retryOnConnectionFailure(true)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    private fun baseUrl(): String = Config.getBaseUrl(ctx).trim().trimEnd('/')
    private fun deviceToken(): String? = SecureStores.getDeviceToken(ctx)

    /**
     * Дополнительная вспомогательная функция для отправки сообщений chat2 от устройства.
     *
     * Этот метод использует X-Device-ID для идентификации трекера. Если текст пустой и kind != "text",
     * параметр text будет пропущен. Возвращает JSONObject ответа сервера или бросает исключение при
     * сетевой ошибке или неуспешном HTTP статусе.
     */
    @Throws(IOException::class)
    fun chatSend(channelId: String, text: String? = null, kind: String = "text", clientMsgId: String): org.json.JSONObject {
        val body = org.json.JSONObject().apply {
            put("channel_id", channelId)
            put("kind", kind)
            put("client_msg_id", clientMsgId)
            if (!text.isNullOrEmpty()) put("text", text)
        }
        val url = baseUrl() + "/api/chat2/send"
        val reqBuilder = Request.Builder()
            .url(url)
            .post(body.toString().toRequestBody(jsonMedia))
        // Добавляем X-Device-ID для идентификации трекера
        val devId = DeviceInfoStore.deviceId(ctx)
        if (!devId.isNullOrBlank()) {
            reqBuilder.header("X-Device-ID", devId)
        }
        val req = reqBuilder.build()
        client.newCall(req).execute().use { resp ->
            val textResp = resp.body?.string() ?: ""
            if (!resp.isSuccessful) {
                throw ApiHttpException(resp.code, textResp)
            }
            return try { org.json.JSONObject(textResp) } catch (_: Exception) { org.json.JSONObject() }
        }
    }


    private fun kindFromPath(path: String): String = when {
        path.contains("/pair") -> "pair"
        path.contains("/profile") -> "profile"
        path.contains("/start") -> "start"
        path.contains("/stop") -> "stop"
        path.contains("/points") -> "points"
        path.contains("/health") -> "health"
        path.contains("/fingerprints") -> "fingerprints"
        path.contains("/sos") -> "sos"
        else -> "api"
    }

    @Throws(IOException::class)
    
private fun shouldRetry(code: Int): Boolean {
    return code == 408 || code == 425 || code == 429 || (code in 500..599)
}

private fun backoffMs(attempt: Int): Long {
    val base = 600L
    val max = 6000L
    val pow = (1 shl attempt).toLong()
    val raw = base * pow
    val jitter = (0..250).random().toLong()
    return (raw + jitter).coerceAtMost(max)
}

private class RetryableHttp(val code: Int, val body: String) : IOException("Retryable HTTP $code")

/**
 * GET helper with retries/backoff and journal logging.
 * (Previous stage had it; in this stage it was accidentally dropped, which breaks bootstrapConfig())
 */
private fun get(path: String, token: String? = null, maxAttempts: Int = 3): JSONObject {
    val url = baseUrl() + path
    val kind = kindFromPath(path)

    var lastErr: Exception? = null

    for (attempt in 0 until maxAttempts) {
        try {
            val reqBuilder = Request.Builder().url(url).get()
            if (!token.isNullOrBlank()) {
                reqBuilder.header("X-DEVICE-TOKEN", token)
            }
            val req = reqBuilder.build()

            client.newCall(req).execute().use { resp ->
                val text = resp.body?.string() ?: ""
                if (!resp.isSuccessful) {
                    JournalLogger.log(ctx, kind, path, false, resp.code, "HTTP ${'$'}{resp.code}", text)
                    if (attempt < maxAttempts - 1 && shouldRetry(resp.code)) {
                        throw RetryableHttp(resp.code, text)
                    }
                    throw ApiHttpException(resp.code, text)
                }

                JournalLogger.log(ctx, kind, path, true, resp.code, null, null)
                return try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            }
        } catch (e: RetryableHttp) {
            lastErr = e
            try { Thread.sleep(backoffMs(attempt)) } catch (_: Exception) {}
            continue
        } catch (e: IOException) {
            lastErr = e
            JournalLogger.log(ctx, kind, path, false, -1, "IO", e.message)
            if (attempt < maxAttempts - 1) {
                try { Thread.sleep(backoffMs(attempt)) } catch (_: Exception) {}
                continue
            }
            throw e
        }
    }

    throw lastErr ?: IOException("Unknown error")
}

private fun post(path: String, body: JSONObject, token: String? = null, maxAttempts: Int = 3): JSONObject {
    val url = baseUrl() + path
    val kind = kindFromPath(path)

    var lastErr: Exception? = null

    for (attempt in 0 until maxAttempts) {
        try {
            val reqBuilder = Request.Builder()
                .url(url)
                .post(body.toString().toRequestBody(jsonMedia))

            if (!token.isNullOrBlank()) {
                reqBuilder.header("X-DEVICE-TOKEN", token)
            }

            val req = reqBuilder.build()
            client.newCall(req).execute().use { resp ->
                val text = resp.body?.string() ?: ""
                if (!resp.isSuccessful) {
                    JournalLogger.log(ctx, kind, path, false, resp.code, "HTTP ${'$'}{resp.code}", text)

                    if (resp.code == 409 && text.contains("session_inactive", ignoreCase = true)) {
                        throw SessionInactiveException(text)
                    }

                    if (attempt < maxAttempts - 1 && shouldRetry(resp.code)) {
                        throw RetryableHttp(resp.code, text)
                    }
                    throw ApiHttpException(resp.code, text)
                }

                JournalLogger.log(ctx, kind, path, true, resp.code, null, null)
                return try { JSONObject(text) } catch (_: Exception) { JSONObject() }
            }
        } catch (e: RetryableHttp) {
            lastErr = e
            try { Thread.sleep(backoffMs(attempt)) } catch (_: Exception) {}
            continue
        } catch (e: IOException) {
            lastErr = e
            JournalLogger.log(ctx, kind, path, false, -1, "IO", e.message)
            if (attempt < maxAttempts - 1) {
                try { Thread.sleep(backoffMs(attempt)) } catch (_: Exception) {}
                continue
            }
            throw e
        }
    }

    throw lastErr ?: IOException("Unknown error")
}

    
    fun bootstrapConfig(token: String): BootstrapResult {
        val t = token.trim()
        if (t.isEmpty()) return BootstrapResult(false, null, null, null, "token_required")
        return try {
            val res = get("/api/mobile/bootstrap/config?token=" + java.net.URLEncoder.encode(t, "UTF-8"))
            BootstrapResult(
                ok = res.optBoolean("ok", false),
                baseUrl = res.optString("base_url", null),
                pairCode = res.optString("pair_code", null),
                label = res.optString("label", null),
                error = null
            )
        } catch (e: Exception) {
            BootstrapResult(false, null, null, null, e.message)
        }
    }

fun pair(code: String): PairResult {
        val body = JSONObject().put("code", code.trim())
        return try {
            val res = post("/api/tracker/pair", body)
            PairResult(
                ok = res.optBoolean("ok", false),
                deviceToken = res.optString("device_token", null),
                deviceId = res.optString("device_id", null),
                userId = res.optString("user_id", null),
                label = res.optString("label", null),
                error = null
            )
        } catch (e: Exception) {
            PairResult(false, null, null, null, null, e.message)
        }
    }

    fun sendProfile(
        fullName: String,
        dutyNumber: String,
        unit: String,
        position: String,
        rank: String,
        phone: String
    ): Boolean {
        val token = deviceToken() ?: return false
        val body = JSONObject()
            .put("full_name", fullName)
            .put("duty_number", dutyNumber)
            .put("unit", unit)
            .put("position", position)
            .put("rank", rank)
            .put("phone", phone)

        return try {
            val res = post("/api/tracker/profile", body, token)
            res.optBoolean("ok", false)
        } catch (e: Exception) {
            StatusStore.setLastError(ctx, e.message)
            false
        }
    }

    fun start(lat: Double?, lon: Double?): StartResult {
        val token = deviceToken() ?: return StartResult(false, null, null, null, "No token")
        val body = JSONObject()
        if (lat != null) body.put("lat", lat)
        if (lon != null) body.put("lon", lon)

        return try {
            val res = post("/api/tracker/start", body, token)
            StartResult(
                ok = res.optBoolean("ok", false),
                sessionId = res.optString("session_id", null),
                shiftId = res.optString("shift_id", null),
                userId = res.optString("user_id", null),
                error = null
            )
        } catch (e: Exception) {
            StartResult(false, null, null, null, e.message)
        }
    }

    fun stop(sessionId: String?): Boolean {
        val token = deviceToken() ?: return false
        val body = JSONObject()
        if (!sessionId.isNullOrBlank()) body.put("session_id", sessionId)

        return try {
            val res = post("/api/tracker/stop", body, token)
            res.optBoolean("ok", false)
        } catch (e: Exception) {
            StatusStore.setLastError(ctx, e.message)
            false
        }
    }

    @Throws(IOException::class)
    fun sendPoints(sessionId: String?, points: List<TrackPointEntity>): Pair<Int, Int> {
        val token = deviceToken() ?: throw IOException("No token")
        val arr = JSONArray()
        for (p in points) {
            val o = JSONObject()
                .put("ts", p.tsEpochMs)
                .put("lat", p.lat)
                .put("lon", p.lon)
            if (p.accuracyM != null) o.put("accuracy_m", p.accuracyM)
            if (p.speedMps != null) o.put("speed_mps", p.speedMps)
            if (p.bearingDeg != null) o.put("bearing_deg", p.bearingDeg)
            arr.put(o)
        }

        val body = JSONObject().put("points", arr)
        if (!sessionId.isNullOrBlank()) body.put("session_id", sessionId)

        try {
            val res = post("/api/tracker/points", body, token)
            val accepted = res.optInt("accepted", 0)
            val dedup = res.optInt("dedup", 0)
            return accepted to dedup
        } catch (e: ApiHttpException) {
            // Server strict mode: session_id may become inactive (409). In this case we must call /start again.
            if (e.statusCode == 409) {
                val active = try {
                    val js = JSONObject(e.responseBody)
                    if (js.has("details")) js.getJSONObject("details").optString("active_session_id", null) else js.optString("active_session_id", null)
                } catch (_: Exception) { null }

                val err = try {
                    val js = JSONObject(e.responseBody)
                    js.optString("code", js.optString("error", ""))
                } catch (_: Exception) { "" }

                if (err == "session_inactive" || e.responseBody.contains("session_inactive")) {
                    throw SessionInactiveException(active)
                }
            }
            throw e
        }
    }

    fun sos(lat: Double?, lon: Double?, accuracyM: Float?, note: String?): SosResult {
        val token = deviceToken() ?: return SosResult(false, null, "No token")
        val body = JSONObject()
        if (lat != null) body.put("lat", lat)
        if (lon != null) body.put("lon", lon)
        if (accuracyM != null) body.put("accuracy_m", accuracyM)
        if (!note.isNullOrBlank()) body.put("note", note.trim())

        val sessionId = SessionStore.getSessionId(ctx)
        if (!sessionId.isNullOrBlank()) body.put("session_id", sessionId)

        return try {
            val res = post("/api/tracker/sos", body, token)
            SosResult(
                ok = res.optBoolean("ok", false),
                sosId = res.optString("sos_id", null),
                error = null
            )
        } catch (e: Exception) {
            StatusStore.setLastError(ctx, e.message)
            SosResult(false, null, e.message)
        }
    }

    fun sosLast(note: String?): SosResult {
        val token = deviceToken() ?: return SosResult(false, null, "No token")
        val body = JSONObject()
        if (!note.isNullOrBlank()) body.put("note", note.trim())
        val sessionId = SessionStore.getSessionId(ctx)
        if (!sessionId.isNullOrBlank()) body.put("session_id", sessionId)

        return try {
            val res = post("/api/tracker/sos/last", body, token)
            SosResult(
                ok = res.optBoolean("ok", false),
                sosId = res.optString("sos_id", null),
                error = null
            )
        } catch (e: Exception) {
            StatusStore.setLastError(ctx, e.message)
            SosResult(false, null, e.message)
        }
    }

    fun sendHealth(payload: DeviceHealthPayload): Boolean {
        val token = deviceToken() ?: run {
            try { StatusStore.setLastError(ctx, "Нет device_token (не привязано)") } catch (_: Exception) {}
            return false
        }
        val body = JSONObject()
            .put("battery_pct", payload.batteryPct)
            .put("is_charging", payload.isCharging)
            .put("net", payload.net)
            .put("gps", payload.gps)
            .put("accuracy_m", payload.accuracyM)
            .put("queue_size", payload.queueSize)
            .put("tracking_on", payload.trackingOn)
            .put("last_send_at", payload.lastSendAtIso)
            .put("last_error", payload.lastError)
            .put("app_version", payload.appVersion)
            .put("device_model", payload.deviceModel)
            .put("os_version", payload.osVersion)

        if (payload.extra != null) body.put("extra", payload.extra)

        return try {
            val res = post("/api/tracker/health", body, token)
            val ok = res.optBoolean("ok", false)
            if (ok) {
                // "Последняя отправка" в UI должна обновляться даже если точки не прошли фильтр:
                // health = факт связи с сервером.
                StatusStore.setLastUpload(ctx, java.time.Instant.now().toString())
                // сбрасываем ошибку только при успешной отправке
                try { StatusStore.setLastError(ctx, "") } catch (_: Exception) {}
            }
            ok
        } catch (e: Exception) {
            // health best-effort, но ошибку фиксируем (для UI/диагностики)
            try { StatusStore.setLastError(ctx, "health: ${e.message}") } catch (_: Exception) {}
            false
        }
    }




    fun relayMeshPayload(payload: JSONObject): Boolean {
        val token = deviceToken()
        return try {
            val res = post("/api/mesh-relay", payload, token)
            res.optBoolean("ok", true)
        } catch (e: Exception) {
            try { StatusStore.setLastError(ctx, "mesh-relay: ${e.message}") } catch (_: Exception) {}
            false
        }
    }

    fun openRealtimeSocket(listener: RealtimeEventListener): WebSocket {
        val wsBase = baseUrl().replaceFirst("http://", "ws://").replaceFirst("https://", "wss://")
        val req = Request.Builder().url("$wsBase/ws").build()
        return client.newWebSocket(req, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    val event = json.optString("event", "")
                    val payload = json.optJSONObject("data") ?: JSONObject()
                    if (event.isNotBlank()) listener.onEvent(event, payload)
                } catch (e: Exception) {
                    listener.onFailure(e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                listener.onFailure(t)
            }
        })
    }

    fun sendFingerprints(sample: org.json.JSONObject): Boolean {
        val token = deviceToken() ?: return false
        val body = org.json.JSONObject().put("samples", org.json.JSONArray().put(sample))
        return try {
            val res = post("/api/tracker/fingerprints", body, token)
            res.optBoolean("ok", false)
        } catch (_: Exception) {
            false
        }
    }
}
