# TV dashboard: plan (RUK-2394)

Kind: **Program**. Built on `docs/dashboard/system-map.md` and `docs/dashboard/reuse-ledger.md`. Revision 4, 2026-11-16 15:50 UTC: the home screen moves to the Fire TV Stick.

## Decision 2026-11-16 15:19 UTC: the home screen runs on the Fire TV Stick

The owner: "Let's just do the fire stick and set the tv to only turn on hdmi 2."

- **Target:** the stick on the Vizio's HDMI-2. It is a **Fire TV Stick 4K (1st gen, 2018), model `AFTMM`**, found by DIAL at `192.168.1.60`. Amazon's device table lists it as Fire OS 6 = Android 7.1 (API 25), with updates until 2029-12-31. Fire OS still allows ADB and sideloading; Amazon's newer Vega OS sticks don't.
- **Closed:** the Vizio home-screen route: the page in VIZIO's web runtime, served from the Mac, and the takeover watcher. Spikes S1-S3, the live check and the old M2 (watcher, LaunchAgent) are dropped. The owner does not want the Mac to run it (14:36): after setup, nothing runs on the Mac.
- **M1 is kept as the reference** and merged into the program branch: its page (`vizio_privacy/dashboard/static/`), its contract (`dashboard/model.py`) and its row and tile rules (`dashboard/service.py`, `plex.py`). The Fire TV app hosts the same page and implements the same contract in Kotlin, checked against the Python output for the same fixtures.

## TV at power-on (the owner's "only turn on HDMI 2")

- `System → Input at Power On` is `Last Used TV Input` (changed 15:1x). The TV offers no fixed-input choice.
- The TV refuses `PUT .../devices/current_input` with `RESULT: FAILURE`, in standby and when on; the item reports `ENABLED: FALSE`. Tried 2026-11-16 at about 15:26 UTC, with one power-on of 37 seconds; the TV was put back in standby. So the input can't be switched over the API, and M1-T1's `set_input` does not work on this TV.
- What works instead is HDMI-CEC One Touch Play (TV: CEC Enabled, One Touch Play Enabled). When the stick wakes, it makes itself the active source and the TV turns on to HDMI-2. Turning the TV off while on HDMI-2 makes HDMI-2 the last-used input.
- In the ADB session (F2): wake the stick (`input keyevent KEYCODE_WAKEUP`), read `current_input` from the TV (expect `HDMI-2`), then the TV goes off with HDMI-2 as its last input.
- `System → Hide From Input List` can hide TV, COMP and HDMI-1 (`Visible`/`Hidden` each); SmartCast is not in that list. Offered to the owner, not done.
- The Vizio remote's V key still opens VIZIO's home. No setting changes that.

## Assumptions (the owner corrects these in a comment or in PR review)

1. **Takeover of the Home button:** Fire OS keeps Amazon's launcher as the system home. Our app comes to the front whenever Amazon's home does, with an accessibility service (Projectivy's method), if F2 shows that works on this stick's Fire OS. Otherwise a remote button opens our app (AFTVnews' 2024 workaround). A brief flash of Amazon's home after pressing Home is acceptable.
2. **Rows** as in revision 3: Continue Watching first, then Plex's suggestion hubs for the video libraries in this prefix order: `movie.recentlyadded`, `tv.recentlyadded`, `tv.startwatching`, `movie.topunwatched`, `tv.moreingenre`, `movie.genre`, `tv.rediscover`, `tv.toprated`. Empty hubs are skipped, there are at most 8 rows, and a hub title that doesn't name its library gets it added ("Start Watching · Anime").
3. **Apps row:** Plex, Netflix, YouTube, Prime Video and Disney+, if installed on the stick (package names from the F2 inventory), then "Settings" (Fire TV settings) and "Amazon Home". The Amazon Home tile pauses the takeover for 15 minutes, so the owner can reach Amazon's app store.
4. **OK on a Plex tile** resumes it in the Plex app on the stick through Plex's deep link: `plex://server://<machineIdentifier>/com.plexapp.plugins.library/library/metadata/<ratingKey>?viewOffset=<ms>&autoPlay=1` with `ACTION_VIEW`, reported working on Plex for Android TV 10.28 (Plex forum, 2025-06-01). For a show it plays the next episode (M1's `includeOnDeck` rule). F2 proves it on the stick.
5. **No Plex sign-in in our app:** the Plex server lets LAN clients read without a token (true for the Mac; F2 checks it from the stick). The Plex app on the stick plays with its own sign-in.
6. **Tracking on the stick:** a CLI in this repository, run from the Mac over ADB (`python3 -m vizio_privacy firetv status | harden [--apply] | undo`), with a dry run, read-back and undo, like `harden`. It switches off the stick's privacy settings and disables Amazon's telemetry packages with `pm disable-user --user 0`, which `pm enable` reverses. Never `pm uninstall`.
7. **Install:** the app is sideloaded with `adb install`, debug-signed for now. The CTO reinstalls updates from the Mac. It is not published to Amazon's Appstore.
8. **Public repository:** the stick's serial number, MAC address, advertising ID and friendly name (it contains a person's name) never enter it.

