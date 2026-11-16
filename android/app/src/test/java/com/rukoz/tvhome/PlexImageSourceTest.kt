package com.rukoz.tvhome

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PlexImageSourceTest {
    @Test
    fun fetchAsksTheFetcherForTheTranscoderUrlAndReturnsItsPair() {
        val asked = mutableListOf<String>()
        val source = PlexImageSource(PlexClient("http://127.0.0.1:1")) { url ->
            asked.add(url)
            "image/png" to byteArrayOf(1, 2, 3)
        }
        val fetched = source.fetch("/library/metadata/1/thumb/2", 240, 360)
        val expected = PlexClient("http://127.0.0.1:1").imageUrl("/library/metadata/1/thumb/2", 240, 360)
        assertEquals(listOf(expected), asked)
        assertEquals("image/png", fetched!!.first)
        assertArrayEquals(byteArrayOf(1, 2, 3), fetched.second)
    }

    @Test
    fun aFetcherReturningNullGivesNull() {
        val source = PlexImageSource(PlexClient("http://127.0.0.1:1")) { null }
        assertNull(source.fetch("/library/metadata/1/thumb/2", 240, 360))
    }
}
