package com.mapv12.dutytracker

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object JournalLogger {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private const val KEEP_LAST = 300

    fun log(ctx: Context, kind: String, endpoint: String, ok: Boolean, statusCode: Int?, message: String?, extra: String?) {
        val ts = System.currentTimeMillis()
        // Also keep "last error" surfaced in StatusStore
        if (!ok && !message.isNullOrBlank()) {
            StatusStore.setLastError(ctx, message)
        }

        scope.launch {
            try {
                val dao = App.db.eventJournalDao()
                dao.insert(
                    EventJournalEntity(
                        tsEpochMs = ts,
                        kind = kind,
                        endpoint = endpoint,
                        ok = ok,
                        statusCode = statusCode,
                        message = message?.take(500),
                        extra = extra?.take(1500)
                    )
                )
                // Trim quietly (cheap)
                dao.trimKeepLast(KEEP_LAST)
            } catch (_: Exception) {
                // journal must never crash app
            }
        }
    }

    fun formatLine(e: EventJournalEntity): String {
        val sdf = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
        val t = sdf.format(Date(e.tsEpochMs))
        val status = if (e.ok) "OK" else "ERR"
        val code = e.statusCode?.toString() ?: "-"
        val msg = e.message?.replace("\n", " ") ?: ""
        return "${'$'}t  [${'$'}status ${'$'}code]  ${'$'}{e.kind} ${'$'}{e.endpoint}  ${'$'}msg"
    }
}
