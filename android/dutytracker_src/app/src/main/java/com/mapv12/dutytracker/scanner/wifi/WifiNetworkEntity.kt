package com.mapv12.dutytracker.scanner.wifi

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "wifi_networks")
data class WifiNetworkEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val ssid: String,
    val bssid: String,
    val capabilities: String,
    val frequency: Int,
    val rssi: Int,
    val securityType: String,
    val channel: Int,
    val isWpsEnabled: Boolean = false,
    val manufacturer: String? = null,
    val firstSeen: Long = System.currentTimeMillis(),
    val lastSeen: Long = System.currentTimeMillis(),
    val isVulnerable: Boolean = false,
    val vulnerabilityType: String? = null,
    val testedPassword: String? = null,
    val lastTested: Long = 0
)
