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
| `vizio_privacy/api.py` | + `PowerState`, `RemoteKey`, `AppConfig`, `InputState`; `power_state`, `current_app`, `launch_app`, `press_key`, `current_input`, `set_input`, `list_inputs` | M1-T1 (RUK-2456) |
| `vizio_privacy/plex.py` | `PlexClient` (identity, libraries, continue watching, section hubs, item, next episode via `includeOnDeck`, play queue, image URL); `PlexItem`, `Hub`, `Library`, enums | M1-T2 (RUK-2458) |
| `vizio_privacy/plex_discovery.py` | GDM discovery: `ServerInfo`, `parse_gdm_reply`, `discover` | M1-T5 (RUK-2461) |
| `vizio_privacy/dashboard/model.py` | The contract below: enums, dataclasses, JSON both ways | M1-T3 (RUK-2459) |
| `vizio_privacy/apps.py` | `AppId` and the pinned launch table | M1-T4 (RUK-2460) |
| `vizio_privacy/dashboard/service.py` | Builds `Home` from Plex and apps; runs actions | M1-T6 (RUK-2465); Plex playback after S2 |
| `vizio_privacy/dashboard/server.py` | `ThreadingHTTPServer`: `/`, `/static/*`, `/api/home`, `/api/action`, `/img` | M1-T7 (RUK-2466) |
| `vizio_privacy/dashboard/static/` | `index.html`, `app.js`, `app.css`: rows, focus, keys | M1-T8 (RUK-2479) |
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

Even after `parse_image_query` accepts it, `p` is untrusted: it can still contain `?`, `&`, `#` or control characters. The server passes it to Plex only as one percent-encoded value of the transcoder's `url` parameter, built with `urllib.parse.urlencode`, and adds the token itself, so `p` can never add or override a Plex query parameter such as `X-Plex-Token`. The T7 spec has a test for `p=/library/x?X-Plex-Token=evil`.

Tile rules (service): a movie's title is its title and its subtitle is the year. An episode's title is the show's name and its subtitle is `S<season> · E<episode> · <title>`. A show's title is its title, with no subtitle. The Continue Watching row is `WIDE`: an episode uses its own `thumb`, a movie its `art`. Every other row is `POSTER`: `thumb`, or `grandparentThumb` for an episode. `progress` is `viewOffset / duration` when both exist.

## What we don't build

A media player (Plex plays). A Plex sign-in, until S2 says it's needed. Settings screens on the TV (the config file and the CLI do that). Anything on the Fire TV Stick. Network changes of any kind.

## Milestones

**M1 — Your home screen on the TV** (RUK-2455, branch `feat/tv-dashboard-m1`). End state: `python3 -m vizio_privacy --host 192.168.1.130 dashboard serve` on the Mac, then `dashboard open`, shows the rows and apps on the TV. The remote moves around, and OK resumes a show or opens an app.

| Task | Depends on | Notes |
|---|---|---|
| T1 TV control calls in `api.py` (RUK-2456) | — | Started 2026-11-16 |
| T2 Plex client `plex.py` (RUK-2458) | — | Started 2026-11-16 |
| T3 Contract `dashboard/model.py` (RUK-2459) | — | Started 2026-11-16 |
| T4 App table `apps.py` (RUK-2460) | — | Started 2026-11-16 |
| T5 Plex discovery `plex_discovery.py` (RUK-2461) | — | Started 2026-11-16 |
| T6 Service `dashboard/service.py` (RUK-2465) | T1-T4 | Merged 2026-11-16. Rows, app tiles and app/input actions. Without a `play` callable, OK on a Plex tile opens the Plex app; the S2 route is passed in as `play` later |
| T7 Server `dashboard/server.py` (RUK-2466) | T3 | Merged 2026-11-16, built against a fake service |
| T8 Page `static/` (RUK-2479) | T3, T7 | Merged 2026-11-16, before S1: written in ES5 with `XMLHttpRequest`, which any TV web runtime runs. If S1 fails, only this page is wasted |
| T9 CLI `dashboard serve` / `open` (RUK-2477) | T6, T7 | Merged 2026-11-16. `open` launches `NAME_SPACE` 4, `APP_ID` "1" with our URL (both options, so S1 can try 2), reads `/app/current` back and exits 1 if the TV did not switch |
| T10 End-to-end test (RUK-2478): mock TV + fake Plex + real HTTP on 127.0.0.1 | T9 | Merged 2026-11-16. Runs `serve` and `open` in-process; Plex playback extends the same file |
| Verification in a real browser (RUK-2490): `tests/demo_dashboard.py` launcher + Playwright arrow-key checks against the mock TV and fake Plex | T8, T10 | Merged 2026-11-16: 11 of 11 checks pass, no bugs. The CTO's review made the toast opaque. After Plex playback merges, only playback is re-checked |
| Plex playback (the S2 route, passed in as `play`) | S2 | Waits for the TV test card on RUK-2394 |
| Live check with the owner | T10 | CTO only |

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
