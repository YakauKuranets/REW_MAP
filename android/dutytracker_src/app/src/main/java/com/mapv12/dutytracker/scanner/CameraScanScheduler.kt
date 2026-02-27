package com.mapv12.dutytracker.scanner

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build

object CameraScanScheduler {

    private const val REQUEST_CODE = 4301

    fun schedulePeriodicScan(context: Context, intervalMinutes: Long = 60) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pendingIntent = buildPendingIntent(context)

        val intervalMs = intervalMinutes.coerceAtLeast(15) * 60 * 1000
        val firstTriggerAt = System.currentTimeMillis() + 10_000L

        alarmManager.cancel(pendingIntent)
        alarmManager.setInexactRepeating(
            AlarmManager.RTC_WAKEUP,
            firstTriggerAt,
            intervalMs,
            pendingIntent
        )
    }

    fun cancelScan(context: Context) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pendingIntent = buildPendingIntent(context)
        alarmManager.cancel(pendingIntent)
    }

    fun startOneTimeScan(context: Context) {
        val intent = CameraScannerForegroundService.createStartIntent(context)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent)
        } else {
            context.startService(intent)
        }
    }

    private fun buildPendingIntent(context: Context): PendingIntent {
        val triggerIntent = Intent(context, CameraScanTriggerReceiver::class.java)
        return PendingIntent.getBroadcast(
            context,
            REQUEST_CODE,
            triggerIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
}
