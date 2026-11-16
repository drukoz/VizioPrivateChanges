# VizioPrivateChanges

Software for the owner's VIZIO SmartCast TV that never touches its firmware. One household uses it. The owner runs the commands, or the CTO runs them in a live session with the owner at the TV. It has two parts:

1. **Privacy settings** (done, merged in PR #1): switches off tracking and ads through the TV's local SmartCast API, and opts the TV's built-in Google Cast out of crash and usage reporting.
2. **Dashboard** (program RUK-2394, branch `feat/tv-dashboard`): the household's own home screen, with **Continue Watching** and suggestions from their Plex server and a row of chosen apps. Since 2026-11-16 it runs on the **Fire TV Stick** on the TV's HDMI-2, as an Android app in `android/` (being built, milestone M2) that shows the dashboard page in a WebView and reads Plex directly. The earlier route, the page in VIZIO's web runtime served from the Mac, is closed; its Python code (milestone M1: `plex.py`, `dashboard/`) is the reference for the page, the contract and the row rules. Design: [docs/dashboard/](docs/dashboard/) (`system-map.md`, `reuse-ledger.md`, `plan.md`; the plan holds the page ↔ app contract).

The owner chose software only: no DNS blocker (no Pi-hole, no router changes). Do not add blocklists or network tooling. Nothing runs on the Mac after setup.

## The TV

- VIZIO D24f-J09 (2021 D-Series, 24" FHD), SmartCast `prod 59.54`, API `3.3.3-2538.0001`, Google Cast built in (Cast firmware 1.68). LAN address `192.168.1.130`, on Wi-Fi. VIZIO updates the firmware by itself: it went from `59.47` to `59.54` between 2026-11-15 and 2026-11-16.
- Paired on 2026-11-16: the token is in the owner's `~/.vizio-privacy/192.168.1.130.json`, and the TV lists the tool under System → Mobile Devices as "Vizio Privacy". On that day `harden --apply` set Viewing Data to Off and Limited Ad Tracking to On, and Cast crash and usage reporting were switched off.
- SmartCast API: HTTPS on port 7345 with a self-signed certificate. `GET /state/device/deviceinfo` works without auth. Everything under `/menu_native/` needs an auth token from a one-time PIN pairing; without one the TV answers HTTP 403 `REQUIRES_PAIRING`.
- Google Cast setup API: reads over plain HTTP on port 8008 (`/setup/eureka_info`). The opt-out write (`/setup/set_eureka_info`) must go over HTTPS on port 8443 (self-signed certificate, no token): this TV answers the same write on 8008 with HTTP 403 and changes nothing.
- Protocol reference for both: [docs/smartcast-api.md](docs/smartcast-api.md).
- Since 2026-11-16 `System → Input at Power On` is `Last Used TV Input` (the only other choice is `SmartCast`). The TV refuses input changes over the API (`PUT .../devices/current_input` answers `RESULT: FAILURE`, on and in standby), so `api.set_input` does not work on this TV; the Fire TV Stick switches the TV to HDMI-2 through CEC One Touch Play when it wakes.
- A custom OS is not possible: the bootloader is locked, the firmware is VIZIO-signed and there is no root access, so no program on the TV can be removed. Its tracking components (`acr`, `eventanalyzer`, `s3logger`, `errorcollector`, `collectd`, `recommendationd`, `watchfree-helper`) can only be switched off through its settings.

## The Fire TV Stick

- Fire TV Stick 4K, 1st gen (2018), model `AFTMM`, Fire OS 6 (Android 7.1, API 25). LAN address `192.168.1.60` (DHCP; found by SSDP/DIAL, see `docs/dashboard/system-map.md` section 0), on the TV's HDMI-2.
- Its friendly name contains a person's name, and its serial number, MAC address and advertising ID are identifiers: never commit or print any of them.
- Only the CTO connects to it, over ADB on Wi-Fi from the Mac, in sessions agreed with the owner. The trusted ADB key is `/Users/drukoz/.vizio-privacy/adb/.android/adbkey`, used by running adb with `HOME=/Users/drukoz/.vizio-privacy/adb` and `ANDROID_ADB_SERVER_PORT=5038`.

## Android toolchain (for `android/`)

Pinned and proved on this Mac on 2026-11-16: Gradle 9.4.1 (wrapper), Android Gradle Plugin 9.2.1, JDK 17, compileSdk 37, targetSdk 37, minSdk 25, `androidx.webkit:webkit` 1.14.0, JUnit 4.13.2 and `org.json:json` 20180813 for unit tests. AGP 9 compiles Kotlin itself: never apply `org.jetbrains.kotlin.android` or `kotlin-android`, and add no `kotlinOptions` block. `source scripts/android-env.sh` selects the JDK, the SDK and the Gradle home under `/Volumes/Storage/paperclip/toolchains/`; the commands are under Commands.

## Layout

- `vizio_privacy/`: Python package.
  - `api.py`: SmartCast client (port 7345), response envelope and enums.
  - `cast.py`: Google Cast opt-out: reads over HTTP on port 8008, the write over HTTPS on port 8443.
  - `pairing.py` and `tokenstore.py`: PIN pairing, and the auth token saved under `~/.vizio-privacy/`.
  - `targets.py`: which settings count as tracking or ads, and the private value of each.
  - `settings.py`: walks the settings tree and sets the matched items (`harden`).
  - `firetv.py`: the Fire TV Stick's Amazon packages over ADB (`firetv status|harden|undo`).
  - `cli.py` and `__main__.py`: the command line.
  - Dashboard (being built; the plan's module table says which task adds what): `plex.py` (Plex client), `apps.py` (app launch table), `dashboard/` (`model.py` contract, `service.py`, `server.py`, `watcher.py`, `static/` page).
  - `api.py`, `cast.py` and `plex.py` open sockets, as does the dashboard server. Each takes a transport argument, so tests can pass a fake.
- `tests/`: `unittest` tests. The unit tests never open a socket; they pass a fake transport or a fake TV (`tests/fakes.py`). `tests/test_e2e.py` runs the command line over real HTTP(S) against a mock TV (`tests/mock_tv.py`) on `127.0.0.1` only, and is skipped when `openssl` is missing.
- `tests/fixtures/`: real answers captured by the CTO on 2026-11-16. `tv/` holds the TV's answers. `plex/` holds the Plex server's, with every title, name, file path and server identifier replaced by a placeholder. Fakes must answer with these files, never with made-up shapes. Only the CTO recaptures them.
- `docs/`: protocol reference (`smartcast-api.md`) and the dashboard design (`dashboard/`).
- `android/`: the TV Home app for the Fire TV Stick (Kotlin, Gradle). `app/src/main/java/com/rukoz/tvhome/` holds the code; its assets are `vizio_privacy/dashboard/static/` (the same page the Python server serves). `scripts/emulator-smoke.sh` runs it on a headless emulator.

## The Plex server

- Plex Media Server 1.43.5 on the owner's TrueNAS box, LAN address `192.168.1.196:32400`. Libraries: 1 Movies, 2 TV Shows, 3 Anime (shows), 4 Music.
- It lets the owner's Mac read without a token (the server allows the LAN). Ask for JSON with `Accept: application/json`. The calls the dashboard uses, and the play-queue body, are in `docs/dashboard/system-map.md`.
- The dashboard server runs on the owner's Mac, `192.168.1.45` (macOS firewall off), on port 8790.

## Commands (run from the repository root)

- Tests: `python3 -m unittest discover -s tests -v`
- CLI: `python3 -m vizio_privacy --help`. For example `python3 -m vizio_privacy --host 192.168.1.130 harden` is a dry run, and `harden --apply` writes.
- Dashboard: `python3 -m vizio_privacy --host 192.168.1.130 dashboard serve` (keep it running), then `dashboard open` in a second terminal.
- Android setup, once per shell: `source scripts/android-env.sh`.
- Android build and unit tests: `(cd android && ./gradlew --no-daemon assembleDebug testDebugUnitTest)`.
- Android smoke test on an emulator: `bash android/scripts/emulator-smoke.sh tvhome-<task id> 5610 "$PWD/android/build/smoke" "$PWD/android/app/build/outputs/apk/debug/app-debug.apk"` (prints PASS or FAIL lines, deletes its emulator).
- Fire TV packages (CTO only, in a session with the owner): `python3 -m vizio_privacy firetv --device 192.168.1.60:5555 --adb-home /Users/drukoz/.vizio-privacy/adb status`, then `harden`, `harden --apply --package <pkg>`, `undo`.

## Toolchain

Python 3.9 or newer, standard library only: no pip installs and no `requirements.txt`. macOS's own `/usr/bin/python3` is 3.9, so the code must run on 3.9:

- start every module with `from __future__ import annotations`;
- use `typing.Optional`, `List`, `Dict` and `Tuple` in signatures;
- no `match` statements;
- no `X | None` outside annotations.

## Conventions

- Enums are `enum.IntEnum` with explicit numbers starting at 0. The TV's own strings (such as `T_LIST_V1`) are mapped to our enum in `api.py`, and turned back into text only when printed.
- Settings changes are dry runs unless `--apply` (in code, `apply=True`) is given. A setting is changed only to one of its own listed choices, and every write is read back. When no choice fits, the setting is reported for a person to set.
- Some settings are protective ("Limit Ad Tracking", "Do Not Track"): their private value is On. `targets.py` decides the private value; never hard-code "Off".
- The CLI never prints the auth token or device identifiers (serial number, MAC address, ESN, `TVAD_ID`, advertising ID). Setting values are printed through `targets.display_value`, which hides identifiers.
- Default branch: `main`. The owner reviews pull requests into it. Work happens on `feat/*` branches, and each task commits on its own worktree's branch.

## Dangers

- **This repository is public.** Never commit an auth token, a token file, or the TV's identifiers (serial number, MAC address, ESN, `TVAD_ID`, `uma_client_id`). Token files live in `~/.vizio-privacy/`, outside the repository.
- **Never commit the household's Plex data**: titles, people, summaries, file paths, the server's `machineIdentifier` or `*.plex.direct` host, or any Plex token. Tests use only `tests/fixtures/plex/`.
- **Never contact the real TV or the real Plex server from tests or engineer tasks.** Starting a pairing puts a PIN on the owner's screen, launching an app takes over their TV, and a settings write changes it. Only the CTO runs commands against `192.168.1.130` or `192.168.1.196`, in a session agreed with the owner. Tests bind only to `127.0.0.1`.
- **Never contact the Fire TV Stick from tests or engineer tasks.** Any ADB command can wake it, and a waking stick turns the TV on through CEC. Tests use an emulator or a fake ADB runner; only the CTO connects to `192.168.1.60`.
- **Never change the network.** No DNS, DHCP or router changes, and no traffic interception (ARP spoofing, proxies).
