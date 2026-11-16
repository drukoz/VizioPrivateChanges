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
        val handlers = ApiHandlers({ FixtureHome.JSON }, ImageSource { _, _, _ -> null }, AppIcons(packageManager))
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/static/", WebViewAssetLoader.AssetsPathHandler(this))
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
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val url = request.url
                if (url != null && url.host == "appassets.androidplatform.net") {
                    val response = handlers.route(url.path ?: "", url.encodedQuery)
                    if (response != null) {
                        Log.i(TAG, "served ${url.path} ${response.status}")
                        val headers = HashMap<String, String>()
                        if (response.cacheControl != null) {
                            headers["Cache-Control"] = response.cacheControl
                        }
                        return WebResourceResponse(
                            response.mimeType,
                            if (response.mimeType == "application/json") "utf-8" else null,
                            response.status,
                            reason(response.status),
                            headers,
                            ByteArrayInputStream(response.body),
                        )
                    }
                }
                return loader.shouldInterceptRequest(request.url)
            }
        }
        setContentView(web)
        web.requestFocus()
        web.addJavascriptInterface(TvHomeBridge { ActionResult(false, "Not available yet") }, "TvHome")
        web.loadUrl("https://appassets.androidplatform.net/static/index.html")
    }

    companion object {
        const val TAG = "TvHome"

        fun reason(status: Int): String = when (status) {
            200 -> "OK"
            400 -> "Bad Request"
            404 -> "Not Found"
            500 -> "Internal Server Error"
            502 -> "Bad Gateway"
            else -> "OK"
        }
    }
}
