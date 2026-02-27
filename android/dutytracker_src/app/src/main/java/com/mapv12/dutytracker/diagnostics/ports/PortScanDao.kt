package com.mapv12.dutytracker.diagnostics.ports

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface PortScanDao {
    @Insert
    suspend fun insertScan(scan: PortScanEntity)

    @Query("SELECT * FROM port_scans WHERE ip = :ip ORDER BY port")
    suspend fun getScansForIp(ip: String): List<PortScanEntity>

    @Query("DELETE FROM port_scans WHERE timestamp < :cutoff")
    suspend fun deleteOldScans(cutoff: Long)
}
