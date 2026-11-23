package com.mytube.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import org.json.JSONObject

class MainActivity : Activity() {

    companion object {
        private const val ACTION_CHANGE_SERVER = "com.mytube.app.CHANGE_SERVER"
        private const val PREFS = "mytube"
        private const val KEY_SERVER = "server_url"
        private const val DEFAULT_SERVER = "http://192.168.1.108:8000"
        private const val REQUEST_NOTIFICATIONS = 1
    }

    private lateinit var root: FrameLayout
    private lateinit var webView: BackgroundWebView
    private var customView: View? = null
    private var customViewCallback: WebChromeClient.CustomViewCallback? = null
    private var activeDialog: AlertDialog? = null

    private val prefs by lazy { getSharedPreferences(PREFS, MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        webView = BackgroundWebView(this)
        root.addView(webView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)

        configureWebView()
        PlaybackService.commandListener = { command, arg -> sendCommand(command, arg) }
        requestNotificationPermission()

        val server = serverUrl()
        when {
            server == null || intent?.action == ACTION_CHANGE_SERVER -> promptForServer()
            savedInstanceState != null && webView.restoreState(savedInstanceState) != null -> Unit
            else -> webView.loadUrl(server)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_CHANGE_SERVER) promptForServer()
    }

    // onPause/onStop deliberately never call webView.onPause()/pauseTimers(): that is what stops
    // playback in generic wrappers when the screen locks.

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onDestroy() {
        activeDialog?.dismiss()
        PlaybackService.commandListener = null
        PlaybackService.stop()
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (customView != null) {
            exitFullscreen()
            return
        }
        val script = """
            (function () {
              if (document.body.classList.contains('user-select-active')) return false;
              var hash = location.hash || '#home';
              if (hash !== '#home' && window.App && typeof window.App.goBack === 'function') {
                window.App.goBack();
                return true;
              }
              return false;
            })()
        """.trimIndent()
        webView.evaluateJavascript(script) { handled ->
            // Keep the activity (and any playback) alive instead of finishing it.
            if (handled != "true") moveTaskToBack(true)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.setBackgroundColor(Color.BLACK)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            userAgentString = "$userAgentString MyTubeAndroid"
        }
        webView.addJavascriptInterface(Bridge(), "MyTubeAndroid")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url
                val server = serverUrl()?.let(Uri::parse) ?: return false
                if (target.host == server.host && target.port == server.port) return false
                openExternally(target)
                return true
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                // A full page (re)load discards the web player, so drop any stale notification.
                webView.keepAlive = false
                PlaybackService.stop()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showLoadError(error.description?.toString().orEmpty())
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowCustomView(view: View, callback: CustomViewCallback) {
                if (customView != null) {
                    callback.onCustomViewHidden()
                    return
                }
                customView = view
                customViewCallback = callback
                root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
                setSystemBarsHidden(true)
                lockOrientationToVideo()
            }

            override fun onHideCustomView() {
                val view = customView ?: return
                root.removeView(view)
                customView = null
                customViewCallback = null
                setSystemBarsHidden(false)
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            }

            // Removes the grey play-button placeholder Android WebView draws before a video loads.
            override fun getDefaultVideoPoster(): Bitmap = Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888)
        }
    }

    private fun exitFullscreen() {
        customViewCallback?.onCustomViewHidden()
    }

    private fun lockOrientationToVideo() {
        val script = """
            (function () {
              var v = document.getElementById('video-player');
              return !v || !v.videoWidth || v.videoWidth >= v.videoHeight;
            })()
        """.trimIndent()
        webView.evaluateJavascript(script) { landscape ->
            if (customView != null && landscape == "true") {
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            }
        }
    }

    private fun setSystemBarsHidden(enabled: Boolean) {
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        if (enabled) {
            controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            controller.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            controller.show(WindowInsetsCompat.Type.systemBars())
        }
    }

    private fun sendCommand(command: String, arg: Double) {
        val safeArg = if (arg.isFinite()) arg else 0.0
        // Each player ignores commands unless it is the one currently playing
        val js = "[window.Player, window.MusicPlayer].forEach(function (p) { " +
            "if (p && typeof p.nativeCommand === 'function') p.nativeCommand(${JSONObject.quote(command)}, $safeArg); });"
        webView.evaluateJavascript(js, null)
    }

    private fun openExternally(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, uri.toString(), Toast.LENGTH_SHORT).show()
        }
    }

    private fun serverUrl(): String? = prefs.getString(KEY_SERVER, null)

    private fun promptForServer() {
        activeDialog?.dismiss()
        val hasServer = serverUrl() != null
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(serverUrl() ?: DEFAULT_SERVER)
            setSelection(text.length)
            hint = getString(R.string.server_prompt_hint)
        }
        val container = FrameLayout(this).apply {
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        val builder = AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle(R.string.server_prompt_title)
            .setView(container)
            .setCancelable(hasServer)
            .setPositiveButton(R.string.save, null)
        if (hasServer) builder.setNegativeButton(R.string.cancel, null)

        val dialog = builder.create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val url = normalizeServer(input.text.toString())
                if (url == null) {
                    input.error = getString(R.string.server_invalid)
                } else {
                    prefs.edit().putString(KEY_SERVER, url).apply()
                    dialog.dismiss()
                    webView.clearHistory()
                    webView.loadUrl(url)
                }
            }
        }
        activeDialog = dialog
        dialog.show()
    }

    private fun normalizeServer(raw: String): String? {
        val url = raw.trim().trimEnd('/')
        val uri = Uri.parse(url)
        if (uri.scheme != "http" && uri.scheme != "https") return null
        if (uri.host.isNullOrBlank()) return null
        return url
    }

    private fun showLoadError(message: String) {
        if (isFinishing || activeDialog?.isShowing == true) return
        val dialog = AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle(R.string.load_error_title)
            .setMessage("${serverUrl().orEmpty()}\n\n$message")
            .setCancelable(false)
            .setPositiveButton(R.string.retry) { _, _ -> serverUrl()?.let(webView::loadUrl) }
            .setNegativeButton(R.string.change_server) { _, _ -> promptForServer() }
            .create()
        activeDialog = dialog
        dialog.show()
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
    }

    /** Methods called from the web player via window.MyTubeAndroid (on a WebView background thread). */
    private inner class Bridge {
        // Keep this 7-argument signature: the video player calls it, and WebView silently drops a call
        // whose argument count does not match, which would stop the playback service from starting.
        @JavascriptInterface
        fun onPlaybackState(
            playing: Boolean,
            title: String?,
            artist: String?,
            artworkUrl: String?,
            positionSec: Double,
            durationSec: Double,
            rate: Double,
        ) = onPlaybackStateWithQueue(playing, title, artist, artworkUrl, positionSec, durationSec, rate, false)

        /** canSkip is true when the web player has a queue, which enables previous/next controls. */
        @JavascriptInterface
        fun onPlaybackStateWithQueue(
            playing: Boolean,
            title: String?,
            artist: String?,
            artworkUrl: String?,
            positionSec: Double,
            durationSec: Double,
            rate: Double,
            canSkip: Boolean,
        ) {
            val info = PlaybackInfo(playing, title.orEmpty(), artist.orEmpty(), artworkUrl.orEmpty(), positionSec, durationSec, rate, canSkip)
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                webView.keepAlive = playing
                PlaybackService.update(this@MainActivity, info)
            }
        }

        @JavascriptInterface
        fun onPlaybackStopped() {
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                webView.keepAlive = false
                PlaybackService.stop()
            }
        }
    }
}
