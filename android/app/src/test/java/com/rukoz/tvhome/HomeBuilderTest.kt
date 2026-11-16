package com.rukoz.tvhome

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

private fun item(
    ratingKey: String = "1",
    type: PlexItemType = PlexItemType.MOVIE,
    title: String = "Title",
    showTitle: String? = null,
    seasonIndex: Int? = null,
    episodeIndex: Int? = null,
    year: Int? = null,
    thumb: String? = null,
    art: String? = null,
    parentThumb: String? = null,
    grandparentThumb: String? = null,
    grandparentArt: String? = null,
    viewOffsetMs: Int? = null,
    durationMs: Int? = null,
): PlexItem = PlexItem(
    ratingKey = ratingKey,
    type = type,
    title = title,
    showTitle = showTitle,
    seasonIndex = seasonIndex,
    episodeIndex = episodeIndex,
    year = year,
    thumb = thumb,
    art = art,
    parentThumb = parentThumb,
    grandparentThumb = grandparentThumb,
    grandparentArt = grandparentArt,
    viewOffsetMs = viewOffsetMs,
    durationMs = durationMs,
    viewCount = 0,
    librarySectionId = null,
    parentRatingKey = null,
    grandparentRatingKey = null,
)

class HomeBuilderTest {
    private val expected = JSONObject(resource("/home_golden/home_rows.json"))

    private fun canonical(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is JSONObject -> value.keys().asSequence().sorted().associateWith { canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).map { canonical(value.get(it)) }
        is Number -> value.toDouble()
        else -> value
    }

    /** Copies tests/fake_pms.py: answers from the fixtures, 404 otherwise; records every call. */
    private class FakePms : PlexTransport {
        val calls = mutableListOf<Pair<String, Map<String, String>>>()
        private val routes = mapOf(
            "/identity" to "identity.json", "/library/sections" to "library_sections.json",
            "/hubs/continueWatching" to "hubs_continue_watching.json",
            "/hubs/sections/1" to "hubs_section_movie.json", "/hubs/sections/2" to "hubs_section_show.json",
            "/library/metadata/4617" to "metadata_episode.json", "/library/metadata/24339" to "metadata_movie.json",
            "/library/metadata/4516" to "metadata_show.json")
        private val onDeck = mapOf(
            "/library/metadata/4516" to "metadata_show_ondeck.json",
            "/library/metadata/19258" to "metadata_show_unstarted_ondeck.json")
        override fun get(url: String, headers: Map<String, String>): PlexResponse {
            calls.add(url to headers)
            val uri = java.net.URI(url)
            val name = if ((uri.rawQuery ?: "").contains("includeOnDeck=1") && uri.path in onDeck) onDeck[uri.path]
                       else routes[uri.path]
            return if (name == null) PlexResponse(404, "Not Found")
                   else PlexResponse(200, javaClass.getResourceAsStream("/plex/$name")!!.bufferedReader(Charsets.UTF_8).readText())
        }
    }

    private fun resource(path: String): String =
        javaClass.getResourceAsStream(path)!!.bufferedReader(Charsets.UTF_8).readText()

    private fun onlineHome(): Home =
        HomeBuilder(PlexClient("http://127.0.0.1:32400", FakePms())).home(emptyList())

    @Test
    fun onlineRowsMatchPython() {
        val actual = onlineHome().toJson()
        val online = expected.getJSONObject("online")
        assertEquals(canonical(online.get("rows")), canonical(actual.get("rows")))
        assertEquals(canonical(online.get("notices")), canonical(actual.get("notices")))
    }

    @Test
    fun offlineMatchesPython() {
        val transport = PlexTransport { _, _ -> throw java.io.IOException("connection refused") }
        val actual = HomeBuilder(PlexClient("http://127.0.0.1:32400", transport)).home(emptyList()).toJson()
        val offline = expected.getJSONObject("offline")
        assertEquals(canonical(offline.get("rows")), canonical(actual.get("rows")))
        assertEquals(canonical(offline.get("notices")), canonical(actual.get("notices")))
    }

    @Test
    fun appsArePassedThrough() {
        val apps = listOf(
            Tile("app:1", "Netflix", null, "/static/apps/1.png", ImageShape.ICON, null,
                 Action(ActionKind.OPEN_APP, "1")),
            Tile("app:2", "Plex", null, "/static/apps/2.png", ImageShape.ICON, null,
                 Action(ActionKind.OPEN_APP, "2")),
        )
        val home = HomeBuilder(PlexClient("http://127.0.0.1:32400", FakePms())).home(apps)
        assertSame(apps, home.apps)
    }

    @Test
    fun rowsAreCappedAtEight() {
        val home = onlineHome()
        assertEquals(8, home.rows.size)
        assertFalse(home.rows.any { it.id == "hub:tv.toprated.2" })
    }

    @Test
    fun oneFailingLibraryIsSkipped() {
        val fake = FakePms()
        val transport = PlexTransport { url, headers ->
            if (java.net.URI(url).path == "/hubs/sections/2") PlexResponse(500, "boom") else fake.get(url, headers)
        }
        val home = HomeBuilder(PlexClient("http://127.0.0.1:32400", transport)).home(emptyList())
        assertEquals(emptyList<String>(), home.notices)
        assertTrue(home.rows.none { it.id.startsWith("hub:tv.") })
        assertTrue(home.rows.any { it.id.startsWith("hub:movie.") })
    }

    @Test
    fun tileRules() {
        val episodeNoSeason = plexTile(
            item(type = PlexItemType.EPISODE, title = "Pilot", showTitle = "Show",
                 seasonIndex = null, episodeIndex = 1),
            ImageShape.POSTER,
        )
        assertEquals("Show", episodeNoSeason.title)
        assertEquals("Pilot", episodeNoSeason.subtitle)

        val episodeEmptyThumb = plexTile(
            item(type = PlexItemType.EPISODE, title = "Pilot", showTitle = "Show",
                 seasonIndex = 1, episodeIndex = 1, thumb = "",
                 grandparentArt = "/library/metadata/4516/art/2"),
            ImageShape.WIDE,
        )
        assertEquals(imagePath("/library/metadata/4516/art/2", 384, 216), episodeEmptyThumb.image)

        val movieHttpArt = plexTile(
            item(type = PlexItemType.MOVIE, title = "Film", art = "http://x/y"),
            ImageShape.WIDE,
        )
        assertNull(movieHttpArt.image)

        val zeroDuration = plexTile(
            item(type = PlexItemType.MOVIE, title = "Film", viewOffsetMs = 10, durationMs = 0),
            ImageShape.POSTER,
        )
        assertNull(zeroDuration.progress)
    }
}
