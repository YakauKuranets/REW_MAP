package com.mapv12.dutytracker.scanner

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface CameraDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertCamera(camera: CameraEntity)

    @Query("SELECT * FROM cameras ORDER BY lastSeen DESC")
    fun getAllCameras(): Flow<List<CameraEntity>>

    @Query("DELETE FROM cameras WHERE lastSeen < :cutoff")
    suspend fun deleteOldCameras(cutoff: Long)

    @Query("SELECT * FROM cameras WHERE ip = :ip")
    suspend fun getCameraByIp(ip: String): CameraEntity?
}
