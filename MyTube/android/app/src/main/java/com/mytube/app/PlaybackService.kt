package com.mytube.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

data class PlaybackInfo(
    val playing: Boolean,
    val title: String,
    val artist: String,
    val artworkUrl: String,
    val positionSec: Double,
    val durationSec: Double,
    val rate: Double,
    /** True when the web player has a queue, so previous/next track controls apply. */
    val canSkip: Boolean,
)

/**
 * Foreground media service that keeps the process (and the WebView's audio) alive while the
 * screen is off or another app is in front, and exposes lock-screen / Bluetooth controls.
 * All companion methods must be called on the main thread.
 */
class PlaybackService : Service() {

    companion object {
        private const val TAG = "MyTubePlayback"
        private const val CHANNEL_ID = "playback"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_PLAY = "com.mytube.app.action.PLAY"
        private const val ACTION_PAUSE = "com.mytube.app.action.PAUSE"
        private const val ACTION_REWIND = "com.mytube.app.action.REWIND"
        private const val ACTION_FORWARD = "com.mytube.app.action.FORWARD"
        private const val ACTION_PREVIOUS = "com.mytube.app.action.PREVIOUS"
        private const val ACTION_NEXT = "com.mytube.app.action.NEXT"
        private const val CUSTOM_SKIP_BACK = "skip_back"
        private const val CUSTOM_SKIP_FORWARD = "skip_forward"
        private const val WAKE_LOCK_TIMEOUT_MS = 6L * 60 * 60 * 1000
        private const val SESSION_ACTIONS =
            PlaybackStateCompat.ACTION_PLAY or PlaybackStateCompat.ACTION_PAUSE or
                PlaybackStateCompat.ACTION_PLAY_PAUSE or PlaybackStateCompat.ACTION_SEEK_TO or
                PlaybackStateCompat.ACTION_REWIND or PlaybackStateCompat.ACTION_FAST_FORWARD or
                PlaybackStateCompat.ACTION_STOP
        private const val QUEUE_ACTIONS =
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS or PlaybackStateCompat.ACTION_SKIP_TO_NEXT

        /** Receives (command, argument) to forward into the web player. */
        var commandListener: ((String, Double) -> Unit)? = null

        private var instance: PlaybackService? = null
        private var pendingInfo: PlaybackInfo? = null

        fun update(context: Context, info: PlaybackInfo) {
            instance?.let {
                it.apply(info)
                return
            }
            if (!info.playing) return
            pendingInfo = info
            try {
                ContextCompat.startForegroundService(context, Intent(context, PlaybackService::class.java))
            } catch (e: Exception) {
                // Android 12+ refuses to start a foreground service while the app is in the background.
                Log.w(TAG, "Could not start playback service", e)
                pendingInfo = null
            }
        }

        fun stop() {
            pendingInfo = null
            instance?.shutdown()
        }
    }

    private lateinit var session: MediaSessionCompat
    private lateinit var wakeLock: PowerManager.WakeLock
    private lateinit var wifiLock: WifiManager.WifiLock
    private val mainHandler = Handler(Looper.getMainLooper())
    private val defaultArtwork: Bitmap? by lazy { BitmapFactory.decodeResource(resources, R.drawable.artwork_default) }
    private var current: PlaybackInfo? = null
    private var isForeground = false
    private var artwork: Bitmap? = null
    private var artworkUrl: String? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createChannel()

