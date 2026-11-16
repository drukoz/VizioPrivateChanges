package com.rukoz.tvhome

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TakeoverPolicyTest {
    private val base = 1_700_000_000_000L

    @Test
    fun homeKeyWhenNotPausedTakesOver() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_KEY, null, 0L, base))
    }

    @Test
    fun secondKeyPressWithinDebounceIsIgnored() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_KEY, null, 0L, base))
        assertFalse(policy.shouldTakeOver(Trigger.HOME_KEY, null, 0L, base + 100))
    }

    @Test
    fun keyPressAfterDebounceTakesOverAgain() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_KEY, null, 0L, base))
        assertTrue(policy.shouldTakeOver(Trigger.HOME_KEY, null, 0L, base + 600))
        assertEquals(base + 600, policy.lastLaunchMs)
    }

    @Test
    fun pausedKeyPressIsIgnoredAndRecordsNothing() {
        val policy = TakeoverPolicy()
        val before = policy.lastLaunchMs
        assertFalse(policy.shouldTakeOver(Trigger.HOME_KEY, null, base + 1000, base))
        assertEquals(before, policy.lastLaunchMs)
    }

    @Test
    fun keyPressAfterThePauseEndsTakesOver() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_KEY, null, base - 1, base))
    }

    @Test
    fun amazonTvLauncherWindowTakesOver() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_WINDOW, "com.amazon.tv.launcher", 0L, base))
    }

    @Test
    fun amazonFireLauncherWindowTakesOver() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_WINDOW, "com.amazon.firelauncher", 0L, base))
    }

    @Test
    fun otherAppWindowDoesNotTakeOver() {
        val policy = TakeoverPolicy()
        assertFalse(policy.shouldTakeOver(Trigger.HOME_WINDOW, "com.netflix.ninja", 0L, base))
        assertEquals(Long.MIN_VALUE / 2, policy.lastLaunchMs)
    }

    @Test
    fun windowWithoutPackageDoesNotTakeOver() {
        val policy = TakeoverPolicy()
        assertFalse(policy.shouldTakeOver(Trigger.HOME_WINDOW, null, 0L, base))
    }

    @Test
    fun homeBroadcastWithoutPackageTakesOver() {
        val policy = TakeoverPolicy()
        assertTrue(policy.shouldTakeOver(Trigger.HOME_BROADCAST, null, 0L, base))
    }
}
