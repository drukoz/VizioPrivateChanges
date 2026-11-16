# VIZIO SmartCast local API (the parts this project uses)

Sources: pyvizio 0.1.64 (MIT, <https://github.com/vkorn/pyvizio>), files `pyvizio/api/_protocol.py`, `pair.py`, `item.py` and `settings.py`. Response samples were read from our TV on 2026-11-15.

## Transport

- URL: `https://<host>:7345<path>`. Some older sets use port 9000. The certificate is self-signed, so certificate verification is off.
- Reads use `GET`. Everything else uses `PUT` with a JSON body and `Content-Type: application/json`.
- Auth: header `AUTH: <auth_token>` on every `/menu_native/` call.
- pyvizio's default timeout is 5 seconds.
- Checked on 2026-11-15 against our TV: `ssl.create_default_context()` with `check_hostname = False` and `verify_mode = ssl.CERT_NONE` connects from macOS's own Python 3.9 (LibreSSL 2.8.3, TLS 1.2) and from Python 3.11 and newer (OpenSSL 3, TLS 1.3). No cipher or protocol overrides are needed.
- With `http.client`, send only the path (plus `?query`) as the request target, never the full URL.

## Response envelope

Keys are case-insensitive: pyvizio lower-cases them before reading.

```json
{"STATUS": {"RESULT": "SUCCESS", "DETAIL": "Success"}, "URI": "/state/device/deviceinfo", "ITEMS": [ ... ]}
```

- Success is HTTP 200 with `STATUS.RESULT` = `SUCCESS`.
- Any other `RESULT` is an error, and `DETAIL` explains it. Known errors: `INVALID_PARAMETER` (bad value), `URI_NOT_FOUND`, and `REQUIRES_PAIRING`.
- An error can come with a non-200 status. Our TV answers an unpaired `GET /menu_native/dynamic/tv_settings` with HTTP 403 and `{"STATUS":{"RESULT":"REQUIRES_PAIRING","DETAIL":"Pairing is required"}}`. Read the envelope even when the status is not 200.
- Lists come in `ITEMS`. Pairing answers come in `ITEM`.

## Device info (no auth needed)

`GET /state/device/deviceinfo` returns `ITEMS[0].VALUE`, which holds:

- `MODEL_NAME` (`D24f-J09`), `API_VERSION`, `SC_INFO` (`prod 59.47` on 2026-11-15, `prod 59.54` on 2026-11-16 after an automatic update), `SETTINGS_ROOT` (`tv_settings`) and `CAST_NAME`;
- `INPUTS`, `CAPABILITIES` and `BINARIES` (firmware components such as `acr`, `s3logger` and `eventanalyzer`);
- `SYSTEM_INFO`, which contains `SERIAL_NUMBER` and `TVAD_ID`. Never print or commit those two.

## Pairing

1. `PUT /pairing/start` with body `{"DEVICE_ID": "<id>", "DEVICE_NAME": "<name>"}`. The answer has `ITEM.CHALLENGE_TYPE` (int) and `ITEM.PAIRING_REQ_TOKEN` (int), and the TV shows a 4-digit PIN.
2. `PUT /pairing/pair` with body `{"DEVICE_ID": "<id>", "CHALLENGE_TYPE": <int>, "PAIRING_REQ_TOKEN": <int>, "RESPONSE_VALUE": "<pin>"}`. The answer has `ITEM.AUTH_TOKEN` (string).
3. To abandon a pairing, `PUT /pairing/cancel` with body `{"DEVICE_ID": "<id>", "DEVICE_NAME": "<name>"}`.

## Settings tree

- `GET /menu_native/dynamic/tv_settings` returns the top-level menus. `GET /menu_native/dynamic/tv_settings/<path>` returns the items of one menu. `<path>` is CNAMEs joined by `/`, for example `admin_and_privacy`.
- `GET /menu_native/static/tv_settings/<path>` returns the same items with their options (`ELEMENTS`, `MINIMUM`, `MAXIMUM` and `CENTER`).
- Item fields:
  - `CNAME`: the path segment;
  - `NAME`: the label shown on screen;
  - `TYPE`;
  - `VALUE`;
  - `HASHVAL`: an int, needed to change the item;
  - `ELEMENTS`: the choices of a list;
  - `MINIMUM`, `MAXIMUM` and `CENTER`: slider bounds.
- `TYPE` values:
  - `T_MENU_V1`: submenu;
  - `T_LIST_V1`: choice list;
  - `T_VALUE_ABS_V1`: slider;
  - `T_VALUE_V1`: value;
  - `T_LIST_X_V1`: extended list.

  Other types exist, such as actions and headers. Treat them as unknown.

## Changing a setting

Send `PUT /menu_native/dynamic/tv_settings/<path>/<cname>` with the `AUTH` header and body `{"REQUEST": "MODIFY", "HASHVAL": <int from the item>, "VALUE": <new value>}`. Read the item first, because the TV rejects a stale `HASHVAL`.

## Known paths

pyvizio reads system information at `system/system_information/...` on older firmware and at `admin_and_privacy/system_information/...` on newer firmware. So `admin_and_privacy` is a top-level menu on current sets.

Read from our TV on 2026-11-16 (SmartCast `prod 59.54`), after pairing. The on-screen label is the item's `NAME`. A list's choices come only from the static menu (`/menu_native/static/tv_settings/<path>`).

| Path | On-screen label | Type | Notes |
|---|---|---|---|
| `admin_and_privacy/viewing_data` | Admin & Privacy → Viewing Data | `T_LIST_V1` | ACR. Was On; set to Off on 2026-11-16. |
| `admin_and_privacy/advertising/limit_ad_tracking` | Admin & Privacy → Advertising → Limited Ad Tracking | `T_LIST_V1` | Protective: On is private. Was Off; set to On on 2026-11-16. The label says "Limited", not "Limit". |
| `admin_and_privacy/advertising/tvad_id_reset` | Reset TV Advertiser ID | `T_ACTION_V1` | An action, not a setting; the tool leaves it alone. |
| `admin_and_privacy/store_demo` | Store Demo | `T_LIST_V1` | Off. |
| `admin_and_privacy/system_information` | TV Information | `T_MENU_V1` | Holds identifiers; never print. |
| `network/viewing_data` | (in the Network menu) | no value | Not a list; `harden` reports it as `NOT_A_LIST`. |
| `system/power_mode` | System → Power Mode | `T_LIST_V1` | Choices `Eco Mode` and `Quick Start` (ours: Quick Start, which keeps the TV online while it is off). |
| `system/input_at_power_on` | System → Input at Power On | `T_LIST_X_V1` | Ours: `SmartCast` (the home screen with ads). The static menu lists no choices. |
| `system/mobile_devices/paired_devices` | System → Mobile Devices | unknown | Lists paired apps; ours shows `{"DEVICE NAME": "Vizio Privacy", "DEVICE ID": "vizio-privacy"}`. |

`harden` on that day matched four items: the two lists above that it changed, and two non-lists (`network/viewing_data`, `tvad_id_reset`). No other tracking or ad switch exists in the tree.

## Google Cast setup API (ports 8008 and 8443)

Source: GHLocalApi, a community OpenAPI description of the Google Cast local API (<https://github.com/rithvikvibhu/GHLocalApi>, file `GoogleHome.openapi3.json`). Both calls below were checked on our TV (Cast firmware 1.68, build of 2023-03-06): the read on 2026-11-15, the write on 2026-11-16.

- Reads: plain HTTP, `http://<host>:8008`. `GET /setup/eureka_info?params=opt_in,device_info` returns JSON with a top-level `opt_in` object. Our TV before the opt-out: `{"crash": true, "opencast": false, "stats": true}`. `crash` is crash reporting and `stats` is usage statistics.
- Our TV does not always honour `params`: it can return the whole record, which includes MAC-like fields (`bssid`, `hotspot_bssid`) and other identifiers. Read only `opt_in`, and never print the rest.
- The write: `POST /setup/set_eureka_info` with `Content-Type: application/json` takes only the fields to change, with `opt_in` at the top level of the body: `{"opt_in": {"crash": false, "stats": false}}`.
  - Over plain HTTP on 8008, our TV answers **403** and changes nothing.
  - Over **HTTPS on 8443** (`https://<host>:8443`, self-signed certificate, so certificate checks are off as for SmartCast), with no token, it answers **200 with an empty body** and applies it. Read back on 2026-11-16: `{"crash": false, "opencast": false, "stats": false}`.
- The device answers 200 OK even for fields it ignores, so a 200 proves nothing. Read `opt_in` again to see whether the change took.
- Later Cast firmware may refuse even the 8443 write unless it carries a `cast-local-authorization-token` header, which needs the owner's Google account. If the TV refuses, report it; do not try to obtain that token.

## Apps, remote keys, inputs and power (used by the dashboard)

Source: pyvizio (`raman325/pyvizio`, MIT): `pyvizio/const.py` (`DEVICE_CONFIGS`, `APP_HOME`), `api/apps.py`, `api/input.py`, `api/remote.py`. Answers marked "read" came from our TV on 2026-11-16; the rest are from pyvizio and are confirmed in the CTO's live test (spike S1-S3). Real answers are in `tests/fixtures/tv/`.

| Call | Body | Answer |
|---|---|---|
| `GET /state/device/power_mode` | — | `ITEMS[0].VALUE`: `0` standby (read), `1` on. |
| `GET /app/current` | — | `ITEM.VALUE` = `{"APP_ID": "707", "NAME_SPACE": 345, "MESSAGE": "dtv-system://power"}` in standby (read). `ITEM.VALUE` can be missing or `null`. |
| `PUT /app/launch` | `{"VALUE": {"MESSAGE": <string or null>, "NAME_SPACE": <int>, "APP_ID": "<string>"}}` | Success envelope. |
| `PUT /key_command/` | `{"KEYLIST": [{"CODESET": <int>, "CODE": <int>, "ACTION": "KEYPRESS"}]}` | Success envelope. |
| `GET /menu_native/dynamic/tv_settings/devices/current_input` | — | `ITEMS[0]`: `CNAME` `current_input`, `VALUE` `"SMARTCAST"`, `HASHVAL` (read). |
| `PUT /menu_native/dynamic/tv_settings/devices/current_input` | `{"REQUEST": "MODIFY", "VALUE": "<input NAME, e.g. HDMI-2>", "HASHVAL": <current HASHVAL>}` | Success envelope. A stale `HASHVAL` is refused. |
| `GET /menu_native/dynamic/tv_settings/devices/name_input` | — | `ITEMS[]` of `T_DEVICE_V1`: `CNAME` (`cast`, `hdmi1`, `hdmi2`, `comp`, `tuner`), `NAME` (`CAST`, `HDMI-1`, `HDMI-2`, `COMP`, `TV`) and `VALUE.NAME`, the owner's label (`HDMI-2` is "Fire TV Stick") (read). |

Remote key codes (`CODESET`, `CODE`): DOWN 3,0 · LEFT 3,1 · OK 3,2 · RIGHT 3,7 · UP 3,8 · BACK 4,0 · HOME 4,15 · EXIT 9,0.

Launch configs come from VIZIO's public catalog: `https://scfs.vizio.com/appservice/vizio_apps_prod.json` (id, name) and `app_availability_prod.json` (id → `app_type_payload`, the `VALUE` above). `NAME_SPACE` 2 and 4 are web apps (pyvizio treats them as equal), 3 native apps (Netflix, Apple TV+), 5 YouTube, 0 Google Cast apps (`APP_ID` is the Cast app id, `MESSAGE` a JSON string `{"CAST_NAMESPACE": ..., "CAST_MESSAGE": {...}}`). SmartCast Home is `NAME_SPACE` 4, `APP_ID` "1", `MESSAGE` `http://127.0.0.1:12345/scfs/sctv/main.html`.
