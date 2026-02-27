package com.mapv12.dutytracker

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.mapv12.dutytracker.security.BiometricGatekeeper
import com.mapv12.dutytracker.ui.theme.DutyTrackerTheme
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.withContext

private enum class MainTab { DASHBOARD, MAP, CHAT }

class MainActivity : AppCompatActivity() {

    private fun startTrackerService() {
        LocationService.setTrackingOn(this, true)
        val intent = Intent(this, LocationService::class.java).apply { action = LocationService.ACTION_START }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ContextCompat.startForegroundService(this, intent)
        } else {
            startService(intent)
        }
    }

    private fun stopTrackerService() {
        LocationService.setTrackingOn(this, false)
        val intent = Intent(this, LocationService::class.java).apply { action = LocationService.ACTION_STOP }
        stopService(intent)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WatchdogWorker.ensureScheduled(this)

        val gatekeeper = BiometricGatekeeper(this)
        gatekeeper.authenticate(
            onSuccess = {
                runCatching { App.unlockDatabase(applicationContext) }
                    .onSuccess {
                        setContent {
                            DutyTrackerTheme {
                                TacticalTerminalApp(
                                    onStartTracking = { startTrackerService() },
                                    onStopTracking = { stopTrackerService() },
                                )
                            }
                        }
                    }
                    .onFailure {
                        Toast.makeText(this, "Не удалось открыть защищенную БД", Toast.LENGTH_LONG).show()
                        finish()
                    }
            },
            onFail = {
                Toast.makeText(this, "Биометрическая авторизация обязательна", Toast.LENGTH_LONG).show()
                finish()
            },
        )
    }
}

@Composable
private fun TacticalTerminalApp(onStartTracking: () -> Unit, onStopTracking: () -> Unit) {
    var activeTab by remember { mutableStateOf(MainTab.DASHBOARD) }
    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = activeTab == MainTab.DASHBOARD, onClick = { activeTab = MainTab.DASHBOARD }, label = { Text("Dashboard") }, icon = { Text("🏠") })
                NavigationBarItem(selected = activeTab == MainTab.MAP, onClick = { activeTab = MainTab.MAP }, label = { Text("Map") }, icon = { Text("🗺️") })
                NavigationBarItem(selected = activeTab == MainTab.CHAT, onClick = { activeTab = MainTab.CHAT }, label = { Text("Chat") }, icon = { Text("💬") })
            }
        }
    ) { paddings ->
        when (activeTab) {
            MainTab.DASHBOARD -> DashboardScreen(Modifier.padding(paddings), onStartTracking, onStopTracking)
            MainTab.MAP -> MapScreen(Modifier.padding(paddings))
            MainTab.CHAT -> ChatScreen(Modifier.padding(paddings))
        }
    }
}

@Composable
fun DashboardScreen(modifier: Modifier = Modifier, onStartTracking: () -> Unit, onStopTracking: () -> Unit, vm: DashboardViewModel = viewModel()) {
    val ctx = LocalContext.current
    val haptics = LocalHapticFeedback.current
    var coords by remember { mutableStateOf("—") }

    val requiredPermissions = remember {
        buildList {
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_SCAN)
                add(Manifest.permission.BLUETOOTH_ADVERTISE)
                add(Manifest.permission.BLUETOOTH_CONNECT)
                add(Manifest.permission.NEARBY_WIFI_DEVICES)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.toTypedArray()
    }

    fun allPermissionsGranted(context: Context): Boolean = requiredPermissions.all {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants ->
        val granted = grants.values.all { it }
        if (granted || allPermissionsGranted(ctx)) {
            onStartTracking()
        } else {
            Toast.makeText(ctx, "Нужны разрешения: локация, Bluetooth/Wi‑Fi Nearby и уведомления", Toast.LENGTH_LONG).show()
        }
    }

    fun requestRadarPermissionsAndStart() {
        if (allPermissionsGranted(ctx)) {
            onStartTracking()
        } else {
            permissionLauncher.launch(requiredPermissions)
        }
    }

    val scannerPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            ctx.startActivity(Intent(ctx, ScannerActivity::class.java))
        } else {
            Toast.makeText(ctx, "Нужно разрешение на камеру для сканера", Toast.LENGTH_LONG).show()
        }
    }

    fun openScanner() {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            ctx.startActivity(Intent(ctx, ScannerActivity::class.java))
        } else {
            scannerPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    LaunchedEffect(Unit) {
        coords = withContext(Dispatchers.IO) {
            val last = StatusStore.getLastLatLon(ctx)
            if (last == null) "—" else "%.6f, %.6f".format(last.first, last.second)
        }
    }

    LaunchedEffect(vm) {
        vm.events.collect { event ->
            when (event) {
                is SosUiEvent.ShowToast -> Toast.makeText(ctx, event.message, Toast.LENGTH_LONG).show()
                SosUiEvent.FallbackMesh -> haptics.performHapticFeedback(HapticFeedbackType.LongPress)
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.Top,
    ) {
        Text("Мобильный тактический терминал", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(12.dp))
        Text("Текущие координаты:", style = MaterialTheme.typography.titleMedium)
        Text(coords, modifier = Modifier.testTag("dashboard_coordinates"), style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            Button(onClick = { requestRadarPermissionsAndStart() }, modifier = Modifier.weight(1f)) {
                Text("🟢 Начать патруль")
            }
            Button(onClick = onStopTracking, modifier = Modifier.weight(1f)) {
                Text("🔴 Закончить")
            }
        }

        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { openScanner() },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("👁️ Сканер")
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.onSosClicked() },
            colors = ButtonDefaults.buttonColors(containerColor = androidx.compose.ui.graphics.Color(0xFFB71C1C)),
            modifier = Modifier
                .fillMaxWidth()
                .height(72.dp)
        ) {
            Text("SOS", style = MaterialTheme.typography.headlineSmall)
        }
    }
}

@Composable
fun MapScreen(modifier: Modifier = Modifier) {
    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text("MapScreen", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text("3D карта и тактические слои подключаются к backend через Postgres/Redis pipeline.")
    }
}

@Composable
fun ChatScreen(modifier: Modifier = Modifier) {
    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text("ChatScreen", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text("Оперативный чат с командным центром работает по WebSocket без FCM.")
    }
}
