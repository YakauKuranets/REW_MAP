package com.mapv12.dutytracker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Авто-восстановление трекинга после перезагрузки.
 *
 * Важно: это "best-effort". Некоторые прошивки агрессивно убивают фоновые задачи,
 * поэтому трекинг всё равно надо закреплять в настройках батареи.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return

        // Если трекинг был включён — поднимаем Foreground service.
        if (LocationService.isTrackingOn(context)) {
            val i = Intent(context, LocationService::class.java).apply {
                this.action = LocationService.ACTION_START
            }
            try {
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                    context.startForegroundService(i)
                } else {
                    context.startService(i)
                }
            } catch (_: Exception) {
                // ignore
            }
        }
    }
}
