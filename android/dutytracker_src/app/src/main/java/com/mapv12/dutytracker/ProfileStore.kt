package com.mapv12.dutytracker

import android.content.Context

object ProfileStore {
    private const val PREF = "dutytracker_profile"

    private const val KEY_FULL_NAME = "full_name"
    private const val KEY_DUTY_NUMBER = "duty_number"
    private const val KEY_UNIT = "unit"
    private const val KEY_POSITION = "position"
    private const val KEY_RANK = "rank"
    private const val KEY_PHONE = "phone"
    private const val KEY_COMPLETE = "profile_complete"

    data class Profile(
        val fullName: String,
        val dutyNumber: String,
        val unit: String,
        val position: String,
        val rank: String,
        val phone: String
    )

    fun isComplete(ctx: Context): Boolean =
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getBoolean(KEY_COMPLETE, false)

    fun load(ctx: Context): Profile? {
        val p = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val full = p.getString(KEY_FULL_NAME, null) ?: return null
        val duty = p.getString(KEY_DUTY_NUMBER, null) ?: return null
        val unit = p.getString(KEY_UNIT, null) ?: return null
        val pos = p.getString(KEY_POSITION, "") ?: ""
        val rank = p.getString(KEY_RANK, "") ?: ""
        val phone = p.getString(KEY_PHONE, "") ?: ""
        return Profile(full, duty, unit, pos, rank, phone)
    }

    fun save(ctx: Context, profile: Profile) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
            .putString(KEY_FULL_NAME, profile.fullName)
            .putString(KEY_DUTY_NUMBER, profile.dutyNumber)
            .putString(KEY_UNIT, profile.unit)
            .putString(KEY_POSITION, profile.position)
            .putString(KEY_RANK, profile.rank)
            .putString(KEY_PHONE, profile.phone)
            .putBoolean(KEY_COMPLETE, true)
            .apply()
    }

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().clear().apply()
    }
}
