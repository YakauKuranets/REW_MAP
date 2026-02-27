package com.mapv12.dutytracker.scanner

import android.content.Context
import androidx.work.*

object CameraScanScheduler {

    private const val UNIQUE_WORK_NAME = "camera_scan_worker"

    fun schedulePeriodicScan(context: Context, intervalMinutes: Long = 60) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.UNMETERED) // только Wi-Fi (не тратим мобильный трафик)
            .setRequiresBatteryNotLow(true)
            .build()

        val workRequest = PeriodicWorkRequestBuilder<CameraScannerWorker>(
            intervalMinutes, java.util.concurrent.TimeUnit.MINUTES
        ).setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, java.util.concurrent.TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP, // не создаём новый, если уже есть
            workRequest
        )
    }

    fun cancelScan(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK_NAME)
    }

    fun startOneTimeScan(context: Context) {
        val workRequest = OneTimeWorkRequestBuilder<CameraScannerWorker>().build()
        WorkManager.getInstance(context).enqueue(workRequest)
    }
}
