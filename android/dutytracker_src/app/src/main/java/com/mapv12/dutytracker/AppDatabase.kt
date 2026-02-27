package com.mapv12.dutytracker

import androidx.room.Database
import androidx.room.RoomDatabase
import com.mapv12.dutytracker.diagnostics.ble.BleDeviceDao
import com.mapv12.dutytracker.diagnostics.ble.BleDeviceEntity
import com.mapv12.dutytracker.diagnostics.ports.PortScanDao
import com.mapv12.dutytracker.diagnostics.ports.PortScanEntity
import com.mapv12.dutytracker.diagnostics.web.WebServiceDao
import com.mapv12.dutytracker.diagnostics.web.WebServiceEntity
import com.mapv12.dutytracker.scanner.CameraDao
import com.mapv12.dutytracker.scanner.CameraEntity
import com.mapv12.dutytracker.scanner.wifi.WifiNetworkDao
import com.mapv12.dutytracker.scanner.wifi.WifiNetworkEntity

@Database(
    entities = [
        TrackPointEntity::class,
        EventJournalEntity::class,
        ChatMessageEntity::class,
        CameraEntity::class,
        WifiNetworkEntity::class,
        BleDeviceEntity::class,
        PortScanEntity::class,
        WebServiceEntity::class
    ],
    version = 12,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun trackPointDao(): TrackPointDao
    abstract fun eventJournalDao(): EventJournalDao
    abstract fun chatMessageDao(): ChatMessageDao
    abstract fun cameraDao(): CameraDao
    abstract fun wifiNetworkDao(): WifiNetworkDao
    abstract fun bleDeviceDao(): BleDeviceDao
    abstract fun portScanDao(): PortScanDao
    abstract fun webServiceDao(): WebServiceDao
}
