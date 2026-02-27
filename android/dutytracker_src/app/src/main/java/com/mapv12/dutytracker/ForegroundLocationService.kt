package com.mapv12.dutytracker

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.*
import com.google.gson.Gson
import com.mapv12.dutytracker.mesh.ReticulumMeshService
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

open class ForegroundLocationService : Service() {

    companion object {
        const val ACTION_START = "com.mapv12.dutytracker.ACTION_START"
        const val ACTION_STOP = "com.mapv12.dutytracker.ACTION_STOP"
        const val ACTION_UPDATE_MODE = "com.mapv12.dutytracker.ACTION_UPDATE_MODE"

        private const val NOTIF_ID = 2001
        private const val CH_ID = "TrackerChannel"

        const val PREF_FLAGS = "dutytracker_flags"
        const val KEY_TRACKING_ON = "tracking_on"

        fun isTrackingOn(ctx: Context): Boolean =
            ctx.getSharedPreferences(PREF_FLAGS, Context.MODE_PRIVATE).getBoolean(KEY_TRACKING_ON, false)

        fun setTrackingOn(ctx: Context, on: Boolean) {
            ctx.getSharedPreferences(PREF_FLAGS, Context.MODE_PRIVATE).edit().putBoolean(KEY_TRACKING_ON, on).apply()
        }

        fun requestModeUpdate(ctx: Context) {
            val i = Intent(ctx, ForegroundLocationService::class.java).apply { action = ACTION_UPDATE_MODE }
            try {
                ctx.startService(i)
            } catch (_: Exception) {}
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var healthJob: Job? = null
    private var wsReconnectJob: Job? = null

    private lateinit var fused: FusedLocationProviderClient
    private val qualityFilter = TrackingQualityFilter()
    private val gson = Gson()
    private val wsMutex = Mutex()
    private val pendingAckBatches = ConcurrentHashMap<String, List<Long>>()

    @Volatile
    private var webSocket: WebSocket? = null
    @Volatile
    private var webSocketConnected: Boolean = false

    private val wsClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .retryOnConnectionFailure(true)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
    }

    private val wsListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            this@ForegroundLocationService.webSocket = webSocket
            webSocketConnected = true
            StatusStore.setLastError(applicationContext, null)
            scope.launch { flushQueuedPoints() }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            scope.launch { handleWsAck(text) }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            webSocketConnected = false
            scheduleReconnect()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            webSocketConnected = false
            StatusStore.setLastError(applicationContext, "ws: ${t.message}")
            scheduleReconnect()
        }
    }

    // --- MESH NETWORK ---
    private var meshNetworkManager: MeshNetworkManager? = null
    private var reticulumMeshService: ReticulumMeshService? = null
    // --------------------

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val loc = result.lastLocation ?: return

            // AUTO mode: adjust effective request based on movement
            try {
                if (TrackingModeStore.get(applicationContext) == TrackingMode.AUTO) {
                    val decided = AutoModeController.decide(
                        speedMps = if (loc.hasSpeed()) loc.speed.toDouble() else null,
                        accuracyM = if (loc.hasAccuracy()) loc.accuracy.toDouble() else null
                    )
                    val current = AutoModeController.getEffective(applicationContext)
                    if (decided != current) {
                        AutoModeController.setEffective(applicationContext, decided)
                        JournalLogger.log(applicationContext, "mode", "auto", true, null, null, "effective=${decided.id}")
                        // Re-apply request quickly
                        requestModeUpdate(applicationContext)
                    }
                }
            } catch (_: Exception) { }

            StatusStore.setLastGps(applicationContext, Instant.now().toString())

            if (loc.hasAccuracy()) {
                StatusStore.setLastAccM(applicationContext, loc.accuracy.toInt())
            }

            val effMode = try {
                val base = TrackingModeStore.get(applicationContext)
                if (base == TrackingMode.AUTO) AutoModeController.getEffective(applicationContext) else base
            } catch (_: Exception) {
                TrackingMode.NORMAL
            }

            val decision = try { qualityFilter.process(loc, effMode) } catch (e: Exception) {
                TrackingQualityFilter.Decision(true, "ok", loc)
            }

            if (!decision.accept) {
                StatusStore.setLastFilter(applicationContext, decision.reason)
                StatusStore.incFilterRejects(applicationContext)
                return
            }

            StatusStore.setLastFilter(applicationContext, decision.reason)
            StatusStore.setLastAccepted(applicationContext, Instant.now().toString())
            try { StatusStore.resetFilterRejects(applicationContext) } catch (_: Exception) {}

            val outLoc = decision.out ?: loc

            try {
                StatusStore.setLastLatLon(applicationContext, outLoc.latitude, outLoc.longitude)
            } catch (_: Exception) {}

            val sessionId = SessionStore.getSessionId(applicationContext)
            val point = TrackPointEntity(
                sessionId = sessionId,
                tsEpochMs = outLoc.time,
                lat = outLoc.latitude,
                lon = outLoc.longitude,
                accuracyM = if (outLoc.hasAccuracy()) outLoc.accuracy.toDouble() else null,
                speedMps = if (outLoc.hasSpeed()) outLoc.speed.toDouble() else null,
                bearingDeg = if (outLoc.hasBearing()) outLoc.bearing.toDouble() else null,
                state = UploadState.PENDING
            )

            scope.launch {
                var insertedId: Long? = null
                try {
                    insertedId = App.db.trackPointDao().insert(point)

                    // --- MESH NETWORK LOGIC ---
                    // Если нет интернета - отправляем точку в Mesh-сеть соседям
                    if (!isNetworkAvailable()) {
                        try {
                            val json = gson.toJson(point)
                            meshNetworkManager?.sendDataToNetwork(json)
                            reticulumMeshService?.broadcastTelemetry(json.toByteArray())
                        } catch (e: Exception) {
                            Log.e("DutyTracker", "Mesh send error", e)
                        }
                    }
                    // --------------------------

                    var left = App.db.trackPointDao().countQueued()
                    if (left > Config.MAX_PENDING_POINTS) {
                        val toDelete = left - Config.MAX_PENDING_POINTS
                        try {
                            App.db.trackPointDao().deleteOldestQueued(toDelete)
                        } catch (_: Exception) {}
                        left = App.db.trackPointDao().countQueued()
                    }

                    StatusStore.setQueue(applicationContext, left)
                } catch (e: Exception) {
                    StatusStore.setLastError(applicationContext, e.message)
                }

                insertedId?.let { sendLatestQueuedPoint(point.copy(id = it)) }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        StatusStore.setServiceRunning(applicationContext, true)
        fused = LocationServices.getFusedLocationProviderClient(this)

        val userId = DeviceInfoStore.deviceId(this)
            ?: DeviceInfoStore.userId(this)
            ?: "UNKNOWN_DEVICE"
        meshNetworkManager = MeshNetworkManager(this, userId)
        reticulumMeshService = ReticulumMeshService(this).also { it.initializeDarkMesh() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_UPDATE_MODE -> {
                applyModeUpdate()
                return START_STICKY
            }
            ACTION_STOP -> {
                stopTracking()
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_START, null -> {
                startTracking()
                meshNetworkManager?.startAdvertising()
                meshNetworkManager?.startDiscovery()
                return START_STICKY
            }
            else -> {
                startTracking()
                meshNetworkManager?.startAdvertising()
                meshNetworkManager?.startDiscovery()
                return START_STICKY
            }
        }
    }

    private fun buildRequest(): LocationRequest {
        val stored = TrackingModeStore.get(applicationContext)
        val mode = if (stored == TrackingMode.AUTO) {
            val eff = AutoModeController.getEffective(applicationContext)
            if (eff == TrackingMode.AUTO) TrackingMode.NORMAL else eff
        } else stored
        return when (mode) {
            TrackingMode.ECO -> LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, 15000L)
                .setMinUpdateIntervalMillis(10000L)
                .setMinUpdateDistanceMeters(20f)
                .setMaxUpdateDelayMillis(0)
                .build()

            TrackingMode.PRECISE -> LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 2000L)
                .setMinUpdateIntervalMillis(1000L)
                .setMinUpdateDistanceMeters(0f)
                .setWaitForAccurateLocation(false)
                .setMaxUpdateDelayMillis(0)
                .build()

            TrackingMode.NORMAL -> LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 5000L)
                .setMinUpdateIntervalMillis(3000L)
                .setMinUpdateDistanceMeters(10f)
                .setMaxUpdateDelayMillis(0)
                .build()

            TrackingMode.AUTO -> LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 5000L)
                .setMinUpdateIntervalMillis(3000L)
                .setMinUpdateDistanceMeters(10f)
                .setMaxUpdateDelayMillis(0)
                .build()
        }
    }

    private fun applyModeUpdate() {
        if (!isTrackingOn(applicationContext)) return
        if (!hasLocationPermission()) return
        try {
            fused.removeLocationUpdates(callback)
        } catch (_: Exception) {}
        try {
            fused.requestLocationUpdates(buildRequest(), callback, Looper.getMainLooper())
        } catch (_: Exception) {}
    }


    private fun startHealthLoop() {
        if (healthJob != null) return
        healthJob = scope.launch {
            while (isTrackingOn(applicationContext)) {
                try {
                    val dao = App.db.trackPointDao()
                    val left = dao.countQueued()
                    StatusStore.setQueue(applicationContext, left)

                    val st = StatusStore.read(applicationContext)
                    val nowIso = Instant.now().toString()
                    val lu = st["last_upload"] as? String
                    val lastSend = if (!lu.isNullOrBlank() && lu != "—") lu else nowIso
                    val payload = DeviceStatus.collect(
                        ctx = applicationContext,
                        queueSize = left,
                        trackingOn = true,
                        accuracyM = StatusStore.getLastAccM(applicationContext),
                        lastSendAtIso = lastSend,
                        lastError = st["last_error"] as? String
                    )
                    val ok = ApiClient(applicationContext).sendHealth(payload)
                    if (ok) {
                        StatusStore.setLastHealth(applicationContext, Instant.now().toString())
                    }
                } catch (_: Exception) { }
                delay(15000)
            }
        }
    }

    private fun stopHealthLoop(sendFinal: Boolean = false) {
        try { healthJob?.cancel() } catch (_: Exception) { }
        healthJob = null

        if (sendFinal) {
            scope.launch {
                try {
                    val dao = App.db.trackPointDao()
                    val left = dao.countQueued()
                    StatusStore.setQueue(applicationContext, left)

                    val st = StatusStore.read(applicationContext)
                    val nowIso = Instant.now().toString()
                    val lu = st["last_upload"] as? String
                    val lastSend = if (!lu.isNullOrBlank() && lu != "—") lu else nowIso
                    val payload = DeviceStatus.collect(
                        ctx = applicationContext,
                        queueSize = left,
                        trackingOn = false,
                        accuracyM = StatusStore.getLastAccM(applicationContext),
                        lastSendAtIso = lastSend,
                        lastError = st["last_error"] as? String
                    )
                    val ok = ApiClient(applicationContext).sendHealth(payload)
                    if (ok) {
                        StatusStore.setLastHealth(applicationContext, Instant.now().toString())
                    }
                } catch (_: Exception) { }
            }
        }
    }

    private fun startTracking() {
        if (!hasLocationPermission()) {
            StatusStore.setLastError(applicationContext, "Нет разрешения на геолокацию")
            stopSelf()
            return
        }

        createChannelIfNeeded()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIF_ID, buildNotification())
        }

        setTrackingOn(applicationContext, true)
        startHealthLoop()
        startWsTunnelLoop()

        val req = buildRequest()

        try {
            fused.requestLocationUpdates(req, callback, Looper.getMainLooper())
        } catch (e: SecurityException) {
            StatusStore.setLastError(applicationContext, e.message)
            stopSelf()
        }
    }

    private fun stopTracking() {
        stopHealthLoop(sendFinal = true)
        stopWsTunnelLoop()

        try { StatusStore.setLastHealth(applicationContext, "") } catch (_: Exception) {}
        setTrackingOn(applicationContext, false)
        try { fused.removeLocationUpdates(callback) } catch (_: Exception) {}
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    // Хелпер для проверки интернета
    private fun isNetworkAvailable(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return false
        val cap = cm.getNetworkCapabilities(net) ?: return false
        return cap.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    private fun createChannelIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(CH_ID, "TrackerChannel", NotificationManager.IMPORTANCE_LOW)
            nm.createNotificationChannel(ch)
        }
    }
    private fun buildNotification(): Notification {
        val stored = TrackingModeStore.get(applicationContext)
        val eff = if (stored == TrackingMode.AUTO) AutoModeController.getEffective(applicationContext) else stored
        val label = if (stored == TrackingMode.AUTO) "auto→${eff.id}" else stored.id
        val queue = StatusStore.getQueue(applicationContext)

        return NotificationCompat.Builder(this, CH_ID)
            .setContentTitle("DutyTracker Radar")
            .setContentText("Локация отслеживается · режим: $label · очередь: $queue")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()
    }


    override fun onDestroy() {
        StatusStore.setServiceRunning(applicationContext, false)
        meshNetworkManager?.stopAll()
        meshNetworkManager = null
        reticulumMeshService = null
        stopTracking()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startWsTunnelLoop() {
        if (wsReconnectJob != null) return
        wsReconnectJob = scope.launch {
            var attempt = 0
            while (isTrackingOn(applicationContext)) {
                if (!isNetworkAvailable()) {
                    delay(1_500)
                    continue
                }

                if (webSocketConnected && webSocket != null) {
                    delay(1_000)
                    continue
                }

                openWebSocket()
                val backoffMs = exponentialBackoffMs(attempt)
                attempt = (attempt + 1).coerceAtMost(8)
                delay(backoffMs)

                if (webSocketConnected) {
                    attempt = 0
                }
            }
        }
    }

    private fun stopWsTunnelLoop() {
        try { wsReconnectJob?.cancel() } catch (_: Exception) {}
        wsReconnectJob = null
        webSocketConnected = false
        try { webSocket?.close(1000, "service_stopped") } catch (_: Exception) {}
        webSocket = null
    }

    private fun scheduleReconnect() {
        if (!isTrackingOn(applicationContext)) return
        if (wsReconnectJob == null || wsReconnectJob?.isCancelled == true) {
            startWsTunnelLoop()
        }
    }

    private fun openWebSocket() {
        val token = SecureStores.getDeviceToken(applicationContext)
        val base = Config.getBaseUrl(applicationContext).trim().trimEnd('/')
        val wsBase = base.replaceFirst("http://", "ws://").replaceFirst("https://", "wss://")
        val reqBuilder = Request.Builder().url("$wsBase/api/duty/telemetry/ws")
        if (!token.isNullOrBlank()) {
            reqBuilder.header("X-DEVICE-TOKEN", token)
        }
        val req = reqBuilder.build()
        webSocket = wsClient.newWebSocket(req, wsListener)
    }

    private suspend fun sendLatestQueuedPoint(point: TrackPointEntity) {
        wsMutex.withLock {
            if (!webSocketConnected || webSocket == null || point.id <= 0) return
            val batchId = UUID.randomUUID().toString()
            val payload = JSONObject()
                .put("type", "telemetry_batch")
                .put("batch_id", batchId)
                .put("points", JSONArray().put(JSONObject(pointToJson(point))))
            val sent = try { webSocket?.send(payload.toString()) ?: false } catch (_: Exception) { false }
            if (sent) {
                pendingAckBatches[batchId] = listOf(point.id)
            }
        }
    }

    private suspend fun flushQueuedPoints() {
        wsMutex.withLock {
            if (!webSocketConnected || webSocket == null) return
            val dao = App.db.trackPointDao()
            while (webSocketConnected) {
                val batch = dao.loadUnsynced(limit = 100)
                if (batch.isEmpty()) break

                val batchId = UUID.randomUUID().toString()
                val payload = JSONObject()
                    .put("type", "telemetry_batch")
                    .put("batch_id", batchId)
                    .put("points", JSONArray().apply {
                        batch.forEach { put(JSONObject(pointToJson(it))) }
                    })

                val sent = try { webSocket?.send(payload.toString()) ?: false } catch (_: Exception) { false }
                if (!sent) break
                pendingAckBatches[batchId] = batch.map { it.id }
            }

            try {
                StatusStore.setQueue(applicationContext, dao.countUnsynced())
            } catch (_: Exception) {}
        }
    }

    private suspend fun handleWsAck(text: String) {
        val ackBatchId = try {
            val json = JSONObject(text)
            when {
                json.optString("event") == "telemetry_ack" -> json.optString("batch_id")
                json.optBoolean("ack", false) -> json.optString("batch_id")
                else -> ""
            }
        } catch (_: Exception) {
            ""
        }
        if (ackBatchId.isBlank()) return

        val ids = pendingAckBatches.remove(ackBatchId).orEmpty()
        if (ids.isEmpty()) return

        try {
            App.db.trackPointDao().markSynced(ids)
            StatusStore.setLastUpload(applicationContext, Instant.now().toString())
            StatusStore.setQueue(applicationContext, App.db.trackPointDao().countUnsynced())
        } catch (_: Exception) {}
    }

    private fun pointToJson(point: TrackPointEntity): String {
        val payload = JSONObject()
            .put("session_id", point.sessionId ?: SessionStore.getSessionId(applicationContext))
            .put("user_id", DeviceInfoStore.deviceId(applicationContext))
            .put("ts_epoch_ms", point.tsEpochMs)
            .put("lat", point.lat)
            .put("lon", point.lon)
        point.accuracyM?.let { payload.put("accuracy_m", it) }
        point.speedMps?.let { payload.put("speed_mps", it) }
        point.bearingDeg?.let { payload.put("bearing_deg", it) }
        return payload.toString()
    }

    private fun exponentialBackoffMs(attempt: Int): Long {
        val base = 1_000L
        val max = 30_000L
        val exp = 1L shl attempt.coerceIn(0, 10)
        val jitter = (0..750).random().toLong()
        return (base * exp + jitter).coerceAtMost(max)
    }
}