## Cheaper route, for the record

Projectivy Launcher (free) on the stick gives an ad-free home with an app row in about an hour, but no Plex Continue Watching or suggestions: Fire OS has no Android TV "Watch Next" provider for it to read. The owner asked for software of our own with Plex rows, so we build the app, and Projectivy stays the fallback.

## Target architecture

```
Fire TV Stick 4K (AFTMM, Fire OS 6, API 25)
  TV Home app (Kotlin, package com.rukoz.tvhome, android/ in this repository)
    HomeActivity: full-screen WebView
      https://appassets.androidplatform.net/static/*   -> the M1 page (assets = vizio_privacy/dashboard/static/)
      GET /api/home                                     -> HomeBuilder (port of service.py) -> contract v1 JSON
      GET /img?p=&w=&h=                                 -> PlexClient -> Plex /photo/:/transcode
      GET /appicon?pkg=                                 -> the installed app's banner or icon (PNG)
      actions: window.TvHome.action(json)               -> AppLauncher | PlexPlayer | AmazonHome
    PlexClient (port of plex.py; HttpURLConnection + org.json) -> Plex 192.168.1.196:32400, no token
    HomeTakeover (AccessibilityService), if F2 passes
Mac, setup only: adb 37.0.1 -> install the APK; python3 -m vizio_privacy firetv (privacy settings, package disables)
```

| Module | Holds | Task |
|---|---|---|
| `android/` Gradle project | Toolchain pins, manifest, `HomeActivity`, asset loader | F1 |
| `Contract.kt` | `RowKind`, `ActionKind`, `ImageShape` with their numbers; `Action`, `Tile`, `Row`, `Home`, `ActionResult`; JSON writing | M2-T1 |
| `PlexClient.kt` | The Plex calls M1's service uses: identity, sections, continue watching, section hubs, item with `includeOnDeck`, image transcode URL | M2-T2 |
| `HomeBuilder.kt` | Rows and tiles by the rules above; golden test against the Python service on the same fixtures | M2-T3 |
| `ApiHandlers.kt`, `TvHomeBridge.kt`, `app.js` change | `/api/home`, `/img`, `/appicon`; the JS bridge; the page uses the bridge when `window.TvHome` exists and keeps the POST otherwise | M2-T4 |
| `Actions.kt` | Open an app by package, Plex deep link, Amazon Home pause | M2-T5 |
| `HomeTakeover.kt` | Accessibility service, method from F2/F4 | M2-T6 |
| `vizio_privacy/firetv.py`, `cli.py` | ADB runner, settings and package plan, `status`/`harden`/`undo` | M2-T7 |

## Contract: page ↔ app

Unchanged from revision 3 (`GET /api/home` JSON, tile rules, `/img` query), with these changes:

- `ActionKind`: `PLAY_PLEX = 0`, `OPEN_APP = 1`, `SWITCH_INPUT = 2` (not used on the stick), `VIZIO_HOME = 3` (not used on the stick), **`AMAZON_HOME = 4`** (new).
- `OPEN_APP`'s `target` is the Android package name, for example `com.netflix.ninja`.
- An app tile's `image` is `/appicon?pkg=<package>`.
- In the app, the page sends actions through `window.TvHome.action('{"kind":<int>,"target":"<str>"}')`, which returns the same `{"ok": ..., "message": ...}` JSON as `POST /api/action`. WebView request interception can't read a POST body, hence the bridge.

