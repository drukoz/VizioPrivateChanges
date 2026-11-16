package com.rukoz.tvhome

import android.content.Context

/**
 * The 15-minute pause of the Home-button takeover, shared by the AMAZON_HOME action (which starts it)
 * and HomeTakeover (which does not bring TV Home forward while it runs). Both run in the app's one process.
 */
object TakeoverPause {
    const val PREFS = "takeover"
    const val KEY_PAUSE_UNTIL_MS = "pauseUntilMs"
    const val PAUSE_MS = 15L * 60L * 1000L

    /** True while nowMs is before the stored end of the pause. */
    fun isPaused(pauseUntilMs: Long, nowMs: Long): Boolean = nowMs < pauseUntilMs

    fun pauseUntil(context: Context): Long =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong(KEY_PAUSE_UNTIL_MS, 0L)

    fun start(context: Context, nowMs: Long = System.currentTimeMillis()) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putLong(KEY_PAUSE_UNTIL_MS, nowMs + PAUSE_MS).apply()
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY_PAUSE_UNTIL_MS).apply()
    }
}
