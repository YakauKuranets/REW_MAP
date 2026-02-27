package com.mapv12.dutytracker

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "event_journal",
    indices = [
        Index(value = ["tsEpochMs"]),
        Index(value = ["kind"])
    ]
)
data class EventJournalEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val tsEpochMs: Long,
    val kind: String,      // pair/start/stop/points/health/sos/profile/worker
    val endpoint: String,
    val ok: Boolean,
    val statusCode: Int?,
    val message: String?,
    val extra: String?
)
