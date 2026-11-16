package com.rukoz.tvhome

import org.json.JSONObject

class ApiResponse(val status: Int, val mimeType: String, val body: ByteArray, val cacheControl: String?)

fun interface ImageSource {
    fun fetch(p: String, w: Int, h: Int): Pair<String, ByteArray>?
}

fun interface IconSource {
    fun icon(pkg: String): ByteArray?
}

internal val PKG_REGEX = Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+$")
private const val MAX_PKG_LENGTH = 200

class ApiHandlers(
    private val homeJson: () -> String,
    private val images: ImageSource,
    private val icons: IconSource,
) {
    fun route(path: String, rawQuery: String?): ApiResponse? {
        if (path == "/api/home") {
            return try {
                ApiResponse(200, "application/json", homeJson().toByteArray(Charsets.UTF_8), "no-store")
            } catch (e: Exception) {
                fail(500, "internal error")
            }
        }
        if (path.startsWith("/api/")) {
            return fail(404, "not found")
        }
        if (path == "/img") {
            return image(rawQuery)
        }
        if (path == "/appicon") {
            return icon(rawQuery)
        }
        return null
    }

    private fun image(rawQuery: String?): ApiResponse {
        val query = try {
            parseImageQuery(rawQuery ?: "")
        } catch (e: IllegalArgumentException) {
            return fail(400, "bad image query")
        }
        val fetched = images.fetch(query.p, query.w, query.h)
            ?: return fail(502, "image not available")
        return ApiResponse(200, fetched.first, fetched.second, "max-age=86400")
    }

    private fun icon(rawQuery: String?): ApiResponse {
        val pkg = pkgParam(rawQuery ?: "")
            ?: return fail(400, "bad app icon query")
        if (!PKG_REGEX.matches(pkg) || pkg.length > MAX_PKG_LENGTH) {
            return fail(400, "bad app icon query")
        }
        val bytes = icons.icon(pkg) ?: return fail(404, "no such app")
        return ApiResponse(200, "image/png", bytes, "max-age=86400")
    }

    private fun pkgParam(query: String): String? {
        var count = 0
        var found: String? = null
        for (part in query.split("&")) {
            val idx = part.indexOf('=')
            if (idx < 0) {
                continue
            }
            if (part.substring(0, idx) != "pkg") {
                continue
            }
            count++
            if (count > 1) {
                return null
            }
            found = try {
                java.net.URLDecoder.decode(part.substring(idx + 1), "UTF-8")
            } catch (e: IllegalArgumentException) {
                return null
            }
        }
        return if (count == 1) found else null
    }

    private fun fail(status: Int, msg: String): ApiResponse =
        ApiResponse(
            status,
            "application/json",
            JSONObject().put("ok", false).put("message", msg).toString().toByteArray(),
            "no-store",
        )
}
