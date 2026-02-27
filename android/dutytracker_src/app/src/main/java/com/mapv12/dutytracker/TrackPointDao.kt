package com.mapv12.dutytracker

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface TrackPointDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(p: TrackPointEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(points: List<TrackPointEntity>): List<Long>

    @Query("SELECT COUNT(*) FROM track_points WHERE state != 3")
    suspend fun countQueued(): Int

    @Query("SELECT COUNT(*) FROM track_points WHERE synced = 0")
    suspend fun countUnsynced(): Int

    @Query("SELECT COUNT(*) FROM track_points WHERE state = 0")
    suspend fun countPending(): Int

    @Query(
        "SELECT * FROM track_points " +
            "WHERE state IN (0, 2) AND attempts < :maxAttempts " +
            "ORDER BY tsEpochMs ASC LIMIT :limit"
    )
    fun observeForUpload(limit: Int, maxAttempts: Int): Flow<List<TrackPointEntity>>

    @Query(
        "UPDATE track_points SET state = 1, updatedAtMs = :nowMs " +
            "WHERE id IN (:ids) AND state IN (0, 2)"
    )
    suspend fun markInflight(ids: List<Long>, nowMs: Long = System.currentTimeMillis()): Int

    @Query(
        "UPDATE track_points SET state = 3, synced = 1, updatedAtMs = :nowMs, lastError = NULL " +
            "WHERE id IN (:ids)"
    )
    suspend fun markUploaded(ids: List<Long>, nowMs: Long = System.currentTimeMillis())

    @Query(
        "UPDATE track_points SET state = 3, synced = 1, updatedAtMs = :nowMs, lastError = NULL " +
            "WHERE id IN (:ids)"
    )
    suspend fun markSynced(ids: List<Long>, nowMs: Long = System.currentTimeMillis())

    @Query(
        "UPDATE track_points SET state = 2, attempts = attempts + 1, updatedAtMs = :nowMs, lastError = :err " +
            "WHERE id IN (:ids)"
    )
    suspend fun markFailed(ids: List<Long>, err: String?, nowMs: Long = System.currentTimeMillis())

    @Query(
        "UPDATE track_points SET state = 2, updatedAtMs = :nowMs, lastError = 'inflight_timeout' " +
            "WHERE state = 1 AND updatedAtMs < :olderThanMs"
    )
    suspend fun resetStuckInflight(olderThanMs: Long, nowMs: Long = System.currentTimeMillis()): Int

    @Query("DELETE FROM track_points WHERE state = 3 AND createdAtMs < :olderThanMs")
    suspend fun pruneUploaded(olderThanMs: Long): Int

    @Query(
        "DELETE FROM track_points WHERE id IN (" +
            "SELECT id FROM track_points WHERE state != 3 ORDER BY tsEpochMs ASC LIMIT :limit" +
            ")"
    )
    suspend fun deleteOldestQueued(limit: Int): Int

    @Query(
        "SELECT * FROM track_points " +
            "WHERE tsEpochMs >= :sinceMs " +
            "ORDER BY tsEpochMs ASC"
    )
    fun observeSince(sinceMs: Long): Flow<List<TrackPointEntity>>

    @Query(
        "SELECT * FROM track_points " +
            "WHERE tsEpochMs >= :sinceMs " +
            "ORDER BY tsEpochMs ASC LIMIT :limit"
    )
    fun observeSinceLimited(sinceMs: Long, limit: Int): Flow<List<TrackPointEntity>>

    @Query("SELECT * FROM track_points ORDER BY tsEpochMs DESC LIMIT 1")
    fun observeLast(): Flow<List<TrackPointEntity>>

    @Query(
        "SELECT * FROM track_points " +
            "WHERE state IN (0, 2) AND attempts < :maxAttempts " +
            "ORDER BY tsEpochMs ASC LIMIT :limit"
    )
    suspend fun loadForUpload(limit: Int, maxAttempts: Int): List<TrackPointEntity>

    @Query(
        "SELECT * FROM track_points " +
            "WHERE synced = 0 " +
            "ORDER BY tsEpochMs ASC LIMIT :limit"
    )
    suspend fun loadUnsynced(limit: Int): List<TrackPointEntity>

    @Query(
        "SELECT * FROM track_points " +
            "WHERE tsEpochMs >= :sinceMs " +
            "ORDER BY tsEpochMs ASC LIMIT :limit"
    )
    suspend fun loadSinceLimitedSnapshot(sinceMs: Long, limit: Int): List<TrackPointEntity>

    @Query("SELECT * FROM track_points ORDER BY tsEpochMs DESC LIMIT 1")
    suspend fun loadLastSnapshot(): TrackPointEntity?
}
