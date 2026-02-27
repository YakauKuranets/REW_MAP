# Tracker API & WS contract (v1)

This document freezes the **technical contract** between:
- Android tracker app
- Backend `/api/tracker/*`
- Admin realtime WS events (Socket.IO)

## Common response fields

All tracker endpoints return JSON with:

- `ok` (bool)
- `schema_version` (int) — currently `1`
- `server_time` (string, ISO8601 UTC-ish, with `Z`)

On error:
- `ok=false`
- `code` (string) — machine-readable
- `error` (string) — human-readable

Common `code` values (all endpoints):
- `missing_token` (401)
- `invalid_token` (403)
- `revoked_token` (403) — token was revoked by admin
- `rate_limited` (429) — see `details.reason` (e.g. `too_many_points` / `too_many_health` / `too_many_sos`)
- `bad_request` (400)
- `session_inactive` (409) — for `/points` when provided `session_id` is not active; `details.active_session_id` may be set

- optional `details` (object)

## Auth

Device requests must include **either**:
- `X-DEVICE-TOKEN: <token>`
or
- `Authorization: Bearer <token>`

If token invalid or revoked:
- `403` + `{ok:false, code:"invalid_token", ...}`

## Endpoints

### POST `/api/tracker/pair`
Body:
- `code` (string)

Response (200):
- `code` (string) — device code used
- `expires_in_min` (int)
- `label` (string|null)
- `device_token` (string) — token to store on device

Errors:
- `400 missing_code`
- `404 invalid_code`
- `410 expired_code`
- `409 code_used`
- `429 rate_limited_ip | rate_limited_code`

### POST `/api/tracker/start`
Body (optional):
- `lat` (float)
- `lon` (float)

Response (200):
- `shift_id` (int)
- `session_id` (int)
- `user_id` (int)
- `device_id` (string) — public device id
- `label` (string|null) — shift/unit label

### POST `/api/tracker/stop`
Body (optional):
- `session_id` (int)

Response (200):
- `session_id` (int)
or if nothing to stop:
- `message: "no_active_session"`

### POST `/api/tracker/points`
Body:
- `session_id` (int, optional but recommended)
- `points` (array) — up to 500 items

Point item:
- `ts` (int ms epoch | string ISO8601)
- `lat` (float)
- `lon` (float)
- `acc` (float, optional)

Response (200):
- `session_id` (int)
- `accepted` (int) — inserted
- `dedup` (int) — duplicates skipped
- `rejected` (int) — invalid items skipped
- `first_ts` (string|null) — min ts of submitted batch (normalized)
- `last_ts` (string|null) — max ts of submitted batch (normalized)

Errors:
- `409 session_inactive` when a provided `session_id` exists but is not active.

### POST `/api/tracker/health`
Body (optional):
- `battery_pct` (0..100)
- `is_charging` (bool)
- `gps_on` (bool)
- `net_type` ("wifi"|"cell"|"none"|...)
- `queue_size` (int)

Response (200):
- `health` (object) — stored row

### POST `/api/tracker/fingerprints`
Body:
- `samples` (array) — up to 50 items (or a single sample dict)

Sample item:
- `ts` (int ms epoch | string ISO8601)
- `lat` (float, optional)
- `lon` (float, optional)
- `accuracy_m` (float, optional)
- `wifi` (array, optional): `{bssid, ssid, rssi, freq}`
- `cell` (array, optional): `{type, mcc, mnc, ci, tac, lac, pci, ...}`
- `mode` (string, optional) — ECO/NORMAL/PRECISE/AUTO
- `purpose` (string, optional) — `train` or `locate`

Response (200):
- `stored` (int)
- `dropped` (int)
- optional `pos_est` (object) — if server produced an indoor estimate from this fingerprint
   - `lat`, `lon`, `accuracy_m`, `confidence`, `matches`, `anchor_ts`
- optional `localized` (bool) — true if an estimated tracking point was injected/broadcast

Notes:
- Server hashes `bssid`/`ssid` and stores only hashes + signal levels.


### POST `/api/tracker/sos`
Body:
- `note` (string, up to 256)
- optional `session_id` (int)
- optional `lat`/`lon`/`accuracy_m`

Response (200):
- `sos_id` (int)
- `sos` (object)

Error:
- `409 need_location` if no coordinates and no last known location is available.

## Admin endpoints (tracker)

- `GET /api/tracker/admin/alerts?active=1`
- `POST /api/tracker/admin/alerts/<id>/ack`
- `POST /api/tracker/admin/alerts/<id>/close`
- `POST /api/tracker/admin/device/<device_id>/rotate`

## Realtime (Socket.IO) events

All tracker events carry a consistent payload shape.

### `tracking_point`
- `user_id` (int)
- `device_id` (string)
- `session_id` (int)
- `ts` (string ISO)
- `lat` (float)
- `lon` (float)
- `accuracy_m` (float|null)
- `source` ("app" | "wifi_est")
- optional `flags` (array) — contains `"est"` for Wi‑Fi estimate points

### `tracking_started`
- `user_id`, `device_id`, `session_id`, `label`

### `tracking_stopped`
- `user_id`, `device_id`, `session_id`, `source`

### `tracker_health`
- `user_id`, `device_id`, `health` (object)

### Alerts
- `tracker_alert`
- `tracker_alert_acked`
- `tracker_alert_closed`

Payload includes:
- `alert` (object) and `device_id`