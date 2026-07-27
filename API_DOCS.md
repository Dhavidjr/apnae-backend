# Apnoea Backend — API Reference (for Frontend Integration)

Base URL (local dev): `http://localhost:8000`
All REST endpoints below are mounted under the prefix **`/api/v1`**.

---
## 1. System Flow (read this first)

1. **User registers an account** → `POST /auth/register`.
2. **User logs in** → `POST /auth/login` → receives a **JWT access token**. This token is sent as `Authorization: Bearer <token>` on every subsequent REST call, and as a `?token=` query param on the frontend websocket.
3. **User registers their hardware device** → `POST /devices/`. The response includes a `device_id` (public identifier) and a **`device_secret`** (shown once — the hardware firmware needs this, not the frontend). Save/display it once so the user can configure their hardware.
4. **The hardware itself** connects to `ws://.../ws/device/{device_id}?secret=...` and streams sensor samples. This is the device's job, not the frontend's — but it's documented here (§5) since your app may include a "device setup" screen showing this connection info.
5. **The frontend queries stored data** any time via REST (`/data/...`) — as raw rows, structured JSON, or a rendered PNG graph.
6. **The frontend can also subscribe to a live feed** for a device via websocket (`/ws/stream/{device_id}?token=...`) to show real-time vitals without polling.
7. **The frontend can request an AI apnoea-risk review** over a time range (`POST /ai/{device_id}/review`) and list past reviews. The AI logic behind this is currently a placeholder heuristic; the response shape is stable and won't change when the real model is swapped in.

Ownership model: every device/data/AI endpoint is scoped to the authenticated user. Requesting a `device_id` you don't own returns `404 Not Found` (not `403`), so the frontend should treat 404 on these routes as "not found or not yours" — no need to distinguish.

---

## 2. Authentication

### 2.1 Register
```
POST /api/v1/auth/register
Content-Type: application/json
```
Request body:
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secret123",
  "full_name": "Alice A"   // optional
}
```
Response `201`:
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice A",
  "is_active": true,
  "created_at": "2026-07-23T08:06:21.103735"
}
```
Errors: `400` if username or email already registered.

### 2.2 Login
```
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded
```
> This is an OAuth2 "password flow" endpoint — send **form data**, not JSON.

