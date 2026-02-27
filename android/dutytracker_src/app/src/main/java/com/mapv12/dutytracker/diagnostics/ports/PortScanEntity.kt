package com.mapv12.dutytracker.diagnostics.ports

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Результат сканирования порта на удалённом хосте.
 * Используется для оценки доступности сетевых сервисов.
 */
@Entity(tableName = "port_scans")
data class PortScanEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val ip: String,
    val port: Int,
    val service: String?,
    val isOpen: Boolean,
    val timestamp: Long = System.currentTimeMillis()
)
