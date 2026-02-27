package com.mapv12.dutytracker.scanner

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.mapv12.dutytracker.App
import com.mapv12.dutytracker.LocationService
import com.mapv12.dutytracker.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class CameraScannerForegroundService : Service() {

    companion object {
        const val ACTION_START_SCAN = "com.mapv12.dutytracker.scanner.ACTION_START_SCAN"
        const val ACTION_STOP_SCAN = "com.mapv12.dutytracker.scanner.ACTION_STOP_SCAN"

        private const val CHANNEL_ID = "camera_scan_channel"
        private const val NOTIFICATION_ID = 3201
        private const val WAKELOCK_TAG = "dutytracker:camera_scan_wakelock"
        private const val MIN_SAFE_BATTERY_PCT = 20

        @Volatile
        private var isScanInProgress = false

        fun createStartIntent(context: Context): Intent =
            Intent(context, CameraScannerForegroundService::class.java).apply {
                action = ACTION_START_SCAN
            }
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START_SCAN
        if (action == ACTION_STOP_SCAN) {
            stopSelf()
            return START_NOT_STICKY
        }

        if (!canRunScanSafely()) {
            stopSelf()
            return START_NOT_STICKY
        }

        synchronized(CameraScannerForegroundService::class.java) {
            if (isScanInProgress) {
                stopSelf()
                return START_NOT_STICKY
            }
            isScanInProgress = true
        }

        ensureNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        acquireWakeLock()

        serviceScope.launch {
            try {
                runScan()
            } finally {
                synchronized(CameraScannerForegroundService::class.java) {
                    isScanInProgress = false
                }
                stopSelf()
            }
        }

        return START_NOT_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        serviceScope.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private suspend fun runScan() {
        val scanner = CameraScanner(applicationContext)
        val foundCameras = scanner.scanNetwork(timeoutMs = 2500, maxPingHosts = 48)

        val cameraDao = App.db.cameraDao()
        val now = System.currentTimeMillis()

        foundCameras.forEach { cam ->
            val existing = cameraDao.getCameraByIp(cam.ip)
            if (existing == null) {
                cameraDao.insertCamera(
                    CameraEntity(
                        ip = cam.ip,
                        port = cam.port,
                        vendor = cam.vendor,
                        onvifUrl = cam.onvifUrl,
                        authType = cam.authType,
                        firstSeen = now,
                        lastSeen = now
                    )
                )
            } else {
                cameraDao.insertCamera(
                    existing.copy(
                        port = cam.port,
                        vendor = cam.vendor ?: existing.vendor,
                        onvifUrl = cam.onvifUrl ?: existing.onvifUrl,
                        authType = cam.authType ?: existing.authType,
                        lastSeen = now,
                        isOnline = true
                    )
                )
            }
        }

        val weekAgo = now - 7 * 24 * 60 * 60 * 1000
        cameraDao.deleteOldCameras(weekAgo)
    }

    private fun canRunScanSafely(): Boolean {
        if (LocationService.isTrackingOn(applicationContext)) return false
        if (!isUnmeteredNetwork()) return false
        if (isBatteryLow()) return false
        return true
    }

    private fun isUnmeteredNetwork(): Boolean {
        return try {
            val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val network = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(network) ?: return false
            val isWifi = caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
            val isUnmetered = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
            isWifi && isUnmetered
        } catch (_: Exception) {
            false
        }
    }

    private fun isBatteryLow(): Boolean {
        val bm = getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return false
        val pct = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return pct in 0 until MIN_SAFE_BATTERY_PCT
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKELOCK_TAG).apply {
            setReferenceCounted(false)
            acquire(3 * 60 * 1000L)
        }
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Camera scanner",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Network camera scan is running"
        }
        nm.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("DutyTracker")
            .setContentText("Scanning local network cameras")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }
}
