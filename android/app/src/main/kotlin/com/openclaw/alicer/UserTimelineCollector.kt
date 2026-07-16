package com.openclaw.alicer

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import androidx.core.content.ContextCompat

object UserTimelineCollector {
    fun collect(context: Context, args: Map<*, *>?): List<Map<String, Any?>> {
        val signals = args?.get("signals") as? Map<*, *> ?: args ?: emptyMap<Any, Any>()
        val now = System.currentTimeMillis() / 1000.0
        val events = mutableListOf<Map<String, Any?>>()
        if (signals["device"] != false) {
            headsetEvent(context, now)?.let(events::add)
        }
        if (signals["music"] != false) {
            UserTimelineNotificationListener.latestMediaEvent(now)?.let(events::add)
        }
        if (signals["location"] != false) {
            locationEvents(context, now, signals["motion"] != false).let(events::addAll)
        }
        return events
    }

    private fun headsetEvent(context: Context, now: Double): Map<String, Any?>? {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return null
        val connected = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any {
                it.type == AudioDeviceInfo.TYPE_WIRED_HEADPHONES ||
                    it.type == AudioDeviceInfo.TYPE_WIRED_HEADSET ||
                    it.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP ||
                    it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    it.type == AudioDeviceInfo.TYPE_USB_HEADSET
            }
        } else {
            @Suppress("DEPRECATION")
            audioManager.isWiredHeadsetOn || BluetoothAdapter.getDefaultAdapter()?.isEnabled == true
        }
        return mapOf(
            "eventTime" to now,
            "source" to "android",
            "eventType" to "device_headset",
            "title" to "耳机状态",
            "summary" to if (connected) "耳机已连接" else "耳机未连接",
            "confidence" to 0.82,
            "privacyLevel" to "context",
            "metadata" to mapOf("connected" to connected),
        )
    }

    private fun locationEvents(context: Context, now: Double, includeMotion: Boolean): List<Map<String, Any?>> {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) return emptyList()
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return emptyList()
        val location = bestLastKnownLocation(manager) ?: return emptyList()
        val locationEvent = mapOf(
            "eventTime" to now,
            "source" to "android",
            "eventType" to "location_snapshot",
            "title" to "后台位置快照",
            "summary" to "手机在后台更新了一次低频位置。",
            "confidence" to 0.68,
            "privacyLevel" to "context",
            "metadata" to mapOf(
                "label" to "当前位置",
                "latitude" to "%.4f".format(location.latitude).toDouble(),
                "longitude" to "%.4f".format(location.longitude).toDouble(),
                "accuracy" to location.accuracy,
                "provider" to location.provider,
            ),
        )
        if (!includeMotion) return listOf(locationEvent)
        return listOf(locationEvent, motionEvent(location, now))
    }

    private fun motionEvent(location: Location, now: Double): Map<String, Any?> {
        val speed = if (location.hasSpeed()) location.speed else 0f
        val activity = when {
            speed >= 7.0f -> "in_vehicle"
            speed >= 1.2f -> "walking"
            else -> "still"
        }
        val summary = when (activity) {
            "in_vehicle" -> "位置速度显示可能在通勤或移动中"
            "walking" -> "位置速度显示可能在步行"
            else -> "位置速度显示当前较稳定"
        }
        return mapOf(
            "eventTime" to now,
            "source" to "android",
            "eventType" to "motion_detected",
            "title" to "运动状态变化",
            "summary" to summary,
            "confidence" to if (location.hasSpeed()) 0.62 else 0.42,
            "privacyLevel" to "context",
            "metadata" to mapOf("activity" to activity, "speed" to speed),
        )
    }

    private fun bestLastKnownLocation(manager: LocationManager): Location? {
        return manager.getProviders(true).mapNotNull { provider ->
            try {
                manager.getLastKnownLocation(provider)
            } catch (_: SecurityException) {
                null
            }
        }.maxByOrNull { it.time }
    }
}
