package com.rukoz.tvhome

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class AppCatalogTest {
    @Test
    fun nothingInstalledGivesOnlyTheAmazonHomeTile() {
        assertEquals(listOf(AMAZON_HOME_TILE), appTiles { false })
    }

    @Test
    fun installedAppsKeepCatalogOrderAndAmazonHomeIsLast() {
        val installed = setOf("com.netflix.ninja", "com.amazon.tv.settings.v2")
        val tiles = appTiles { pkg -> pkg in installed }
        assertEquals(
            listOf("app:com.netflix.ninja", "app:com.amazon.tv.settings.v2", "app:amazon-home"),
            tiles.map { it.id },
        )
        assertEquals(
            listOf("Netflix", "Settings", "Amazon Home"),
            tiles.map { it.title },
        )
    }

    @Test
    fun netflixTileJson() {
        val json = JSONObject(appTile(KnownApp("com.netflix.ninja", "Netflix")).toJson().toString())
        assertEquals("/appicon?pkg=com.netflix.ninja", json.getString("image"))
        assertEquals(2, json.getInt("shape"))
        val action = json.getJSONObject("action")
        assertEquals(1, action.getInt("kind"))
        assertEquals("com.netflix.ninja", action.getString("target"))
    }

    @Test
    fun amazonHomeTileActionJson() {
        val json = JSONObject(AMAZON_HOME_TILE.action.toJson().toString())
        assertEquals(4, json.getInt("kind"))
        assertEquals("home", json.getString("target"))
    }
}
