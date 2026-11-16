# VizioPrivateChanges

Software for the owner's VIZIO SmartCast TV that never touches its firmware. One household uses it. The owner runs the commands, or the CTO runs them in a live session with the owner at the TV. It has two parts:

1. **Privacy settings** (done, merged in PR #1): switches off tracking and ads through the TV's local SmartCast API, and opts the TV's built-in Google Cast out of crash and usage reporting.
2. **Dashboard** (in progress, program RUK-2394, branch `feat/tv-dashboard`): the household's own home screen in place of VIZIO's. It shows Continue Watching and suggestions from their Plex server, plus a row of chosen apps. The page runs in the TV's built-in web-app runtime, is served from the owner's Mac, and the remote drives it. Design: [docs/dashboard/](docs/dashboard/) (`system-map.md`, `reuse-ledger.md`, `plan.md`; the plan holds the page ↔ server contract).

The owner chose software only: no DNS blocker (no Pi-hole, no router changes) and no extra device. Do not add blocklists or network tooling.

## The TV

- VIZIO D24f-J09 (2021 D-Series, 24" FHD), SmartCast `prod 59.54`, API `3.3.3-2538.0001`, Google Cast built in (Cast firmware 1.68). LAN address `192.168.1.130`, on Wi-Fi. VIZIO updates the firmware by itself: it went from `59.47` to `59.54` between 2026-11-15 and 2026-11-16.
- Paired on 2026-11-16: the token is in the owner's `~/.vizio-privacy/192.168.1.130.json`, and the TV lists the tool under System → Mobile Devices as "Vizio Privacy". On that day `harden --apply` set Viewing Data to Off and Limited Ad Tracking to On, and Cast crash and usage reporting were switched off.
- SmartCast API: HTTPS on port 7345 with a self-signed certificate. `GET /state/device/deviceinfo` works without auth. Everything under `/menu_native/` needs an auth token from a one-time PIN pairing; without one the TV answers HTTP 403 `REQUIRES_PAIRING`.
- Google Cast setup API: reads over plain HTTP on port 8008 (`/setup/eureka_info`). The opt-out write (`/setup/set_eureka_info`) must go over HTTPS on port 8443 (self-signed certificate, no token): this TV answers the same write on 8008 with HTTP 403 and changes nothing.
- Protocol reference for both: [docs/smartcast-api.md](docs/smartcast-api.md).
- A custom OS is not possible: the bootloader is locked, the firmware is VIZIO-signed and there is no root access, so no program on the TV can be removed. Its tracking components (`acr`, `eventanalyzer`, `s3logger`, `errorcollector`, `collectd`, `recommendationd`, `watchfree-helper`) can only be switched off through its settings.

## Layout

- `vizio_privacy/`: Python package.
  - `api.py`: SmartCast client (port 7345), response envelope and enums.
  - `cast.py`: Google Cast opt-out: reads over HTTP on port 8008, the write over HTTPS on port 8443.
  - `pairing.py` and `tokenstore.py`: PIN pairing, and the auth token saved under `~/.vizio-privacy/`.
  - `targets.py`: which settings count as tracking or ads, and the private value of each.
  - `settings.py`: walks the settings tree and sets the matched items (`harden`).
  - `cli.py` and `__main__.py`: the command line.
  - Dashboard (being built; the plan's module table says which task adds what): `plex.py` (Plex client), `apps.py` (app launch table), `dashboard/` (`model.py` contract, `service.py`, `server.py`, `watcher.py`, `static/` page).
  - `api.py`, `cast.py` and `plex.py` open sockets, as does the dashboard server. Each takes a transport argument, so tests can pass a fake.
- `tests/`: `unittest` tests. The unit tests never open a socket; they pass a fake transport or a fake TV (`tests/fakes.py`). `tests/test_e2e.py` runs the command line over real HTTP(S) against a mock TV (`tests/mock_tv.py`) on `127.0.0.1` only, and is skipped when `openssl` is missing.
- `tests/fixtures/`: real answers captured by the CTO on 2026-11-16. `tv/` holds the TV's answers. `plex/` holds the Plex server's, with every title, name, file path and server identifier replaced by a placeholder. Fakes must answer with these files, never with made-up shapes. Only the CTO recaptures them.
- `docs/`: protocol reference (`smartcast-api.md`) and the dashboard design (`dashboard/`).

## The Plex server

- Plex Media Server 1.43.5 on the owner's TrueNAS box, LAN address `192.168.1.196:32400`. Libraries: 1 Movies, 2 TV Shows, 3 Anime (shows), 4 Music.
- It lets the owner's Mac read without a token (the server allows the LAN). Ask for JSON with `Accept: application/json`. The calls the dashboard uses, and the play-queue body, are in `docs/dashboard/system-map.md`.
- The dashboard server runs on the owner's Mac, `192.168.1.45` (macOS firewall off), on port 8790.

## Commands (run from the repository root)

- Tests: `python3 -m unittest discover -s tests -v`
- CLI: `python3 -m vizio_privacy --help`. For example `python3 -m vizio_privacy --host 192.168.1.130 harden` is a dry run, and `harden --apply` writes.

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
- **Never change the network.** No DNS, DHCP or router changes, and no traffic interception (ARP spoofing, proxies).
