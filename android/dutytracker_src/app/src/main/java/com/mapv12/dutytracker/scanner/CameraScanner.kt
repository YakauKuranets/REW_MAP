package com.mapv12.dutytracker.scanner

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.*

class CameraScanner(private val context: Context) {

    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val multicastLock = wifiManager.createMulticastLock("camera_scanner")

    data class ScanResult(
        val ip: String,
        val port: Int,
        val vendor: String? = null,
        val onvifUrl: String? = null,
        val authType: String? = null
    )

    /**
     * Основной метод: запускает все виды обнаружения
     */
    suspend fun scanNetwork(timeoutMs: Long = 3000, maxPingHosts: Int = 64): List<ScanResult> = withContext(Dispatchers.IO) {
        val results = mutableSetOf<ScanResult>()

        // 1. ONVIF WS-Discovery (multicast)
        try {
            results.addAll(discoverOnvif(timeoutMs))
        } catch (e: Exception) {
            // log
        }

        // 2. SSDP (UPnP)
        try {
            results.addAll(discoverSsdp(timeoutMs))
        } catch (e: Exception) {
        }

        // 3. ARP-сканирование локальной сети (ping sweep)
        try {
            results.addAll(discoverByPing(maxPingHosts))
        } catch (e: Exception) {
        }

        // Для каждого найденного IP попытаемся определить вендора через HTTP
        val final = results.toList()
        val withVendor = final.map { result ->
            val (vendor, auth) = fingerprintHttp(result.ip, result.port)
            result.copy(vendor = vendor ?: result.vendor, authType = auth)
        }
        return@withContext withVendor.distinctBy { it.ip }
    }

    // ---------- ONVIF ----------
    private suspend fun discoverOnvif(timeoutMs: Long): List<ScanResult> = withContext(Dispatchers.IO) {
        val socket = MulticastSocket(3702).apply {
            soTimeout = timeoutMs.toInt()
            joinGroup(InetAddress.getByName("239.255.255.250"))
        }
        val probe = createOnvifProbe()
        socket.send(DatagramPacket(probe, probe.size, InetAddress.getByName("239.255.255.250"), 3702))

        val buffer = ByteArray(4096)
        val start = System.currentTimeMillis()
        val results = mutableListOf<ScanResult>()

        while (System.currentTimeMillis() - start < timeoutMs) {
            try {
                val packet = DatagramPacket(buffer, buffer.size)
                socket.receive(packet)
                val ip = packet.address.hostAddress
                val response = String(packet.data, 0, packet.length)
                // Пытаемся извлечь XAddrs (URL ONVIF) и вендора
                val xaddrs = extractXAddrs(response)
                results.add(ScanResult(ip = ip, port = 80, onvifUrl = xaddrs.firstOrNull()))
            } catch (e: SocketTimeoutException) {
                break
            }
        }
        socket.close()
        return@withContext results
    }

    private fun createOnvifProbe(): ByteArray {
        val uuid = java.util.UUID.randomUUID().toString()
        val xml = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
            xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
    <e:Header>
        <w:MessageID>uuid:$uuid</w:MessageID>
        <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
        <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
    </e:Header>
    <e:Body>
        <d:Probe>
            <d:Types>dn:NetworkVideoTransmitter</d:Types>
        </d:Probe>
    </e:Body>
</e:Envelope>"""
        return xml.toByteArray()
    }

    private fun extractXAddrs(xml: String): List<String> {
        val regex = "<d:XAddrs>(.*?)</d:XAddrs>".toRegex()
        return regex.findAll(xml).flatMap { it.groupValues[1].split(' ') }.map { it.trim() }
    }

    // ---------- SSDP ----------
    private suspend fun discoverSsdp(timeoutMs: Long): List<ScanResult> = withContext(Dispatchers.IO) {
        val socket = MulticastSocket(1900).apply {
            soTimeout = timeoutMs.toInt()
            joinGroup(InetAddress.getByName("239.255.255.250"))
        }
        val search = """
            M-SEARCH * HTTP/1.1
            HOST: 239.255.255.250:1900
            MAN: "ssdp:discover"
            MX: 2
            ST: ssdp:all

        """.trimIndent().replace("\n", "\r\n").toByteArray()
        socket.send(DatagramPacket(search, search.size, InetAddress.getByName("239.255.255.250"), 1900))

        val buffer = ByteArray(4096)
        val start = System.currentTimeMillis()
        val results = mutableListOf<ScanResult>()

        while (System.currentTimeMillis() - start < timeoutMs) {
            try {
                val packet = DatagramPacket(buffer, buffer.size)
                socket.receive(packet)
                val ip = packet.address.hostAddress
                val response = String(packet.data, 0, packet.length)
                if (response.contains("camera", ignoreCase = true) || response.contains("video", ignoreCase = true)) {
                    results.add(ScanResult(ip = ip, port = 80))
                }
            } catch (e: SocketTimeoutException) {
                break
            }
        }
        socket.close()
        return@withContext results
    }

    // ---------- ARP-сканирование (ping sweep) ----------
    private suspend fun discoverByPing(maxHosts: Int): List<ScanResult> = withContext(Dispatchers.IO) {
        val dhcp = wifiManager.dhcpInfo ?: return@withContext emptyList()
        val gateway = intToIp(dhcp.gateway)
        val ipParts = gateway.split('.').take(3).joinToString(".")
        val results = mutableListOf<ScanResult>()

        (1..maxHosts.coerceIn(1, 254)).forEach { i ->
            val target = "$ipParts.$i"
            if (InetAddress.getByName(target).isReachable(200)) {
                results.add(ScanResult(ip = target, port = 80))
            }
        }
        return@withContext results
    }

    // ---------- HTTP fingerprint ----------
    private fun fingerprintHttp(ip: String, port: Int): Pair<String?, String?> {
        val client = OkHttpClient.Builder()
            .connectTimeout(2, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(2, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        val request = Request.Builder()
            .url("http://$ip:$port/")
            .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            .build()
        return try {
            val response = client.newCall(request).execute()
            val text = response.body?.string()?.lowercase() ?: ""
            val headers = response.headers
            val server = headers["Server"]?.lowercase() ?: ""

            val vendor = when {
                "hikvision" in text || "hikvision" in server -> "hikvision"
                "dahua" in text || "dahua" in server -> "dahua"
                "axis" in text || "axis" in server -> "axis"
                else -> null
            }

            val authType = if (response.code == 401) {
                val auth = headers["WWW-Authenticate"]?.lowercase()
                when {
                    auth?.contains("digest") == true -> "digest"
                    auth?.contains("basic") == true -> "basic"
                    else -> null
                }
            } else null

            response.close()
            Pair(vendor, authType)
        } catch (e: Exception) {
            Pair(null, null)
        }
    }

    private fun intToIp(addr: Int): String = "${addr and 0xFF}.${addr shr 8 and 0xFF}.${addr shr 16 and 0xFF}.${addr shr 24 and 0xFF}"
}
