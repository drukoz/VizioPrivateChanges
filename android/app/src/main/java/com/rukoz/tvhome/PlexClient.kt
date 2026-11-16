package com.rukoz.tvhome

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class PlexResponse(val status: Int, val body: String)

fun interface PlexTransport {
    fun get(url: String, headers: Map<String, String>): PlexResponse
}

class HttpPlexTransport(
    private val connectTimeoutMs: Int = 4000,
    private val readTimeoutMs: Int = 8000,
) : PlexTransport {
    override fun get(url: String, headers: Map<String, String>): PlexResponse {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.connectTimeout = connectTimeoutMs
            connection.readTimeout = readTimeoutMs
            for ((key, value) in headers) connection.setRequestProperty(key, value)
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            return PlexResponse(status, body)
        } finally {
            connection.disconnect()
        }
    }
}

class PlexException(val status: Int, val detail: String) : Exception("$status: $detail")

enum class PlexItemType(val value: Int) {
    MOVIE(0),
    EPISODE(1),
    SHOW(2),
    SEASON(3),
    OTHER(4),
    ;

    companion object {
        fun fromText(text: String?): PlexItemType {
            if (text == null) return OTHER
            return when (text.lowercase().trim()) {
                "movie" -> MOVIE
                "episode" -> EPISODE
                "show" -> SHOW
                "season" -> SEASON
                else -> OTHER
            }
        }
    }
}

enum class LibraryType(val value: Int) {
    MOVIE(0),
    SHOW(1),
    MUSIC(2),
    PHOTO(3),
    OTHER(4),
    ;

    companion object {
        fun fromText(text: String?): LibraryType {
            if (text == null) return OTHER
            return when (text.lowercase().trim()) {
                "movie" -> MOVIE
                "show" -> SHOW
                "artist" -> MUSIC
                "photo" -> PHOTO
                else -> OTHER
            }
        }
    }
}

private fun textField(obj: JSONObject, key: String): String? {
    val value = obj.opt(key)
    return if (value == null || value === JSONObject.NULL) null else value.toString()
}

private fun asInt(value: Any?): Int? = when (value) {
    null, JSONObject.NULL -> null
    is Int -> value
    is Long -> value.toInt()
    is Double -> value.toInt()
    is Boolean -> if (value) 1 else 0
    is String -> value.trim().toIntOrNull()
    else -> null
}

private fun quote(s: String): String {
    val sb = StringBuilder()
    for (byte in s.toByteArray(Charsets.UTF_8)) {
        val c = byte.toInt() and 0xFF
        val keep = (c in 'A'.code..'Z'.code) || (c in 'a'.code..'z'.code) || (c in '0'.code..'9'.code) ||
            c == '-'.code || c == '_'.code || c == '.'.code || c == '~'.code
        if (keep) {
            sb.append(c.toChar())
        } else {
            sb.append('%')
            sb.append(String.format("%02X", c))
        }
    }
    return sb.toString()
}

data class PlexItem(
    val ratingKey: String,
    val type: PlexItemType,
    val title: String,
    val showTitle: String?,
    val seasonIndex: Int?,
    val episodeIndex: Int?,
    val year: Int?,
    val thumb: String?,
    val art: String?,
    val parentThumb: String?,
    val grandparentThumb: String?,
    val grandparentArt: String?,
    val viewOffsetMs: Int?,
    val durationMs: Int?,
    val viewCount: Int,
    val librarySectionId: Int?,
    val parentRatingKey: String?,
    val grandparentRatingKey: String?,
) {
    companion object {
        fun fromJson(obj: JSONObject): PlexItem = PlexItem(
            ratingKey = textField(obj, "ratingKey") ?: "",
            type = PlexItemType.fromText(textField(obj, "type")),
            title = textField(obj, "title") ?: "",
            showTitle = textField(obj, "grandparentTitle"),
            seasonIndex = asInt(obj.opt("parentIndex")),
            episodeIndex = asInt(obj.opt("index")),
            year = asInt(obj.opt("year")),
            thumb = textField(obj, "thumb"),
            art = textField(obj, "art"),
            parentThumb = textField(obj, "parentThumb"),
            grandparentThumb = textField(obj, "grandparentThumb"),
            grandparentArt = textField(obj, "grandparentArt"),
            viewOffsetMs = asInt(obj.opt("viewOffset")),
            durationMs = asInt(obj.opt("duration")),
            viewCount = asInt(obj.opt("viewCount")) ?: 0,
            librarySectionId = asInt(obj.opt("librarySectionID")),
            parentRatingKey = textField(obj, "parentRatingKey"),
            grandparentRatingKey = textField(obj, "grandparentRatingKey"),
        )
    }
}

