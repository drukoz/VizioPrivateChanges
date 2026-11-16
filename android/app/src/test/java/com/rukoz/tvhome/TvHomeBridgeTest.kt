package com.rukoz.tvhome

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TvHomeBridgeTest {
    @Test
    fun validActionRuns() {
        var seen: Action? = null
        val bridge = TvHomeBridge { action ->
            seen = action
            ActionResult(true, "Opening Netflix")
        }
        val reply = bridge.handle("""{"kind":1,"target":"com.netflix.ninja"}""")
        assertEquals(Action(ActionKind.OPEN_APP, "com.netflix.ninja"), seen)
        assertEquals(ActionResult(true, "Opening Netflix").toJson().toString(), reply)
    }

    @Test
    fun arrayIsRejected() {
        val bridge = TvHomeBridge { ActionResult(true, "unused") }
        val reply = JSONObject(bridge.handle("[1]"))
        assertFalse(reply.getBoolean("ok"))
        assertTrue(reply.getString("message").startsWith("action must be a dict"))
    }

    @Test
    fun garbageIsRejected() {
        val bridge = TvHomeBridge { ActionResult(true, "unused") }
        for (body in listOf("", "{")) {
            val reply = JSONObject(bridge.handle(body))
            assertFalse(reply.getBoolean("ok"))
            assertEquals("body must be UTF-8 JSON", reply.getString("message"))
        }
    }

    @Test
    fun badKindIsRejected() {
        var called = false
        val bridge = TvHomeBridge {
            called = true
            ActionResult(true, "unused")
        }
        val reply = JSONObject(bridge.handle("""{"kind":9,"target":"x"}"""))
        assertFalse(reply.getBoolean("ok"))
        assertFalse(called)
    }

    @Test
    fun runValueErrorIsReported() {
        val bridge = TvHomeBridge { throw IllegalArgumentException("nope") }
        val reply = JSONObject(bridge.handle("""{"kind":1,"target":"com.netflix.ninja"}"""))
        assertFalse(reply.getBoolean("ok"))
        assertEquals("nope", reply.getString("message"))
    }

    @Test
    fun runCrashIsInternalError() {
        val bridge = TvHomeBridge { throw RuntimeException("boom") }
        val reply = JSONObject(bridge.handle("""{"kind":1,"target":"com.netflix.ninja"}"""))
        assertFalse(reply.getBoolean("ok"))
        assertEquals("internal error", reply.getString("message"))
    }
}
