package com.mapv12.dutytracker.scanner.wifi

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.mapv12.dutytracker.App
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class WifiScanWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val analyzer = WifiSecurityAnalyzer(applicationContext)
            val networks = analyzer.analyzeNetworks()

            val wifiDao = App.db.wifiNetworkDao()

            networks.forEach { net ->
                val existing = wifiDao.getNetworkByBssid(net.bssid)
                val now = System.currentTimeMillis()
                val entity = WifiNetworkEntity(
                    id = existing?.id ?: 0,
                    ssid = net.ssid,
                    bssid = net.bssid,
                    capabilities = net.securityType,
                    frequency = net.frequency,
                    rssi = net.signalStrength,
                    securityType = net.securityType,
                    channel = net.channel,
                    isWpsEnabled = net.isWpsSupported,
                    manufacturer = net.manufacturer,
                    firstSeen = existing?.firstSeen ?: now,
                    lastSeen = now,
                    isVulnerable = existing?.isVulnerable ?: false,
                    vulnerabilityType = existing?.vulnerabilityType,
                    testedPassword = existing?.testedPassword,
                    lastTested = existing?.lastTested ?: 0
                )
                wifiDao.insertNetwork(entity)
            }

            val dayAgo = System.currentTimeMillis() - 24 * 60 * 60 * 1000
            wifiDao.deleteOldNetworks(dayAgo)

            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
