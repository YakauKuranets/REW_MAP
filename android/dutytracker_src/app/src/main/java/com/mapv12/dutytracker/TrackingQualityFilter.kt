package com.mapv12.dutytracker

import android.location.Location
import kotlin.math.*

/**
 * Lightweight location quality filter + smoothing.
 *
 * Goals:
 * - reduce jitter at rest
 * - reject spikes/teleports
 * - avoid sending very inaccurate fixes (but don't freeze indoors)
 */
class TrackingQualityFilter {

    data class Decision(
        val accept: Boolean,
        val reason: String,
        val out: Location? = null
    )

    private var lastAccepted: Location? = null
    private var lastSavedAtMs: Long = 0
    /** Время последней принятой точки (любой точности). */
    private var lastAcceptedAtMs: Long = 0

    /** Время последнего принудительного принятия (чтобы не замусоривать трек). */
    private var lastForcedAtMs: Long = 0

    /** Время первого полученного Location (чтобы не "залипать" на строгом пороге). */
    private var firstSeenAtMs: Long = 0

    // Exponential smoothing state (for jitter at rest)
    private var emaLat: Double? = null
    private var emaLon: Double? = null

    /**
     * Returns accepted location (possibly smoothed) or reject decision.
     */
    fun process(inLoc: Location, mode: TrackingMode = TrackingMode.NORMAL): Decision {
        val now = System.currentTimeMillis()

        if (firstSeenAtMs <= 0L) firstSeenAtMs = now

        // 1) Drop stale fixes (device sometimes replays cached fixes)
        val ageMs = now - inLoc.time
        if (ageMs > 15_000) {
            return Decision(false, "stale ${(ageMs / 1000.0).roundToInt()}s")
        }

        // 2) Accuracy gate (adaptive)
        val acc = if (inLoc.hasAccuracy()) inLoc.accuracy.toDouble() else 9999.0
        val maxAcc = dynamicMaxAccuracy(now, mode)
        if (acc > maxAcc) {
            // В помещении точность часто "плохая", но лучше иметь редкие точки с большим кругом,
            // чем полностью пустую карту (вечный reject).
            val ref = when {
                lastAcceptedAtMs > 0L -> lastAcceptedAtMs
                firstSeenAtMs > 0L -> firstSeenAtMs
                else -> now
            }
            val sinceAnyAccept = (now - ref).coerceAtLeast(0L)
            val canForce = (sinceAnyAccept >= 45_000L) && ((now - lastForcedAtMs) >= 30_000L) && (acc <= 900.0)

            if (canForce) {
                // Если есть предыдущая точка — всё равно защищаемся от телепортов.
                val prev = lastAccepted
                if (prev != null) {
                    val dtMs = (inLoc.time - prev.time).coerceAtLeast(1L)
                    val distM = haversine(prev.latitude, prev.longitude, inLoc.latitude, inLoc.longitude)
                    val speedCalc = distM / (dtMs / 1000.0)
                    val speedLoc = if (inLoc.hasSpeed()) inLoc.speed.toDouble() else speedCalc
                    val speed = max(speedCalc, speedLoc)
                    if (isTeleport(distM, speed)) {
                        return Decision(false, "jump ${distM.roundToInt()}m@${speed.roundToInt()}m/s")
                    }
                }

                lastForcedAtMs = now
                val out = Location(inLoc)
                accept(out, now)
                return Decision(true, "force_acc ${acc.roundToInt()}m>${maxAcc.roundToInt()}m", out)
            }

            return Decision(false, "acc ${acc.roundToInt()}m>${maxAcc.roundToInt()}m")
        }

        val prev = lastAccepted
        if (prev != null) {
            val dtMs = (inLoc.time - prev.time).coerceAtLeast(1L)
            val distM = haversine(prev.latitude, prev.longitude, inLoc.latitude, inLoc.longitude)
            val speedCalc = distM / (dtMs / 1000.0)
            val speedLoc = if (inLoc.hasSpeed()) inLoc.speed.toDouble() else speedCalc
            val speed = max(speedCalc, speedLoc)

            // 3) Teleport / spike reject
            if (isTeleport(distM, speed)) {
                return Decision(false, "jump ${distM.roundToInt()}m@${speed.roundToInt()}m/s")
            }

            // 4) Stationary decimation: when basically not moving - do not spam points too often
            // (keeps one point roughly every 8s if staying in place)
            val minIntervalMs = when (mode) {
                TrackingMode.PRECISE -> 3_000L
                TrackingMode.NORMAL -> 6_000L
                TrackingMode.ECO -> 12_000L
                TrackingMode.AUTO -> 6_000L
            }
            val stillDistM = when (mode) {
                TrackingMode.PRECISE -> 2.0
                TrackingMode.NORMAL -> 3.0
                TrackingMode.ECO -> 5.0
                TrackingMode.AUTO -> 3.0
            }
            if (distM < stillDistM && speed < 0.7 && (now - lastSavedAtMs) < minIntervalMs) {
                return Decision(false, "still ${distM.roundToInt()}m")
            }

            // 5) Smoothing when slow / jittery
            if (shouldSmooth(speed, acc, distM, mode)) {
                val alpha = alphaForAccuracy(acc, mode)
                val baseLat = emaLat ?: prev.latitude
                val baseLon = emaLon ?: prev.longitude
                val outLat = baseLat + alpha * (inLoc.latitude - baseLat)
                val outLon = baseLon + alpha * (inLoc.longitude - baseLon)

                val out = Location(inLoc).apply {
                    latitude = outLat
                    longitude = outLon
                }

                accept(out, now)
                return Decision(true, "ok_smooth", out)
            }
        }

        // Accept as-is
        val out = Location(inLoc)
        accept(out, now)
        return Decision(true, "ok", out)
    }

