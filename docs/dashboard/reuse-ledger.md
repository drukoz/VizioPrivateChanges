# TV dashboard: reuse ledger (RUK-2394)

## Fire TV route (2026-11-16)

The home screen now runs on the Fire TV Stick 4K (2018, Fire OS 6, API 25) as an Android app. The Python rules below (standard library only) still hold for the CLI; the app has its own toolchain.

| Capability | Candidates (pin, licence, date) | Decision |
|---|---|---|
| Whole product | Projectivy Launcher (free, closed source, Android TV and Fire TV; home override through an accessibility service); Wolf Launcher; FLauncher (open source, Flutter); ATV Launcher | **Build** our own app: none of them shows Continue Watching or suggestions from a local Plex server on Fire OS, which has no Android TV "Watch Next" provider. Projectivy is the owner's no-code fallback and the reference for the takeover method (F4). |
| UI | WebView hosting M1's page; Leanback (`androidx.leanback`); Compose for TV | **Use the WebView with M1's page**: the page is built and browser-tested (RUK-2479, RUK-2490), it is ES5 so an old Fire OS WebView runs it, and the Python dev server keeps serving the same page. Leanback or Compose would be a second UI to write and test. |
| Serving the page and the API inside the app | `androidx.webkit:webkit` 1.14.0 `WebViewAssetLoader` (Apache-2.0) | **Use.** In the Gradle cache; built in the CTO prototype P0. A `PathHandler` per prefix (`/static/`, `/api/`); `/img` and `/appicon` are matched in `shouldInterceptRequest`. |
| JSON | Android's `org.json`; `org.json:json:20180813` for JVM unit tests (Android's copy is a stub there) | **Use.** |
| HTTP to Plex | `java.net.HttpURLConnection` | **Use**: a few GETs, no OkHttp. Cleartext to the LAN needs `android:usesCleartextTraffic="true"`. |
| Plex playback | Plex Android deep link `plex://server://<machineIdentifier>/com.plexapp.plugins.library/library/metadata/<ratingKey>?viewOffset=<ms>&autoPlay=1` with `ACTION_VIEW` (forums.plex.tv/t/920935, Plex for Android TV 10.28, 2025-06-01; the older `START_PLAYBACK` extra form: forums.plex.tv/t/755047, 2021); Plex Companion player API on port 32500 | **Use the deep link**, proved on the stick in F2. Companion is the fallback. |
| Home-button takeover | Accessibility service watching the foreground app (Projectivy); `pm disable-user com.amazon.tv.launcher`; a remapped remote button (AFTVnews, 2024-12-16: "Amazon continuously blocks new methods for replacing the home screen") | F4 research, then F2 on the stick. |
| Device access | `adb` 37.0.1 from `/Volumes/Storage/paperclip/toolchains/android-sdk/platform-tools` | **Use.** CTO only. |
| Telemetry and ad packages | Community Fire TV debloat lists | F3 research. Every row is checked on the stick before the CLI uses it. |

**Toolchain (pinned, proved by P0 on 2026-11-16):** Gradle 9.4.1 (wrapper), Android Gradle Plugin 9.2.1 with its built-in Kotlin (no Kotlin plugin applied), JDK 17 at `/Volumes/Storage/paperclip/toolchains/jdk-17/Contents/Home`, Android SDK at `/Volumes/Storage/paperclip/toolchains/android-sdk` (platform `android-37`, build-tools 36.0.0 and 37.0.0), compileSdk 37, targetSdk 37, minSdk 25.

**Spike S3, answered 2026-11-16:** `MODIFY current_input` to `HDMI-2` fails on this TV (`RESULT: FAILURE`, on and in standby). The rows below are the Vizio route's ledger, kept for M1's code.


Constraint from the owner and the guide: standard-library Python only, runnable on macOS's own `/usr/bin/python3` 3.9 with no pip installs, and no extra device. That rules out every third-party Python package below, whatever its quality.

## Whole products

| Candidate | What it does | Decision |
|---|---|---|
| Plex app on SmartCast (catalog id 40, `NAME_SPACE` 2, `APP_ID` "9") | Its own home has Continue Watching and suggestions | **Use for playback**, not as the home screen: it has no app row and can't be made the TV's home. |
| Homarr, Homepage (gethomepage), Dashy, Heimdall (self-hosted dashboards) | Browser dashboards with service widgets | No: mouse-driven pages with no remote (D-pad) focus, no Continue Watching posters, and they need Docker or Node on a host. |
| Projectivy Launcher, FLauncher, Wolf Launcher (Android TV launchers) | Ad-free home screens with Plex rows | No: they don't run on SmartCast. On the Fire TV Stick, Amazon blocks replacing the home screen, and that's a second device the owner didn't ask about. |
| Kodi + PlexKodiConnect | Plex-backed home screen with widgets | No: needs an Android or Linux device; SmartCast can't run it. |
| Home Assistant Cast / DashCast (`84912283`) | Show a web page through Chromecast | Fallback only if S1 fails: Cast receivers on this TV may not get remote keys. |

