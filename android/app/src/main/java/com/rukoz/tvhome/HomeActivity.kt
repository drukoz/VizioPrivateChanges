package com.rukoz.tvhome

import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader
import java.io.ByteArrayInputStream

class HomeActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/static/", WebViewAssetLoader.AssetsPathHandler(this))
            .addPathHandler("/api/", WebViewAssetLoader.PathHandler { path ->
                if (path == "home") {
                    Log.i(TAG, "served /api/home")
                    WebResourceResponse("application/json", "utf-8", ByteArrayInputStream(FixtureHome.JSON.toByteArray()))
                } else {
                    null
                }
            })
            .build()
        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(message: ConsoleMessage): Boolean {
                Log.i(TAG, "console ${message.messageLevel()}: ${message.message()} (${message.sourceId()}:${message.lineNumber()})")
                return true
            }
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)
        }
        setContentView(web)
        web.requestFocus()
        web.loadUrl("https://appassets.androidplatform.net/static/index.html")
    }

    companion object {
        const val TAG = "TvHome"
    }
}
