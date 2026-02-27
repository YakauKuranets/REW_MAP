package com.mapv12.dutytracker.scanner

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat

/**
 * Поддержка новых протоколов аутентификации и радиоинтерфейсов: BLE-сканирование маяков и устройств.
 */
class BleScanner(private val context: Context) {

    data class BleDevice(
        val address: String,
        val name: String?,
        val rssi: Int,
        val manufacturerData: ByteArray?
    )

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private val scanResults = mutableListOf<BleDevice>()
    private val mainHandler = Handler(Looper.getMainLooper())

    @SuppressLint("MissingPermission")
    fun startScan(
        timeoutMs: Long = 5_000,
        callback: (List<BleDevice>) -> Unit,
        onError: (String) -> Unit = {}
    ) {
        if (!hasBlePermissions()) {
            onError("Missing BLE scan permissions")
            callback(emptyList())
            return
        }

        val adapter = bluetoothAdapter
        if (adapter == null || !adapter.isEnabled) {
            onError("Bluetooth adapter is unavailable or disabled")
            callback(emptyList())
            return
        }

        val scanner = adapter.bluetoothLeScanner
        if (scanner == null) {
            onError("Bluetooth LE scanner is unavailable")
            callback(emptyList())
            return
        }

        scanResults.clear()

        val scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                result ?: return
                val manufacturerData = result.scanRecord
                    ?.manufacturerSpecificData
                    ?.takeIf { it.size() > 0 }
                    ?.valueAt(0)

                scanResults.add(
                    BleDevice(
                        address = result.device?.address ?: "",
                        name = result.device?.name,
                        rssi = result.rssi,
                        manufacturerData = manufacturerData
                    )
                )
            }

            override fun onScanFailed(errorCode: Int) {
                onError("BLE scan failed: $errorCode")
            }
        }

        scanner.startScan(scanCallback)
        mainHandler.postDelayed({
            scanner.stopScan(scanCallback)
            callback(scanResults.filter { it.address.isNotBlank() }.distinctBy { it.address })
        }, timeoutMs)
    }

    private fun hasBlePermissions(): Boolean {
        val permissions = listOf(
            Manifest.permission.BLUETOOTH,
            Manifest.permission.BLUETOOTH_ADMIN,
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.ACCESS_FINE_LOCATION
        )
        return permissions.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        }
    }
}
