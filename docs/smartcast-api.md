# VIZIO SmartCast local API (the parts this project uses)

Sources: pyvizio 0.1.64 (MIT, <https://github.com/vkorn/pyvizio>), files `pyvizio/api/_protocol.py`, `pair.py`, `item.py` and `settings.py`. Response samples were read from our TV on 2026-11-15.

## Transport

- URL: `https://<host>:7345<path>`. Some older sets use port 9000. The certificate is self-signed, so certificate verification is off.
- Reads use `GET`. Everything else uses `PUT` with a JSON body and `Content-Type: application/json`.
- Auth: header `AUTH: <auth_token>` on every `/menu_native/` call.
- pyvizio's default timeout is 5 seconds.

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

- `MODEL_NAME` (`D24f-J09`), `API_VERSION`, `SC_INFO` (`prod 59.47`), `SETTINGS_ROOT` (`tv_settings`) and `CAST_NAME`;
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

pyvizio reads system information at `system/system_information/...` on older firmware and at `admin_and_privacy/system_information/...` on newer firmware. So `admin_and_privacy` is a top-level menu on current sets. The exact CNAME of "Viewing Data" (ACR) on our TV will only be known after the first `dump` that follows pairing.
