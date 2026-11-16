package com.rukoz.tvhome

data class KnownApp(val pkg: String, val title: String)

val KNOWN_APPS: List<KnownApp> = listOf(
    KnownApp("com.plexapp.android", "Plex"),
    KnownApp("com.netflix.ninja", "Netflix"),
    KnownApp("com.amazon.firetv.youtube", "YouTube"),
    KnownApp("com.amazon.avod", "Prime Video"),
    KnownApp("com.disney.disneyplus", "Disney+"),
    KnownApp("com.amazon.tv.settings.v2", "Settings"),
)

val AMAZON_HOME_TILE = Tile(
    id = "app:amazon-home",
    title = "Amazon Home",
    subtitle = null,
    image = null,
    shape = ImageShape.ICON,
    progress = null,
    action = Action(ActionKind.AMAZON_HOME, "home"),
)

fun appTile(app: KnownApp): Tile = Tile(
    id = "app:" + app.pkg,
    title = app.title,
    subtitle = null,
    image = "/appicon?pkg=" + app.pkg,
    shape = ImageShape.ICON,
    progress = null,
    action = Action(ActionKind.OPEN_APP, app.pkg),
)

fun appTiles(isInstalled: (String) -> Boolean): List<Tile> =
    KNOWN_APPS.filter { isInstalled(it.pkg) }.map(::appTile) + AMAZON_HOME_TILE
