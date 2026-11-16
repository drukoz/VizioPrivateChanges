package com.rukoz.tvhome

private val WIDE_SIZE = 384 to 216
private val POSTER_SIZE = 240 to 360

val HUB_ORDER = listOf("movie.recentlyadded", "tv.recentlyadded", "tv.startwatching", "movie.topunwatched",
                       "tv.moreingenre", "movie.genre", "tv.rediscover", "tv.toprated")
const val MAX_ROWS = 8
const val PLEX_OFFLINE_NOTICE = "Plex is not answering; showing apps only."

private const val SEP = " · "

private fun titles(item: PlexItem): Pair<String, String?> {
    if (item.type == PlexItemType.MOVIE) {
        return item.title to item.year?.toString()
    }
    if (item.type == PlexItemType.EPISODE) {
        val title = item.showTitle ?: item.title
        val subtitle = if (item.seasonIndex != null && item.episodeIndex != null) {
            "S${item.seasonIndex}${SEP}E${item.episodeIndex}${SEP}${item.title}"
        } else {
            item.title
        }
        return title to subtitle
    }
    return item.title to null
}

private fun image(item: PlexItem, shape: ImageShape): String? {
    val path: String?
    val width: Int
    val height: Int
    if (shape == ImageShape.WIDE) {
        path = if (item.type == PlexItemType.EPISODE) {
            if (!item.thumb.isNullOrEmpty()) item.thumb else item.grandparentArt
        } else {
            item.art
        }
        width = WIDE_SIZE.first
        height = WIDE_SIZE.second
    } else {
        path = if (item.type == PlexItemType.EPISODE) {
            if (!item.grandparentThumb.isNullOrEmpty()) item.grandparentThumb else item.thumb
        } else {
            item.thumb
        }
        width = POSTER_SIZE.first
        height = POSTER_SIZE.second
    }
    if (path == null || !path.startsWith("/library/")) return null
    return imagePath(path, width, height)
}

fun plexTile(item: PlexItem, shape: ImageShape): Tile {
    val (title, subtitle) = titles(item)
    val progress = if (item.viewOffsetMs != null && item.durationMs != null && item.durationMs > 0) {
        item.viewOffsetMs.toDouble() / item.durationMs.toDouble()
    } else {
        null
    }
    return Tile(
        id = "plex:" + item.ratingKey,
        title = title,
        subtitle = subtitle,
        image = image(item, shape),
        shape = shape,
        progress = progress,
        action = Action(ActionKind.PLAY_PLEX, item.ratingKey),
    )
}

private fun hubRank(identifier: String): Int? {
    val rank = HUB_ORDER.indexOfFirst { prefix -> identifier == prefix || identifier.startsWith("$prefix.") }
    return if (rank < 0) null else rank
}

private fun hubTitle(hub: Hub, library: Library): String {
    if (hub.title.lowercase().contains(library.title.lowercase())) return hub.title
    return hub.title + SEP + library.title
}

private class RankedRow(val rank: Int, val position: Int, val row: Row)

class HomeBuilder(private val plex: PlexClient) {
    fun home(apps: List<Tile>): Home {
        val notices = mutableListOf<String>()
        val rows: List<Row> = try {
            plexRows().take(MAX_ROWS)
        } catch (e: PlexException) {
            notices.add(PLEX_OFFLINE_NOTICE)
            emptyList()
        } catch (e: java.io.IOException) {
            notices.add(PLEX_OFFLINE_NOTICE)
            emptyList()
        }
        return Home(rows = rows, apps = apps, notices = notices)
    }

    private fun plexRows(): List<Row> {
        val rows = mutableListOf<Row>()
        val items = plex.continueWatching(20)
        if (items.isNotEmpty()) {
            rows.add(
                Row(
                    id = "continueWatching",
                    title = "Continue Watching",
                    kind = RowKind.CONTINUE_WATCHING,
                    tiles = items.map { plexTile(it, ImageShape.WIDE) },
                )
            )
        }
        val candidates = mutableListOf<RankedRow>()
        for ((position, library) in plex.libraries().withIndex()) {
            if (library.type != LibraryType.MOVIE && library.type != LibraryType.SHOW) continue
            val hubs = try {
                plex.sectionHubs(library.sectionId, 20)
            } catch (e: PlexException) {
                continue
            } catch (e: java.io.IOException) {
                continue
            }
            for (hub in hubs) {
                val rank = hubRank(hub.identifier) ?: continue
                if (hub.items.isEmpty()) continue
                candidates.add(
                    RankedRow(
                        rank,
                        position,
                        Row(
                            id = "hub:" + hub.identifier,
                            title = hubTitle(hub, library),
                            kind = RowKind.PLEX_HUB,
                            tiles = hub.items.map { plexTile(it, ImageShape.POSTER) },
                        )
                    )
                )
            }
        }
        rows.addAll(candidates.sortedWith(compareBy({ it.rank }, { it.position })).map { it.row })
        return rows
    }
}
