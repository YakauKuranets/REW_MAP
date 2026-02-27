package com.mapv12.dutytracker.scanner.wifi

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager

object WifiScanScheduler {

    private const val UNIQUE_WORK_NAME = "wifi_scan_worker"

    fun schedulePeriodicScan(context: Context, intervalMinutes: Long = 30) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.NOT_ROAMING)
            .setRequiresBatteryNotLow(true)
            .build()

        val workRequest = PeriodicWorkRequestBuilder<WifiScanWorker>(
            intervalMinutes, java.util.concurrent.TimeUnit.MINUTES
        ).setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, java.util.concurrent.TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            workRequest
        )
    }

    fun startOneTimeScan(context: Context) {
        val workRequest = OneTimeWorkRequestBuilder<WifiScanWorker>().build()
        WorkManager.getInstance(context).enqueue(workRequest)
    }

    fun cancelScan(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK_NAME)
    }
}
