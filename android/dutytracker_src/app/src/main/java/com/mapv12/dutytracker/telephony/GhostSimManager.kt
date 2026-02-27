package com.mapv12.dutytracker.telephony

import android.content.Context
import android.os.Build
import android.telephony.euicc.EuiccManager
import android.util.Log

/**
 * Safety-first eSIM capability helper.
 *
 * NOTE:
 * Privileged subscription switching/wiping APIs are intentionally NOT invoked here.
 * Such operations require system-level privileges and can be unsafe/abusive outside
 * controlled OEM or enterprise device-owner environments.
 */
class GhostSimManager(private val context: Context) {

    private val euiccManager = context.getSystemService(Context.EUICC_SERVICE) as? EuiccManager

    companion object {
        private const val TAG = "GhostSimManager"
    }

    /**
     * Проверяет, поддерживает ли устройство eSIM-подсистему.
     */
    fun isGhostModeSupported(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return false
        }
        return euiccManager?.isEnabled == true
    }

    /**
     * Безопасный no-op: переключение профилей eSIM не выполняется в пользовательской сборке.
     */
    fun executeIdentitySwitch(targetSubscriptionId: Int) {
        Log.w(
            TAG,
            "[GHOST_MODE] Запрошено переключение eSIM (SubID=$targetSubscriptionId), " +
                "но операция отключена в non-system сборке.",
        )
    }

    /**
     * Безопасный no-op: стирание eSIM профиля не выполняется в пользовательской сборке.
     */
    fun burnCurrentIdentity() {
        Log.w(TAG, "[GHOST_MODE] Запрошено удаление eSIM профиля, но операция отключена.")
    }
}
