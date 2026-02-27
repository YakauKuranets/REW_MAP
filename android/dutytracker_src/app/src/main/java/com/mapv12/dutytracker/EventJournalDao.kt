package com.mapv12.dutytracker

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface EventJournalDao {

    @Insert
    suspend fun insert(e: EventJournalEntity): Long

    @Query("SELECT * FROM event_journal ORDER BY id DESC LIMIT :limit")
    suspend fun last(limit: Int): List<EventJournalEntity>

    @Query("DELETE FROM event_journal WHERE id NOT IN (SELECT id FROM event_journal ORDER BY id DESC LIMIT :keep)")
    suspend fun trimKeepLast(keep: Int)
}
