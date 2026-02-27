package com.mapv12.dutytracker

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.mapv12.dutytracker.ui.theme.DutyTrackerTheme

class MapActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            DutyTrackerTheme {
                MapScreen()
            }
        }
    }
}
