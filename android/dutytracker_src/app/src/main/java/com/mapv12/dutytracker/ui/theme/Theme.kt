package com.mapv12.dutytracker.ui.theme

import android.app.Activity
import androidx.compose.foundation.shape.CutCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat

private val CyberpunkColorScheme = darkColorScheme(
    primary = NeonCyan,
    onPrimary = CyberBlack,
    primaryContainer = NeonCyanDim,
    secondary = CrimsonRed,
    onSecondary = TextWhite,
    background = CyberBlack,
    surface = CyberDarkGray,
    onBackground = NeonCyan,
    onSurface = TextWhite,
    error = CrimsonRed,
    onError = CyberBlack,
    outline = NeonCyan
)

// Агрессивные рубленые формы вместо закругленных углов
val CyberShapes = Shapes(
    small = CutCornerShape(topStart = 8.dp, bottomEnd = 8.dp), // Срезанные углы для кнопок
    medium = CutCornerShape(topStart = 12.dp, bottomEnd = 12.dp), // Для карточек
    large = CutCornerShape(0.dp) // Жесткие прямые углы для панелей
)

@Composable
fun DutyTrackerTheme(
    // Принудительно игнорируем светлую тему ОС, всегда используем темную
    darkTheme: Boolean = true,
    content: @Composable () -> Unit
) {
    val colorScheme = CyberpunkColorScheme
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.background.toArgb()
            window.navigationBarColor = colorScheme.background.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        shapes = CyberShapes,
        content = content
    )
}