data class Hub(val identifier: String, val title: String, val items: List<PlexItem>)

data class Library(val sectionId: Int, val title: String, val type: LibraryType)

class PlexClient(
    baseUrl: String,
    private val transport: PlexTransport = HttpPlexTransport(),
    private val token: String? = null,
) {
    val baseUrl: String = baseUrl.trimEnd('/')

    private fun headers(): Map<String, String> {
        val headers = linkedMapOf(
            "Accept" to "application/json",
            "X-Plex-Client-Identifier" to "com.rukoz.tvhome",
            "X-Plex-Product" to "TV Home",
            "X-Plex-Version" to "1",
        )
        if (!token.isNullOrEmpty()) headers["X-Plex-Token"] = token
        return headers
    }

    private fun request(path: String): JSONObject {
        val response = transport.get(baseUrl + path, headers())
        val raw = response.body
        if (response.status !in 200..299) throw PlexException(response.status, raw.take(200))
        val parsed = parseJsonObject(raw) ?: throw PlexException(response.status, "response is not JSON")
        return parsed
    }

    private fun container(path: String): JSONObject {
        val parsed = request(path)
        val mediaContainer = parsed.opt("MediaContainer")
        return if (mediaContainer is JSONObject) mediaContainer else JSONObject()
    }

    fun identity(): Pair<String, String> {
        val container = container("/identity")
        return (textField(container, "machineIdentifier") ?: "") to (textField(container, "version") ?: "")
    }

    fun libraries(): List<Library> {
        val container = container("/library/sections")
        val libraries = mutableListOf<Library>()
        for (directory in dictList(container, "Directory")) {
            val sectionId = asInt(directory.opt("key")) ?: continue
            libraries.add(
                Library(
                    sectionId = sectionId,
                    title = textField(directory, "title") ?: "",
                    type = LibraryType.fromText(textField(directory, "type")),
                )
            )
        }
        return libraries
    }

    fun continueWatching(count: Int = 20): List<PlexItem> {
        val container = container("/hubs/continueWatching?count=$count")
        val hubs = dictList(container, "Hub")
        if (hubs.isEmpty()) return emptyList()
        return dictList(hubs[0], "Metadata").map { PlexItem.fromJson(it) }
    }

    fun sectionHubs(sectionId: Int, count: Int = 20): List<Hub> {
        val container = container("/hubs/sections/$sectionId?count=$count")
        return dictList(container, "Hub").map { hub ->
            Hub(
                identifier = textField(hub, "hubIdentifier") ?: "",
                title = textField(hub, "title") ?: "",
                items = dictList(hub, "Metadata").map { PlexItem.fromJson(it) },
            )
        }
    }

    fun item(ratingKey: String): PlexItem {
        val container = container("/library/metadata/$ratingKey")
        val metadata = dictList(container, "Metadata")
        if (metadata.isEmpty()) throw PlexException(404, "no such item")
        return PlexItem.fromJson(metadata[0])
    }

    fun nextEpisode(ratingKey: String): PlexItem? {
        val container = container("/library/metadata/$ratingKey?includeOnDeck=1")
        val metadata = dictList(container, "Metadata")
        if (metadata.isEmpty()) return null
        val onDeck = metadata[0].opt("OnDeck")
        if (onDeck !is JSONObject) return null
        val nested = onDeck.opt("Metadata")
        if (nested is JSONArray) {
            if (nested.length() == 0) return null
            val first = nested.get(0)
            return if (first is JSONObject) PlexItem.fromJson(first) else null
        }
        if (nested is JSONObject) return PlexItem.fromJson(nested)
        return null
    }

    fun imageUrl(path: String, width: Int, height: Int): String {
        var url = "$baseUrl/photo/:/transcode?width=$width&height=$height&minSize=1&upscale=1&url=" + quote(path)
        if (!token.isNullOrEmpty()) url += "&X-Plex-Token=$token"
        return url
    }

    private fun dictList(obj: JSONObject, key: String): List<JSONObject> {
        val value = obj.opt(key)
        if (value !is JSONArray) return emptyList()
        val entries = mutableListOf<JSONObject>()
        for (index in 0 until value.length()) {
            val entry = value.get(index)
            if (entry is JSONObject) entries.add(entry)
        }
        return entries
    }

    private fun parseJsonObject(raw: String): JSONObject? {
        if (raw.isBlank()) return null
        return try {
            JSONObject(raw.trim())
        } catch (e: JSONException) {
            null
        }
    }
}
