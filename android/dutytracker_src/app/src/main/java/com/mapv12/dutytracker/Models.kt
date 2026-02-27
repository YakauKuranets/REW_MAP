package com.mapv12.dutytracker

data class PairResult(
    val ok: Boolean,
    val deviceToken: String?,
    val deviceId: String?,
    val userId: String?,
    val label: String?,
    val error: String? = null
)

data class BootstrapResult(
    val ok: Boolean,
    val baseUrl: String?,
    val pairCode: String?,
    val label: String?,
    val error: String? = null
)

data class StartResult(
    val ok: Boolean,
    val sessionId: String?,
    val shiftId: String?,
    val userId: String?,
    val error: String? = null
)

data class SosResult(
    val ok: Boolean,
    val sosId: String?,
    val error: String? = null
)

data class DeviceHealthPayload(
    val batteryPct: Int?,
    val isCharging: Boolean?,
    val net: String?,
    val gps: String?,
    val accuracyM: Double?,
    val queueSize: Int?,
    val trackingOn: Boolean?,
    val lastSendAtIso: String?,
    val lastError: String?,
    val appVersion: String?,
    val deviceModel: String?,
    val osVersion: String?,
    val extra: org.json.JSONObject? = null
)
