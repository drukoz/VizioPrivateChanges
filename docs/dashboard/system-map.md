# TV dashboard: system map (RUK-2394)

Kind: **Program**. It is a new product surface on an existing tool, it talks to two outside systems, and it is about 15-20 subtasks. Written 2026-11-16 from the code on `feat/tv-dejunk` (`6044137`), live read-only probes of the TV and the Plex server, and VIZIO's public app catalog.

## 0. Since 2026-11-16 15:19 UTC: the Fire TV Stick

The owner chose the Fire TV Stick on the Vizio's HDMI-2 as the home screen's device, and asked for the TV to come on to HDMI 2. This section supersedes sections 2, 5 and 6 for the dashboard. Sections 1-9 below describe the Vizio route, which is closed; they stay as the reference for M1's code (page, contract, Plex calls, row rules).

### The stick

| What | Value (source) |
|---|---|
| Model | Fire TV Stick 4K, 1st gen (2018), `AFTMM`: DIAL device description `http://192.168.1.60:60000/dd.xml` (`manufacturer` Amazon, `modelName` AFTMM), read 2026-11-16. Its `friendlyName` contains a person's name: never commit it. |
| OS | Fire OS 6 = Android 7.1, API 25 (Amazon's Fire TV device specifications). Updates until 2029-12-31 (Tom's Guide). Exact build, WebView version: F2. |
| Network | `192.168.1.60` by DHCP. Find it again with SSDP `M-SEARCH` for `urn:dial-multiscreen-org:service:dial:1`: the responder whose description says `AFTMM`. DIAL on 60000, DIAL apps on 8009. ADB on TCP 5555 once the owner switches on ADB debugging. |
| Connection | Vizio HDMI-2 (CEC name "Fire TV Stick"). The Vizio's `USB Power` is `Always On`. |
| Remote | Fire TV voice remote with TV power and volume (CEC). |

### How we reach it

