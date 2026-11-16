package com.rukoz.tvhome

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.util.Log
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent

/**
 * Brings TV Home forward when the Home button is pressed or Amazon's launcher appears,
 * unless the 15-minute Amazon Home pause is running. Switched on over ADB
 * (settings put secure enabled_accessibility_services) because Fire OS 6 has no settings screen.
 */
class HomeTakeover : AccessibilityService() {
    private val policy = TakeoverPolicy()
    private var receiver: BroadcastReceiver? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        val r = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                if (intent?.action == Intent.ACTION_CLOSE_SYSTEM_DIALOGS &&
                    intent.getStringExtra("reason") == "homekey"
                ) {
                    trigger(Trigger.HOME_BROADCAST, null)
                }
            }
        }
        receiver = r
        val filter = IntentFilter(Intent.ACTION_CLOSE_SYSTEM_DIALOGS)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(r, filter, Context.RECEIVER_EXPORTED)
        } else {
            registerReceiver(r, filter)
        }
        Log.i(HomeActivity.TAG, "takeover connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            trigger(Trigger.HOME_WINDOW, event.packageName?.toString())
        }
    }

    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event?.keyCode == KeyEvent.KEYCODE_HOME && event.action == KeyEvent.ACTION_DOWN) {
            return trigger(Trigger.HOME_KEY, null)
        }
        return false
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        receiver?.let {
            try {
                unregisterReceiver(it)
            } catch (e: IllegalArgumentException) {
                // already unregistered
            }
            receiver = null
        }
        super.onDestroy()
    }

    private fun trigger(t: Trigger, pkg: String?): Boolean {
        if (!policy.shouldTakeOver(t, pkg, TakeoverPause.pauseUntil(this), System.currentTimeMillis())) {
            return false
        }
        bringForward()
        Log.i(HomeActivity.TAG, "takeover ${t.name}")
        return true
    }

    private fun bringForward() {
        startActivity(
            Intent(this, HomeActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
        )
    }
}
