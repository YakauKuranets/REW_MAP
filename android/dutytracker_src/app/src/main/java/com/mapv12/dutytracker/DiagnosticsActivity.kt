package com.mapv12.dutytracker

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.mapv12.dutytracker.diagnostics.ble.BluetoothDeviceDiscoverer
import com.mapv12.dutytracker.diagnostics.ports.NetworkPortAnalyzer
import com.mapv12.dutytracker.diagnostics.ports.PortScanEntity
import com.mapv12.dutytracker.diagnostics.web.WebServiceAnalyzer
import com.mapv12.dutytracker.wordlists.WordlistUpdater
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class DiagnosticsActivity : AppCompatActivity() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private lateinit var tvIds: TextView
    private lateinit var tvStatus: TextView
    private lateinit var tvIssues: TextView
    private lateinit var llIssueActions: LinearLayout
    private lateinit var tvDiagnosticsHint: TextView
    private lateinit var rvDiagnostics: RecyclerView
    private val diagnosticsAdapter = DiagnosticsResultAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_diagnostics)

        val tb = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(tb)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        tb.setNavigationOnClickListener { finish() }

        tvIds = findViewById(R.id.tv_ids)
        tvStatus = findViewById(R.id.tv_status)
        tvIssues = findViewById(R.id.tv_issues)
        llIssueActions = findViewById(R.id.ll_issue_actions)
        tvDiagnosticsHint = findViewById(R.id.tv_diagnostics_hint)
        rvDiagnostics = findViewById(R.id.rv_diagnostics_results)
        rvDiagnostics.layoutManager = LinearLayoutManager(this)
        rvDiagnostics.adapter = diagnosticsAdapter

        findViewById<MaterialButton>(R.id.btn_oem_guide).setOnClickListener {
            startActivity(Intent(this, OemGuideActivity::class.java))
        }
        findViewById<MaterialButton>(R.id.btn_open_journal).setOnClickListener {
            startActivity(Intent(this, JournalActivity::class.java))
        }
        findViewById<MaterialButton>(R.id.btn_export_logs).setOnClickListener {
            exportJournalAndShare()
        }

        findViewById<MaterialButton>(R.id.btn_app_settings).setOnClickListener { openAppSettings() }
        findViewById<MaterialButton>(R.id.btn_location_settings).setOnClickListener { openLocationSettings() }
        findViewById<MaterialButton>(R.id.btn_battery_settings).setOnClickListener { openBatterySettings() }

        findViewById<MaterialButton>(R.id.btn_notif_settings).setOnClickListener { SystemActions.openNotificationsSettings(this) }
        findViewById<MaterialButton>(R.id.btn_internet_settings).setOnClickListener { SystemActions.openInternetSettings(this) }
        findViewById<MaterialButton>(R.id.btn_request_ignore_battery_opt).setOnClickListener { SystemActions.requestIgnoreBatteryOptimizations(this) }

        findViewById<MaterialButton>(R.id.btn_ble_scan).setOnClickListener {
            startBleScan()
        }
        findViewById<MaterialButton>(R.id.btn_port_scan).setOnClickListener {
            startPortScan()
        }
        findViewById<MaterialButton>(R.id.btn_web_scan).setOnClickListener {
            startWebScan()
        }
        findViewById<MaterialButton>(R.id.btn_check_updates).setOnClickListener {
            startWordlistUpdateCheck()
        }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh() {
        val deviceId = DeviceInfoStore.deviceId(this) ?: "—"
        val userId = DeviceInfoStore.userId(this) ?: "—"
        val label = DeviceInfoStore.label(this) ?: "—"
        val sessionId = SessionStore.getSessionId(this) ?: "—"
        tvIds.text = "device_id: $deviceId\nuser_id: $userId\nlabel: $label\nsession_id: $sessionId"

        val issues = Survivability.collect(this)
        tvIssues.text = if (issues.isEmpty()) "Нет" else issues.joinToString("\n• ", prefix = "• ") { it.title }
        renderIssueActions(issues)

        val tracking = ForegroundLocationService.isTrackingOn(this)
        val mode = TrackingModeStore.get(this)
        val eff = StatusStore.getEffectiveMode(this).ifBlank { mode.id }

        val lastGps = StatusStore.getLastGps(this).ifBlank { "—" }
        val lastUpload = StatusStore.getLastUpload(this).ifBlank { "—" }
        val lastHealth = StatusStore.getLastHealth(this).ifBlank { "—" }
        val lastErr = StatusStore.getLastError(this).ifBlank { "—" }
        val lastAcc = StatusStore.getLastAccM(this)
        val accStr = if (lastAcc != null) String.format(Locale.US, "%.0f м", lastAcc) else "—"

        scope.launch {
            val queued = withContext(Dispatchers.IO) {
                try { App.db.trackPointDao().countQueued() } catch (_: Exception) { -1 }
            }
            val qStr = if (queued >= 0) queued.toString() else "—"

            tvStatus.text =
                "tracking: ${if (tracking) "ON" else "OFF"}\n" +
                "mode: ${mode.id} (effective: ${eff})\n" +
                "queue: $qStr\n" +
                "accuracy: $accStr\n" +
                "last_gps: $lastGps\n" +
                "last_upload: $lastUpload\n" +
                "last_health: $lastHealth\n" +
                "last_error: $lastErr"
        }
    }

    private fun renderIssueActions(issues: List<Issue>) {
        try {
            llIssueActions.removeAllViews()
            if (issues.isEmpty()) return
            for (issue in issues) {
                llIssueActions.addView(issueRow(issue))
            }
        } catch (_: Exception) {}
    }

    private fun issueRow(issue: Issue): LinearLayout {
        val row = LinearLayout(this)
        row.orientation = LinearLayout.HORIZONTAL
        row.layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        row.setPadding(0, 2, 0, 2)

        val tv = TextView(this)
        tv.text = "• ${issue.title}"
        tv.textSize = 13f
        val tvLp = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        row.addView(tv, tvLp)

        if (issue.fix !is FixAction.None) {
            val btn = com.google.android.material.button.MaterialButton(
                this,
                null,
                com.google.android.material.R.attr.materialButtonOutlinedStyle
            )
            btn.text = "Исправить"
            btn.textSize = 12f
            btn.minHeight = 0
            btn.setPadding(18, 6, 18, 6)
            btn.setOnClickListener { performFix(issue.fix) }
            val blp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            blp.marginStart = 10
            row.addView(btn, blp)
        }

        return row
    }

    private fun performFix(fix: FixAction) {
        when (fix) {
            is FixAction.RequestPermissions -> SystemActions.requestPermissions(this, fix.perms, fix.requestCode)
            FixAction.OpenAppSettings -> SystemActions.openAppSettings(this)
            FixAction.OpenLocationSettings -> SystemActions.openLocationSettings(this)
            FixAction.OpenNotificationsSettings -> {
                if (Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ) {
                    SystemActions.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 701)
                }
                SystemActions.openNotificationsSettings(this)
            }
            FixAction.OpenInternetSettings -> SystemActions.openInternetSettings(this)
            FixAction.RequestIgnoreBatteryOpt -> SystemActions.requestIgnoreBatteryOptimizations(this)
            FixAction.OpenBackgroundLocationFlow -> SystemActions.startBackgroundLocationFlow(this)
            FixAction.None -> {}
        }
    }

    private fun openAppSettings() {
        try {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
            })
        } catch (_: Exception) {}
    }

    private fun openLocationSettings() {
        try { startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) } catch (_: Exception) {}
    }

    private fun openBatterySettings() {
        try {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        } catch (_: Exception) {
            try { startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS)) } catch (_: Exception) {}
        }
    }

    private fun startBleScan() {
        tvDiagnosticsHint.text = "Bluetooth-устройства рядом: выполняется сканирование..."
        lifecycleScope.launch {
            val discoverer = BluetoothDeviceDiscoverer(this@DiagnosticsActivity)
            discoverer.startDiscovery(this, 5000) { devices ->
                runOnUiThread {
                    val rows = devices.map {
                        "${it.address} | RSSI ${it.rssi} dBm | ${it.manufacturer ?: "UNKNOWN"}"
                    }
                    diagnosticsAdapter.submit(rows.ifEmpty { listOf("Устройства не обнаружены") })
                    tvDiagnosticsHint.text = "Bluetooth-устройства рядом"
                }
                lifecycleScope.launch(Dispatchers.IO) {
                    devices.forEach { App.db.bleDeviceDao().insertDevice(it) }
                }
            }
        }
    }

    private fun startPortScan() {
        val targetIp = "192.168.1.1"
        tvDiagnosticsHint.text = "Анализ сетевых портов. Используйте только на своих устройствах."
        lifecycleScope.launch {
            val analyzer = NetworkPortAnalyzer()
            val results = analyzer.scanPorts(targetIp)
            val openResults = results.filter { it.isOpen }
            diagnosticsAdapter.submit(
                openResults.map { "$targetIp:${it.port} ${it.service ?: "Unknown"}" }
                    .ifEmpty { listOf("Открытые порты не найдены") }
            )

            withContext(Dispatchers.IO) {
                openResults.forEach { info ->
                    App.db.portScanDao().insertScan(
                        PortScanEntity(
                            ip = targetIp,
                            port = info.port,
                            service = info.service,
                            isOpen = true
                        )
                    )
                }
            }
        }
    }

    private fun startWebScan() {
        val targetIp = "192.168.1.1"
        tvDiagnosticsHint.text = "Информация о веб-сервисах"
        lifecycleScope.launch {
            val webAnalyzer = WebServiceAnalyzer()
            val webPorts = listOf(80, 443, 8080, 8443)
            val rows = mutableListOf<String>()

            withContext(Dispatchers.IO) {
                for (port in webPorts) {
                    val info = webAnalyzer.analyze(targetIp, port) ?: continue
                    val row = "$targetIp:${info.port} code=${info.statusCode} auth=${if (info.authRequired) "yes" else "no"} server=${info.serverHeader ?: "-"}"
                    rows.add(row)
                    App.db.webServiceDao().insert(webAnalyzer.toEntity(targetIp, info))
                }
            }

            diagnosticsAdapter.submit(rows.ifEmpty { listOf("Веб-сервисы не обнаружены") })
        }
    }



    private fun startWordlistUpdateCheck() {
        tvDiagnosticsHint.text = "Проверка обновления словарей..."
        lifecycleScope.launch {
            val updater = WordlistUpdater(this@DiagnosticsActivity)
            val info = updater.checkForUpdates()
            if (info == null) {
                Toast.makeText(this@DiagnosticsActivity, "Уже используется последняя версия", Toast.LENGTH_SHORT).show()
                tvDiagnosticsHint.text = "Регулярное обновление словарей позволяет выявлять больше распространённых паролей"
                return@launch
            }

            androidx.appcompat.app.AlertDialog.Builder(this@DiagnosticsActivity)
                .setTitle("Доступно обновление")
                .setMessage("Новая версия словаря (v${info.version}, ${info.size} записей). Загрузить?")
                .setPositiveButton("Загрузить") { _, _ ->
                    lifecycleScope.launch {
                        val file = updater.downloadWordlist(info)
                        if (file != null) {
                            val loaded = updater.loadWordlist(info.name)
                            val count = loaded?.size ?: 0
                            diagnosticsAdapter.submit(
                                listOf(
                                    "Словарь: ${info.name}",
                                    "Версия: v${info.version}",
                                    "Записей: $count",
                                    "Файл: ${file.name}"
                                )
                            )
                            Toast.makeText(this@DiagnosticsActivity, "Обновление загружено", Toast.LENGTH_SHORT).show()
                            tvDiagnosticsHint.text = "Регулярное обновление словарей позволяет выявлять больше распространённых паролей"
                        } else {
                            Toast.makeText(this@DiagnosticsActivity, "Ошибка загрузки", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                .setNegativeButton("Отмена", null)
                .show()
        }
    }

    private fun exportJournalAndShare() {
        scope.launch {
            try {
                val (rows, st) = withContext(Dispatchers.IO) {
                    val rows = App.db.eventJournalDao().last(500).reversed()
                    val st = StatusStore.read(this@DiagnosticsActivity)
                    rows to st
                }

                val sb = StringBuilder()
                sb.append("DutyTracker export\n")
                sb.append("Time: ").append(SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())).append('\n')
                sb.append("device_id: ").append(DeviceInfoStore.deviceId(this@DiagnosticsActivity) ?: "-").append('\n')
                sb.append("user_id: ").append(DeviceInfoStore.userId(this@DiagnosticsActivity) ?: "-").append('\n')
                sb.append("label: ").append(DeviceInfoStore.label(this@DiagnosticsActivity) ?: "-").append('\n')
                sb.append("session_id: ").append(SessionStore.getSessionId(this@DiagnosticsActivity) ?: "-").append('\n')
                sb.append("status_store: ").append(st.toString()).append("\n\n")
                sb.append("journal (last 500):\n")
                for (e in rows) sb.append(JournalLogger.formatLine(e)).append('\n')

                val f = java.io.File(cacheDir, "dutytracker_journal_${System.currentTimeMillis()}.txt")
                withContext(Dispatchers.IO) {
                    f.writeText(sb.toString(), Charsets.UTF_8)
                }

                val uri = FileProvider.getUriForFile(this@DiagnosticsActivity, "${packageName}.fileprovider", f)
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                startActivity(Intent.createChooser(send, "Отправить лог"))
            } catch (e: Exception) {
                Toast.makeText(this@DiagnosticsActivity, "Экспорт лога: ошибка (${e.message})", Toast.LENGTH_LONG).show()
            }
        }
    }
}


private class DiagnosticsResultAdapter : RecyclerView.Adapter<DiagnosticsResultAdapter.VH>() {
    private val items = mutableListOf<String>()

    fun submit(rows: List<String>) {
        items.clear()
        items.addAll(rows)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: android.view.ViewGroup, viewType: Int): VH {
        val tv = TextView(parent.context).apply {
            setPadding(16, 12, 16, 12)
            textSize = 12f
        }
        return VH(tv)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.textView.text = items[position]
    }

    override fun getItemCount(): Int = items.size

    class VH(itemView: android.view.View) : RecyclerView.ViewHolder(itemView) {
        val textView: TextView = itemView as TextView
    }
}
