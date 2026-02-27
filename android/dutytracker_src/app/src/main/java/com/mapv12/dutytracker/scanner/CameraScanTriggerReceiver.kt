package com.mapv12.dutytracker.scanner

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class CameraScanTriggerReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val serviceIntent = CameraScannerForegroundService.createStartIntent(context)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
