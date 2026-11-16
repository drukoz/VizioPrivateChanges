package com.rukoz.tvhome

const val PLEX_PACKAGE = "com.plexapp.android"

enum class StepKind(val value: Int) {
    LAUNCH_PACKAGE(0),
    PLEX_DEEP_LINK(1),
    AMAZON_HOME(2),
    REFUSE(3),
}

/** pkg: LAUNCH_PACKAGE's package (PLEX_PACKAGE for the Plex fallback); uri: PLEX_DEEP_LINK's link; message: REFUSE's message. */
data class ActionStep(val kind: StepKind, val pkg: String? = null, val uri: String? = null, val message: String? = null)

fun plexDeepLink(machineId: String, ratingKey: String, viewOffsetMs: Int?): String =
    "plex://server://$machineId/com.plexapp.plugins.library/library/metadata/$ratingKey?viewOffset=${viewOffsetMs ?: 0}&autoPlay=1"

class ActionPlanner(private val plex: PlexClient) {
    private var cachedMachineId: String = ""

    fun plan(action: Action): ActionStep = when (action.kind) {
        ActionKind.OPEN_APP -> planOpenApp(action.target)
        ActionKind.PLAY_PLEX -> planPlayPlex(action.target)
        ActionKind.AMAZON_HOME -> ActionStep(StepKind.AMAZON_HOME)
        ActionKind.SWITCH_INPUT, ActionKind.VIZIO_HOME ->
            ActionStep(StepKind.REFUSE, message = "That works only on the VIZIO TV.")
    }

    private fun planOpenApp(target: String): ActionStep {
        if (target.length > MAX_TARGET_LENGTH || !PKG_REGEX.matches(target)) {
            throw IllegalArgumentException("not an app package: $target")
        }
        return ActionStep(StepKind.LAUNCH_PACKAGE, pkg = target)
    }

    private fun planPlayPlex(target: String): ActionStep {
        if (target.isEmpty() || !target.all { it in '0'..'9' }) {
            throw IllegalArgumentException("not a Plex rating key: $target")
        }
        return try {
            if (cachedMachineId.isEmpty()) {
                val machineId = plex.identity().first
                if (machineId.isNotEmpty()) cachedMachineId = machineId
            }
            if (cachedMachineId.isEmpty()) {
                ActionStep(StepKind.LAUNCH_PACKAGE, pkg = PLEX_PACKAGE)
            } else {
                val item = plex.item(target)
                val key: String
                val offset: Int?
                if (item.type == PlexItemType.SHOW) {
                    val next = plex.nextEpisode(target)
                    if (next != null) {
                        key = next.ratingKey
                        offset = next.viewOffsetMs
                    } else {
                        key = item.ratingKey
                        offset = null
                    }
                } else {
                    key = item.ratingKey
                    offset = item.viewOffsetMs
                }
                ActionStep(StepKind.PLEX_DEEP_LINK, uri = plexDeepLink(cachedMachineId, key, offset))
            }
        } catch (e: PlexException) {
            ActionStep(StepKind.LAUNCH_PACKAGE, pkg = PLEX_PACKAGE)
        } catch (e: java.io.IOException) {
            ActionStep(StepKind.LAUNCH_PACKAGE, pkg = PLEX_PACKAGE)
        }
    }
}
