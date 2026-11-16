package com.rukoz.tvhome

/**
 * The launchers whose window changes mean "Amazon's home screen is coming up".
 * UNVERIFIED until the live session reads the real package name on the stick.
 */
val AMAZON_HOME_PACKAGES: Set<String> = setOf("com.amazon.tv.launcher", "com.amazon.firelauncher")

const val TAKEOVER_DEBOUNCE_MS = 500L

enum class Trigger(val value: Int) {
    HOME_KEY(0),
    HOME_WINDOW(1),
    HOME_BROADCAST(2),
}

/** Pure decision logic of the Home-button takeover: no android.* imports, tested on the JVM. */
class TakeoverPolicy {
    var lastLaunchMs: Long = Long.MIN_VALUE / 2
        private set

    /** True when TV Home should be brought forward now; records the launch time when it returns true. */
    fun shouldTakeOver(trigger: Trigger, windowPackage: String?, pauseUntilMs: Long, nowMs: Long): Boolean {
        if (TakeoverPause.isPaused(pauseUntilMs, nowMs)) return false
        if (trigger == Trigger.HOME_WINDOW && windowPackage !in AMAZON_HOME_PACKAGES) return false
        if (nowMs - lastLaunchMs < TAKEOVER_DEBOUNCE_MS) return false
        lastLaunchMs = nowMs
        return true
    }
}
