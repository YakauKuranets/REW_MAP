package com.mapv12.dutytracker

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import org.json.JSONObject

object DeviceStatus {

    fun collect(
        ctx: Context,
        queueSize: Int?,
        trackingOn: Boolean?,
        accuracyM: Double?,
        lastSendAtIso: String?,
        lastError: String?
    ): DeviceHealthPayload {
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val pct = try { bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) } catch (_: Exception) { -1 }
        val batteryPct = if (pct in 0..100) pct else null

        val isCharging = try {
            val st = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS)
            st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL
        } catch (_: Exception) {
            null
        }

        val net = networkType(ctx)
        val gps = gpsState(ctx)

        val extra = JSONObject()
        try { extra.put("power_save", isPowerSave(ctx)) } catch (_: Exception) {}

        // Survivability flags (used by Command Center recommendations)
        try { extra.put("battery_opt_ignored", isBatteryOptIgnored(ctx)) } catch (_: Exception) {}
        try { extra.put("notif_granted", isNotificationsGranted(ctx)) } catch (_: Exception) {}
        try { extra.put("bg_location_granted", isBackgroundLocationGranted(ctx)) } catch (_: Exception) {}
        try { extra.put("fine_location_granted", isFineLocationGranted(ctx)) } catch (_: Exception) {}
        try { extra.put("location_enabled", isLocationEnabled(ctx)) } catch (_: Exception) {}


        // Indoor tuning hints (best-effort): Wi‑Fi/BLE scanning settings
        // These help MAX indoor even when Wi‑Fi/Bluetooth are OFF (Android "Location" scanning features).
        try {
            val wifiScanAlways = readGlobalBool(ctx, "wifi_scan_always_enabled")
                ?: readGlobalBool(ctx, "wifi_scan_always_available")
            if (wifiScanAlways != null) extra.put("wifi_scan_always", wifiScanAlways)
        } catch (_: Exception) {}
        try {
            val bleScanAlways = readGlobalBool(ctx, "ble_scan_always_enabled")
            if (bleScanAlways != null) extra.put("ble_scan_always", bleScanAlways)
        } catch (_: Exception) {}


        return DeviceHealthPayload(
            batteryPct = batteryPct,
            isCharging = isCharging,
            net = net,
            gps = gps,
            accuracyM = accuracyM,
            queueSize = queueSize,
            trackingOn = trackingOn,
            lastSendAtIso = lastSendAtIso,
            lastError = lastError,
            appVersion = BuildConfig.VERSION_NAME,
            deviceModel = Build.MANUFACTURER + " " + Build.MODEL,
            osVersion = Build.VERSION.RELEASE,
            extra = extra
        )
    }

    private fun networkType(ctx: Context): String? {
        return try {
            val cm = ContextCompat.getSystemService(ctx, ConnectivityManager::class.java) ?: return null
            val n = cm.activeNetwork ?: return "none"
            val caps = cm.getNetworkCapabilities(n) ?: return "none"
            when {
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cell"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "eth"
                else -> "unknown"
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun gpsState(ctx: Context): String? {
        return try {
            val mode = Settings.Secure.getInt(ctx.contentResolver, Settings.Secure.LOCATION_MODE)
            if (mode == Settings.Secure.LOCATION_MODE_OFF) "off" else "ok"
        } catch (_: Exception) {
            null
        }
    }

    private fun isPowerSave(ctx: Context): Boolean {
        return try {
            val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            pm.isPowerSaveMode
        } catch (_: Exception) {
            false
        }
    }


    private fun isBatteryOptIgnored(ctx: Context): Boolean {
        return try {
            val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            pm.isIgnoringBatteryOptimizations(ctx.packageName)
        } catch (_: Exception) {
            false
        }
    }

    private fun isNotificationsGranted(ctx: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT < 33) return true
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        } catch (_: Exception) {
            true
        }
    }

    private fun isBackgroundLocationGranted(ctx: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT < 29) return true
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED
        } catch (_: Exception) {
            true
        }
    }

    private fun isFineLocationGranted(ctx: Context): Boolean {
        return try {
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        } catch (_: Exception) {
            false
        }
    }

    private fun isLocationEnabled(ctx: Context): Boolean {
        return try {
            val mode = Settings.Secure.getInt(ctx.contentResolver, Settings.Secure.LOCATION_MODE)
            mode != Settings.Secure.LOCATION_MODE_OFF
        } catch (_: Exception) {
            true
        }
    }

    private fun readGlobalBool(ctx: Context, key: String): Boolean? {
        return try {
            val v = Settings.Global.getInt(ctx.contentResolver, key, -1)
            if (v == -1) null else (v == 1)
        } catch (_: Exception) {
            null
        }
    }

}
