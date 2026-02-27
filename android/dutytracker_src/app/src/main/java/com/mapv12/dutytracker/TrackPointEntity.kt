package com.mapv12.dutytracker

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

object UploadState {
    const val PENDING = 0
    const val INFLIGHT = 1
    const val FAILED = 2
    const val UPLOADED = 3
}

@Entity(
    tableName = "track_points",
    indices = [
        Index(value = ["sessionId", "tsEpochMs"], unique = false),
        Index(value = ["state"]),
        Index(value = ["synced"]),
        Index(value = ["updatedAtMs"])
    ]
)
data class TrackPointEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,

    val sessionId: String?,
    val tsEpochMs: Long,
    val lat: Double,
    val lon: Double,
    val accuracyM: Double?,
    val speedMps: Double?,
    val bearingDeg: Double?,

    /** 0=pending,1=inflight,2=failed,3=uploaded */
    val state: Int = UploadState.PENDING,
    /** 0=not synced to backend websocket, 1=synced/acked */
    val synced: Int = 0,
    val attempts: Int = 0,
    val lastError: String? = null,
    val createdAtMs: Long = System.currentTimeMillis(),
    val updatedAtMs: Long = System.currentTimeMillis()
)
