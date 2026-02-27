package com.mapv12.dutytracker

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

class WatchdogWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork() = withContext(Dispatchers.IO) {
        val ctx = applicationContext
        val should = LocationService.isTrackingOn(ctx)
        val running = StatusStore.isServiceRunning(ctx)
        if (should && !running) {
            try {
                JournalLogger.log(ctx, "watchdog", "restart_service", true, null, null, null)
                val i = Intent(ctx, LocationService::class.java)
                ContextCompat.startForegroundService(ctx, i)
            } catch (e: Exception) {
                JournalLogger.log(ctx, "watchdog", "restart_service", false, null, e.message, null)
                return@withContext Result.retry()
            }
        }
        Result.success()
    }

    companion object {
        private const val UNIQUE_NAME = "dutytracker_watchdog"
        private const val IMMEDIATE_NAME = "dutytracker_watchdog_immediate"

        fun ensureScheduled(ctx: Context) {
            val periodic = PeriodicWorkRequestBuilder<WatchdogWorker>(15, TimeUnit.MINUTES)
                .setInitialDelay(15, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                periodic
            )

            val immediate = OneTimeWorkRequestBuilder<WatchdogWorker>().build()
            WorkManager.getInstance(ctx).enqueueUniqueWork(
                IMMEDIATE_NAME,
                ExistingWorkPolicy.REPLACE,
                immediate
            )
        }
    }
}
