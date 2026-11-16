package com.rukoz.tvhome

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

private fun errorBody(message: String): String =
    JSONObject().put("ok", false).put("message", message).toString()

class ApiHandlersTest {
    private val home = """{"version":1,"rows":[],"apps":[],"notices":[]}"""

    private fun handlers(
        homeJson: () -> String = { home },
        images: ImageSource = ImageSource { _, _, _ -> null },
        icons: IconSource = IconSource { null },
    ): ApiHandlers = ApiHandlers(homeJson, images, icons)

    @Test
    fun homeIsServed() {
        val r = handlers().route("/api/home", null)!!
        assertEquals(200, r.status)
        assertEquals("application/json", r.mimeType)
        assertEquals(home, String(r.body, Charsets.UTF_8))
        assertEquals("no-store", r.cacheControl)
    }

    @Test
    fun homeFailureIs500() {
        val r = handlers(homeJson = { throw RuntimeException("plex is down") }).route("/api/home", null)!!
        assertEquals(500, r.status)
        assertEquals("application/json", r.mimeType)
        assertEquals(errorBody("internal error"), String(r.body, Charsets.UTF_8))
        assertEquals("no-store", r.cacheControl)
    }

    @Test
    fun unknownApiIs404() {
        val r = handlers().route("/api/action", null)!!
        assertEquals(404, r.status)
        assertEquals(errorBody("not found"), String(r.body, Charsets.UTF_8))
        assertEquals("no-store", r.cacheControl)
    }

    @Test
    fun imageIsServed() {
        var seen: Triple<String, Int, Int>? = null
        val pixels = byteArrayOf(1, 2, 3, 4)
        val source = ImageSource { p, w, h ->
            seen = Triple(p, w, h)
            Pair("image/jpeg", pixels)
        }
        val r = handlers(images = source).route(
            "/img",
            "p=%2Flibrary%2Fmetadata%2F1%2Fthumb%2F2&w=240&h=360",
        )!!
        assertEquals(Triple("/library/metadata/1/thumb/2", 240, 360), seen)
        assertEquals(200, r.status)
        assertEquals("image/jpeg", r.mimeType)
        assertEquals(pixels.toList(), r.body.toList())
        assertEquals("max-age=86400", r.cacheControl)
    }

    @Test
    fun badImageQueryIs400() {
        for (query in listOf("p=%2Fother&w=1&h=1", null)) {
            val r = handlers().route("/img", query)!!
            assertEquals(400, r.status)
            assertEquals(errorBody("bad image query"), String(r.body, Charsets.UTF_8))
            assertEquals("no-store", r.cacheControl)
        }
    }

    @Test
    fun missingImageIs502() {
        val r = handlers().route("/img", "p=%2Flibrary%2Fmetadata%2F1%2Fthumb%2F2&w=240&h=360")!!
        assertEquals(502, r.status)
        assertEquals(errorBody("image not available"), String(r.body, Charsets.UTF_8))
    }

    @Test
    fun iconIsServed() {
        val png = byteArrayOf(-119, 80, 78, 71)
        val r = handlers(icons = IconSource { pkg ->
            if (pkg == "com.netflix.ninja") png else null
        }).route("/appicon", "pkg=com.netflix.ninja")!!
        assertEquals(200, r.status)
        assertEquals("image/png", r.mimeType)
        assertEquals(png.toList(), r.body.toList())
        assertEquals("max-age=86400", r.cacheControl)
    }

    @Test
    fun badIconQueryIs400() {
        for (query in listOf("pkg=..%2Fx", "pkg=a", "w=1", "pkg=com.netflix.ninja&pkg=com.netflix.ninja")) {
            val r = handlers().route("/appicon", query)!!
            assertEquals(400, r.status)
            assertEquals(errorBody("bad app icon query"), String(r.body, Charsets.UTF_8))
            assertEquals("no-store", r.cacheControl)
        }
    }

    @Test
    fun missingIconIs404() {
        val r = handlers().route("/appicon", "pkg=com.netflix.ninja")!!
        assertEquals(404, r.status)
        assertEquals(errorBody("no such app"), String(r.body, Charsets.UTF_8))
    }

    @Test
    fun otherPathsAreNotOurs() {
        assertNull(handlers().route("/static/index.html", null))
        assertNull(handlers().route("/", null))
    }
}
