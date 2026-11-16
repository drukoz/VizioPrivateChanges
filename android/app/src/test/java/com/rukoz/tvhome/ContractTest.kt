package com.rukoz.tvhome

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

private fun canonical(value: Any?): Any? = when (value) {
    null, JSONObject.NULL -> null
    is JSONObject -> value.keys().asSequence().sorted().associateWith { canonical(value.get(it)) }
    is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
    is Number -> value.toDouble()
    else -> value
}

private fun resource(name: String): String =
    ContractTest::class.java.getResourceAsStream("/contract/$name")!!
        .bufferedReader(Charsets.UTF_8).readText()

private val IMAGE_CASES = listOf(
    Triple("/library/metadata/4617/thumb/1700000000", 384, 216),
    Triple("/library/metadata/2/thumb/1?x=a b&c=ü*~", 240, 360),
    Triple("/library/metadata/9/art/1+2", 1920, 1080),
)

private fun goldenHome(): Home = Home(
    rows = listOf(
        Row("continueWatching", "Continue Watching", RowKind.CONTINUE_WATCHING, listOf(
            Tile("plex:4617", "Show A", "S1 · E2 · Episode B",
                 imagePath(IMAGE_CASES[0].first, 384, 216), ImageShape.WIDE, 0.33333,
                 Action(ActionKind.PLAY_PLEX, "4617")),
            Tile("plex:24339", "Movie C", "2024", null, ImageShape.WIDE, 1.25,
                 Action(ActionKind.PLAY_PLEX, "24339")),
            Tile("plex:1", "Movie D", null, null, ImageShape.WIDE, -0.2,
                 Action(ActionKind.PLAY_PLEX, "1")),
        )),
        Row("hub:movie.recentlyadded.1", "Recently Added Movies", RowKind.PLEX_HUB, listOf(
            Tile("plex:2", "Movie E", null, imagePath(IMAGE_CASES[1].first, 240, 360),
                 ImageShape.POSTER, null, Action(ActionKind.PLAY_PLEX, "2")),
        )),
    ),
    apps = listOf(
        Tile("app:com.netflix.ninja", "Netflix", null, "/appicon?pkg=com.netflix.ninja",
             ImageShape.ICON, null, Action(ActionKind.OPEN_APP, "com.netflix.ninja")),
        Tile("app:amazon-home", "Amazon Home", null, null, ImageShape.ICON, null,
             Action(ActionKind.AMAZON_HOME, "com.amazon.tv.launcher")),
    ),
    notices = listOf("Plex is not answering; showing apps only."),
)

class ContractTest {
    @Test
    fun homeMatchesPythonGolden() {
        assertEquals(
            canonical(JSONObject(resource("home.json"))),
            canonical(goldenHome().toJson()),
        )
    }

    @Test
    fun actionResultsMatchGolden() {
        val actual = JSONArray()
        actual.put(ActionResult(true, "Opening Netflix").toJson())
        actual.put(ActionResult(false, "Plex is not installed").toJson())
        assertEquals(canonical(JSONArray(resource("action_results.json"))), canonical(actual))
    }

    @Test
    fun imagePathsMatchGolden() {
        val entries = JSONArray(resource("image_paths.json"))
        for (i in 0 until entries.length()) {
            val entry = entries.getJSONObject(i)
            assertEquals(
                entry.getString("path"),
                imagePath(entry.getString("p"), entry.getInt("w"), entry.getInt("h")),
            )
        }
    }

    @Test
    fun imageQueriesRoundTrip() {
        val entries = JSONArray(resource("image_paths.json"))
        for (i in 0 until entries.length()) {
            val entry = entries.getJSONObject(i)
            val query = entry.getString("path").substringAfter("?")
            assertEquals(
                ImageQuery(entry.getString("p"), entry.getInt("w"), entry.getInt("h")),
                parseImageQuery(query),
            )
        }
    }

    @Test
    fun actionFromJsonAccepts() {
        assertEquals(
            Action(ActionKind.PLAY_PLEX, "4617"),
            Action.fromJson(JSONObject("""{"kind":0,"target":"4617"}""")),
        )
        assertEquals(
            Action(ActionKind.AMAZON_HOME, "com.amazon.tv.launcher"),
            Action.fromJson(JSONObject("""{"kind":4,"target":"com.amazon.tv.launcher"}""")),
        )
    }

    @Test
    fun actionFromJsonRejects() {
        val rejects = listOf<Any>(
            JSONArray(),
            JSONObject("{}"),
            JSONObject("""{"kind":true,"target":"1"}"""),
            JSONObject("""{"kind":1.0,"target":"1"}"""),
            JSONObject("""{"kind":"1","target":"1"}"""),
            JSONObject("""{"kind":9,"target":"1"}"""),
            JSONObject("""{"kind":1}"""),
            JSONObject("""{"kind":1,"target":5}"""),
            JSONObject("""{"kind":1,"target":"   "}"""),
            JSONObject("""{"kind":1,"target":"${"x".repeat(201)}"}"""),
        )
        for (value in rejects) {
            assertThrows(IllegalArgumentException::class.java) { Action.fromJson(value) }
        }
    }

    @Test
    fun parseImageQueryRejects() {
        val rejects = listOf(
            "",
            "w=1&h=1",
            "p=/library/a&p=/library/b&w=1&h=1",
            "p=/other&w=1&h=1",
            "p=/library/../x&w=1&h=1",
            "p=/library/http://x&w=1&h=1",
            "p=/library/a&w=0&h=1",
            "p=/library/a&w=1921&h=1",
            "p=/library/a&w=1&h=1081",
            "p=/library/a&w=-1&h=1",
            "p=/library/a&w=1x&h=1",
            "p=/library/a&w=&h=1",
        )
        for (query in rejects) {
            assertThrows(IllegalArgumentException::class.java) { parseImageQuery(query) }
        }
    }
}
