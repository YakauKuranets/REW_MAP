package com.mapv12.dutytracker.utils

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

object CyberHaptics {

    // Агрессивный двойной импульс при успешном перехвате или захвате цели
    fun triggerTargetAcquired(context: Context) {
        val vibrator = getVibrator(context) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // 0ms задержка, 150ms мощная вибрация, 100ms пауза, 300ms добивающая
            val timings = longArrayOf(0, 150, 100, 300)
            val amplitudes = intArrayOf(0, 255, 0, 255) // Максимальная сила (255)
            vibrator.vibrate(VibrationEffect.createWaveform(timings, amplitudes, -1))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(longArrayOf(0, 150, 100, 300), -1)
        }
    }

    // Короткий жесткий "щелчок" (tick) при обновлении радара
    fun triggerScanTick(context: Context) {
        val vibrator = getVibrator(context) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(30, 150))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(30)
        }
    }

    private fun getVibrator(context: Context): Vibrator? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
            vibratorManager.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }
    }
}
