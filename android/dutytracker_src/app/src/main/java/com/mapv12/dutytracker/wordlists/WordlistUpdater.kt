package com.mapv12.dutytracker.wordlists

import android.content.Context
import androidx.security.crypto.EncryptedFile
import androidx.security.crypto.MasterKey
import com.mapv12.dutytracker.Config
import com.mapv12.dutytracker.SecureStores
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

data class WordlistInfo(
    val name: String,
    val version: Int,
    val size: Int,
    val hash: String,
    val updated: String
)

class WordlistUpdater(private val context: Context, private val apiKey: String? = SecureStores.getAuditApiKey(context)) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(90, TimeUnit.SECONDS)
        .build()

    private fun buildRequest(path: String): Request.Builder {
        val base = Config.getBaseUrl(context).trim().trimEnd('/')
        val builder = Request.Builder().url(base + path)
        apiKey?.takeIf { it.isNotBlank() }?.let { builder.header("X-API-Key", it) }
        SecureStores.getDeviceToken(context)?.takeIf { it.isNotBlank() }?.let { builder.header("X-DEVICE-TOKEN", it) }
        return builder
    }

    suspend fun checkForUpdates(): WordlistInfo? = withContext(Dispatchers.IO) {
        val req = buildRequest("/wordlists/version").get().build()
        runCatching {
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val body = resp.body?.string().orEmpty()
                if (body.isBlank()) return@use null
                val json = JSONObject(body)
                val server = WordlistInfo(
                    name = json.optString("name"),
                    version = json.optInt("version", 0),
                    size = json.optInt("size", 0),
                    hash = json.optString("hash"),
                    updated = json.optString("updated")
                )
                val localVersion = localVersion(server.name)
                if (server.version > localVersion) server else null
            }
        }.getOrNull()
    }

    suspend fun downloadWordlist(info: WordlistInfo): File? = withContext(Dispatchers.IO) {
        val req = buildRequest("/wordlists/download").get().build()
        runCatching {
            val rootDir = File(context.filesDir, "wordlists")
            if (!rootDir.exists()) rootDir.mkdirs()
            val target = File(rootDir, "${info.name}_v${info.version}.enc")

            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@use null
                val plainBytes = resp.body?.bytes() ?: return@use null
                val masterKey = MasterKey.Builder(context)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()
                val encryptedFile = EncryptedFile.Builder(
                    context,
                    target,
                    masterKey,
                    EncryptedFile.FileEncryptionScheme.AES256_GCM_HKDF_4KB
                ).build()
                encryptedFile.openFileOutput().use { it.write(plainBytes) }
                saveLocalVersion(info.name, info.version)
                target
            }
        }.getOrNull()
    }

    suspend fun loadWordlist(name: String = "rockyou_optimized"): List<String>? = withContext(Dispatchers.IO) {
        val version = localVersion(name)
        if (version <= 0) return@withContext null
        val file = File(File(context.filesDir, "wordlists"), "${name}_v${version}.enc")
        if (!file.exists()) return@withContext null

        runCatching {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            val encryptedFile = EncryptedFile.Builder(
                context,
                file,
                masterKey,
                EncryptedFile.FileEncryptionScheme.AES256_GCM_HKDF_4KB
            ).build()
            encryptedFile.openFileInput().bufferedReader(Charsets.UTF_8).use { br ->
                br.lineSequence().map { it.trim() }.filter { it.isNotBlank() }.toList()
            }
        }.getOrNull()
    }

    private fun localVersion(name: String): Int {
        return context.getSharedPreferences("wordlist_meta", Context.MODE_PRIVATE)
            .getInt("${name}_version", 0)
    }

    private fun saveLocalVersion(name: String, version: Int) {
        context.getSharedPreferences("wordlist_meta", Context.MODE_PRIVATE)
            .edit()
            .putInt("${name}_version", version)
            .apply()
    }
}
