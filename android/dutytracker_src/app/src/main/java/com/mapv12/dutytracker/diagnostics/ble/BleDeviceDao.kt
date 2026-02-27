package com.mapv12.dutytracker.diagnostics.ble

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface BleDeviceDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertDevice(device: BleDeviceEntity)

    @Query("SELECT * FROM ble_devices ORDER BY rssi DESC")
    fun getAllDevices(): Flow<List<BleDeviceEntity>>

    @Query("DELETE FROM ble_devices WHERE lastSeen < :cutoff")
    suspend fun deleteOldDevices(cutoff: Long)
}
