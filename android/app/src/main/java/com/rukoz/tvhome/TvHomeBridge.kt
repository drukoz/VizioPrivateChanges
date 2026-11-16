package com.rukoz.tvhome

import org.json.JSONTokener

class TvHomeBridge(private val run: (Action) -> ActionResult) {
    @android.webkit.JavascriptInterface
    fun action(json: String): String = handle(json)

    fun handle(json: String): String {
        val value = try {
            JSONTokener(json).nextValue()
        } catch (e: org.json.JSONException) {
            return fail("body must be UTF-8 JSON")
        }
        val action = try {
            Action.fromJson(value)
        } catch (e: IllegalArgumentException) {
            return ActionResult(false, e.message ?: "bad action").toJson().toString()
        }
        val result = try {
            run(action)
        } catch (e: IllegalArgumentException) {
            ActionResult(false, e.message ?: "bad action")
        } catch (e: Exception) {
            ActionResult(false, "internal error")
        }
        return result.toJson().toString()
    }

    private fun fail(msg: String): String = ActionResult(false, msg).toJson().toString()
}
