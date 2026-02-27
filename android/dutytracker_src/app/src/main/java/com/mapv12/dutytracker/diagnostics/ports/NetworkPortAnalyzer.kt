package com.mapv12.dutytracker.diagnostics.ports

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

/**
 * Анализирует открытые порты на указанном IP-адресе.
 * Помогает определить, какие сетевые сервисы доступны.
 */
class NetworkPortAnalyzer {

    // Наиболее распространённые порты для сканирования
    private val commonPorts = listOf(
        21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143,
        443, 445, 993, 995, 1723, 3306, 3389, 5900, 8080, 8443
    )

    data class PortInfo(
        val port: Int,
        val isOpen: Boolean,
        val service: String? = null
    )

    /**
     * Сканирует список портов на указанном хосте.
     * @param ip целевой IP
     * @param timeout таймаут подключения в миллисекундах
     * @return список результатов по каждому порту
     */
    suspend fun scanPorts(ip: String, timeout: Int = 1000): List<PortInfo> = withContext(Dispatchers.IO) {
        commonPorts.map { port ->
            val isOpen = try {
                val socket = Socket()
                socket.connect(InetSocketAddress(ip, port), timeout)
                socket.close()
                true
            } catch (_: SocketTimeoutException) {
                false
            } catch (_: Exception) {
                false
            }
            val service = guessService(port)
            PortInfo(port, isOpen, if (isOpen) service else null)
        }
    }

    private fun guessService(port: Int): String = when (port) {
        21 -> "FTP"
        22 -> "SSH"
        23 -> "Telnet"
        25 -> "SMTP"
        53 -> "DNS"
        80 -> "HTTP"
        110 -> "POP3"
        111 -> "RPC"
        135 -> "RPC"
        139 -> "NetBIOS"
        143 -> "IMAP"
        443 -> "HTTPS"
        445 -> "SMB"
        993 -> "IMAPS"
        995 -> "POP3S"
        1723 -> "PPTP"
        3306 -> "MySQL"
        3389 -> "RDP"
        5900 -> "VNC"
        8080 -> "HTTP-Alt"
        8443 -> "HTTPS-Alt"
        else -> "Unknown"
    }
}
