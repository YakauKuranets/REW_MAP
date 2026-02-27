package com.mapv12.dutytracker

import android.graphics.Color
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * JournalAdapter — современный ListAdapter с DiffUtil.
 * Отображает события трекинга в журнале.
 */
class JournalAdapter : ListAdapter<EventJournalEntity, JournalAdapter.VH>(DIFF) {

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<EventJournalEntity>() {
            override fun areItemsTheSame(a: EventJournalEntity, b: EventJournalEntity) = a.id == b.id
            override fun areContentsTheSame(a: EventJournalEntity, b: EventJournalEntity) = a == b
        }

        private val sdf = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

        // Маппинг типа события → emoji-иконка + цвет индикатора
        private data class EventStyle(val icon: String, val color: String)
        private val styleMap = mapOf(
            "upload"       to EventStyle("📤", "#1A56DB"),
            "gps"          to EventStyle("📡", "#10b981"),
            "error"        to EventStyle("❌", "#ef4444"),
            "start"        to EventStyle("▶️", "#10b981"),
            "stop"         to EventStyle("⏹", "#6b7280"),
            "sos"          to EventStyle("🆘", "#ef4444"),
            "pair"         to EventStyle("🔗", "#6d28d9"),
            "boot"         to EventStyle("🔄", "#f59e0b"),
            "watchdog"     to EventStyle("🐕", "#f59e0b"),
            "filter"       to EventStyle("🎯", "#3b82f6"),
            "health"       to EventStyle("💓", "#10b981"),
        )
        private val defaultStyle = EventStyle("📋", "#74778C")
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_journal, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        holder.bind(getItem(position))
    }

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val tvType: TextView    = itemView.findViewById(R.id.tv_event_type)
        private val tvDetail: TextView  = itemView.findViewById(R.id.tv_event_detail)
        private val tvTime: TextView    = itemView.findViewById(R.id.tv_event_time)
        private val indicator: View     = itemView.findViewById(R.id.view_indicator)

        fun bind(e: EventJournalEntity) {
            val style = styleMap[e.kind.lowercase()] ?: defaultStyle

            // Заголовок: иконка + тип + статус
            val status = if (e.ok) "OK" else "ERR ${e.statusCode ?: ""}"
            tvType.text = "${style.icon}  ${e.kind.uppercase(Locale.getDefault())} · $status"

            // Детали: endpoint + сообщение
            val parts = buildList {
                e.endpoint?.takeIf { it.isNotBlank() }?.let { add(it) }
                e.message?.trim()?.takeIf { it.isNotBlank() }?.let { add(it) }
                    ?: e.extra?.trim()?.takeIf { it.isNotBlank() }?.let { add(it) }
            }
            tvDetail.text = parts.joinToString(" · ").ifBlank { "—" }

            // Время
            tvTime.text = sdf.format(Date(e.tsEpochMs))

            // Цветной индикатор слева
            runCatching {
                val color = if (!e.ok) "#ef4444" else style.color
                indicator.setBackgroundColor(Color.parseColor(color))
            }
        }
    }
}
