package com.openclaw.alicer

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.openclaw.alicer/user_timeline"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "collectSnapshot" -> result.success(UserTimelineCollector.collect(this, call.arguments as? Map<*, *>))
                "configureBackground" -> {
                    configureBackground(call.arguments as? Map<*, *>)
                    result.success(null)
                }
                "requestPermissions" -> result.success(requestTimelinePermissions(call.arguments as? Map<*, *>))
                else -> result.notImplemented()
            }
        }
    }

    private fun configureBackground(args: Map<*, *>?) {
        val enabled = args?.get("enabled") as? Boolean ?: false
        val prefs = getSharedPreferences(UserTimelineWorker.PREFS, MODE_PRIVATE)
        val editor = prefs.edit().putBoolean("enabled", enabled)
        editor.putString("baseUrl", args?.get("baseUrl")?.toString().orEmpty())
        editor.putString("settings", JSONObject(args?.get("settings") as? Map<*, *> ?: emptyMap<Any, Any>()).toString())
        editor.putString("signals", JSONObject(args?.get("signals") as? Map<*, *> ?: emptyMap<Any, Any>()).toString())
        editor.apply()

        val manager = WorkManager.getInstance(this)
        if (!enabled) {
            manager.cancelUniqueWork(UserTimelineWorker.WORK_NAME)
            return
        }
        val interval = ((args?.get("intervalMinutes") as? Number)?.toLong() ?: 30L).coerceIn(15L, 180L)
        val request = PeriodicWorkRequestBuilder<UserTimelineWorker>(interval, TimeUnit.MINUTES).build()
        manager.enqueueUniquePeriodicWork(
            UserTimelineWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    private fun requestTimelinePermissions(args: Map<*, *>?): Map<String, List<String>> {
        val requested = mutableListOf<String>()
        if (args?.get("location") != false) {
            requested += Manifest.permission.ACCESS_COARSE_LOCATION
            requested += Manifest.permission.ACCESS_FINE_LOCATION
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                requested += Manifest.permission.ACCESS_BACKGROUND_LOCATION
            }
        }
        if (args?.get("motion") != false && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            requested += Manifest.permission.ACTIVITY_RECOGNITION
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requested += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = requested.distinct().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 7103)
        }
        val pending = mutableListOf<String>()
        if (args?.get("music") != false && !UserTimelineNotificationListener.isEnabled(this)) {
            pending += "通知访问（音乐状态）"
        }
        if (args?.get("appUsage") == true) {
            pending += "使用情况访问（App 类别）"
        }
        return mapOf(
            "granted" to requested.distinct().filter {
                ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
            },
            "pending" to pending,
        )
    }
}
