# TV dashboard: plan (RUK-2394)

Kind: **Program**. Built on `docs/dashboard/system-map.md` and `docs/dashboard/reuse-ledger.md`.

## Assumptions (the owner corrects these in a comment or in PR review)

1. **"Uninstall the junk ad apps" can't be done on this TV**: SmartCast has no uninstall, and the apps are part of VIZIO's home screen, which VIZIO serves. We replace what the household sees instead. The dashboard opens when the TV turns on and whenever it returns to VIZIO's home, so VIZIO's home shows for a second or two at most.
2. **The server runs on the owner's Mac** (`192.168.1.45`) as a user LaunchAgent. The TrueNAS box would also work (Docker), but we have no access to it. We'll revisit if the Mac isn't always on.
3. **No Plex sign-in for now.** The Plex server lets the Mac read without a token. If spike S2 shows Plex's Cast app needs one, a later subtask adds Plex's PIN link (the owner types a code at plex.tv/link).
4. **Rows:** Continue Watching first, then Plex's own suggestion hubs for the video libraries (Movies, TV Shows, Anime), in this order of hub identifier prefixes: `movie.recentlyadded`, `tv.recentlyadded`, `tv.startwatching`, `movie.topunwatched`, `tv.moreingenre`, `movie.genre`, `tv.rediscover`, `tv.toprated`. Empty hubs are skipped, and there are at most 8 rows. Music and photos are left out. A hub whose title doesn't name its library gets the library added ("Start Watching · Anime").
5. **Apps row:** what the owner picks on the TV-test card. Until then: Plex, Netflix, YouTube, Prime Video, Disney+, Fire TV Stick, then VIZIO Home last.
6. **Remote:** Back on the dashboard does nothing. The remote's home (V) key goes to VIZIO's home, and the watcher brings the dashboard back within about 3 s. The "VIZIO Home" tile pauses the takeover for 15 minutes.
7. **OK on a Plex tile plays at once**, resuming where it stopped. For a show it plays the next unwatched episode. A details screen ("play from start") comes later, if the owner wants it.
8. The **Fire TV Stick's own ads** are out of scope: it's a separate device, and changing it needs ADB debugging, which the owner hasn't asked for.

## Cheaper route, for the record

Opening the Plex app automatically at switch-on would give Continue Watching and suggestions for about a day of work, without the app row. We're building the full dashboard as asked. If S1 fails, this becomes the fallback.

## Target architecture

```
TV (Conjure web runtime)                Mac: python3 -m vizio_privacy dashboard serve
  index.html / app.js / app.css  --HTTP-->  dashboard/server.py  (static, /api/home, /api/action, /img)
                                             dashboard/service.py (rows + actions)
                                               |-- plex.py  --HTTP 32400--> Plex (TrueNAS)
                                               |-- apps.py  (pinned launch table)
                                               `-- api.py   --HTTPS 7345--> TV SmartCast API
                                             dashboard/watcher.py (M2: power-on / home takeover)