ADB over Wi-Fi from the Mac, CTO only, in sessions agreed with the owner: `/Volumes/Storage/paperclip/toolchains/android-sdk/platform-tools/adb` (37.0.1), with `ANDROID_USER_HOME=/Users/drukoz/.vizio-privacy/adb` (the key the stick trusts) and `ANDROID_ADB_SERVER_PORT=5038` (its own ADB server, so the engineers' emulator server never holds that key). Any ADB command can wake the stick, and a waking stick turns the TV on through CEC.

### Workflows on the stick (target)

1. **Switch on:** Home or power on the Fire TV remote wakes the stick; CEC One Touch Play turns the TV on to HDMI-2; Amazon's home appears and the takeover (F2/F4) brings TV Home to the front. With the Vizio remote, the TV comes on to its last-used input, HDMI-2 once it was last turned off there.
2. **Resume a show:** OK on a Continue Watching tile, then the Plex deep link, and the Plex app plays from `viewOffset`. Back or Home returns to TV Home.
3. **Open an app:** OK on Netflix launches its leanback launch intent. Home returns to TV Home.
4. **Amazon's home on purpose:** the "Amazon Home" tile pauses the takeover for 15 minutes and opens Amazon's launcher (app store, Amazon's own settings).
5. **Install or update:** the CTO runs `adb install -r` from the Mac and switches the takeover service on with `settings put secure` (F2 decides the exact keys).
6. **Tracking off:** the CTO runs `python3 -m vizio_privacy firetv harden --apply` from the Mac (M2-T7).

### TV facts found for the HDMI-2 request (2026-11-16, read live)

| Item | Finding |
|---|---|
| `system/input_at_power_on` | `T_LIST_X_V1`, choices `SmartCast`, `Last Used TV Input`. Set to `Last Used TV Input` (was `SmartCast`). |
| `devices/current_input` | `VALUE` `SMARTCAST`, `ENABLED` `FALSE`, `HIDDEN` `TRUE`. `PUT {"REQUEST":"MODIFY","VALUE":"HDMI-2","HASHVAL":<current>}` answers HTTP 200 with `RESULT` `FAILURE`, in standby and when on. |
| `system/hide_from_input_list` | One `T_LIST_V1` per input: `tuner` (TV), `comp`, `hdmi1`, `hdmi2`; choices `Visible`, `Hidden`; all `Visible`. SmartCast is not listed. |
| `system/cec` | `cec_function` Enabled, `one_touch_play` Enabled, `device_discovery` (action). |
| `system/power_mode` | Quick Start. Key `CODESET 11` `CODE 1` powers on and `CODE 0` powers off over `/key_command/` (used once, 2026-11-16). |

### Still to read in F2

Fire OS build (`getprop ro.build.version.name`), WebView package and version, installed packages (Plex, Netflix, YouTube, Prime Video, Disney+ and their names), Amazon's privacy settings and their `settings` keys, whether third-party accessibility services can be switched on, and whether the stick can read Plex without a token.

## 1. Purpose and users

The owner's household watches a VIZIO D24f-J09 SmartCast TV. Its home screen is VIZIO's, full of ads and WatchFree+, and the TV gives no way to uninstall apps. The dashboard replaces what the household sees: a home screen of their own, with **Continue Watching** and suggestions from their Plex server and a bottom row of a few chosen apps, driven with the TV remote. The household uses it daily. The owner (or the CTO in an agreed session) installs and updates it.

## 2. Where it runs

| Part | Where | Notes |
|---|---|---|
| Dashboard page (HTML/CSS/JS) | The TV's built-in web-app runtime (VIZIO "Conjure", `NAME_SPACE` 2/4), opened through `PUT /app/launch` with our URL in `MESSAGE` | To be proved live (spike S1). Engine version unknown until S1 reads its user agent. |
| Dashboard server and home-screen watcher | The owner's Mac, `192.168.1.45` (en0), macOS 26, `/usr/bin/python3` 3.9.6, as a user LaunchAgent | Application Firewall off (checked 2026-11-16). A page served on `0.0.0.0:8790` was loaded over the LAN address by headless Chrome (dry run S4). |
| Plex Media Server | TrueNAS box `192.168.1.196:32400`, PMS 1.43.5 | Found by GDM. Lets the Mac read without a token (`/hubs/...` answered 200 with no token). Refuses a transient token without auth (`/security/token` 400). |
| TV | `192.168.1.130`, SmartCast `prod 59.54`, API `3.3.3-2538.0001`, Cast built in | Paired: token in `/Users/drukoz/.vizio-privacy/192.168.1.130.json`. HDMI-2 is named "Fire TV Stick". Power mode Quick Start. |

## 3. Build, test and release

Unchanged from the guide: `python3 -m unittest discover -s tests -v` on Python 3.9 and newer, standard library only, no CI. A change reaches the household when the owner merges a pull request into `main` and the service is (re)installed on the Mac with `dashboard install`. Dangerous: anything that contacts the real TV (only the CTO, in an agreed session), and committing private data (the repository is public).

## 4. External systems

**SmartCast local API** (HTTPS 7345, self-signed, header `AUTH: <token>`), hand-written client `vizio_privacy/api.py`, reference pyvizio 0.1.64 (`raman325/pyvizio`, MIT; async aiohttp, so not usable as a library here). Calls the dashboard needs, with real answers read 2026-11-16 (fixtures in `tests/fixtures/tv/`):

| Call | Body / answer |
|---|---|
| `GET /state/device/power_mode` | `ITEMS[0].VALUE`: `0` standby (read live), `1` on (pyvizio). |
| `GET /app/current` | `ITEM.VALUE` = `{"APP_ID": "707", "NAME_SPACE": 345, "MESSAGE": "dtv-system://power"}` in standby (read live). Home screen and our page: S1. |
| `PUT /app/launch` | `{"VALUE": {"MESSAGE": <str or null>, "NAME_SPACE": <int>, "APP_ID": <str>}}` (pyvizio `LaunchAppConfigCommand`). Answer: S1. |
| `PUT /key_command/` | `{"KEYLIST": [{"CODESET": <int>, "CODE": <int>, "ACTION": "KEYPRESS"}]}`. Codes (pyvizio const): DOWN 3/0, LEFT 3/1, OK 3/2, RIGHT 3/7, UP 3/8, BACK 4/0, HOME 4/15, EXIT 9/0. |
| `GET /menu_native/dynamic/tv_settings/devices/current_input` | `ITEMS[0]`: `VALUE` `"SMARTCAST"`, `HASHVAL` (read live). |
| `PUT` the same path | `{"REQUEST": "MODIFY", "VALUE": "<input NAME, e.g. HDMI-2>", "HASHVAL": <current>}` (pyvizio `ChangeInputCommand`). Live: S3. |
| `GET .../devices/name_input` | Inputs: `cast` (`SMARTCAST`), `hdmi1`, `hdmi2` (`NAME` "HDMI-2", `VALUE.NAME` "Fire TV Stick"), `comp`, `tuner`. |

**VIZIO app catalog** (public, no auth): `https://scfs.vizio.com/appservice/vizio_apps_prod.json` (id, name, country) and `app_availability_prod.json` (id → `app_type_payload`, the launch body). 348 apps on 2026-11-16: `NAME_SPACE` 2 (344, web apps; 3 carry a URL in `MESSAGE`, e.g. WatchFree+ `http://127.0.0.1:12345/scfs/sctv/main.html#/watchfreeplus`), 3 (native: Netflix, Apple TV+), 5 (YouTube, YouTube TV), 0 (Google Cast apps with a Cast `LOAD` message: XUMO Play, Pluto TV), 4 (one). pyvizio treats 2 and 4 as equivalent; its SmartCast Home config is `NAME_SPACE` 4, `APP_ID` "1", `MESSAGE` `http://127.0.0.1:12345/scfs/sctv/main.html`.

**Google Cast receiver on the TV**, reached through `/app/launch` with `NAME_SPACE` 0: `APP_ID` is the Cast app id and `MESSAGE` is `{"CAST_NAMESPACE": ..., "CAST_MESSAGE": {...}}`. Plex's Cast app is `9AC194DC` (pychromecast `PlexController`, MIT). Its `LOAD` message (pychromecast `media_to_chromecast_command`) carries the play queue, offset in seconds and the server's address. Live: S2.

**Plex Media Server HTTP API**, JSON with `Accept: application/json`. Community OpenAPI description: `LukasParke/plex-api-spec` (MIT, active). Calls, all checked live without a token on 2026-11-16 (scrubbed fixtures in `tests/fixtures/plex/`):

| Call | Use |
|---|---|
| GDM: UDP `M-SEARCH * HTTP/1.1` to `239.0.0.250:32414` | Find the server: reply headers `Name`, `Port`, `Resource-Identifier`, `Version`. |
| `GET /identity` | `machineIdentifier`, `version`. |
| `GET /library/sections` | Libraries: 1 Movies (movie), 2 TV Shows (show), 3 Anime (show), 4 Music (artist). |
| `GET /hubs/continueWatching` | One hub, `Metadata[]` of episodes and movies with `viewOffset` and `duration` (19 items). |
| `GET /hubs?count=N` | Home hubs: `home.continue`, `home.ondeck`, `home.movies.recent`, `home.television.recent`, music/photos/videos/playlists. |
| `GET /hubs/sections/<id>?count=N` | Suggestions per library: Movies `movie.inprogress`, `movie.recentlyreleased`, `movie.recentlyadded`, `movie.genre.*`, `movie.by.actor.or.director.*`, `movie.topunwatched`, `movie.recentlyviewed`; shows `tv.inprogress`, `tv.recentlyaired`, `tv.recentlyadded`, `tv.startwatching`, `tv.rediscover`, `tv.moreingenre`, `tv.toprated`, `tv.recentlyviewed`. |
| `POST /playQueues?type=video&uri=server://<machine>/com.plexapp.plugins.library/library/metadata/<ratingKey>&own=1&...` | Play queue for Cast playback: `playQueueID`, `playQueueSelectedItemID`. |
| `GET /photo/:/transcode?width=&height=&minSize=1&upscale=1&url=<thumb path>` | Resized posters (our server proxies them). |
| `GET /status/sessions` | Verification only: who is playing what. |

Media is mostly MKV/HEVC (the sampled Continue Watching item: MKV, HEVC Main 10, AAC), so a home-made browser player would need Plex to transcode; handing playback to Plex's own player avoids that.

**macOS launchd**: a LaunchAgent plist in `~/Library/LaunchAgents/` started with `launchctl bootstrap gui/<uid>`.

## 5. Surfaces

- **TV dashboard page**: rows of poster tiles (Continue Watching first, then Plex suggestion rows), a bottom row of app tiles, moved through with the remote's arrows and OK.
- **CLI**: today `info`, `pair`, `status`, `harden`, `cast-optout`, `dump`. New: `dashboard serve`, `dashboard open`, `dashboard install`, `dashboard uninstall`, `dashboard status`.
- **Background watcher** (inside `dashboard serve`): opens the dashboard when the TV turns on or returns to VIZIO's home screen.

## 6. Workflows

1. **Switch on**: the TV opens VIZIO's home (Input at Power On = SmartCast) → the watcher, polling power and current app every 2 s, sees it → `PUT /app/launch` with our page → the page asks our server for its rows → the server reads Plex.
2. **Resume a show**: OK on a Continue Watching tile → server creates a play queue → launches Plex's Cast app with a `LOAD` at the resume point → Plex plays. Leaving Plex returns to VIZIO's home → watcher → dashboard.
3. **Open an app**: OK on Netflix → server launches it with the catalog's config. Exiting it → VIZIO home → watcher → dashboard.
4. **Fire TV Stick**: OK on its tile → server switches the input to HDMI-2. The watcher leaves HDMI inputs alone.
5. **VIZIO's home on purpose**: OK on "VIZIO Home" → takeover paused for 15 minutes.
6. **Install**: `dashboard install` writes the LaunchAgent, which starts the server at login and restarts it if it stops.

## 7. Data and configuration

- `~/.vizio-privacy/192.168.1.130.json`: TV token (exists, mode 600).
- `~/.vizio-privacy/dashboard.json` (new, mode 600): Plex server URL, chosen apps, rows, port, takeover on or off.
- No Plex token (not needed for reads). If S2 shows Plex's Cast app needs one, it is obtained with Plex's PIN link (owner enters a code at plex.tv/link) and kept in `~/.vizio-privacy/plex.json`, mode 600.
- Logs: `~/Library/Logs/vizio-dashboard.log`.

## 8. Where the weight is

Existing `vizio_privacy/`: `api.py` 231 lines, `cast.py` 179, `cli.py` 244, `pairing.py` 104, `tokenstore.py` 59, `settings.py` 208, `targets.py` 124; `tests/` about 1,700 lines with `fakes.py` (FakeTransport, FakeTV) and `mock_tv.py` (HTTPS mock for end-to-end tests). All of it is real logic; none is generated or dead. New code is estimated at 1,200-1,500 lines plus tests: Plex client, app table, dashboard service, HTTP server, watcher, launchd glue, and a 400-line page.

## 9. What must not change

The existing commands and their output; `harden` stays a dry run unless `--apply`; the token file's location and format; nothing prints the token or device identifiers; standard library only, Python 3.9.
