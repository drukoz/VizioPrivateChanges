# VizioPrivateChanges

Tools that strip tracking and ads from the owner's VIZIO SmartCast TV without touching its firmware. There are two parts: privacy settings changed through the TV's local SmartCast API, and DNS blocklists for the TV's telemetry and ACR (content-recognition) servers. One household uses it. The owner runs the commands, or the CTO runs them in a live session with the owner at the TV.

## The TV

- VIZIO D24f-J09 (2021 D-Series, 24" FHD), SmartCast `prod 59.47`, API `3.3.3-2538.0001`, Google Cast built in. LAN address `192.168.1.130`, on Wi-Fi.
- SmartCast API: HTTPS on port 7345 with a self-signed certificate. `GET /state/device/deviceinfo` works without auth. Everything under `/menu_native/` needs an auth token from a one-time PIN pairing; without one the TV answers HTTP 403 `REQUIRES_PAIRING`. Protocol reference: [docs/smartcast-api.md](docs/smartcast-api.md).
- A custom OS is not possible: the bootloader is locked, the firmware is VIZIO-signed and there is no root access. The tracking components in its firmware (`acr`, `eventanalyzer`, `s3logger`, `errorcollector`, Sentry error reporting, WatchFree+) can only be switched off in settings or cut off at DNS.

## Layout

- `vizio_privacy/`: Python package. `api.py` is the SmartCast client and the only code that does network I/O. `cli.py` and `__main__.py` are the command line.
- `tests/`: `unittest` tests. They never open a socket; they pass a fake transport or a fake client.
- `blocklists/`: DNS block and keep lists, with their sources. `tools/` holds the checker and generator for them.
- `docs/`: API reference and runbooks.

## Commands (run from the repository root)

- Tests: `python3 -m unittest discover -s tests -v`
- CLI: `python3 -m vizio_privacy --help`
- Blocklists: `python3 tools/blocklists.py check`, then `python3 tools/blocklists.py build`

## Toolchain

Python 3.9 or newer, standard library only: no pip installs and no `requirements.txt`. macOS's own `/usr/bin/python3` is 3.9, so the code must run on 3.9:

- start every module with `from __future__ import annotations`;
- use `typing.Optional`, `List`, `Dict` and `Tuple` in signatures;
- no `match` statements;
- no `X | None` outside annotations.

## Conventions

- Enums are `enum.IntEnum` with explicit numbers starting at 0. The TV's own strings (such as `T_LIST_V1`) are mapped to our enum in `api.py`, and turned back into text only when printed.
- The CLI never prints the auth token or device identifiers (serial number, MAC address, ESN, `TVAD_ID`).
- Default branch: `main`. The owner reviews pull requests into it. Work happens on `feat/*` branches, and each task commits on its own worktree's branch.

## Dangers

- **This repository is public.** Never commit an auth token, a token file, or the TV's identifiers (serial number, MAC address, ESN, `TVAD_ID`, `uma_client_id`). Token files live in `~/.vizio-privacy/`, outside the repository.
- **Never contact the real TV from tests or engineer tasks.** Starting a pairing puts a PIN on the owner's screen, and a settings write changes their TV. Only the CTO runs commands against `192.168.1.130`, in a session agreed with the owner.
- **Never change the network.** No DNS, DHCP or router changes, and no traffic interception (ARP spoofing, proxies). The owner decides where a DNS blocker runs.
