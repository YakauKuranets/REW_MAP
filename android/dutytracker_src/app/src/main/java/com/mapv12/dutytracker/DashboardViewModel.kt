package com.mapv12.dutytracker

import android.annotation.SuppressLint
import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import kotlin.coroutines.resume

sealed class SosUiEvent {
    data class ShowToast(val message: String) : SosUiEvent()
    object FallbackMesh : SosUiEvent()
}

class DashboardViewModel(application: Application) : AndroidViewModel(application) {

    private val appContext = application.applicationContext
    private val apiClient = ApiClient(appContext)
    private val meshManager = MeshNetworkManager(appContext)

    private val _events = MutableSharedFlow<SosUiEvent>(extraBufferCapacity = 4, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val events: SharedFlow<SosUiEvent> = _events

    init {
        meshManager.startMesh()
    }

    fun onSosClicked() {
        viewModelScope.launch {
            val (lat, lon) = getCurrentCoordinates() ?: StatusStore.getLastLatLon(appContext) ?: (0.0 to 0.0)
            val hasInternet = isInternetAvailable()

            val sentOnline = if (hasInternet) {
                try {
                    apiClient.sos(lat, lon, null, null).ok
                } catch (_: Exception) {
                    false
                }
            } else {
                false
            }

            if (!sentOnline) {
                val emergency = JSONObject()
                    .put("type", "SOS")
                    .put("agent_id", SessionStore.getSessionId(appContext) ?: "unknown_agent")
                    .put("lat", lat)
                    .put("lon", lon)
                    .put("ttl", 3)

                meshManager.broadcastEmergency(emergency.toString())
                _events.tryEmit(SosUiEvent.FallbackMesh)
                _events.tryEmit(SosUiEvent.ShowToast("Сеть недоступна. Отправлено через Mesh-сеть"))
            }
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun getCurrentCoordinates(): Pair<Double, Double>? {
        val fused = LocationServices.getFusedLocationProviderClient(appContext)
        val cts = CancellationTokenSource()
        return suspendCancellableCoroutine { cont ->
            fused.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, cts.token)
                .addOnSuccessListener { location ->
                    if (location == null) cont.resume(null)
                    else cont.resume(location.latitude to location.longitude)
                }
                .addOnFailureListener {
                    cont.resume(null)
                }
            cont.invokeOnCancellation { cts.cancel() }
        }
    }

    private fun isInternetAvailable(): Boolean {
        val cm = appContext.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val network = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    override fun onCleared() {
        meshManager.stopAll()
        super.onCleared()
    }
}
