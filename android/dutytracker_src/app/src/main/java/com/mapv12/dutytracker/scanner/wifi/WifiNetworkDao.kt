package com.mapv12.dutytracker.scanner.wifi

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface WifiNetworkDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNetwork(network: WifiNetworkEntity)

    @Query("SELECT * FROM wifi_networks ORDER BY rssi DESC")
    fun getAllNetworks(): Flow<List<WifiNetworkEntity>>

    @Query("SELECT * FROM wifi_networks WHERE bssid = :bssid")
    suspend fun getNetworkByBssid(bssid: String): WifiNetworkEntity?

    @Query("DELETE FROM wifi_networks WHERE lastSeen < :cutoff")
    suspend fun deleteOldNetworks(cutoff: Long)

    @Query("UPDATE wifi_networks SET isVulnerable = 0, vulnerabilityType = NULL, testedPassword = NULL")
    suspend fun resetVulnerabilityStatus()
}
