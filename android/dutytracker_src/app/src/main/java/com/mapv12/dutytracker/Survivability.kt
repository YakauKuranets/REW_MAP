package com.mapv12.dutytracker

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import androidx.core.content.ContextCompat
import java.time.Instant

data class Issue(
    val code: String,
    val title: String,
    val fix: FixAction = FixAction.None
)

sealed class FixAction {
    object None : FixAction()
    data class RequestPermissions(val perms: Array<String>, val requestCode: Int = 701) : FixAction()
    object OpenAppSettings : FixAction()
    object OpenLocationSettings : FixAction()
    object OpenNotificationsSettings : FixAction()
    object OpenInternetSettings : FixAction()
    object RequestIgnoreBatteryOpt : FixAction()
    object OpenBackgroundLocationFlow : FixAction()
}

object Survivability {

    fun collect(ctx: Context): List<Issue> {
        val issues = mutableListOf<Issue>()

        if (!hasLocationPermission(ctx)) {
            issues.add(
                Issue(
                    code = "no_location_permission",
                    title = "Нет разрешения на геолокацию",
                    fix = FixAction.RequestPermissions(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION
                        ),
                        requestCode = 701
                    )
                )
            )
        }

        if (Build.VERSION.SDK_INT >= 29 && hasLocationPermission(ctx) && !hasBackgroundLocationPermission(ctx)) {
            issues.add(
                Issue(
                    code = "no_background_location",
                    title = "Нет геолокации «Всегда» (фон) — нужно разрешить",
                    fix = FixAction.OpenBackgroundLocationFlow
                )
            )
        }

        if (Build.VERSION.SDK_INT >= 33 && !hasNotificationPermission(ctx)) {
            issues.add(
                Issue(
                    code = "no_notifications",
                    title = "Нет разрешения на уведомления (Android 13+)",
                    fix = FixAction.OpenNotificationsSettings
                )
            )
        }

        if (!hasNetwork(ctx)) {
            issues.add(Issue("no_network", "Нет сети (Wi‑Fi/Cell)", FixAction.OpenInternetSettings))
        }

        if (!isLocationEnabled(ctx)) {
            issues.add(Issue("location_off", "Выключена геолокация (Location Services)", FixAction.OpenLocationSettings))
        }

        // Stale GPS while tracking
        try {
            if (ForegroundLocationService.isTrackingOn(ctx)) {
                val lastGpsIso = StatusStore.getLastGps(ctx)
                if (lastGpsIso.isBlank()) {
                    issues.add(Issue("no_gps_fix", "Нет GPS данных (ожидание сигнала/разрешений)", FixAction.OpenLocationSettings))
                } else {
                    val t = Instant.parse(lastGpsIso)
                    val age = Instant.now().epochSecond - t.epochSecond
                    if (age > 30) {
                        issues.add(Issue("stale_gps", "Нет свежих GPS данных > 30s (проверь сигнал/разрешения)", FixAction.OpenLocationSettings))
                    }
                }
            }
        } catch (_: Exception) {
        }

        // Filter status (optional diagnostic)
        try {
            val lf = StatusStore.getLastFilter(ctx)
            val rej = StatusStore.getFilterRejects(ctx)
            if (lf.isNotBlank() && lf != "ok") {
                issues.add(Issue("filter", "Фильтр: $lf (rej=$rej)", FixAction.None))
            }
        } catch (_: Exception) {
        }

        // Battery optimizations
        if (!isBatteryOptIgnored(ctx)) {
            issues.add(Issue("battery_optimizations", "Батарея: оптимизация включена (может убивать фон)", FixAction.RequestIgnoreBatteryOpt))
        }

        return issues
    }

    private fun hasNetwork(ctx: Context): Boolean {
        return try {
            val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val n = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(n) ?: return false
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        } catch (_: Exception) {
            true
        }
    }

    private fun isLocationEnabled(ctx: Context): Boolean {
        return try {
            val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
            lm.isProviderEnabled(LocationManager.GPS_PROVIDER) || lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
        } catch (_: Exception) {
            true
        }
    }

    private fun hasLocationPermission(ctx: Context): Boolean {
        val fine = ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    private fun hasBackgroundLocationPermission(ctx: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT < 29) return true
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED
        } catch (_: Exception) {
            true
        }
    }

    private fun hasNotificationPermission(ctx: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT < 33) return true
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        } catch (_: Exception) {
            true
        }
    }

    private fun isBatteryOptIgnored(ctx: Context): Boolean {
        return try {
            val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            pm.isIgnoringBatteryOptimizations(ctx.packageName)
        } catch (_: Exception) {
            true
        }
    }
}