        session = MediaSessionCompat(this, "MyTube").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() = dispatch("play")
                override fun onPause() = dispatch("pause")
                override fun onStop() = dispatch("pause")
                override fun onRewind() = dispatch("seekbackward")
                override fun onFastForward() = dispatch("seekforward")
                override fun onSkipToPrevious() = dispatch("previous")
                override fun onSkipToNext() = dispatch("next")
                override fun onCustomAction(action: String?, extras: Bundle?) {
                    when (action) {
                        CUSTOM_SKIP_BACK -> dispatch("seekbackward")
                        CUSTOM_SKIP_FORWARD -> dispatch("seekforward")
                    }
                }
                override fun onSeekTo(pos: Long) = dispatch("seekto", pos / 1000.0)
            })
        }

        wakeLock = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MyTube:playback")
            .apply { setReferenceCounted(false) }
        @Suppress("DEPRECATION")
        wifiLock = (applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "MyTube:playback")
            .apply { setReferenceCounted(false) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        instance = this
        when (intent?.action) {
            ACTION_PLAY -> dispatch("play")
            ACTION_PAUSE -> dispatch("pause")
            ACTION_REWIND -> dispatch("seekbackward")
            ACTION_FORWARD -> dispatch("seekforward")
            ACTION_PREVIOUS -> dispatch("previous")
            ACTION_NEXT -> dispatch("next")
            else -> {
                val info = pendingInfo ?: current
                pendingInfo = null
                if (info != null) apply(info) else shutdown()
            }
        }
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        shutdown()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        releaseLocks()
        session.isActive = false
        session.release()
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun dispatch(command: String, arg: Double = 0.0) {
        commandListener?.invoke(command, arg)
    }

    private fun apply(info: PlaybackInfo) {
        current = info
        session.isActive = true

        val durationMs = if (info.durationSec.isFinite() && info.durationSec > 0) (info.durationSec * 1000).toLong() else -1L
        val positionMs = if (info.positionSec.isFinite() && info.positionSec > 0) (info.positionSec * 1000).toLong() else 0L
        val rate = if (info.rate.isFinite() && info.rate > 0) info.rate.toFloat() else 1f

        session.setMetadata(
            MediaMetadataCompat.Builder()
                .putString(MediaMetadataCompat.METADATA_KEY_TITLE, info.title)
                .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, info.artist)
                .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, getString(R.string.app_name))
                .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, durationMs)
                .putBitmap(MediaMetadataCompat.METADATA_KEY_ART, artwork ?: defaultArtwork)
                .build()
        )
        session.setPlaybackState(
            PlaybackStateCompat.Builder()
                .setActions(SESSION_ACTIONS or if (info.canSkip) QUEUE_ACTIONS else 0L)
                .addCustomAction(
                    PlaybackStateCompat.CustomAction.Builder(CUSTOM_SKIP_BACK, getString(R.string.rewind), R.drawable.ic_rewind).build()
                )
                .addCustomAction(
                    PlaybackStateCompat.CustomAction.Builder(CUSTOM_SKIP_FORWARD, getString(R.string.forward), R.drawable.ic_forward).build()
                )
                .setState(
                    if (info.playing) PlaybackStateCompat.STATE_PLAYING else PlaybackStateCompat.STATE_PAUSED,
                    positionMs,
                    if (info.playing) rate else 0f,
                )
                .build()
        )

        val notification = buildNotification(info)
        if (!isForeground) {
            val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
            isForeground = true
        } else {
            try {
                NotificationManagerCompat.from(this).notify(NOTIFICATION_ID, notification)
            } catch (e: SecurityException) {
                // Notification permission denied; the service keeps running without a visible update.
            }
        }

        if (info.playing) acquireLocks() else releaseLocks()
        loadArtwork(info.artworkUrl)
    }

    private fun shutdown() {
        current = null
        releaseLocks()
        session.isActive = false
        if (isForeground) {
            ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
            isForeground = false
        }
        if (instance === this) instance = null
        stopSelf()
    }

    private fun acquireLocks() {
        if (!wakeLock.isHeld) wakeLock.acquire(WAKE_LOCK_TIMEOUT_MS)
        if (!wifiLock.isHeld) wifiLock.acquire()
    }

    private fun releaseLocks() {
        if (wakeLock.isHeld) wakeLock.release()
        if (wifiLock.isHeld) wifiLock.release()
    }

    private fun buildNotification(info: PlaybackInfo): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val playPause = if (info.playing) {
            action(R.drawable.ic_pause, R.string.pause, ACTION_PAUSE, 2)
        } else {
            action(R.drawable.ic_play, R.string.play, ACTION_PLAY, 1)
        }

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(info.title.ifBlank { getString(R.string.app_name) })
            .setContentText(info.artist)
            .setLargeIcon(artwork ?: defaultArtwork)
            .setContentIntent(openApp)
            .setOngoing(info.playing)
            .setSilent(true)
            .setShowWhen(false)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        if (info.canSkip) {
            builder
                .addAction(action(R.drawable.ic_skip_previous, R.string.previous, ACTION_PREVIOUS, 5))
                .addAction(playPause)
                .addAction(action(R.drawable.ic_skip_next, R.string.next, ACTION_NEXT, 6))
        } else {
            builder
                .addAction(action(R.drawable.ic_rewind, R.string.rewind, ACTION_REWIND, 3))
                .addAction(playPause)
                .addAction(action(R.drawable.ic_forward, R.string.forward, ACTION_FORWARD, 4))
        }

        return builder
            .setStyle(
                androidx.media.app.NotificationCompat.MediaStyle()
                    .setMediaSession(session.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2)
            )
            .build()
    }

    private fun action(icon: Int, label: Int, action: String, requestCode: Int): NotificationCompat.Action {
        val intent = PendingIntent.getService(
            this, requestCode,
            Intent(this, PlaybackService::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Action(icon, getString(label), intent)
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(CHANNEL_ID, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW).apply {
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun loadArtwork(url: String) {
        if (url == artworkUrl) return
        artworkUrl = url
        artwork = null
        if (!url.startsWith("http://") && !url.startsWith("https://")) return

        thread(name = "MyTubeArtwork", isDaemon = true) {
            val bitmap = try {
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.connectTimeout = 5000
                connection.readTimeout = 10000
                try {
                    connection.inputStream.use { BitmapFactory.decodeStream(it) }?.let { scaleDown(it, 512) }
                } finally {
                    connection.disconnect()
                }
            } catch (e: Exception) {
                Log.w(TAG, "Artwork load failed", e)
                null
            }
            mainHandler.post {
                val info = current
                if (bitmap != null && artworkUrl == url && info != null) {
                    artwork = bitmap
                    apply(info)
                }
            }
        }
    }

    private fun scaleDown(bitmap: Bitmap, maxSize: Int): Bitmap {
        val largest = maxOf(bitmap.width, bitmap.height)
        if (largest <= maxSize) return bitmap
        val scale = maxSize.toFloat() / largest
        return Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt(), (bitmap.height * scale).toInt(), true)
    }
}
