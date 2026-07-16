package com.openclaw.alicer

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class UserTimelineWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (!prefs.getBoolean("enabled", false)) return Result.success()
        val baseUrl = prefs.getString("baseUrl", "").orEmpty().trimEnd('/')
        if (baseUrl.isBlank()) return Result.retry()
        val signals = JSONObject(prefs.getString("signals", "{}") ?: "{}").toMap()
        val events = UserTimelineCollector.collect(applicationContext, mapOf("signals" to signals))
        if (events.isEmpty()) return Result.success()
        return try {
            postEvents(
                baseUrl = baseUrl,
                settings = JSONObject(prefs.getString("settings", "{}") ?: "{}"),
                events = events,
            )
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    private fun postEvents(baseUrl: String, settings: JSONObject, events: List<Map<String, Any?>>) {
        val url = URL("$baseUrl/api/user/timeline/events")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10000
            readTimeout = 20000
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json")
        }
        val body = JSONObject()
            .put("settings", settings)
            .put("events", JSONArray(events.map { JSONObject(it) }))
            .toString()
        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { it.write(body) }
        if (connection.responseCode !in 200..299) {
            throw IllegalStateException("Timeline sync failed: ${connection.responseCode}")
        }
        connection.disconnect()
    }

    companion object {
        const val PREFS = "user_timeline"
        const val WORK_NAME = "user_timeline_background_sync"
    }
}

private fun JSONObject.toMap(): Map<String, Any?> {
    val result = mutableMapOf<String, Any?>()
    val keys = keys()
    while (keys.hasNext()) {
        val key = keys.next()
        result[key] = when (val value = get(key)) {
            is JSONObject -> value.toMap()
            else -> value
        }
    }
    return result
}
