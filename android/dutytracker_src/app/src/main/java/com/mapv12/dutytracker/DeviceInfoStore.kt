package com.mapv12.dutytracker

import android.content.Context

object DeviceInfoStore {
    private const val PREF = "dutytracker_device_info"
    private const val KEY_DEVICE_ID = "device_id"
    private const val KEY_USER_ID = "user_id"
    private const val KEY_LABEL = "label"

    fun set(ctx: Context, deviceId: String?, userId: String?, label: String?) {
        val ed = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
        if (deviceId.isNullOrBlank()) ed.remove(KEY_DEVICE_ID) else ed.putString(KEY_DEVICE_ID, deviceId)
        if (userId.isNullOrBlank()) ed.remove(KEY_USER_ID) else ed.putString(KEY_USER_ID, userId)
        if (label.isNullOrBlank()) ed.remove(KEY_LABEL) else ed.putString(KEY_LABEL, label)
        ed.apply()
    }

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().clear().apply()
    }

    fun deviceId(ctx: Context): String? = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY_DEVICE_ID, null)
    fun userId(ctx: Context): String? = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY_USER_ID, null)
    fun label(ctx: Context): String? = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY_LABEL, null)
}