```

| Module | Holds | Status |
|---|---|---|
| `vizio_privacy/api.py` | + `PowerState`, `RemoteKey`, `AppConfig`, `InputState`; `power_state`, `current_app`, `launch_app`, `press_key`, `current_input`, `set_input`, `list_inputs` | M1-T1 |
| `vizio_privacy/plex.py` | GDM discovery; `PlexClient` (identity, libraries, continue watching, section hubs, item, next episode, play queue, image URL); `PlexItem`, `Hub`, `Library`, enums | M1-T2 |
| `vizio_privacy/dashboard/model.py` | The contract below: enums, dataclasses, JSON both ways | M1-T3 |
| `vizio_privacy/apps.py` | `AppId` and the pinned launch table | M1-T4 |
| `vizio_privacy/dashboard/service.py` | Builds `Home` from Plex and apps; runs actions | M1, after S1/S2 |
| `vizio_privacy/dashboard/server.py` | `ThreadingHTTPServer`: `/`, `/static/*`, `/api/home`, `/api/action`, `/img` | M1, after S1 |
| `vizio_privacy/dashboard/static/` | `index.html`, `app.js`, `app.css`: rows, focus, keys | M1, after S1 |
| `cli.py` | `dashboard serve`, `dashboard open` (M1); `install`, `uninstall`, `status` (M2) | M1/M2 |
| `vizio_privacy/dashboard/watcher.py`, `launchd.py` | Takeover loop; LaunchAgent | M2 |

## Contract: page ↔ server (M1-T3 codes it)

Enums are integers on the wire (company rule). Text appears only in labels.

- `RowKind`: `CONTINUE_WATCHING = 0`, `PLEX_HUB = 1`
- `ActionKind`: `PLAY_PLEX = 0`, `OPEN_APP = 1`, `SWITCH_INPUT = 2`, `VIZIO_HOME = 3`
- `ImageShape`: `POSTER = 0` (2:3), `WIDE = 1` (16:9), `ICON = 2` (app tile)

`GET /api/home` →

```json
{"version": 1,
 "rows": [{"id": "continueWatching", "title": "Continue Watching", "kind": 0,
           "tiles": [{"id": "plex:4619", "title": "Show name", "subtitle": "S2 · E5 · Episode name",
                      "image": "/img?p=%2Flibrary%2Fmetadata%2F4619%2Fthumb%2F1790131474&w=384&h=216",
                      "shape": 1, "progress": 0.42, "action": {"kind": 0, "target": "4619"}}]}],
 "apps": [{"id": "app:1", "title": "Netflix", "subtitle": null, "image": "/static/apps/1.png",
           "shape": 2, "progress": null, "action": {"kind": 1, "target": "1"}}],
 "notices": ["Plex is not answering; showing apps only."]}
```

`POST /api/action` with `{"kind": <ActionKind>, "target": "<string>"}` → `{"ok": true, "message": "Opening Netflix"}`. A bad `kind` or a missing `target` answers 400 with `ok: false`.

`GET /img?p=<Plex image path starting with /library/>&w=<int 1..1920>&h=<int 1..1080>` → JPEG from Plex's `/photo/:/transcode`. Anything else answers 400.

Tile rules (service): a movie's title is its title and its subtitle is the year. An episode's title is the show's name and its subtitle is `S<season> · E<episode> · <title>`. A show's title is its title, with no subtitle. The Continue Watching row is `WIDE`: an episode uses its own `thumb`, a movie its `art`. Every other row is `POSTER`: `thumb`, or `grandparentThumb` for an episode. `progress` is `viewOffset / duration` when both exist.

## What we don't build

A media player (Plex plays). A Plex sign-in, until S2 says it's needed. Settings screens on the TV (the config file and the CLI do that). Anything on the Fire TV Stick. Network changes of any kind.

## Milestones

**M1 — Your home screen on the TV** (branch `feat/tv-dashboard-m1`). End state: `python3 -m vizio_privacy --host 192.168.1.130 dashboard serve` on the Mac, then `dashboard open`, shows the rows and apps on the TV. The remote moves around, and OK resumes a show or opens an app.

| Task | Depends on | Notes |
|---|---|---|
| T1 TV control calls in `api.py` | — | Now |
| T2 Plex client `plex.py` | — | Now |
| T3 Contract `dashboard/model.py` | — | Now |
| T4 App table `apps.py` | — | Now |
| T5 Service `dashboard/service.py` | T1-T4, S2 | Play route chosen by S2 |
| T6 Server `dashboard/server.py` | T3 | Built against a fake service |
| T7 Page `static/` | T3, S1 | Language level from S1's user agent |
| T8 CLI `dashboard serve` / `open` | T5, T6 | |
| T9 End-to-end test: mock TV + fake Plex + real HTTP on 127.0.0.1 | T8 | QA Engineer or Test Writer |
| Live check with the owner | T9 | CTO only |

**M2 — It replaces VIZIO's home** (branch `feat/tv-dashboard-m2`, cut from M1's). It covers:
- the watcher: on power-on, or when the current app is VIZIO's home, it launches the dashboard, and it leaves HDMI inputs and other apps alone;
- the VIZIO Home pause;
- the config file `~/.vizio-privacy/dashboard.json`;
- `dashboard install`, `uninstall` and `status` (LaunchAgent) and logging;
- notices for "Plex offline" and "TV offline";
- QA verification;
- README how-to.
It ends with the CTO installing the service, with the owner's OK.

**Later, only if the owner asks:** a details screen, next-episode autoplay, artwork backgrounds, a clock.

## Risks

- **S1 fails** (the runtime won't load our URL, or keys don't reach it): fall back to opening the Plex app at switch-on (above), or a Cast receiver page shown without remote control.
- **S2 fails**: OK on a Plex tile opens the Plex app at its home instead of resuming the show. A later subtask can try Plex's remote-control protocol or the PIN-link token.
- **VIZIO firmware updates** can change app ids or the runtime. The app table is pinned to the 2026-11-16 catalog, and `dashboard status` (M2) reports launch failures.
- **The Mac must be on**, or the TV shows VIZIO's home as before. Nothing breaks.
- **Public repository**: Plex titles, server identifiers and tokens never enter it. Test data comes from the CTO's scrubbed captures (`tests/fixtures/`).
