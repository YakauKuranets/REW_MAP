package com.mapv12.dutytracker

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityComposeTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun dashboardShowsCoordinates() {
        val ctx = composeRule.activity
        StatusStore.setLastLatLon(ctx, 53.900001, 27.560001)

        composeRule.waitForIdle()
        composeRule.onNodeWithTag("dashboard_coordinates").assertIsDisplayed()
    }
}
