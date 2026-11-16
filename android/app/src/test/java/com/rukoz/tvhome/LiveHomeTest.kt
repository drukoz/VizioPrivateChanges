package com.rukoz.tvhome

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class LiveHomeTest {
    @Test
    fun plexDownGivesNoRowsTheOfflineNoticeAndAppsOnly() {
        val plex = PlexClient("http://127.0.0.1:1", PlexTransport { _, _ -> throw java.io.IOException("down") })
        val json = JSONObject(LiveHome(HomeBuilder(plex)) { appTiles { false } }.json())
        assertEquals(0, json.getJSONArray("rows").length())
        val notices = json.getJSONArray("notices")
        assertEquals(1, notices.length())
        assertEquals(PLEX_OFFLINE_NOTICE, notices.getString(0))
        val apps = json.getJSONArray("apps")
        assertEquals(1, apps.length())
        assertEquals("app:amazon-home", apps.getJSONObject(0).getString("id"))
    }

    @Test
    fun plexBaseUrlFromHonoursTheExtraOnlyOnDebuggableHttpUrls() {
        assertEquals(DEFAULT_PLEX_BASE_URL, plexBaseUrlFrom(null, true))
        assertEquals("http://10.0.2.2:32400", plexBaseUrlFrom("http://10.0.2.2:32400", true))
        assertEquals(DEFAULT_PLEX_BASE_URL, plexBaseUrlFrom("http://10.0.2.2:32400", false))
        assertEquals(DEFAULT_PLEX_BASE_URL, plexBaseUrlFrom("file:///x", true))
    }
}
