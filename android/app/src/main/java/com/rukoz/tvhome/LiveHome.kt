package com.rukoz.tvhome

const val DEFAULT_PLEX_BASE_URL = "http://192.168.1.196:32400"
const val EXTRA_PLEX_BASE_URL = "plexBaseUrl"

/** The intent extra wins only on a debuggable build and only when it starts with "http://"; otherwise the default. */
fun plexBaseUrlFrom(extra: String?, debuggable: Boolean): String {
    if (debuggable && extra != null && extra.startsWith("http://")) return extra
    return DEFAULT_PLEX_BASE_URL
}

class LiveHome(private val builder: HomeBuilder, private val apps: () -> List<Tile>) {
    fun json(): String = builder.home(apps()).toJson().toString()
}
