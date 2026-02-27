package com.mapv12.dutytracker.security

import android.util.Log
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat

class BiometricGatekeeper(private val activity: AppCompatActivity) {

    fun authenticate(onSuccess: () -> Unit, onFail: () -> Unit) {
        val executor = ContextCompat.getMainExecutor(activity)
        val biometricPrompt = BiometricPrompt(
            activity,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    Log.e("Gatekeeper", "Ошибка авторизации: $errString")
                    onFail()
                }

                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    Log.i("Gatekeeper", "Биометрия подтверждена. Доступ к ключам TrustZone открыт.")
                    onSuccess()
                }

                override fun onAuthenticationFailed() {
                    Log.w("Gatekeeper", "Отпечаток не распознан!")
                }
            },
        )

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Командный доступ")
            .setSubtitle("Аутентификация для расшифровки локальных баз данных")
            .setNegativeButtonText("Отмена")
            .build()

        biometricPrompt.authenticate(promptInfo)
    }
}
