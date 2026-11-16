package com.rukoz.tvhome

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

fun interface BytesFetcher {
    fun get(url: String): Pair<String, ByteArray>?
}

class HttpBytesFetcher(
    private val connectTimeoutMs: Int = 4000,
    private val readTimeoutMs: Int = 8000,
    private val maxBytes: Int = 5 * 1024 * 1024,
) : BytesFetcher {
    override fun get(url: String): Pair<String, ByteArray>? {
        // /img has no try/catch in ApiHandlers, so nothing may escape into shouldInterceptRequest.
        val connection = try {
            URL(url).openConnection() as HttpURLConnection
        } catch (e: IOException) {
            return null
        }
        try {
            connection.requestMethod = "GET"
            connection.connectTimeout = connectTimeoutMs
            connection.readTimeout = readTimeoutMs
            if (connection.responseCode != 200) return null
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(16 * 1024)
            connection.inputStream.use { stream ->
                while (true) {
                    val read = stream.read(buffer)
                    if (read < 0) break
                    out.write(buffer, 0, read)
                    if (out.size() > maxBytes) return null
                }
            }
            val rawType = connection.contentType
            val type = rawType?.substringBefore(';')?.trim()
            val mimeType = if (type.isNullOrEmpty()) "image/jpeg" else type
            return mimeType to out.toByteArray()
        } catch (e: IOException) {
            return null
        } finally {
            connection.disconnect()
        }
    }
}

class PlexImageSource(
    private val plex: PlexClient,
    private val fetcher: BytesFetcher = HttpBytesFetcher(),
) : ImageSource {
    override fun fetch(p: String, w: Int, h: Int): Pair<String, ByteArray>? =
        fetcher.get(plex.imageUrl(p, w, h))
}