    private fun accept(loc: Location, nowMs: Long) {
        lastAccepted = loc
        lastSavedAtMs = nowMs
        lastAcceptedAtMs = nowMs
        emaLat = loc.latitude
        emaLon = loc.longitude
    }

    /**
     * Adaptive accuracy threshold:
     * - normally expects good accuracy
     * - if no good fix for a while, expands threshold so tracker still advances indoors
     */
    private fun dynamicMaxAccuracy(nowMs: Long, mode: TrackingMode): Double {
        // Порог должен быть "мягким" в помещении, иначе трекер легко уходит в вечный reject.
        // Особенно критично для PRECISE: если первый фикс 60–150м, старый код никогда не
        // расширял лимит (lastGoodAtMs оставался 0) → очередь всегда 0 → на карте нет метки.

        // Base thresholds per mode.
        val (base, mid, worst, extreme) = when (mode) {
            // PRECISE: сначала ждём точность, но если её нет — всё равно двигаемся.
            TrackingMode.PRECISE -> Quad(25.0, 120.0, 250.0, 350.0)
            TrackingMode.NORMAL  -> Quad(35.0, 140.0, 260.0, 380.0)
            TrackingMode.ECO     -> Quad(60.0, 160.0, 320.0, 450.0)
            TrackingMode.AUTO    -> Quad(35.0, 140.0, 260.0, 380.0)
        }

        val ref = when {
            lastAcceptedAtMs > 0L -> lastAcceptedAtMs
            firstSeenAtMs > 0L -> firstSeenAtMs
            else -> nowMs
        }

        val dt = (nowMs - ref).coerceAtLeast(0L)
        return when {
            dt > 300_000 -> extreme
            dt > 120_000 -> worst
            dt > 30_000 -> mid
            else -> base
        }
    }

    /** Kotlin doesn't have a built-in Quad. */
    private data class Quad<A, B, C, D>(val a: A, val b: B, val c: C, val d: D)

    private fun isTeleport(distM: Double, speedMps: Double): Boolean {
        // Big jump with very high speed
        if (distM > 250.0 && speedMps > 50.0) return true
        // Huge jump even with moderate speed
        if (distM > 1500.0 && speedMps > 20.0) return true
        return false
    }

    private fun shouldSmooth(speedMps: Double, accM: Double, distM: Double, mode: TrackingMode): Boolean {
        // Smooth mostly at slow speeds; at higher speeds we trust raw GNSS more
        val maxSmoothSpeed = when (mode) {
            TrackingMode.PRECISE -> 1.2
            TrackingMode.NORMAL -> 1.6
            TrackingMode.ECO -> 2.2
            TrackingMode.AUTO -> 1.6
        }
        if (speedMps > maxSmoothSpeed) return false
        // If accuracy is already great, no need to smooth much
        val accGate = when (mode) {
            TrackingMode.PRECISE -> 7.0
            TrackingMode.NORMAL -> 8.0
            TrackingMode.ECO -> 10.0
            TrackingMode.AUTO -> 8.0
        }
        if (accM < accGate) return false
        // If jumpy distance, do not smooth (it might be a real move)
        val maxDist = when (mode) {
            TrackingMode.PRECISE -> 18.0
            TrackingMode.NORMAL -> 25.0
            TrackingMode.ECO -> 35.0
            TrackingMode.AUTO -> 25.0
        }
        if (distM > maxDist) return false
        return true
    }

    private fun alphaForAccuracy(accM: Double, mode: TrackingMode): Double {
        // ECO can smooth a bit stronger, PRECISE a bit weaker.
        val k = when (mode) {
            TrackingMode.PRECISE -> 0.85
            TrackingMode.NORMAL -> 1.0
            TrackingMode.ECO -> 1.25
            TrackingMode.AUTO -> 1.0
        }
        val a = when {
            accM <= 10.0 -> 0.35
            accM <= 20.0 -> 0.25
            accM <= 35.0 -> 0.18
            else -> 0.12
        }
        return (a * k).coerceIn(0.08, 0.45)
    }

    private fun haversine(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val r = 6371000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a = sin(dLat / 2).pow(2.0) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2).pow(2.0)
        val c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return r * c
    }
}
