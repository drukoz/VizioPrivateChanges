package com.rukoz.tvhome

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test
import org.json.JSONArray
import org.json.JSONObject

class ActionsTest {
    private companion object {
        const val BASE = "http://127.0.0.1:32400"
    }

    /** Answers by the part of the URL after the base URL, query included; 404 otherwise; records every request. */
    private class FakePms : PlexTransport {
        val requests = mutableListOf<String>()

        private fun metadata(key: String, type: String, title: String): JSONObject =
            JSONObject().put("ratingKey", key).put("type", type).put("title", title)

        private fun container(vararg items: JSONObject): String = JSONObject().put(
            "MediaContainer",
            JSONObject().put("Metadata", JSONArray().apply { items.forEach { put(it) } }),
        ).toString()

        private val routes: Map<String, String> = mapOf(
            "/identity" to JSONObject().put(
                "MediaContainer",
                JSONObject().put("machineIdentifier", "abc123").put("version", "1"),
            ).toString(),
            "/library/metadata/10" to container(
                metadata("10", "movie", "M").put("viewOffset", 5000)),
            "/library/metadata/20" to container(
                metadata("20", "show", "S")),
            "/library/metadata/20?includeOnDeck=1" to container(
                metadata("20", "show", "S").put("OnDeck", JSONObject().put("Metadata",
                    JSONArray().put(metadata("21", "episode", "E").put("viewOffset", 7000))))),
        )

        override fun get(url: String, headers: Map<String, String>): PlexResponse {
            val rest = if (url.startsWith(BASE)) url.substring(BASE.length) else url
            requests.add(rest)
            val body = routes[rest] ?: return PlexResponse(404, "Not Found")
            return PlexResponse(200, body)
        }
    }

    private fun fakePlex(fake: FakePms): PlexClient = PlexClient(BASE, fake)

    @Test
    fun moviePlansDeepLinkWithResumeOffset() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.PLAY_PLEX, "10"))
        assertEquals(StepKind.PLEX_DEEP_LINK, step.kind)
        assertEquals(
            "plex://server://abc123/com.plexapp.plugins.library/library/metadata/10?viewOffset=5000&autoPlay=1",
            step.uri,
        )
    }

    @Test
    fun showPlansDeepLinkForOnDeckEpisode() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.PLAY_PLEX, "20"))
        assertEquals(StepKind.PLEX_DEEP_LINK, step.kind)
        assertEquals(
            "plex://server://abc123/com.plexapp.plugins.library/library/metadata/21?viewOffset=7000&autoPlay=1",
            step.uri,
        )
    }

    @Test
    fun missingItemFallsBackToOpeningPlex() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.PLAY_PLEX, "99"))
        assertEquals(StepKind.LAUNCH_PACKAGE, step.kind)
        assertEquals(PLEX_PACKAGE, step.pkg)
    }

    @Test
    fun transportFailureFallsBackToOpeningPlex() {
        val transport = PlexTransport { _, _ -> throw java.io.IOException("connection refused") }
        val step = ActionPlanner(PlexClient(BASE, transport)).plan(Action(ActionKind.PLAY_PLEX, "10"))
        assertEquals(StepKind.LAUNCH_PACKAGE, step.kind)
        assertEquals(PLEX_PACKAGE, step.pkg)
    }

    @Test
    fun identityIsAskedOnceOverTwoPlans() {
        val fake = FakePms()
        val planner = ActionPlanner(fakePlex(fake))
        planner.plan(Action(ActionKind.PLAY_PLEX, "10"))
        planner.plan(Action(ActionKind.PLAY_PLEX, "20"))
        assertEquals(1, fake.requests.count { it == "/identity" })
    }

    @Test
    fun nonDigitRatingKeyThrows() {
        val planner = ActionPlanner(fakePlex(FakePms()))
        assertThrows(IllegalArgumentException::class.java) {
            planner.plan(Action(ActionKind.PLAY_PLEX, "12a"))
        }
    }

    @Test
    fun openAppPlansPackageLaunch() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.OPEN_APP, "com.netflix.ninja"))
        assertEquals(StepKind.LAUNCH_PACKAGE, step.kind)
        assertEquals("com.netflix.ninja", step.pkg)
    }

    @Test
    fun openAppRejectsPathTraversal() {
        val planner = ActionPlanner(fakePlex(FakePms()))
        assertThrows(IllegalArgumentException::class.java) {
            planner.plan(Action(ActionKind.OPEN_APP, "../x"))
        }
    }

    @Test
    fun amazonHomePlansAmazonHome() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.AMAZON_HOME, "home"))
        assertEquals(StepKind.AMAZON_HOME, step.kind)
    }

    @Test
    fun switchInputRefuses() {
        val step = ActionPlanner(fakePlex(FakePms())).plan(Action(ActionKind.SWITCH_INPUT, "hdmi2"))
        assertEquals(StepKind.REFUSE, step.kind)
    }

    @Test
    fun bridgeReportsBadPackageAsNotOk() {
        val plex = fakePlex(FakePms())
        val reply = TvHomeBridge { a -> ActionResult(true, ActionPlanner(plex).plan(a).kind.name) }
            .handle("""{"kind":1,"target":"../x"}""")
        assertFalse(JSONObject(reply).getBoolean("ok"))
    }
}