## Generators

Plex has an OpenAPI description (`LukasParke/plex-api-spec`, MIT, pushed 2026-11-16; Plex also publishes an official one that `thde/plex` generates a Go client from). Generated Python clients (Speakeasy's `plex-api-client`, `openapi-python-client`) need `httpx`, `attrs` or `pydantic`. **Build** instead: a thin stdlib client for the eight calls in the system map, with field names checked against the spec and against real answers (`tests/fixtures/plex/`). SmartCast has no published spec.

## Our own code

| Capability | Where | Decision |
|---|---|---|
| SmartCast transport, envelope, auth header | `vizio_privacy/api.py` `SmartCastClient`, `default_transport` | **Use and extend** with launch, current app, power, input and key calls. |
| TV token | `vizio_privacy/tokenstore.py` | **Use** as is. |
| Test fakes | `tests/fakes.py` `FakeTransport`, `FakeTV`; `tests/mock_tv.py` | **Use and extend**. |

## Libraries

| Capability | Candidates (pin, licence, last push) | Decision |
|---|---|---|
| Plex client | python-plexapi 4.x (`pushingkarmaorg/python-plexapi`, BSD-3, 2026-11-09, needs `requests`) | **Build** (stdlib rule). Use it and the spec as references for endpoints. |
| SmartCast client | pyvizio 0.1.64 (MIT, needs `aiohttp`) | **Build** (already ours); pyvizio is the protocol reference. |
| Plex playback hand-off | pychromecast `controllers/plex.py` (MIT): Cast app `9AC194DC`, `LOAD` format | **Use the protocol** through the TV's own `/app/launch` (`NAME_SPACE` 0). Needs spike S2. Fallback: launch the Plex app (`NAME_SPACE` 2, `APP_ID` "9") at its home. |
| HTTP server | stdlib `http.server.ThreadingHTTPServer` | **Use**. Proved by the S4 dry run. |
| Remote (D-pad) focus on the page | js-spatial-navigation (MPL-2.0, 2024-05), BBC LRUD (Apache-2.0, 2023-07), WICG polyfill, Norigin (React) | **Build**: the layout is rows of tiles, so up/down moves between rows and left/right within one, about 60 lines. No bundler, and no risk from an old TV engine. |
| Page framework | none | **Build** in plain HTML, CSS and ES5 JavaScript, with no build step. Raise the language level only if S1 shows the engine supports it. |
| Plex discovery | GDM (UDP 32414) | **Build**, about 20 lines, proved live. |
| Posters | PMS `/photo/:/transcode` | **Use**, proxied by our server so the TV only talks to the Mac. |
| Service | macOS launchd LaunchAgent | **Use**. |
| App launch table | VIZIO catalog snapshot 2026-11-16 | **Use (data)**: a pinned table of the apps the owner can choose. |

## Toolchain

Python 3.9+ standard library, unchanged. The page targets the TV's engine, whose version S1 reads from its user agent.

## Spikes

| Id | Question | Status |
|---|---|---|
| S1 (dropped 2026-11-16) | Does `PUT /app/launch` (`NAME_SPACE` 2 or 4, our URL in `MESSAGE`) open our page, do remote keys reach it, and how does `/app/current` report it and the home screen? | Pending: needs the TV on (owner's "TV test" card). Script: `cto-scratch/RUK-2394/dashboard-spike/live_dashboard_test.py`. |
| S2 (dropped 2026-11-16) | Does a Plex `LOAD` through `NAME_SPACE` 0 / `9AC194DC` resume an item without a token? Does the SmartCast Plex app register as a player? | Pending, same session. |
| S3 | Does `MODIFY current_input` to `HDMI-2` switch to the Fire TV Stick, and back? | Answered 2026-11-16: no. The TV answers `RESULT: FAILURE`, on and in standby. |
| S4 | Can the TV reach a page served from the Mac? | Done: Mac firewall off; served on `0.0.0.0:8790`, loaded over `192.168.1.45` by headless Chrome. |
| S5 | Can the Mac read Plex rows and create a play queue without a token? | Done 2026-11-16. |
