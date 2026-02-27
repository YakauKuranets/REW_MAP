package com.mapv12.dutytracker

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.util.Log
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

class MeshNetworkManager(
    private val context: Context,
    userId: String = "${Build.MODEL}_${Build.ID}",
) {

    val connectionsClient: ConnectionsClient = Nearby.getConnectionsClient(context)

    private val STRATEGY = Strategy.P2P_CLUSTER // MESH-топология (каждый с каждым)
    private val serviceId = "com.agency.v4.mesh"
    private val endpointName = userId
    private val managerScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val connectedEndpoints = ConcurrentHashMap.newKeySet<String>()
    private val authenticatedEndpoints = ConcurrentHashMap.newKeySet<String>()

    // Секретный ключ Роя (в проде должен прилетать с сервера и храниться в Keystore)
    private val MESH_PRE_SHARED_KEY = "AGENCY_V4_BLACK_PROTOCOL"

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            if (payload.type != Payload.Type.BYTES) return
            val rawData = payload.asBytes()?.toString(Charsets.UTF_8) ?: return

            val packet = try {
                JSONObject(rawData)
            } catch (e: Exception) {
                Log.w("MeshNetwork", "Invalid JSON payload from $endpointId", e)
                return
            }

            if (packet.optString("type") == "AUTH_HANDSHAKE") {
                if (packet.optString("psk") == MESH_PRE_SHARED_KEY) {
                    authenticatedEndpoints.add(endpointId)
                    Log.i("MeshNetwork", "Узел $endpointId успешно авторизован в Рое.")
                } else {
                    Log.e("MeshNetwork", "Узел $endpointId провалил авторизацию! Разрыв связи.")
                    connectionsClient.disconnectFromEndpoint(endpointId)
                }
                return
            }

            if (!authenticatedEndpoints.contains(endpointId)) {
                Log.w("MeshNetwork", "Блокировка пакета от неавторизованного узла $endpointId")
                return
            }

            val ttl = packet.optInt("ttl", 0)
            if (ttl <= 0) {
                Log.d("MeshNetwork", "Drop packet from $endpointId because ttl=$ttl")
                return
            }
            packet.put("ttl", ttl - 1)

            managerScope.launch {
                if (isInternetAvailable()) {
                    ApiClient(context).relayMeshPayload(packet)
                } else {
                    relayToOtherPeers(packet, endpointId)
                }
            }
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) = Unit
    }

    private val connectionLifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, connectionInfo: ConnectionInfo) {
            Log.w("MeshNetwork", "Входящее соединение от $endpointId. Выполняю крипто-проверку...")
            connectionsClient.acceptConnection(endpointId, payloadCallback)
        }

        override fun onConnectionResult(endpointId: String, result: ConnectionResolution) {
            if (result.status.isSuccess) {
                Log.i("MeshNetwork", "Узел $endpointId предварительно подтвержден.")
                connectedEndpoints.add(endpointId)

                val authPacket = JSONObject().apply {
                    put("type", "AUTH_HANDSHAKE")
                    put("psk", MESH_PRE_SHARED_KEY)
                }
                connectionsClient.sendPayload(
                    endpointId,
                    Payload.fromBytes(authPacket.toString().toByteArray(Charsets.UTF_8))
                )
            } else {
                Log.e("MeshNetwork", "Отказ в соединении узлу $endpointId")
            }
        }

        override fun onDisconnected(endpointId: String) {
            connectedEndpoints.remove(endpointId)
            authenticatedEndpoints.remove(endpointId)
        }
    }

    fun startMesh() {
        startAdvertising()
        startDiscovery()
    }

    fun startAdvertising() {
        val options = AdvertisingOptions.Builder().setStrategy(STRATEGY).build()
        connectionsClient.startAdvertising(endpointName, serviceId, connectionLifecycleCallback, options)
    }

    fun startDiscovery() {
        val options = DiscoveryOptions.Builder().setStrategy(STRATEGY).build()
        connectionsClient.startDiscovery(
            serviceId,
            object : EndpointDiscoveryCallback() {
                override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
                    connectionsClient.requestConnection(endpointName, endpointId, connectionLifecycleCallback)
                }

                override fun onEndpointLost(endpointId: String) = Unit
            },
            options
        )
    }

    fun broadcastEmergency(jsonPayload: String): Boolean {
        val targets = connectedEndpoints.toList()
        if (targets.isEmpty()) return false
        val payload = Payload.fromBytes(jsonPayload.toByteArray(Charsets.UTF_8))
        connectionsClient.sendPayload(targets, payload)
        return true
    }

    private fun isInternetAvailable(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val network = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun relayToOtherPeers(packet: JSONObject, sourceEndpointId: String) {
        val relayTargets = connectedEndpoints.filter { it != sourceEndpointId }
        if (relayTargets.isEmpty()) return

        val payload = Payload.fromBytes(packet.toString().toByteArray(Charsets.UTF_8))
        connectionsClient.sendPayload(relayTargets, payload)
    }

    fun stopAll() {
        connectionsClient.stopAdvertising()
        connectionsClient.stopDiscovery()
        connectionsClient.stopAllEndpoints()
        connectedEndpoints.clear()
        authenticatedEndpoints.clear()
    }

    fun restartMesh() {
        stopAll()
        startAdvertising()
        startDiscovery()
    }
}
