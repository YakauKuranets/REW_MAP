package com.mapv12.dutytracker.diagnostics.ble

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Хранит информацию об обнаруженных Bluetooth-устройствах.
 * Используется для инвентаризации беспроводных устройств в зоне покрытия.
 */
@Entity(tableName = "ble_devices")
data class BleDeviceEntity(
    @PrimaryKey val address: String,
    val name: String?,
    val rssi: Int,
    val manufacturer: String?,
    val firstSeen: Long = System.currentTimeMillis(),
    val lastSeen: Long = System.currentTimeMillis()
)
