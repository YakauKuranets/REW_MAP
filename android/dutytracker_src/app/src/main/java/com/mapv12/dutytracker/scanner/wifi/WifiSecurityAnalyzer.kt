package com.mapv12.dutytracker.scanner.wifi

import android.content.Context
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import com.mapv12.dutytracker.Config
import com.mapv12.dutytracker.SecureStores
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class WifiSecurityAnalyzer(private val context: Context) {

    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(30, TimeUnit.SECONDS)
        .build()

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    data class SecurityAnalysisResult(
        val ssid: String,
        val bssid: String,
        val securityType: String,
        val signalStrength: Int,
        val signalPercentage: Int,
        val channel: Int,
        val frequency: Int,
        val isWpsSupported: Boolean,
        val manufacturer: String?,
        val channelCongestion: String
    )

    /**
     * Сканирует доступные сети и возвращает детальный анализ.
     * Предназначено для authorised тестирования безопасности.
     */
    suspend fun analyzeNetworks(): List<SecurityAnalysisResult> = withContext(Dispatchers.IO) {
        val success = wifiManager.startScan()
        if (!success) return@withContext emptyList()

        delay(2000)

        val scanResults = wifiManager.scanResults.orEmpty()

        scanResults.map { result ->
            val securityType = parseSecurityType(result.capabilities.orEmpty())
            val channel = convertFrequencyToChannel(result.frequency)
            val wpsSupported = checkWpsSupport(result.capabilities.orEmpty())

            SecurityAnalysisResult(
                ssid = result.SSID.ifEmpty { "<Hidden>" },
                bssid = result.BSSID,
                securityType = securityType,
                signalStrength = result.level,
                signalPercentage = calculateSignalPercentage(result.level),
                channel = channel,
                frequency = result.frequency,
                isWpsSupported = wpsSupported,
                manufacturer = getManufacturerFromBssid(result.BSSID),
                channelCongestion = analyzeChannelCongestion(scanResults, channel)
            )
        }.sortedByDescending { it.signalStrength }
    }

    suspend fun fullSecurityAssessment(
        ssid: String,
        bssid: String,
        securityType: String
    ): SecurityAssessmentResult {
        if (securityType == "OPEN") {
            return SecurityAssessmentResult(
                isVulnerable = true,
                vulnerabilityType = "OPEN_NETWORK"
            )
        }

        return runCatching {
            requestServerAssessment(ssid, bssid, securityType)
        }.getOrElse {
            SecurityAssessmentResult()
        }
    }

    private fun requestServerAssessment(
        ssid: String,
        bssid: String,
        securityType: String
    ): SecurityAssessmentResult {
        val payload = JSONObject().apply {
            put("ssid", ssid)
            put("bssid", bssid)
            put("securityType", securityType)
        }

        val url = Config.getBaseUrl(context).trim().trimEnd('/') + "/api/wifi/audit/analyze"
        val reqBuilder = Request.Builder()
            .url(url)
            .post(payload.toString().toRequestBody(jsonMedia))

        SecureStores.getDeviceToken(context)?.takeIf { it.isNotBlank() }?.let {
            reqBuilder.header("X-DEVICE-TOKEN", it)
        }

        client.newCall(reqBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) return SecurityAssessmentResult()
            val body = resp.body?.string().orEmpty()
            if (body.isBlank()) return SecurityAssessmentResult()

            val json = JSONObject(body)
            return SecurityAssessmentResult(
                isVulnerable = json.optBoolean("isVulnerable", false),
                vulnerabilityType = json.optString("vulnerabilityType").takeIf { it.isNotBlank() },
                foundPassword = json.optString("testedPassword").takeIf { it.isNotBlank() },
                serverReport = json.optString("report").takeIf { it.isNotBlank() }
            )
        }
    }

    private fun parseSecurityType(capabilities: String): String {
        return when {
            capabilities.contains("WPA3-SAE", ignoreCase = true) -> "WPA3-SAE"
            capabilities.contains("WPA3", ignoreCase = true) -> "WPA3"
            capabilities.contains("WPA2", ignoreCase = true) -> "WPA2"
            capabilities.contains("WPA", ignoreCase = true) -> "WPA"
            capabilities.contains("WEP", ignoreCase = true) -> "WEP"
            capabilities.contains("OPEN", ignoreCase = true) -> "OPEN"
            else -> "UNKNOWN"
        }
    }

    private fun checkWpsSupport(capabilities: String): Boolean {
        return capabilities.contains("WPS", ignoreCase = true)
    }

    private fun convertFrequencyToChannel(frequency: Int): Int {
        return when (frequency) {
            in 2412..2484 -> (frequency - 2412) / 5 + 1
            in 5170..5825 -> (frequency - 5170) / 5 + 34
            else -> 0
        }
    }

    private fun calculateSignalPercentage(rssi: Int): Int {
        val min = -100
        val max = -50
        return ((rssi - min) * 100 / (max - min)).coerceIn(0, 100)
    }

    private fun analyzeChannelCongestion(scanResults: List<ScanResult>, channel: Int): String {
        val count = scanResults.count { convertFrequencyToChannel(it.frequency) == channel }
        return when {
            count < 3 -> "Низкая"
            count < 6 -> "Средняя"
            else -> "Высокая"
        }
    }

    private fun getManufacturerFromBssid(bssid: String): String? {
        val normalized = bssid.replace(":", "")
        if (normalized.length < 6) return null
        val oui = normalized.substring(0, 6).uppercase()
        return when (oui.substring(0, 3)) {
            "001" -> "TP-Link"
            "002" -> "D-Link"
            "003" -> "Netgear"
            "004" -> "Huawei"
            else -> null
        }
    }
}

data class SecurityAssessmentResult(
    var isVulnerable: Boolean = false,
    var vulnerabilityType: String? = null,
    var foundPassword: String? = null,
    var serverReport: String? = null
)
