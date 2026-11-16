package com.rukoz.tvhome

import org.json.JSONArray
import org.json.JSONObject

const val CONTRACT_VERSION = 1
const val MAX_TARGET_LENGTH = 200

enum class RowKind(val value: Int) {
    CONTINUE_WATCHING(0),
    PLEX_HUB(1),
}

enum class ActionKind(val value: Int) {
    PLAY_PLEX(0),
    OPEN_APP(1),
    SWITCH_INPUT(2),
    VIZIO_HOME(3),
    AMAZON_HOME(4),
    ;

    companion object {
        fun fromValue(value: Int): ActionKind? = entries.firstOrNull { it.value == value }
    }
}

enum class ImageShape(val value: Int) {
    POSTER(0),
    WIDE(1),
    ICON(2),
}

data class Action(val kind: ActionKind, val target: String) {
    fun toJson(): JSONObject {
        val obj = JSONObject()
        obj.put("kind", kind.value)
        obj.put("target", target)
        return obj
    }

    companion object {
        fun fromJson(value: Any?): Action {
            val obj = value as? JSONObject
                ?: throw IllegalArgumentException(
                    "action must be a dict, got " + (value?.javaClass?.simpleName ?: "null")
                )
            if (!obj.has("kind")) {
                throw IllegalArgumentException("action is missing 'kind'")
            }
            val rawKind = obj.get("kind")
            if (rawKind !is Int && rawKind !is Long) {
                throw IllegalArgumentException("action 'kind' must be an int, got $rawKind")
            }
            val actionKind = ActionKind.fromValue(rawKind.toInt())
                ?: throw IllegalArgumentException(
                    "action 'kind' is not an ActionKind value: $rawKind"
                )
            if (!obj.has("target")) {
                throw IllegalArgumentException("action is missing 'target'")
            }
            val rawTarget = obj.get("target")
            if (rawTarget !is String) {
                throw IllegalArgumentException("action 'target' must be a str, got $rawTarget")
            }
            if (rawTarget.isBlank()) {
                throw IllegalArgumentException("action 'target' is empty after strip()")
            }
            if (rawTarget.length > MAX_TARGET_LENGTH) {
                throw IllegalArgumentException(
                    "action 'target' is longer than $MAX_TARGET_LENGTH characters"
                )
            }
            return Action(actionKind, rawTarget)
        }
    }
}

data class Tile(
    val id: String,
    val title: String,
    val subtitle: String?,
    val image: String?,
    val shape: ImageShape,
    val progress: Double?,
    val action: Action,
) {
    fun toJson(): JSONObject {
        val obj = JSONObject()
        obj.put("id", id)
        obj.put("title", title)
        obj.put("subtitle", subtitle ?: JSONObject.NULL)
        obj.put("image", image ?: JSONObject.NULL)
        obj.put("shape", shape.value)
        val p = progress
        obj.put(
            "progress",
            if (p == null) JSONObject.NULL else Math.round(p.coerceIn(0.0, 1.0) * 1000.0) / 1000.0
        )
        obj.put("action", action.toJson())
        return obj
    }
}

data class Row(
    val id: String,
    val title: String,
    val kind: RowKind,
    val tiles: List<Tile>,
) {
    fun toJson(): JSONObject {
        val obj = JSONObject()
        obj.put("id", id)
        obj.put("title", title)
        obj.put("kind", kind.value)
        val arr = JSONArray()
        for (tile in tiles) {
            arr.put(tile.toJson())
        }
        obj.put("tiles", arr)
        return obj
    }
}

data class Home(
    val rows: List<Row>,
    val apps: List<Tile>,
    val notices: List<String> = emptyList(),
) {
    fun toJson(): JSONObject {
        val obj = JSONObject()
        obj.put("version", CONTRACT_VERSION)
        val rowsArr = JSONArray()
        for (row in rows) {
            rowsArr.put(row.toJson())
        }
        obj.put("rows", rowsArr)
        val appsArr = JSONArray()
        for (tile in apps) {
            appsArr.put(tile.toJson())
        }
        obj.put("apps", appsArr)
        val noticesArr = JSONArray()
        for (notice in notices) {
            noticesArr.put(notice)
        }
        obj.put("notices", noticesArr)
        return obj
    }
}

data class ActionResult(val ok: Boolean, val message: String) {
    fun toJson(): JSONObject {
        val obj = JSONObject()
        obj.put("ok", ok)
        obj.put("message", message)
        return obj
    }
}

data class ImageQuery(val p: String, val w: Int, val h: Int)

fun imagePath(plexPath: String, width: Int, height: Int): String {
    return "/img?p=" + percentEncode(plexPath) + "&w=$width&h=$height"
}

private fun percentEncode(value: String): String {
    val sb = StringBuilder()
    for (byte in value.toByteArray(Charsets.UTF_8)) {
        val c = byte.toInt() and 0xFF
        val keep = (c in 65..90) || (c in 97..122) || (c in 48..57) ||
            c == 45 || c == 95 || c == 46 || c == 126
        if (keep) {
            sb.append(c.toChar())
        } else {
            sb.append('%').append(String.format("%02X", c))
        }
    }
    return sb.toString()
}

fun parseImageQuery(query: String): ImageQuery {
    val params = LinkedHashMap<String, MutableList<String>>()
    for (part in query.split("&")) {
        val idx = part.indexOf('=')
        if (idx < 0) {
            continue
        }
        val name = java.net.URLDecoder.decode(part.substring(0, idx), "UTF-8")
        val value = java.net.URLDecoder.decode(part.substring(idx + 1), "UTF-8")
        if (value.isEmpty()) {
            continue
        }
        params.getOrPut(name) { mutableListOf() }.add(value)
    }

    val pValues = params["p"]
    if (pValues == null || pValues.size != 1) {
        throw IllegalArgumentException("'p' must be present exactly once")
    }
    val p = pValues[0]
    if (!p.startsWith("/library/")) {
        throw IllegalArgumentException("'p' must start with /library/")
    }
    if (p.contains("..")) {
        throw IllegalArgumentException("'p' must not contain ..")
    }
    if (p.contains("://")) {
        throw IllegalArgumentException("'p' must not contain ://")
    }

    val w = parseSide(params, "w", 1920)
    val h = parseSide(params, "h", 1080)
    return ImageQuery(p, w, h)
}

private fun parseSide(params: Map<String, List<String>>, name: String, maximum: Int): Int {
    val values = params[name]
    if (values == null || values.size != 1) {
        throw IllegalArgumentException("'$name' must be present exactly once")
    }
    val raw = values[0]
    if (raw.isEmpty() || !raw.all { it in '0'..'9' }) {
        throw IllegalArgumentException("'$name' must be digits only, got $raw")
    }
    val number = raw.toInt()
    if (number < 1 || number > maximum) {
        throw IllegalArgumentException("'$name' must be from 1 to $maximum, got $number")
    }
    return number
}
