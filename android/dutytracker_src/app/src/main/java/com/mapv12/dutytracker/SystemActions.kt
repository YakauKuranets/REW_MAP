package com.mapv12.dutytracker

import android.app.Activity
import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import androidx.core.app.ActivityCompat

/**
 * Safe wrappers around common "fix" actions used in the UI.
 * All methods are best-effort and should never crash the app.
 */
object SystemActions {

    fun openAppSettings(ctx: Context) {
        try {
            ctx.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:${ctx.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        } catch (_: Exception) {
        }
    }

    fun openLocationSettings(ctx: Context) {
        try {
            ctx.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        } catch (_: Exception) {
        }
    }

    fun openNotificationsSettings(ctx: Context) {
        try {
            val i = if (Build.VERSION.SDK_INT >= 26) {
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                    putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName)
                }
            } else {
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:${ctx.packageName}")
                }
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(i)
        } catch (_: Exception) {
            openAppSettings(ctx)
        }
    }

    fun openInternetSettings(ctx: Context) {
        // Android 10+ has a nice panel, otherwise fallback.
        try {
            val i = if (Build.VERSION.SDK_INT >= 29) {
                Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY)
            } else {
                Intent(Settings.ACTION_WIFI_SETTINGS)
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(i)
        } catch (_: Exception) {
        }
    }

    fun openBatteryOptimizationSettings(ctx: Context) {
        try {
            ctx.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        } catch (_: Exception) {
            try {
                ctx.startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                })
            } catch (_: Exception) {
            }
        }
    }

    fun requestIgnoreBatteryOptimizations(activity: Activity) {
        try {
            val pm = activity.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            if (pm.isIgnoringBatteryOptimizations(activity.packageName)) {
                Toast.makeText(activity, "Уже разрешено (исключение включено)", Toast.LENGTH_SHORT).show()
                return
            }
        } catch (_: Exception) {
        }

        try {
            activity.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:${activity.packageName}")
            })
        } catch (_: Exception) {
            openBatteryOptimizationSettings(activity)
        }
    }


    fun openAppLocationPermissionSettings(ctx: Context) {
        // Best effort: open app details page where user can set Location -> "Allow all the time".
        try {
            ctx.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:${ctx.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
            Toast.makeText(ctx, "Открой: Разрешения → Геолокация → «Разрешить всегда»", Toast.LENGTH_LONG).show()
        } catch (_: Exception) {
            openAppSettings(ctx)
        }
    }

    fun startBackgroundLocationFlow(activity: Activity) {
        // Android 10: can request ACCESS_BACKGROUND_LOCATION after foreground permission.
        if (Build.VERSION.SDK_INT == 29) {
            try {
                ActivityCompat.requestPermissions(
                    activity,
                    arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION),
                    702
                )
                Toast.makeText(activity, "Выбери «Разрешить всегда» для геолокации", Toast.LENGTH_LONG).show()
                return
            } catch (_: Exception) {
            }
        }
        // Android 11+ usually requires going to settings.
        openAppLocationPermissionSettings(activity)
    }

    fun openOemBackgroundSettings(ctx: Context): Boolean {
        // Tries to open manufacturer-specific background/autostart settings screens.
        val m = (android.os.Build.MANUFACTURER ?: "").lowercase()
        val pkg = ctx.packageName

        fun tryStart(i: Intent): Boolean {
            return try {
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                ctx.startActivity(i)
                true
            } catch (_: Exception) { false }
        }

        // Xiaomi / Redmi / Poco (MIUI)
        if (m.contains("xiaomi") || m.contains("redmi") || m.contains("poco")) {
            val intents = listOf(
                Intent().setClassName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
                Intent().setClassName("com.miui.securitycenter", "com.miui.powerkeeper.ui.HiddenAppsConfigActivity")
                    .putExtra("package_name", pkg),
                Intent("miui.intent.action.OP_AUTO_START").addCategory(Intent.CATEGORY_DEFAULT)
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // Huawei / Honor (EMUI)
        if (m.contains("huawei") || m.contains("honor")) {
            val intents = listOf(
                Intent().setClassName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
                Intent().setClassName("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"),
                Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // Samsung
        if (m.contains("samsung")) {
            val intents = listOf(
                Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$pkg"))
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // Oppo / Realme (ColorOS)
        if (m.contains("oppo") || m.contains("realme")) {
            val intents = listOf(
                Intent().setClassName("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"),
                Intent().setClassName("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"),
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$pkg"))
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // Vivo / iQOO (Funtouch)
        if (m.contains("vivo") || m.contains("iqoo")) {
            val intents = listOf(
                Intent().setClassName("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"),
                Intent().setClassName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager"),
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$pkg"))
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // OnePlus
        if (m.contains("oneplus")) {
            val intents = listOf(
                Intent().setClassName("com.oneplus.security", "com.oneplus.security.chainlaunch.view.ChainLaunchAppListActivity"),
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$pkg"))
            )
            for (i in intents) if (tryStart(i)) return true
        }

        // Fallback
        return tryStart(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
    }

    fun requestPermissions(activity: Activity, perms: Array<String>, requestCode: Int) {
        try {
            ActivityCompat.requestPermissions(activity, perms, requestCode)
        } catch (_: Exception) {
        }
    }
}
