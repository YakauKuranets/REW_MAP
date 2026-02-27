package com.mapv12.dutytracker

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.room.Room
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.mapv12.dutytracker.wordlists.WordlistInfo
import com.mapv12.dutytracker.wordlists.WordlistUpdater
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import com.mapv12.dutytracker.security.HardwareKeyStore
import net.sqlcipher.database.SupportFactory

/**
 * Application class — точка входа.
 * Инициализирует Room БД, воркеры, каналы уведомлений.
 */
class App : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    override fun onCreate() {
        super.onCreate()


        // Watchdog: перезапускает трекинг если сервис убит системой
        runCatching { WatchdogWorker.ensureScheduled(applicationContext) }

        createNotificationChannels()
        checkWordlistUpdates()
    }


    private fun checkWordlistUpdates() {
        appScope.launch {
            val updater = WordlistUpdater(this@App)
            val updateInfo = updater.checkForUpdates()
            if (updateInfo != null) {
                showUpdateNotification(updateInfo)
            }
        }
    }

    private fun showUpdateNotification(info: WordlistInfo) {
        val builder = NotificationCompat.Builder(this, CHANNEL_TRACKING)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Обновление базы данных для повышения точности анализа")
            .setContentText("Доступна версия v${info.version} (${info.size} записей)")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "Регулярное обновление словарей позволяет выявлять больше распространённых паролей"
                )
            )
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)

        try {
            NotificationManagerCompat.from(this).notify(7301, builder.build())
        } catch (_: SecurityException) {
            // ignored on missing notification permission
        }
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)

        // Канал трекинга — уведомление всегда видно пока служба активна
        NotificationChannel(
            CHANNEL_TRACKING,
            "Трекинг дежурства",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Показывает статус активного GPS-трекинга"
            nm.createNotificationChannel(this)
        }

        // Канал SOS — высокий приоритет
        NotificationChannel(
            CHANNEL_SOS,
            "SOS / Экстренный вызов",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Уведомления об экстренных вызовах"
            nm.createNotificationChannel(this)
        }
    }

    companion object {
        @Volatile
        private var _db: AppDatabase? = null

        fun isDbUnlocked(): Boolean = _db != null

        val db: AppDatabase
            get() = _db ?: error("Database is locked. Authenticate user first.")

        @Synchronized
        fun unlockDatabase(ctx: Context): Boolean {
            if (_db != null) return true

            val hwStore = HardwareKeyStore(ctx)
            val dbPassphrase = hwStore.getOrCreateProtectedDbPassphrase().toByteArray()
            val factory = SupportFactory(dbPassphrase)

            _db = Room.databaseBuilder(
                ctx.applicationContext,
                AppDatabase::class.java,
                "dutytracker_secure.db",
            )
                .openHelperFactory(factory)
                .fallbackToDestructiveMigration()
                .build()

            dbPassphrase.fill(0)
            return true
        }

        const val CHANNEL_TRACKING = "dutytracker_tracking"
        const val CHANNEL_SOS      = "dutytracker_sos"
    }
}