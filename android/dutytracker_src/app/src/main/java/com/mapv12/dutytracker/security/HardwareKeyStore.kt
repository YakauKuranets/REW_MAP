package com.mapv12.dutytracker.security

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class HardwareKeyStore(private val context: Context) {

    companion object {
        private const val TAG = "HardwareKeyStore"
        private const val KEY_ALIAS = "playe_master_hardware_key"
        private const val PREF = "playe_hw_keystore"
        private const val KEY_DB_BLOB = "db_passphrase_blob"
        private const val KEY_DB_IV = "db_passphrase_iv"
    }

    private val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun getOrGenerateMasterKey(): SecretKey {
        if (keyStore.containsAlias(KEY_ALIAS)) {
            Log.i(TAG, "[TRUST_ZONE] Аппаратный ключ найден в Secure Enclave.")
            return keyStore.getKey(KEY_ALIAS, null) as SecretKey
        }

        Log.w(TAG, "[TRUST_ZONE] Инициализация генерации ключа в чипе...")
        val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")

        val builder = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setUserAuthenticationRequired(true)
            .setUserAuthenticationValidityDurationSeconds(300)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val hasStrongBox = context.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
            if (hasStrongBox) {
                builder.setIsStrongBoxBacked(true)
                Log.w(TAG, "[TRUST_ZONE] Аппаратный сейф (StrongBox) АКТИВИРОВАН. Высший уровень защиты.")
            } else {
                Log.w(TAG, "[TRUST_ZONE] StrongBox не найден. Используется стандартная TrustZone (TEE).")
            }
        }

        keyGenerator.init(builder.build())
        Log.w(TAG, "[TRUST_ZONE] Мастер-ключ выжжен в кристалле.")
        return keyGenerator.generateKey()
    }

    fun getOrCreateProtectedDbPassphrase(): String {
        val prefs = context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        val blobB64 = prefs.getString(KEY_DB_BLOB, null)
        val ivB64 = prefs.getString(KEY_DB_IV, null)

        if (!blobB64.isNullOrBlank() && !ivB64.isNullOrBlank()) {
            return decrypt(blobB64, ivB64)
        }

        val passphrase = ByteArray(32)
        java.security.SecureRandom().nextBytes(passphrase)
        val raw = Base64.encodeToString(passphrase, Base64.NO_WRAP)

        val (cipherTextB64, ivOutB64) = encrypt(raw)
        prefs.edit().putString(KEY_DB_BLOB, cipherTextB64).putString(KEY_DB_IV, ivOutB64).apply()

        passphrase.fill(0)
        return raw
    }

    private fun encrypt(plainText: String): Pair<String, String> {
        val key = getOrGenerateMasterKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val encrypted = cipher.doFinal(plainText.toByteArray(StandardCharsets.UTF_8))
        val iv = cipher.iv
        return Base64.encodeToString(encrypted, Base64.NO_WRAP) to Base64.encodeToString(iv, Base64.NO_WRAP)
    }

    private fun decrypt(cipherTextB64: String, ivB64: String): String {
        val key = getOrGenerateMasterKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val iv = Base64.decode(ivB64, Base64.NO_WRAP)
        val spec = GCMParameterSpec(128, iv)
        cipher.init(Cipher.DECRYPT_MODE, key, spec)
        val plain = cipher.doFinal(Base64.decode(cipherTextB64, Base64.NO_WRAP))
        return String(plain, StandardCharsets.UTF_8)
    }
}