Body (form-encoded):
```
username=alice&password=secret123
```
Response `200`:
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```
Errors: `401` on bad credentials.

Store `access_token`. Default expiry is 24 hours (`ACCESS_TOKEN_EXPIRE_MINUTES`, server-configured). There is no refresh-token endpoint — re-login when it expires (a `401` on any authenticated call signals this).

### 2.3 Current user
```
GET /api/v1/auth/me
Authorization: Bearer <token>
```
Response `200`: same shape as register response.

### 2.4 Using the token
Every endpoint below (except register/login) requires:
```
Authorization: Bearer <access_token>
```

---

## 3. Devices

A "device" record represents a piece of hardware the user owns. It must exist before the hardware can connect over its websocket.

### 3.1 Register a device
```
POST /api/v1/devices/
Authorization: Bearer <token>
Content-Type: application/json
```
Body:
```json
{
  "device_id": "dev-001",   // optional — physical ID printed on hardware; server generates one if omitted
  "name": "Bedside Unit"     // optional friendly name
}
```
Response `201` (**the only time `device_secret` is returned in full** — show it to the user once, they must configure it on the hardware):
```json
{
  "device_id": "dev-001",
  "name": "Bedside Unit",
  "is_active": true,
  "created_at": "2026-07-23T08:06:21.413831",
  "last_seen_at": null,
  "device_secret": "R8bGsNlkh3EKPt-PmIfkc5XqjBwiLPik0DJKWJ3m-2Y"
}
```
Errors: `400` if `device_id` already registered by anyone.

### 3.2 List my devices
```
GET /api/v1/devices/
Authorization: Bearer <token>
```
Response `200`: array of device objects **without** `device_secret`:
```json
[
  {
    "device_id": "dev-001",
    "name": "Bedside Unit",
    "is_active": true,
    "created_at": "2026-07-23T08:06:21.413831",
    "last_seen_at": "2026-07-23T09:12:03.001Z"
  }
]
```
`last_seen_at` is updated automatically whenever the hardware sends a reading — useful for an "online/offline" indicator in the UI (e.g. flag offline if `last_seen_at` is older than a few minutes, or `null` if it has never connected).

### 3.3 Get a single device
```
GET /api/v1/devices/{device_id}
Authorization: Bearer <token>
```
Response `200`: single device object (no secret). `404` if not found/not owned.

### 3.4 Update a device
```
PATCH /api/v1/devices/{device_id}
Authorization: Bearer <token>
Content-Type: application/json
```
Body (all fields optional):
```json
{ "name": "New name", "is_active": false }
```
Setting `is_active: false` disables the device — its hardware websocket connection will be refused until re-enabled. Useful for a "pause monitoring" toggle in the UI.

### 3.5 Regenerate device secret
```
POST /api/v1/devices/{device_id}/regenerate-secret
Authorization: Bearer <token>
```
Response `200`: same shape as registration response, with a **new** `device_secret`. Use this if a secret is compromised or the hardware needs re-provisioning. The old secret stops working immediately.

### 3.6 Delete a device
```
DELETE /api/v1/devices/{device_id}
Authorization: Bearer <token>
```
Response `204` (no body). Cascades: deletes all of the device's stored readings and AI reviews too. Confirm with the user before calling this.

---

## 4. Sensor Data Retrieval

All endpoints below are scoped to one device (`{device_id}` = the public string ID) and require `Authorization: Bearer <token>`. Common query params across the range/paginated endpoints:

| Param    | Type              | Default | Notes |
|----------|-------------------|---------|-------|
| `start`  | ISO 8601 datetime | none    | inclusive lower bound on `recorded_at` |
| `end`    | ISO 8601 datetime | none    | inclusive upper bound on `recorded_at` |
| `limit`  | int               | 200     | max 5000 (server clamps silently) |
| `offset` | int               | 0       | pagination offset |
| `order`  | `asc` \| `desc`   | `asc`   | sort by `recorded_at` |

### 4.1 Raw rows
```
GET /api/v1/data/{device_id}/raw?start=...&end=...&limit=...&offset=...&order=...
```
Returns a plain JSON array, exactly as stored — no wrapper object. Good for quick dumps / debugging.
```json
[
  {
    "id": 15,
    "device_id": "dev-001",
    "body_temperature": 36.7,
    "heart_rate": 84.0,
    "spo2": 98.0,
    "heart_beat_height": 0.54,
    "recorded_at": "2026-07-23T08:09:17.463773"
  }
]
```

### 4.2 Structured JSON (recommended for charts/tables)
```
GET /api/v1/data/{device_id}/json?start=...&end=...&limit=...&offset=...&order=...
```
Returns an envelope with query metadata plus the readings — useful for building "showing X of Y, page Z" UI:
```json
{
  "device_id": "dev-001",
  "count": 5,
  "start": null,
  "end": null,
  "limit": 5,
  "offset": 0,
  "order": "desc",
  "readings": [
    {
      "id": 15,
      "body_temperature": 36.7,
      "heart_rate": 84.0,
      "spo2": 98.0,
      "heart_beat_height": 0.54,
      "recorded_at": "2026-07-23T08:09:17.463773"
    }
  ]
}
```

### 4.3 Latest single reading
```
GET /api/v1/data/{device_id}/latest
```
Returns the single most recent `SensorReadingOut` object (same shape as one item in `readings` above). `404` if the device has never sent any data. Good for a live "current vitals" card that you poll on an interval, or as an initial value before opening the live websocket.

### 4.4 Rendered graph (PNG image)
```
GET /api/v1/data/{device_id}/graph?metric=spo2&start=...&end=...&limit=...&order=...
```
`metric` is one of: `body_temperature` | `heart_rate` | `spo2` | `heart_beat_height` | `all` (default `all`, which renders 4 stacked subplots).

Response is a binary `image/png` — not JSON. Use it directly as an `<img src="...">` (with the `Authorization` header sent via `fetch`/`XHR` and rendered from a blob URL, since `<img src>` alone can't set custom headers), e.g.:
```js
const res = await fetch(`/api/v1/data/${deviceId}/graph?metric=heart_rate`, {
  headers: { Authorization: `Bearer ${token}` }
});
const blob = await res.blob();
imgElement.src = URL.createObjectURL(blob);
```
If you need chart data to render with a frontend charting library instead of an image, use the `/json` endpoint (§4.2) and plot client-side.

### 4.5 Export as a downloadable file
```
GET /api/v1/data/{device_id}/export?format=json&start=...&end=...&order=...
GET /api/v1/data/{device_id}/export?format=csv&start=...&end=...&order=...
```
Returns the file with a `Content-Disposition: attachment` header (browser will download it if you navigate to the URL, or you can fetch+blob it for an in-app "download" button). No `limit`/`offset` — always returns up to `MAX_QUERY_LIMIT` (5000) matching rows.

---

## 5. Hardware Ingestion Websocket (background info, not typically used by the frontend)

```
ws://<host>/api/v1/ws/device/{device_id}?secret=<device_secret>
```
The connection is refused (`WS_1008_POLICY_VIOLATION`) if the `device_id`/`secret` pair is invalid or the device is disabled. Once connected, the hardware sends one JSON message per sample:
```json
{
  "body_temperature": 36.8,
  "heart_rate": 72,
  "spo2": 97,
  "heart_beat_height": 0.42,
  "timestamp": "2026-07-23T10:00:00"   // optional; server uses current time if omitted
}
```
Server responds to each message with either:
```json
{ "type": "ack", "reading_id": 123 }
```
or, if validation fails (values out of physiological range, missing fields, wrong types):
```json
{ "type": "error", "detail": [ { "loc": ["heart_rate"], "msg": "...", "type": "value_error" } ] }
```
An error reply does **not** close the connection — the device can just send the next sample.

Valid ranges enforced server-side: `heart_rate` 0–300, `spo2` 0–100, `body_temperature` 20–45 °C. `heart_beat_height` (accelerometer-derived) has no fixed range.

The frontend generally won't open this connection itself — it's documented here in case your app has a device-setup/testing screen that needs to explain the connection string to a user provisioning their hardware.

---

## 6. Live Data Websocket (for the frontend)

```
ws://<host>/api/v1/ws/stream/{device_id}?token=<jwt_access_token>
```
- `token` is the same JWT used for REST calls, passed as a query param because browsers can't set custom headers on a websocket handshake.
- Connection is refused if the token is invalid/expired, or if the device doesn't exist / isn't owned by that user.
- On successful connect, the server immediately sends:
```json
{ "type": "connected", "device_id": "dev-001" }
```
- From then on, every time the hardware sends a new reading, this socket receives:
```json
{
  "type": "reading",
  "device_id": "dev-001",
  "data": {
    "id": 124,
    "body_temperature": 36.9,
    "heart_rate": 72.0,
    "spo2": 97.0,
    "heart_beat_height": 0.5,
    "recorded_at": "2026-07-23T08:07:51.412837"
  }
}
```
- The frontend does not need to send anything after connecting; the client can simply listen. The connection stays open until the client closes it or the network drops — implement standard reconnect-with-backoff logic on the frontend.
- Multiple frontend clients (e.g. multiple browser tabs, or a phone + web dashboard) can subscribe to the same `device_id` simultaneously; each gets its own copy of every broadcast.

**Suggested frontend pattern:** on mount, call `GET /data/{device_id}/latest` to seed initial state, then open the stream websocket to receive subsequent updates live, appending each `reading` message to your local chart/state.

---

## 7. AI Apnoea Review

> The current prediction logic is a placeholder heuristic (documented as such by the backend). The response shape below is stable and will not change when a real model replaces it, so it's safe to build the full UI against this contract now.

### 7.1 Request a review
```
POST /api/v1/ai/{device_id}/review
Authorization: Bearer <token>
Content-Type: application/json
```
Body (all fields optional — omit entirely or send `{}` for the default: last 24 hours):
```json
{
  "start": "2026-07-22T08:00:00",     // optional ISO 8601
  "end": "2026-07-23T08:00:00",       // optional ISO 8601
  "limit_samples": 500                 // optional: analyze only the most recent N samples in range
}
```
Response `201`:
```json
{
  "id": 1,
  "device_id": "dev-001",
  "created_at": "2026-07-23T08:06:58.150131",
  "range_start": "2026-07-22T08:06:58.147154",
  "range_end": "2026-07-23T08:06:58.147154",
  "samples_analyzed": 15,
  "apnea_detected": false,
  "risk_score": 0.1,
  "confidence": 0.1,
  "summary": "Analyzed 15 samples. 1 sample(s) flagged out of range (SpO2<90.0 or HR outside [45.0, 140.0]). No significant apnoea risk detected.",
  "model_version": "placeholder-v0",
  "details": {
    "flagged_events": [
      {
        "reading_id": 8,
        "recorded_at": "2026-07-23T08:08:07.463773",
        "spo2": 85.0,
        "heart_rate": 77.0,
        "body_temperature": 36.6,
        "heart_beat_height": 0.47,
        "reasons": ["low_spo2"]
      }
    ],
    "stats": {
      "spo2_min": 85.0,
      "spo2_avg": 97.1,
      "heart_rate_min": 70.0,
      "heart_rate_max": 84.0,
      "heart_rate_avg": 77.0,
      "heart_beat_height_std": 0.043,
      "flat_signal_detected": false
    },
    "thresholds_used": {
      "spo2_apnea_threshold": 90.0,
      "heart_rate_low_threshold": 45.0,
      "heart_rate_high_threshold": 140.0,
      "heart_beat_flatness_std_threshold": 0.02
    },
    "disclaimer": "PLACEHOLDER heuristic output. Not a validated medical prediction."
  }
}
```
Field notes for UI purposes:
- `apnea_detected` (bool) — drive a clear pass/fail badge.
- `risk_score` (0.0–1.0) — good for a gauge/progress bar.
- `confidence` (0.0–1.0) — consider showing as a secondary, smaller indicator; low confidence means few samples were available.
- `details.flagged_events` — an array you can render as a timeline/list of specific anomalous moments, each with the exact `recorded_at` and readings.
- `details.disclaimer` — always present; consider surfacing this in the UI (e.g. tooltip) so users understand this is not a certified medical diagnosis while the model is a placeholder.

Errors: `400` if `start >= end`.

### 7.2 List past reviews for a device
```
GET /api/v1/ai/{device_id}/reviews?limit=50&offset=0
```
Response `200`: array of review objects (same shape as above), most recent first. Good for a "review history" tab.

### 7.3 Get a single review by ID
```
GET /api/v1/ai/reviews/{review_id}
```
Response `200`: single review object. `404` if it doesn't exist or belongs to another user.

---

## 8. Error Response Conventions

| Status | Meaning |
|--------|---------|
| `400`  | Bad request — e.g. duplicate username/email, duplicate device_id, `start >= end` |
| `401`  | Missing/invalid/expired JWT — prompt re-login |
| `404`  | Resource not found, **or** exists but not owned by the current user |
| `422`  | Request body/query failed schema validation (FastAPI default format — array of `{loc, msg, type}`) |

Standard FastAPI validation error shape (`422`):
```json
{
  "detail": [
    { "loc": ["body", "password"], "msg": "String should have at least 6 characters", "type": "string_too_short" }
  ]
}
```
Most other handled errors return:
```json
{ "detail": "Human readable message" }
```

---

## 9. Quick Reference — All Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST   | `/api/v1/auth/register` | — | Create account |
| POST   | `/api/v1/auth/login` | — | Get JWT (form-encoded) |
| GET    | `/api/v1/auth/me` | JWT | Current user profile |
| POST   | `/api/v1/devices/` | JWT | Register a device |
| GET    | `/api/v1/devices/` | JWT | List my devices |
| GET    | `/api/v1/devices/{device_id}` | JWT | Get one device |
| PATCH  | `/api/v1/devices/{device_id}` | JWT | Rename / enable-disable |
| POST   | `/api/v1/devices/{device_id}/regenerate-secret` | JWT | Rotate device secret |
| DELETE | `/api/v1/devices/{device_id}` | JWT | Delete device + its data |
| GET    | `/api/v1/data/{device_id}/raw` | JWT | Raw rows array |
| GET    | `/api/v1/data/{device_id}/json` | JWT | JSON envelope + readings |
| GET    | `/api/v1/data/{device_id}/latest` | JWT | Most recent reading |
| GET    | `/api/v1/data/{device_id}/graph` | JWT | PNG chart |
| GET    | `/api/v1/data/{device_id}/export` | JWT | Download json/csv |
| POST   | `/api/v1/ai/{device_id}/review` | JWT | Run apnoea prediction |
| GET    | `/api/v1/ai/{device_id}/reviews` | JWT | Review history |
| GET    | `/api/v1/ai/reviews/{review_id}` | JWT | One review |
| WS     | `/api/v1/ws/device/{device_id}?secret=...` | device secret | Hardware → server ingestion |
| WS     | `/api/v1/ws/stream/{device_id}?token=...` | JWT | Server → frontend live feed |
