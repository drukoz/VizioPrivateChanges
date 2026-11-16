# TV dashboard: reuse ledger (RUK-2394)

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
| S1 | Does `PUT /app/launch` (`NAME_SPACE` 2 or 4, our URL in `MESSAGE`) open our page, do remote keys reach it, and how does `/app/current` report it and the home screen? | Pending: needs the TV on (owner's "TV test" card). Script: `cto-scratch/RUK-2394/dashboard-spike/live_dashboard_test.py`. |
| S2 | Does a Plex `LOAD` through `NAME_SPACE` 0 / `9AC194DC` resume an item without a token? Does the SmartCast Plex app register as a player? | Pending, same session. |
| S3 | Does `MODIFY current_input` to `HDMI-2` switch to the Fire TV Stick, and back? | Pending, same session. |
| S4 | Can the TV reach a page served from the Mac? | Done: Mac firewall off; served on `0.0.0.0:8790`, loaded over `192.168.1.45` by headless Chrome. |
| S5 | Can the Mac read Plex rows and create a play queue without a token? | Done 2026-11-16. |
