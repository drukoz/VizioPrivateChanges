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

private fun golden(item: PlexItem?): Any {
    if (item == null) return JSONObject.NULL
    return JSONObject()
        .put("rating_key", item.ratingKey)
        .put("type", item.type.value)
        .put("title", item.title)
        .put("show_title", item.showTitle ?: JSONObject.NULL)
        .put("season_index", item.seasonIndex ?: JSONObject.NULL)
        .put("episode_index", item.episodeIndex ?: JSONObject.NULL)
        .put("year", item.year ?: JSONObject.NULL)
        .put("thumb", item.thumb ?: JSONObject.NULL)
        .put("art", item.art ?: JSONObject.NULL)
        .put("parent_thumb", item.parentThumb ?: JSONObject.NULL)
        .put("grandparent_thumb", item.grandparentThumb ?: JSONObject.NULL)
        .put("grandparent_art", item.grandparentArt ?: JSONObject.NULL)
        .put("view_offset_ms", item.viewOffsetMs ?: JSONObject.NULL)
        .put("duration_ms", item.durationMs ?: JSONObject.NULL)
        .put("view_count", item.viewCount)
        .put("library_section_id", item.librarySectionId ?: JSONObject.NULL)
        .put("parent_rating_key", item.parentRatingKey ?: JSONObject.NULL)
        .put("grandparent_rating_key", item.grandparentRatingKey ?: JSONObject.NULL)
}

private fun golden(hub: Hub): JSONObject = JSONObject()
    .put("identifier", hub.identifier)
    .put("title", hub.title)
    .put("items", JSONArray(hub.items.map { golden(it) }))

private fun golden(library: Library): JSONObject = JSONObject()
    .put("section_id", library.sectionId)
    .put("title", library.title)
    .put("type", library.type.value)

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

class PlexClientTest {
    private val expected = JSONObject(resource("/plex_golden/plex_client.json"))
    private val client = PlexClient("http://127.0.0.1:32400", FakePms())

    private fun resource(path: String): String =
        javaClass.getResourceAsStream(path)!!.bufferedReader(Charsets.UTF_8).readText()

    @Test
    fun identityMatchesGolden() {
        val (machine, version) = client.identity()
        val actual = JSONObject().put("machine_identifier", machine).put("version", version)
        assertEquals(canonical(expected.get("identity")), canonical(actual))
    }

    @Test
    fun librariesMatchGolden() {
        val actual = JSONArray(client.libraries().map { golden(it) })
        assertEquals(canonical(expected.get("libraries")), canonical(actual))
    }

    @Test
    fun continueWatchingMatchesGolden() {
        val actual = JSONArray(client.continueWatching(20).map { golden(it) })
        assertEquals(canonical(expected.get("continue_watching")), canonical(actual))
    }

    @Test
    fun sectionHubsMatchGolden() {
        val section1 = JSONArray(client.sectionHubs(1, 20).map { golden(it) })
        assertEquals(canonical(expected.get("section_hubs_1")), canonical(section1))
        val section2 = JSONArray(client.sectionHubs(2, 20).map { golden(it) })
        assertEquals(canonical(expected.get("section_hubs_2")), canonical(section2))
    }

    @Test
    fun itemsMatchGolden() {
        for (key in listOf("item_4617", "item_24339", "item_4516")) {
            val ratingKey = key.removePrefix("item_")
            assertEquals(canonical(expected.get(key)), canonical(golden(client.item(ratingKey))))
        }
    }

    @Test
    fun nextEpisodeMatchesGolden() {
        for (key in listOf("next_episode_4516", "next_episode_19258", "next_episode_4617")) {
            val ratingKey = key.removePrefix("next_episode_")
            assertEquals(canonical(expected.get(key)), canonical(golden(client.nextEpisode(ratingKey))))
        }
    }

    @Test
    fun imageUrlMatchesGolden() {
        assertEquals(
            expected.getString("image_url"),
            client.imageUrl("/library/metadata/1/thumb/2?x=a b", 240, 360),
        )
    }

    @Test
    fun missingItemThrows404() {
        val error = assertThrows(PlexException::class.java) { client.item("999") }
        assertEquals(404, error.status)
        assertEquals(404, expected.getInt("item_999_status"))
    }

    @Test
    fun sendsPlexHeaders() {
        val fake = FakePms()
        PlexClient("http://127.0.0.1:32400", fake).identity()
        assertEquals(1, fake.calls.size)
        val (url, headers) = fake.calls[0]
        assertEquals("http://127.0.0.1:32400/identity", url)
        assertEquals("application/json", headers["Accept"])
        assertEquals("com.rukoz.tvhome", headers["X-Plex-Client-Identifier"])
        assertEquals("TV Home", headers["X-Plex-Product"])
        assertEquals("1", headers["X-Plex-Version"])
        assertEquals(null, headers["X-Plex-Token"])

        val tokened = FakePms()
        val withToken = PlexClient("http://127.0.0.1:32400", tokened, token = "t")
        withToken.identity()
        assertEquals("t", tokened.calls[0].second["X-Plex-Token"])
        assertEquals(
            true,
            withToken.imageUrl("/library/metadata/1/thumb/2?x=a b", 240, 360).endsWith("&X-Plex-Token=t"),
        )
    }

    @Test
    fun errorsBecomePlexException() {
        val serverError = PlexTransport { _, _ -> PlexResponse(500, "x".repeat(300)) }
        val statusError = assertThrows(PlexException::class.java) {
            PlexClient("http://127.0.0.1:32400", serverError).identity()
        }
        assertEquals(500, statusError.status)
        assertEquals(200, statusError.detail.length)

        val notJson = PlexTransport { _, _ -> PlexResponse(200, "not json") }
        val parseError = assertThrows(PlexException::class.java) {
            PlexClient("http://127.0.0.1:32400", notJson).identity()
        }
        assertEquals("response is not JSON", parseError.detail)
    }

    @Test
    fun continueWatchingRequestsCount() {
        val fake = FakePms()
        val plex = PlexClient("http://127.0.0.1:32400", fake)
        plex.continueWatching(20)
        assertEquals("http://127.0.0.1:32400/hubs/continueWatching?count=20", fake.calls[0].first)
        plex.sectionHubs(2, 20)
        assertEquals("http://127.0.0.1:32400/hubs/sections/2?count=20", fake.calls[1].first)
        plex.nextEpisode("4516")
        assertEquals("http://127.0.0.1:32400/library/metadata/4516?includeOnDeck=1", fake.calls[2].first)
    }
}
