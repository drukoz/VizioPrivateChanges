package com.rukoz.tvhome

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.util.Log

class ActionRunner(private val context: android.content.Context, private val planner: ActionPlanner) {
    fun run(action: Action): ActionResult {
        val step = planner.plan(action)
        Log.i(HomeActivity.TAG, "action ${action.kind.name} -> ${step.kind.name}")
        return when (step.kind) {
            StepKind.LAUNCH_PACKAGE -> launchPackage(step.pkg!!)
            StepKind.PLEX_DEEP_LINK -> playDeepLink(step.uri!!)
            StepKind.AMAZON_HOME -> {
                TakeoverPause.start(context.applicationContext)
                context.applicationContext.startActivity(
                    Intent(Intent.ACTION_MAIN)
                        .addCategory(Intent.CATEGORY_HOME)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
                ActionResult(true, "Amazon Home for 15 minutes")
            }
            StepKind.REFUSE -> ActionResult(false, step.message!!)
        }
    }

    private fun launchPackage(pkg: String): ActionResult {
        val pm = context.applicationContext.packageManager
        val label = KNOWN_APPS.firstOrNull { it.pkg == pkg }?.title ?: pkg
        val intent = pm.getLeanbackLaunchIntentForPackage(pkg) ?: pm.getLaunchIntentForPackage(pkg)
        if (intent == null) return ActionResult(false, "$label is not installed.")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.applicationContext.startActivity(intent)
        return ActionResult(true, "Opening $label")
    }

    private fun playDeepLink(uri: String): ActionResult {
        val appContext = context.applicationContext
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(uri))
            .setPackage(PLEX_PACKAGE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (appContext.packageManager.resolveActivity(intent, 0) == null) {
            return launchPackage(PLEX_PACKAGE)
        }
        return try {
            appContext.startActivity(intent)
            ActionResult(true, "Playing in Plex")
        } catch (e: ActivityNotFoundException) {
            launchPackage(PLEX_PACKAGE)
        }
    }
}
