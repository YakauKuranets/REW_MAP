package com.mapv12.dutytracker

import android.content.Context

/**
 * AUTO режим: сам выбирает эффективный режим (ECO/NORMAL/PRECISE) по движению.
 * Идея простая: стоим -> ECO, движемся -> NORMAL, быстро/плохая точность -> PRECISE.
 *
 * Это можно усложнять дальше (учесть батарею/экран/сеть), но уже сейчас это снимает боль
 * "или батарею убивает, или точность слабая".
 */
object AutoModeController {

    private const val SPEED_STILL = 0.5      // m/s ~ 1.8 km/h
    private const val SPEED_FAST = 5.0       // m/s ~ 18 km/h
    private const val ACC_GOOD = 15.0        // meters

    fun decide(speedMps: Double?, accuracyM: Double?): TrackingMode {
        val s = speedMps ?: 0.0
        val acc = accuracyM ?: 999.0

        return when {
            s < SPEED_STILL -> TrackingMode.ECO
            s >= SPEED_FAST && acc > ACC_GOOD -> TrackingMode.PRECISE
            else -> TrackingMode.NORMAL
        }
    }

    fun getEffective(ctx: Context): TrackingMode {
        val id = StatusStore.getEffectiveMode(ctx)
        return TrackingMode.fromId(id)
    }

    fun setEffective(ctx: Context, mode: TrackingMode) {
        StatusStore.setEffectiveMode(ctx, mode.id)
    }
}
