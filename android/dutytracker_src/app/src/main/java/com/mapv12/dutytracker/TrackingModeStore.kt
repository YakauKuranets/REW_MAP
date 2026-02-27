package com.mapv12.dutytracker

import android.content.Context

/**
 * Режимы трекинга: балансируем точность / батарею.
 *
 * ECO     — реже, экономит батарею.
 * NORMAL  — по умолчанию.
 * PRECISE — чаще и точнее, батарея расходуется быстрее.
 */
enum class TrackingMode(val id: String) {
    ECO("eco"),
    NORMAL("normal"),
    PRECISE("precise"),
    AUTO("auto");

    companion object {
        fun fromId(id: String?): TrackingMode =
            values().firstOrNull { it.id == id } ?: NORMAL
    }
}

object TrackingModeStore {
    private const val PREF = "dutytracker_mode"
    private const val KEY = "tracking_mode"

    fun get(ctx: Context): TrackingMode {
        val id = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY, null)
        return TrackingMode.fromId(id)
    }

    fun set(ctx: Context, mode: TrackingMode) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(KEY, mode.id).apply()
    }
}
