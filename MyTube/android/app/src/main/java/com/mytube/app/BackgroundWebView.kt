package com.mytube.app

import android.annotation.SuppressLint
import android.content.Context
import android.view.View
import android.webkit.WebView

/**
 * WebView that keeps reporting itself as visible while media is playing. Otherwise Chromium marks
 * the page hidden when the screen locks or the app is backgrounded, throttling the timers hls.js
 * relies on to fetch segments, which stalls or pauses playback.
 */
@SuppressLint("ViewConstructor")
class BackgroundWebView(context: Context) : WebView(context) {

    var keepAlive = false

    override fun onWindowVisibilityChanged(visibility: Int) {
        if (keepAlive && visibility != View.VISIBLE) {
            super.onWindowVisibilityChanged(View.VISIBLE)
            return
        }
        super.onWindowVisibilityChanged(visibility)
    }
}
