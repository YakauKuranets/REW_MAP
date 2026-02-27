package com.mapv12.dutytracker

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity

class OemGuideActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_oem_guide)

        val tb = findViewById<com.google.android.material.appbar.MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(tb)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        tb.setNavigationOnClickListener { finish() }

        findViewById<Button>(R.id.btn_open_app_settings).setOnClickListener {
            try {
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:$packageName")
                })
            } catch (_: Exception) {}
        }

        findViewById<Button>(R.id.btn_open_location_settings).setOnClickListener {
            try {
                startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
            } catch (_: Exception) {}
        }

        findViewById<Button>(R.id.btn_open_battery_settings).setOnClickListener {
            try {
                // generic battery optimization settings (OEM-specific screens may vary)
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (_: Exception) {
                try { startActivity(Intent(Settings.ACTION_SETTINGS)) } catch (_: Exception) {}
            }
        }

        findViewById<Button>(R.id.btn_request_ignore_battery_opt).setOnClickListener {
            try {
                val pm = getSystemService(android.content.Context.POWER_SERVICE) as android.os.PowerManager
                if (pm.isIgnoringBatteryOptimizations(packageName)) {
                    android.widget.Toast.makeText(this, "Уже разрешено (исключение включено)", android.widget.Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
            } catch (_: Exception) {}

            try {
                // Open direct whitelist request dialog (works on many devices)
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                })
            } catch (_: Exception) {
                // Fallback to generic screen
                try {
                    startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                } catch (_: Exception) {
                    try { startActivity(Intent(Settings.ACTION_SETTINGS)) } catch (_: Exception) {}
                }
            }
        }

        findViewById<Button>(R.id.btn_open_oem_bg_settings).setOnClickListener {
            val ok = SystemActions.openOemBackgroundSettings(this)
            if (!ok) {
                try {
                    android.widget.Toast.makeText(this, "Не удалось открыть OEM-экран — открыл(а) общий раздел батареи", android.widget.Toast.LENGTH_LONG).show()
                } catch (_: Exception) {}
            }
        }

        findViewById<Button>(R.id.btn_open_location_permission).setOnClickListener {
            SystemActions.startBackgroundLocationFlow(this)
        }

    }
}
