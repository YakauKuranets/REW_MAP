package com.mapv12.dutytracker

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.mapv12.dutytracker.scanner.wifi.WifiNetworkEntity
import com.mapv12.dutytracker.scanner.wifi.WifiSecurityAuditClient
import com.mapv12.dutytracker.utils.CyberHaptics
import kotlinx.coroutines.launch

class WifiAnalysisActivity : AppCompatActivity() {

    private lateinit var recycler: RecyclerView
    private lateinit var tvChannelAnalysis: TextView
    private lateinit var tvAccessPointInfo: TextView
    private lateinit var tvWpa3Warning: TextView
    private val adapter = WifiNetworkSelectAdapter()
    private val auditClient by lazy { WifiSecurityAuditClient(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_wifi_analysis)

        recycler = findViewById(R.id.recyclerView)
        tvChannelAnalysis = findViewById(R.id.tvChannelAnalysis)
        tvAccessPointInfo = findViewById(R.id.tvAccessPointInfo)
        tvWpa3Warning = findViewById(R.id.tvWpa3Warning)

        recycler.layoutManager = LinearLayoutManager(this)
        recycler.adapter = adapter

        val btnTabChannels: Button = findViewById(R.id.btnTabChannels)
        val btnTabAccessPoint: Button = findViewById(R.id.btnTabAccessPoint)
        val btnTabHistory: Button = findViewById(R.id.btnTabHistory)
        val btnDeepAnalysis: Button = findViewById(R.id.btnDeepAnalysis)

        fun showTab(tab: String) {
            when (tab) {
                "channels" -> {
                    tvChannelAnalysis.visibility = View.VISIBLE
                    tvAccessPointInfo.visibility = View.GONE
                    recycler.visibility = View.GONE
                }
                "ap" -> {
                    tvChannelAnalysis.visibility = View.GONE
                    tvAccessPointInfo.visibility = View.VISIBLE
                    recycler.visibility = View.GONE
                }
                else -> {
                    tvChannelAnalysis.visibility = View.GONE
                    tvAccessPointInfo.visibility = View.GONE
                    recycler.visibility = View.VISIBLE
                }
            }
        }

        btnTabChannels.setOnClickListener { showTab("channels") }
        btnTabAccessPoint.setOnClickListener { showTab("ap") }
        btnTabHistory.setOnClickListener { showTab("history") }

        btnDeepAnalysis.setOnClickListener {
            val selected = adapter.getSelected()
            if (selected == null) {
                AlertDialog.Builder(this)
                    .setTitle("Сеть не выбрана")
                    .setMessage("Выберите сеть из истории сканирования для запуска анализа.")
                    .setPositiveButton("OK", null)
                    .show()
                return@setOnClickListener
            }

            val securityType = selected.securityType
            val isWpa3 = securityType.equals("WPA3", ignoreCase = true) || securityType.equals("WPA3-SAE", ignoreCase = true)
            if (isWpa3) {
                AlertDialog.Builder(this)
                    .setTitle("Анализ WPA3")
                    .setMessage("WPA3 — современный протокол с усиленной защитой. Анализ может занять значительно больше времени (в 100 раз медленнее WPA2). Продолжить?")
                    .setPositiveButton("Да") { _, _ -> startDeepAnalysis(selected) }
                    .setNegativeButton("Нет", null)
                    .show()
            } else {
                startDeepAnalysis(selected)
            }
        }

        showTab("history")

        lifecycleScope.launch {
            App.db.wifiNetworkDao().getAllNetworks().collect { results ->
                adapter.submitList(results)
                updateChannelAnalytics(results)
                updateAccessPointInfo(results)

                val hasVulnerable = results.any { network ->
                    val type = network.securityType.uppercase()
                    type.contains("WEP") || type == "OPEN"
                }

                val hasWpa3 = results.any { it.securityType.contains("WPA3", ignoreCase = true) }
                tvWpa3Warning.text = if (hasWpa3) {
                    "Обнаружены WPA3-сети: для них анализ длится дольше."
                } else {
                    ""
                }

                if (hasVulnerable) {
                    CyberHaptics.triggerTargetAcquired(this@WifiAnalysisActivity)
                } else if (results.isNotEmpty()) {
                    CyberHaptics.triggerScanTick(this@WifiAnalysisActivity)
                }
            }
        }
    }

