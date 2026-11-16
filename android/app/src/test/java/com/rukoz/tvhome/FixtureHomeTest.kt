package com.rukoz.tvhome

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class FixtureHomeTest {
    @Test
    fun fixtureFollowsTheContract() {
        val home = JSONObject(FixtureHome.JSON)
        assertEquals(1, home.getInt("version"))
        assertEquals(0, home.getJSONArray("rows").getJSONObject(0).getInt("kind"))
        assertEquals(1, home.getJSONArray("apps").getJSONObject(0).getJSONObject("action").getInt("kind"))
    }
}
