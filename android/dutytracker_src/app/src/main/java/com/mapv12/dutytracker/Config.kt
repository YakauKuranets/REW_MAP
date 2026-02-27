package com.mapv12.dutytracker

import android.content.Context

object Config {
    const val MAX_PENDING_POINTS = 2000
    const val MAX_UPLOADED_KEEP_DAYS = 7

    // Default: emulator -> host machine
    private const val DEFAULT_BASE_URL = "http://10.0.2.2:5000"

    private const val PREF = "dutytracker_prefs"
    private const val KEY_BASE_URL = "base_url"

    fun getBaseUrl(ctx: Context): String {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val v = p.getString(KEY_BASE_URL, null)?.trim()
        return if (!v.isNullOrEmpty()) v else DEFAULT_BASE_URL
    }

    fun setBaseUrl(ctx: Context, baseUrl: String) {
        val clean = baseUrl.trim().trimEnd('/')
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_BASE_URL, clean)
            .apply()
    }
}
