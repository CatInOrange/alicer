package com.openclaw.alicer

import android.content.ComponentName
import android.content.Context
import android.app.Notification
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

class UserTimelineNotificationListener : NotificationListenerService() {
    override fun onListenerConnected() {
        instance = this
        refreshFromActiveNotifications()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        rememberIfMedia(sbn)
    }

    private fun refreshFromActiveNotifications() {
        try {
            activeNotifications
                ?.sortedByDescending { it.postTime }
                ?.forEach { rememberIfMedia(it) }
        } catch (_: SecurityException) {
        } catch (_: RuntimeException) {
        }
    }

    private fun rememberIfMedia(sbn: StatusBarNotification?) {
        val notification = sbn?.notification ?: return
        if (!looksLikeMedia(sbn.packageName, notification.category)) return
        val title = notification.extras
            ?.getCharSequence("android.title")
            ?.toString()
            ?.trim()
            .orEmpty()
        val text = listOf("android.text", "android.subText", "android.infoText")
            .mapNotNull { notification.extras?.getCharSequence(it)?.toString()?.trim() }
            .firstOrNull { it.isNotBlank() }
            .orEmpty()
        if (title.isBlank() && text.isBlank()) return
        latestTitle = title
        latestArtist = text
        latestPackage = sbn.packageName
        latestAt = System.currentTimeMillis()
    }

    companion object {
        private var instance: UserTimelineNotificationListener? = null
        private var latestTitle: String = ""
        private var latestArtist: String = ""
        private var latestPackage: String = ""
        private var latestAt: Long = 0L

        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                "enabled_notification_listeners",
            ) ?: return false
            val component = ComponentName(context, UserTimelineNotificationListener::class.java)
            return enabled.split(":").any { it.equals(component.flattenToString(), ignoreCase = true) }
        }

        fun latestMediaEvent(now: Double): Map<String, Any?>? {
            instance?.refreshFromActiveNotifications()
            if (latestTitle.isBlank()) return null
            if (System.currentTimeMillis() - latestAt > 6 * 3600 * 1000) return null
            return mapOf(
                "eventTime" to now,
                "source" to "android",
                "eventType" to "music_playing",
                "title" to latestTitle,
                "summary" to listOf("正在听歌", latestTitle, latestArtist)
                    .filter { it.isNotBlank() }
                    .joinToString(" · "),
                "confidence" to 0.7,
                "privacyLevel" to "context",
                "metadata" to mapOf(
                    "title" to latestTitle,
                    "artist" to latestArtist,
                    "package" to latestPackage,
                ),
            )
        }

        private fun looksLikeMedia(packageName: String, category: String?): Boolean {
            if (category == Notification.CATEGORY_TRANSPORT) return true
            val lower = packageName.lowercase()
            return listOf("music", "spotify", "netease", "qqmusic", "kugou", "kuwo", "apple")
                .any { lower.contains(it) }
        }
    }
}
