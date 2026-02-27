package com.mapv12.dutytracker.scanner

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "cameras")
data class CameraEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val ip: String,
    val port: Int,
    val vendor: String?,
    val model: String?,
    val onvifUrl: String?,
    val authType: String? = null,
    val firstSeen: Long = System.currentTimeMillis(),
    val lastSeen: Long = System.currentTimeMillis(),
    val isOnline: Boolean = true
)
