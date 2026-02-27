package com.mapv12.dutytracker

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import android.telephony.*
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * Collects a "radio fingerprint" (Wi‑Fi scan + nearby cellular towers).
 * This is used for future indoor / low‑GPS positioning without beacons.
 *
 * Important: this collector is best-effort and must never break tracking.
 */
object FingerprintCollector {

    private fun hasAnyLocationPermission(ctx: Context): Boolean {
        val fine = ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    private fun hasNearbyWifiPermission(ctx: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= 33) {
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.NEARBY_WIFI_DEVICES) == PackageManager.PERMISSION_GRANTED
        } else {
            true
        }
    }

    fun collectSample(ctx: Context): JSONObject? {
        return try {
            val sample = JSONObject()
            sample.put("ts", Instant.now().toString())

            // Attach last accepted GPS (if any) — used for training radio-map.
            try {
                val ll = StatusStore.getLastLatLon(ctx)
                if (ll != null) {
                    sample.put("lat", ll.first)
                    sample.put("lon", ll.second)
                }
            } catch (_: Exception) {}

            try {
                StatusStore.getLastAccM(ctx)?.let { sample.put("accuracy_m", it) }
            } catch (_: Exception) {}

            // GNSS freshness (age of last accepted point) — helps server decide train vs locate
            try {
                val lastAccIso = StatusStore.getLastAccepted(ctx)
                if (lastAccIso.isNotBlank()) {
                    sample.put("gps_last_accepted", lastAccIso)
                    try {
                        val ageSec = kotlin.math.max(0, (Instant.now().epochSecond - Instant.parse(lastAccIso).epochSecond).toInt())
                        sample.put("gps_age_sec", ageSec)
                    } catch (_: Exception) {}
                }
            } catch (_: Exception) {}

            // Filter diagnostics (why points may be rejected)
            try {
                val st = StatusStore.read(ctx)
                sample.put("filter_rejects", (st["filter_rejects"] as? Int) ?: 0)
                sample.put("last_filter", (st["last_filter"] as? String) ?: "")
            } catch (_: Exception) {}


            // Tracking mode context (useful for debugging)
            try {
                val stored = TrackingModeStore.get(ctx)
                val eff = if (stored == TrackingMode.AUTO) AutoModeController.getEffective(ctx) else stored
                sample.put("mode", if (stored == TrackingMode.AUTO) "AUTO" else stored.id)
                if (stored == TrackingMode.AUTO) sample.put("effective_mode", eff.id)
            } catch (_: Exception) {}

            sample.put("wifi", collectWifi(ctx))
            sample.put("cell", collectCell(ctx))

            sample
        } catch (_: Exception) {
            null
        }
    }

    private fun collectWifi(ctx: Context): JSONArray {
        val arr = JSONArray()
        try {
            val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return arr

            // For Android 13+ scanning requires NEARBY_WIFI_DEVICES.
            if (!hasNearbyWifiPermission(ctx)) return arr

            // Also requires location permission to get scan results on modern Android.
            if (!hasAnyLocationPermission(ctx)) return arr

            // Best effort: trigger scan (may be rate-limited by OS). We ignore result.
            try { wm.startScan() } catch (_: Exception) {}

            val results = try { wm.scanResults } catch (_: Exception) { emptyList() }

            // Keep top ~15 strongest APs
            val sorted = results
                .filterNotNull()
                .sortedByDescending { it.level }
                .take(15)

            for (r in sorted) {
                val o = JSONObject()
                try { o.put("bssid", r.BSSID ?: "") } catch (_: Exception) {}
                try { o.put("ssid", r.SSID ?: "") } catch (_: Exception) {}
                try { o.put("rssi", r.level) } catch (_: Exception) {}
                try { o.put("freq", r.frequency) } catch (_: Exception) {}
                arr.put(o)
            }
        } catch (_: Exception) {}
        return arr
    }

    private fun collectCell(ctx: Context): JSONArray {
        val arr = JSONArray()
        try {
            if (!hasAnyLocationPermission(ctx)) return arr

            val tm = ctx.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager ?: return arr
            val cells = try { tm.allCellInfo } catch (_: Exception) { emptyList() }

            // Keep up to ~8 towers
            for (ci in cells.take(8)) {
                val o = JSONObject()
                try {
                    when (ci) {
                        is CellInfoLte -> {
                            o.put("type", "lte")
                            val id = ci.cellIdentity
                            // Use reflection-based getters for maximum compatibility across SDK/API levels.
                            safePut(o, "mcc", cellIdField(id, "getMccString", "getMcc"))
                            safePut(o, "mnc", cellIdField(id, "getMncString", "getMnc"))
                            safePut(o, "ci", id.ci)
                            safePut(o, "tac", id.tac)
                            safePut(o, "pci", id.pci)
                            safePut(o, "dbm", ci.cellSignalStrength.dbm)
                            safePut(o, "asu", ci.cellSignalStrength.asuLevel)
                        }
                        is CellInfoWcdma -> {
                            o.put("type", "wcdma")
                            val id = ci.cellIdentity
                            // Use reflection-based getters for maximum compatibility across SDK/API levels.
                            safePut(o, "mcc", cellIdField(id, "getMccString", "getMcc"))
                            safePut(o, "mnc", cellIdField(id, "getMncString", "getMnc"))
                            safePut(o, "ci", id.cid)
                            safePut(o, "lac", id.lac)
                            safePut(o, "psc", id.psc)
                            safePut(o, "dbm", ci.cellSignalStrength.dbm)
                            safePut(o, "asu", ci.cellSignalStrength.asuLevel)
                        }
                        is CellInfoGsm -> {
                            o.put("type", "gsm")
                            val id = ci.cellIdentity
                            safePut(o, "mcc", cellIdField(id, "getMccString", "getMcc"))
                            safePut(o, "mnc", cellIdField(id, "getMncString", "getMnc"))
                            safePut(o, "ci", id.cid)
                            safePut(o, "lac", id.lac)
                            safePut(o, "dbm", ci.cellSignalStrength.dbm)
                            safePut(o, "asu", ci.cellSignalStrength.asuLevel)
                        }
                        is CellInfoNr -> {
                            o.put("type", "nr")
                            val id = ci.cellIdentity
                            // Android NR APIs vary by platform level. Use reflection to avoid compile-time breaks.
                            safePut(o, "mcc", cellIdField(id, "getMccString", "getMcc"))
                            safePut(o, "mnc", cellIdField(id, "getMncString", "getMnc"))
                            safePut(o, "ci", cellIdField(id, "getNci"))
                            safePut(o, "tac", cellIdField(id, "getTac"))
                            safePut(o, "pci", cellIdField(id, "getPci"))
                            safePut(o, "dbm", ci.cellSignalStrength.dbm)
                            safePut(o, "asu", ci.cellSignalStrength.asuLevel)
                        }
                        is CellInfoCdma -> {
                            o.put("type", "cdma")
                            val id = ci.cellIdentity
                            safePut(o, "sid", id.systemId)
                            safePut(o, "nid", id.networkId)
                            safePut(o, "bid", id.basestationId)
                            safePut(o, "dbm", ci.cellSignalStrength.dbm)
                            safePut(o, "asu", ci.cellSignalStrength.asuLevel)
                        }
                        else -> {
                            o.put("type", "unknown")
                        }
                    }
                } catch (_: Exception) {
                    // ignore broken tower
                }

                // Keep only if at least has type
                if (o.optString("type").isNotBlank()) arr.put(o)
            }
        } catch (_: Exception) {}
        return arr
    }

    private fun safePut(o: JSONObject, k: String, v: Any?) {
        try {
            when (v) {
                null -> {}
                is String -> if (v.isNotBlank()) o.put(k, v)
                else -> o.put(k, v)
            }
        } catch (_: Exception) {}
    }

    /**
     * Safely read a field from telephony CellIdentity via reflection.
     * This avoids build breaks across different Android SDKs where some getters may not exist.
     */
    private fun cellIdField(obj: Any, vararg getterNames: String): Any? {
        for (name in getterNames) {
            try {
                val m = obj.javaClass.getMethod(name)
                val v = m.invoke(obj)
                when (v) {
                    null -> continue
                    is String -> {
                        val s = v.trim()
                        if (s.isNotEmpty() && s != "2147483647") return s
                    }
                    is Int -> {
                        // Some platforms use Integer.MAX_VALUE as UNAVAILABLE.
                        if (v != Int.MAX_VALUE && v != 0 && v != -1) return v
                    }
                    is Long -> {
                        if (v != Long.MAX_VALUE && v != 0L && v != -1L) return v
                    }
                    else -> return v
                }
            } catch (_: NoSuchMethodException) {
                // try next name
            } catch (_: Exception) {
                // ignore and try next name
            }
        }
        return null
    }
}
