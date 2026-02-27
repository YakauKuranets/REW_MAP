package com.mapv12.dutytracker.diagnostics.web

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface WebServiceDao {
    @Insert
    suspend fun insert(service: WebServiceEntity)

    @Query("SELECT * FROM web_services WHERE ip = :ip")
    suspend fun getForIp(ip: String): List<WebServiceEntity>

    @Query("DELETE FROM web_services WHERE timestamp < :cutoff")
    suspend fun deleteOldServices(cutoff: Long)
}
