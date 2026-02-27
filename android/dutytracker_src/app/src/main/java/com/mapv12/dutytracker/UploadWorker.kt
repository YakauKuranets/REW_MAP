package com.mapv12.dutytracker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.time.Instant

class UploadWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val ctx = applicationContext
        val token = SecureStores.getDeviceToken(ctx)
        val dao = App.db.trackPointDao()

        if (token.isNullOrBlank()) {
            StatusStore.setLastError(ctx, "No device token")
            return@withContext Result.success()
        }

        val api = ApiClient(ctx)

        try {
            // Release stuck inflight points (e.g., process killed mid-upload)
            val nowMs = System.currentTimeMillis()
            dao.resetStuckInflight(olderThanMs = nowMs - 10 * 60 * 1000L)

            var sessionId = SessionStore.getSessionId(ctx)
            if (sessionId.isNullOrBlank()) {
                // Best effort: start a new session, but do not block if it fails
                val start = api.start(null, null)
                if (start.ok && !start.sessionId.isNullOrBlank()) {
                    sessionId = start.sessionId
                    SessionStore.setSessionId(ctx, sessionId)
                }
            }

            // Upload loop (small batches)
            var uploadedAny = false
            while (true) {
                val batch = dao.loadForUpload(limit = 100, maxAttempts = 10)
                if (batch.isEmpty()) break

                val ids = batch.map { it.id }
                dao.markInflight(ids)

                try {
                    // Ensure session exists
                    if (sessionId.isNullOrBlank()) {
                        val start = api.start(null, null)
                        if (!start.ok || start.sessionId.isNullOrBlank()) throw IOException("Cannot start session: ${start.error ?: "unknown"}")
                        sessionId = start.sessionId
                        SessionStore.setSessionId(ctx, sessionId)
                    }

                    // May throw SessionInactiveException (HTTP 409)
                    api.sendPoints(sessionId!!, batch)

                    dao.markUploaded(ids)
                    uploadedAny = true
                } catch (e: SessionInactiveException) {
                    JournalLogger.log(ctx, "worker", "upload/session_inactive", true, 409, "session_inactive", "active=${e.activeSessionId ?: "-"}")
                    // Start a fresh session and retry once for this batch
                    val start = api.start(null, null)
                    if (start.ok && !start.sessionId.isNullOrBlank()) {
                        sessionId = start.sessionId
                        SessionStore.setSessionId(ctx, sessionId)
                        try {
                            api.sendPoints(sessionId!!, batch)
                            dao.markUploaded(ids)
                            uploadedAny = true
                        } catch (e2: Exception) {
                            dao.markFailed(ids, e2.message)
                            throw e2
                        }
                    } else {
                        dao.markFailed(ids, "session_inactive: cannot restart")
                        throw IOException("Failed to restart session after 409")
                    }
                } catch (e: Exception) {
                    dao.markFailed(ids, e.message)
                    throw e
                }
            }

            val left = dao.countQueued()
            StatusStore.setQueue(ctx, left)
            if (uploadedAny) StatusStore.setLastUpload(ctx, Instant.now().toString())
            StatusStore.setLastError(ctx, null)
            JournalLogger.log(ctx, "worker", "upload", true, 200, null, "queue_left=$left")

            // health heartbeat (best-effort, not fatal)
            try {
                val nowIso = Instant.now().toString()
                val lastIso = StatusStore.getLastHealth(ctx)
                val should = try {
                    if (lastIso.isBlank()) true else {
                        val last = Instant.parse(lastIso)
                        val now = Instant.parse(nowIso)
                        (now.epochSecond - last.epochSecond) > 45
                    }
                } catch (_: Exception) { true }

                if (should) {
                    val payload = DeviceStatus.collect(
                        ctx = ctx,
                        queueSize = left,
                        trackingOn = ForegroundLocationService.isTrackingOn(ctx),
                        accuracyM = StatusStore.getLastAccM(ctx),
                        lastSendAtIso = run {
                            val lu = StatusStore.read(ctx)["last_upload"] as? String
                            if (!lu.isNullOrBlank() && lu != "—") lu else nowIso
                        },
                        lastError = StatusStore.read(ctx)["last_error"] as? String
                    )
                    api.sendHealth(payload)
                    StatusStore.setLastHealth(ctx, Instant.now().toString())

                    // Radio fingerprint (Wi‑Fi + cell) — best-effort
                    try {
                        if (FingerprintStore.shouldSend(ctx)) {
                            val sample = FingerprintCollector.collectSample(ctx)
                            if (sample != null) {
                                // MAX-2: mark sample as train (good GNSS) or locate (no reliable GNSS)
                                try {
                                    val hasLat = sample.has("lat") && sample.has("lon")
                                    val acc = try { sample.optDouble("accuracy_m") } catch (_: Exception) { Double.NaN }
                                    val goodAcc = (!acc.isNaN()) && (acc > 0.0) && (acc <= 60.0)
                                    val gpsAge = try { sample.optInt("gps_age_sec", 9999) } catch (_: Exception) { 9999 }
                                    // Train only if GNSS fix is fresh enough; otherwise treat as "locate" (indoors)
                                    val purpose = if (hasLat && goodAcc && gpsAge <= 45) "train" else "locate"
                                    sample.put("purpose", purpose)
                                    sample.put("source", "android")
                                } catch (_: Exception) {}
                                val okFp = api.sendFingerprints(sample)
                                if (okFp) FingerprintStore.markSent(ctx)
                            }
                        }
                    } catch (_: Exception) {}
                }
            } catch (_: Exception) {}

            return@withContext Result.success()
        } catch (e: Exception) {
            JournalLogger.log(ctx, "worker", "upload", false, null, e.message, null)
            StatusStore.setLastError(ctx, e.message)
            try {
                val left = dao.countQueued()
                StatusStore.setQueue(ctx, left)
                val nowIso = try { Instant.now().toString() } catch (_: Exception) { "" }
                val lastUpload = try { StatusStore.read(ctx)["last_upload"] as? String } catch (_: Exception) { null }
                val payload = DeviceStatus.collect(
                    ctx = ctx,
                    queueSize = left,
                    trackingOn = ForegroundLocationService.isTrackingOn(ctx),
                    accuracyM = null,
                    lastSendAtIso = if (!lastUpload.isNullOrBlank() && lastUpload != "—") lastUpload else nowIso,
                    lastError = e.message
                )
                api.sendHealth(payload)
            } catch (_: Exception) {}
            return@withContext Result.retry()
        }
    }
}
