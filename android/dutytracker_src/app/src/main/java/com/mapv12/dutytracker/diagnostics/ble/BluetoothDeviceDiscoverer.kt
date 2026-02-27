package com.mapv12.dutytracker.diagnostics.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.Locale

/**
 * Обнаруживает Bluetooth-устройства в радиусе действия.
 * Предназначен для инвентаризации и мониторинга беспроводных устройств.
 */
class BluetoothDeviceDiscoverer(private val context: Context) {

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private val scanner = bluetoothAdapter?.bluetoothLeScanner
    private val devices = mutableListOf<BleDeviceEntity>()

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult?) {
            result ?: return
            val address = result.device?.address ?: return
            val name = result.device?.name
            val rssi = result.rssi
            val manufacturer = extractManufacturer(result)
            devices.add(
                BleDeviceEntity(
                    address = address,
                    name = name,
                    rssi = rssi,
                    manufacturer = manufacturer,
                    lastSeen = System.currentTimeMillis()
                )
            )
        }
    }

    /**
     * Запускает сканирование на заданное время.
     * @param scope CoroutineScope для таймера
     * @param durationMs длительность сканирования в мс
     * @param onComplete callback со списком уникальных устройств
     */
    @SuppressLint("MissingPermission")
    fun startDiscovery(
        scope: CoroutineScope,
        durationMs: Long = 5000,
        onComplete: (List<BleDeviceEntity>) -> Unit
    ) {
        val activeScanner = scanner ?: run {
            onComplete(emptyList())
            return
        }

        devices.clear()
        activeScanner.startScan(null, ScanSettings.Builder().build(), scanCallback)
        scope.launch(Dispatchers.IO) {
            delay(durationMs)
            activeScanner.stopScan(scanCallback)
            val uniqueDevices = devices
                .distinctBy { it.address }
                .sortedByDescending { it.rssi }
            onComplete(uniqueDevices)
        }
    }

    private fun extractManufacturer(result: ScanResult): String? {
        val manufacturerData = result.scanRecord?.manufacturerSpecificData ?: return null
        if (manufacturerData.size() == 0) return null
        val companyCode = manufacturerData.keyAt(0)
        return "0x" + companyCode.toString(16).uppercase(Locale.ROOT)
    }
}
