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
import android.os.Build
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class LocationService : Service() {

    companion object {
        const val ACTION_START = "com.mapv12.dutytracker.ACTION_START"
        const val ACTION_STOP = "com.mapv12.dutytracker.ACTION_STOP"

        private const val NOTIFICATION_ID = 2042
        private const val CHANNEL_ID = "TrackerChannel"

        fun isTrackingOn(ctx: Context): Boolean = ForegroundLocationService.isTrackingOn(ctx)
        fun setTrackingOn(ctx: Context, on: Boolean) = ForegroundLocationService.setTrackingOn(ctx, on)
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var fused: FusedLocationProviderClient

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val location = result.lastLocation ?: return
            val sessionId = SessionStore.getSessionId(applicationContext)
            val point = TrackPointEntity(
                sessionId = sessionId,
                tsEpochMs = location.time,
                lat = location.latitude,
                lon = location.longitude,
                accuracyM = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
                speedMps = if (location.hasSpeed()) location.speed.toDouble() else null,
                bearingDeg = if (location.hasBearing()) location.bearing.toDouble() else null,
                state = UploadState.PENDING,
            )

            scope.launch {
                try {
                    App.db.trackPointDao().insert(point)
                    StatusStore.setLastLatLon(applicationContext, point.lat, point.lon)
                    StatusStore.setLastGps(applicationContext, java.time.Instant.now().toString())
                } catch (e: Exception) {
                    StatusStore.setLastError(applicationContext, e.message)
                }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTracking()
            stopSelf()
            return START_NOT_STICKY
        }

        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        startTracking()
        return START_STICKY
    }

    private fun startTracking() {
        if (!hasLocationPermission()) {
            StatusStore.setLastError(applicationContext, "Нет разрешения на геолокацию")
            stopSelf()
            return
        }

        setTrackingOn(applicationContext, true)
        StatusStore.setServiceRunning(applicationContext, true)

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 7_000L)
            .setMinUpdateIntervalMillis(5_000L)
            .setMaxUpdateDelayMillis(10_000L)
            .build()

        try {
            fused.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
        } catch (e: SecurityException) {
            StatusStore.setLastError(applicationContext, e.message)
            stopSelf()
        }
    }

    private fun stopTracking() {
        try {
            fused.removeLocationUpdates(locationCallback)
        } catch (_: Exception) {
        }
        setTrackingOn(applicationContext, false)
        StatusStore.setServiceRunning(applicationContext, false)
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(
                CHANNEL_ID,
                "TrackerChannel",
                NotificationManager.IMPORTANCE_LOW,
            )
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("DutyTracker Radar")
            .setContentText("Локация отслеживается")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .build()
    }

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    override fun onDestroy() {
        stopTracking()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