## What we don't build

A media player (Plex plays). A Plex sign-in. Settings screens in the app. Anything more on the Vizio than its HDMI-2 setting. Publishing to Amazon's Appstore. Network changes of any kind.

## Phase 0/1: spikes and research (now)

| Id | What | Who | Status |
|---|---|---|---|
| P0 | Toolchain prototype: AGP 9.2.1 with built-in Kotlin, Gradle 9.4.1, JDK 17, compileSdk 37, minSdk 25, androidx.webkit 1.14.0, JUnit 4.13.2, org.json 20180813; `assembleDebug testDebugUnitTest` | CTO | Done 15:45 UTC: BUILD SUCCESSFUL in 16 s, 1 test passed |
| F1 | Android skeleton in `android/`: hosts the M1 page from assets with a fixed `/api/home`, one JVM test, emulator smoke script | Engineer | Assigned |
| F2 | Live on the stick, with the owner: ADB authorization; inventory (Fire OS build, WebView version, packages, settings, accessibility); TV's last input to HDMI-2; F1's APK on the stick; Plex deep-link test (if the owner agrees); takeover probe | CTO | Waiting for the "Five minutes at the Fire TV" card |
| F3 | Research: Fire OS 6 telemetry and ad packages, and the privacy settings | Local agent | Assigned |
| F4 | Research: replacing Amazon's home screen on Fire OS 6 | Local agent | Assigned |

## M2: your home screen on the Fire TV (branch `feat/tv-dashboard-m2`)

End state: pressing Home on the Fire TV remote shows our screen with Continue Watching, suggestions and the apps row. OK resumes a show in Plex or opens an app, and the stick's tracking settings are off. Subtasks are created when F1-F4 are in.

| Task | Depends on | Notes |
|---|---|---|
| T1 Contract in Kotlin | F1 | Golden JSON written by the Python model |
| T2 PlexClient | T1 | Tests read `tests/fixtures/plex/` |
| T3 HomeBuilder | T1, T2 | Parity with `service.py` on the fixtures |
| T4 Handlers, bridge, page change | T1 | Built against a fixed home until T3 lands |
| T5 Actions | T1, F2 | Package names and the deep link from F2 |
| T6 Takeover | F2, F4 | |
| T7 `vizio_privacy firetv` CLI | F2, F3 | Tests use a fake ADB runner; never a device |
| T8 QA: emulator run with a fake Plex on 127.0.0.1, arrow keys, actions; CLI tests | T1-T7 | QA Engineer |
| Live install with the owner | T8 | CTO only |

**Later, in one cleanup task:** remove the Vizio-only code (`apps.py`'s VIZIO table, `dashboard open`, the TV launch and input actions in `service.py`).

## Risks

- **An Amazon update blocks the takeover:** Home shows Amazon's home again; the app still opens from the apps list or a mapped button. `firetv status` reports whether the takeover service is on.
- **Plex changes its deep link** (it broke the info-page link in 2025-05): OK falls back to opening Plex at the item or at its home. F2 tests the stick's Plex version.
- **The stick's WebView is old:** the page is ES5 (written for VIZIO's runtime), so the risk is low; F2 reads the WebView version.
- **2018 hardware** (1.5 GB RAM): posters come sized from Plex's transcoder, and there are at most 8 rows.
- **Disabling a package breaks something:** only `pm disable-user`, applied one package at a time live with a check after each, and `undo` restores every one.
- **Public repository:** no device identifiers or names; Plex fixtures stay scrubbed.

## Revision 3 (Vizio route), for the record

M1 (RUK-2455) merged ten subtasks and a browser verification on `feat/tv-dashboard-m1` (261 tests). Spikes S1-S3 and the live TV check never ran; S3's question (`MODIFY current_input`) was answered on 2026-11-16: the TV refuses it.
