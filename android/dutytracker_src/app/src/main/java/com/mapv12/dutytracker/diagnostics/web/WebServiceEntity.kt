package com.mapv12.dutytracker.diagnostics.web

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Информация о веб-сервисе, обнаруженном на открытом порту.
 * Содержит заголовки, код ответа и другую диагностическую информацию.
 */
@Entity(tableName = "web_services")
data class WebServiceEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val ip: String,
    val port: Int,
    val url: String,
    val statusCode: Int,
    val serverHeader: String?,
    val title: String?,
    val authRequired: Boolean,
    val timestamp: Long = System.currentTimeMillis()
)
