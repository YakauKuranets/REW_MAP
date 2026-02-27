package com.mapv12.dutytracker

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomFlowIntegrationTest {

    private lateinit var db: AppDatabase

    @Before
    fun setup() {
        db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            AppDatabase::class.java
        ).allowMainThreadQueries().build()
    }

    @After
    fun tearDown() {
        db.close()
    }

    @Test
    fun trackPointFlowEmitsAfterInsert() = runBlocking {
        val dao = db.trackPointDao()

        dao.insert(
            TrackPointEntity(
                sessionId = "s-1",
                tsEpochMs = System.currentTimeMillis(),
                lat = 53.9,
                lon = 27.56,
                accuracyM = 8.0,
                speedMps = 0.0,
                bearingDeg = 0.0
            )
        )

        val emitted = dao.observeSince(0L).first()
        assertEquals(1, emitted.size)
        assertEquals(53.9, emitted.first().lat, 0.00001)
    }
}