    private fun startDeepAnalysis(network: WifiNetworkEntity) {
        lifecycleScope.launch {
            val response = auditClient.requestAudit(network)
            if (response == null) {
                AlertDialog.Builder(this@WifiAnalysisActivity)
                    .setTitle("Ошибка анализа")
                    .setMessage("Не удалось запустить анализ сети ${network.ssid}. Проверьте подключение к серверу.")
                    .setPositiveButton("OK", null)
                    .show()
                return@launch
            }

            val message = buildString {
                append("Запущен анализ для ${network.ssid.ifBlank { "<hidden>" }}\n")
                append("Тип защиты: ${network.securityType}\n")
                append("Task ID: ${response.taskId}")
                if (response.estimatedTime > 0) {
                    append("\nОценка времени: ${response.estimatedTime} сек")
                }
            }

            AlertDialog.Builder(this@WifiAnalysisActivity)
                .setTitle("Углублённый анализ современных протоколов")
                .setMessage(message)
                .setPositiveButton("OK", null)
                .show()
        }
    }

    private fun updateChannelAnalytics(results: List<WifiNetworkEntity>) {
        if (results.isEmpty()) {
            tvChannelAnalysis.text = "CH.MON // Нет данных"
            return
        }

        val channelLoad = results.groupingBy { it.channel }.eachCount().toList().sortedByDescending { it.second }
        val busyLine = channelLoad.take(5).joinToString(" | ") { "ch${it.first}:${it.second}" }
        val recommended = channelLoad.minByOrNull { it.second }?.first ?: 1
        tvChannelAnalysis.text = "CH.MON // Загруженность: $busyLine\nРекомендация: использовать канал $recommended"
    }

    private fun updateAccessPointInfo(results: List<WifiNetworkEntity>) {
        val strongest = results.maxByOrNull { it.rssi }
        if (strongest == null) {
            tvAccessPointInfo.text = "AP.INFO // Нет данных"
            return
        }

        tvAccessPointInfo.text = buildString {
            append("AP.INFO // TARGET\n")
            append("SSID: ${strongest.ssid.ifBlank { "<hidden>" }}\n")
            append("BSSID: ${strongest.bssid}\n")
            append("VENDOR: ${strongest.manufacturer ?: "UNKNOWN"}\n")
            append("RSSI: ${strongest.rssi} dBm\n")
            append("SEC: ${strongest.securityType}")
        }
    }
}

private class WifiNetworkSelectAdapter : RecyclerView.Adapter<WifiNetworkSelectAdapter.VH>() {
    private val items = mutableListOf<WifiNetworkEntity>()
    private var selectedPosition = RecyclerView.NO_POSITION

    fun submitList(newItems: List<WifiNetworkEntity>) {
        items.clear()
        items.addAll(newItems)
        if (selectedPosition >= items.size) selectedPosition = RecyclerView.NO_POSITION
        notifyDataSetChanged()
    }

    fun getSelected(): WifiNetworkEntity? {
        return if (selectedPosition in items.indices) items[selectedPosition] else null
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_wifi_network, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(items[position], position == selectedPosition)
        holder.itemView.setOnClickListener {
            val previous = selectedPosition
            selectedPosition = holder.bindingAdapterPosition
            if (previous != RecyclerView.NO_POSITION) notifyItemChanged(previous)
            notifyItemChanged(selectedPosition)
        }
    }

    override fun getItemCount(): Int = items.size

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val tvSsid: TextView = itemView.findViewById(R.id.tvSsid)
        private val tvBssid: TextView = itemView.findViewById(R.id.tvBssid)
        private val tvSignal: TextView = itemView.findViewById(R.id.tvSignal)
        private val tvSecurity: TextView = itemView.findViewById(R.id.tvSecurity)

        fun bind(item: WifiNetworkEntity, selected: Boolean) {
            tvSsid.text = item.ssid.ifBlank { "<hidden>" }
            tvBssid.text = item.bssid
            tvSignal.text = "${item.rssi} dBm"
            tvSecurity.text = item.securityType
            itemView.alpha = if (selected) 1f else 0.85f
        }
    }
}
