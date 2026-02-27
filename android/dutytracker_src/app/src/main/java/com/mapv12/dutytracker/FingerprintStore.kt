package com.mapv12.dutytracker

import android.content.Context
import java.time.Instant

/**
 * Throttle/state for sending radio fingerprints.
 *
 * IMPORTANT:
 *  - best-effort only (must never break tracking)
 *  - we do NOT create a new Room table yet (so no DB migration risk)
 */
object FingerprintStore {

    // Stage MAX-1: send fingerprints about once per minute.
    private const val MIN_SEND_INTERVAL_SEC = 60L

    fun shouldSend(ctx: Context): Boolean {
        return try {
            val lastIso = StatusStore.getLastFingerprintSent(ctx)
            if (lastIso.isBlank()) return true
            val last = Instant.parse(lastIso)
            val now = Instant.now()
            (now.epochSecond - last.epochSecond) >= MIN_SEND_INTERVAL_SEC
        } catch (_: Exception) {
            true
        }
    }

    fun markSent(ctx: Context) {
        try {
            StatusStore.setLastFingerprintSent(ctx, Instant.now().toString())
        } catch (_: Exception) {}
    }
}
