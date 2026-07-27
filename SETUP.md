# Apnoea Backend — Local Setup & Deployment Guide

This document explains how to run the backend locally in a Python virtual
environment, how to test it, and how to deploy it to a server.

---

## 1. Requirements

- Python 3.10+ (tested on 3.12)
- pip
- (Optional, for production) a Linux server with `systemd` and `nginx`

---

## 2. Project layout

```
apnea_backend/
├── app/
│   ├── main.py              # FastAPI app entrypoint
│   ├── config.py            # Settings loaded from environment / .env
│   ├── database.py          # SQLAlchemy engine/session
│   ├── models.py             # ORM models (User, Device, SensorReading, AIReview)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── security.py           # Password hashing + JWT auth
│   ├── deps.py                # Shared FastAPI dependencies (device ownership)
│   ├── websocket_manager.py  # In-memory websocket connection manager
│   ├── ai_placeholder.py     # PLACEHOLDER apnoea prediction logic
│   ├── utils/plotting.py     # Matplotlib graph rendering
│   └── routers/
│       ├── auth_router.py    # /auth/*
│       ├── devices.py        # /devices/*
│       ├── data.py           # /data/*  (raw / json / graph / export)
│       ├── ai_review.py      # /ai/*
│       └── ws.py              # /ws/device/*  and  /ws/stream/*
├── scripts/
│   └── simulate_device.py    # Simulates hardware for local testing
├── requirements.txt
├── .env.example
├── run.py
└── SETUP.md                  # This file
```

---

## 3. Local setup (virtual environment)

```bash
# 1. Unzip / clone the project, then cd into it
cd apnea_backend

# 2. Create a virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows (PowerShell: venv\Scripts\Activate.ps1)

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create your local environment file
cp .env.example .env
# Edit .env and set a real SECRET_KEY, e.g.:
python3 -c "import secrets; print(secrets.token_hex(32))"

# 6. Run the development server
python run.py
# or equivalently:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs (Swagger UI): `http://localhost:8000/docs`
Alternative docs (ReDoc): `http://localhost:8000/redoc`

On first run, a `apnoea.db` SQLite file is automatically created in the
project root with all required tables (`Base.metadata.create_all` runs at
startup — no manual migration step is needed for a fresh install).

---

## 4. Quick smoke test

With the server running, in another terminal:

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"secret123"}'

# Log in (OAuth2 password flow -> form data, not JSON)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=alice&password=secret123"
# -> {"access_token": "...", "token_type": "bearer"}

TOKEN="<paste access_token here>"

# Register a device (hardware)
curl -X POST http://localhost:8000/api/v1/devices/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"dev-001","name":"Bedside Unit"}'
# -> includes a one-time "device_secret" — save it, the hardware needs it
```

### Simulate the hardware sending data (no physical device needed)

```bash
python scripts/simulate_device.py \
  --url ws://localhost:8000/api/v1 \
  --device-id dev-001 \
  --secret <device_secret_from_above> \
  --interval 1 \
  --count 20
```

### Retrieve the data

```bash
# Raw rows
curl "http://localhost:8000/api/v1/data/dev-001/raw" -H "Authorization: Bearer $TOKEN"

# Structured JSON with query metadata
curl "http://localhost:8000/api/v1/data/dev-001/json?limit=50&order=desc" -H "Authorization: Bearer $TOKEN"

# PNG graph (save to file)
curl "http://localhost:8000/api/v1/data/dev-001/graph?metric=spo2" \
  -H "Authorization: Bearer $TOKEN" -o spo2_graph.png

# CSV export
curl "http://localhost:8000/api/v1/data/dev-001/export?format=csv" \
  -H "Authorization: Bearer $TOKEN" -o readings.csv
```

### Request an AI review

```bash
curl -X POST "http://localhost:8000/api/v1/ai/dev-001/review" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{}'
# Defaults to analyzing the last 24 hours of stored data.
# Pass {"start": "...", "end": "..."} (ISO 8601) for a specific range.
```

### Live stream to a frontend client

Frontend connects to:
```
ws://localhost:8000/api/v1/ws/stream/dev-001?token=<JWT access_token>
```
It will receive a `{"type":"connected", ...}` message, then a
`{"type":"reading", "device_id": "...", "data": {...}}` message every time the
hardware sends a new sample.

---

## 5. Authentication & connection model summary

| Actor            | Connects to                                   | Credential                          |
|------------------|------------------------------------------------|--------------------------------------|
| End user (app)   | REST endpoints (`/auth`, `/devices`, `/data`, `/ai`) | JWT Bearer token from `/auth/login` |
| Hardware device  | `ws://.../ws/device/{device_id}?secret=...`     | `device_id` + `device_secret` (issued at registration) |
| Frontend viewer  | `ws://.../ws/stream/{device_id}?token=...`      | JWT Bearer token (query param, since browsers can't set ws headers) |

A device must be registered by an authenticated user (`POST /devices/`)
before the hardware can open a websocket connection. The returned
`device_secret` is shown only once (and again via
`POST /devices/{device_id}/regenerate-secret` if it needs to be rotated).

---

## 6. Configuration reference (`.env`)

| Variable                     | Default                         | Description |
|-------------------------------|----------------------------------|--------------|
| `DATABASE_URL`                | `sqlite:///./apnoea.db`         | SQLAlchemy DB URL. Swap for Postgres/MySQL URL in production if desired. |
| `SECRET_KEY`                  | *(must change)*                  | JWT signing secret. Generate with `secrets.token_hex(32)`. |
| `ALGORITHM`                   | `HS256`                          | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | `1440` (24h)                     | JWT expiry. |
| `CORS_ORIGINS`                 | `*`                               | Comma-separated allowed origins. Restrict in production. |
| `MAX_QUERY_LIMIT`              | `5000`                            | Hard cap on rows returned per data query/export. |
| `DEFAULT_QUERY_LIMIT`          | `200`                             | Default page size when `limit` isn't specified. |

---

## 7. Running tests / verifying the install

A quick way to sanity check the whole stack without any hardware:

```bash
source venv/bin/activate
python run.py &            # start the server in the background
sleep 2
python scripts/simulate_device.py --device-id dev-001 --secret <secret> --count 5
```

(You need to have registered a user + device first, per section 4.)

---

## 8. Deployment

### 8.1 General production notes

- **Switch the database** for anything beyond a single-process/light-traffic
  deployment. SQLite works fine for development and small deployments, but
  for concurrent writers at scale, point `DATABASE_URL` at Postgres, e.g.
  `postgresql+psycopg2://user:pass@host:5432/apnoea` (install
  `psycopg2-binary` in that case) — no application code changes are needed
  since SQLAlchemy abstracts the dialect.
- **Set a strong `SECRET_KEY`** and never commit `.env` to version control.
- **Restrict `CORS_ORIGINS`** to your actual frontend domain(s).
- **Run behind HTTPS/WSS** (via a reverse proxy — see below). Browsers will
  refuse to open `ws://` connections from an `https://` page (must be `wss://`).
- **Do not use `--reload`** in production; it's a development convenience only.

### 8.2 Run with Gunicorn + Uvicorn workers (recommended for production)

```bash
pip install gunicorn
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 \
  -b 0.0.0.0:8000 \
  --timeout 120
```

> Note: websocket connections are long-lived; keep worker count aligned with
> expected concurrent connections and consider `--timeout` implications for
> idle websocket workers.

### 8.3 systemd service (example)

`/etc/systemd/system/apnoea-backend.service`:

```ini
[Unit]
Description=Apnoea Backend
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/apnea_backend
Environment="PATH=/opt/apnea_backend/venv/bin"
EnvironmentFile=/opt/apnea_backend/.env
ExecStart=/opt/apnea_backend/venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now apnoea-backend
```

### 8.4 Nginx reverse proxy (with WebSocket support)

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Required for websocket upgrade
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Keep long-lived websocket connections open
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

With this in place, hardware and frontends connect over `wss://api.yourdomain.com/api/v1/ws/...`.

### 8.5 Docker (optional)

A minimal `Dockerfile` if you prefer containerized deployment:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000"]
```

```bash
docker build -t apnoea-backend .
docker run -d -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data apnoea-backend
```

> If using SQLite in Docker, mount a volume for the `.db` file so data isn't
> lost when the container is recreated (set `DATABASE_URL=sqlite:////app/data/apnoea.db`).

---

## 9. Replacing the placeholder AI

The apnoea prediction logic lives entirely in `app/ai_placeholder.py`,
in the function `run_apnea_prediction(readings)`. It currently uses simple
threshold heuristics (documented in the file) so the rest of the system
(storage, endpoints, review history) can be built and used today.

To plug in a real model:
1. Load your trained model at module import time (or lazily on first call).
2. Replace the body of `run_apnea_prediction()` with real inference over the
   `readings` list (list of `SensorReading` ORM objects, chronologically ordered).
3. Return a dict with the same keys currently returned
   (`apnea_detected`, `risk_score`, `confidence`, `summary`, `model_version`, `details`)
   so `app/routers/ai_review.py` and `schemas.AIReviewOut` keep working unchanged.

If inference becomes slow, convert `POST /ai/{device_id}/review` in
`app/routers/ai_review.py` to enqueue a background job (e.g. Celery, RQ, or
FastAPI `BackgroundTasks`) and have clients poll
`GET /ai/reviews/{review_id}` for the result instead of waiting synchronously.

---

## 10. Security notes

- Passwords are hashed with bcrypt (via passlib); plaintext passwords are
  never stored.
- JWTs are signed with `SECRET_KEY`/`ALGORITHM` and expire after
  `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Every device/data/AI-review endpoint checks that the authenticated user
  owns the requested `device_id`; a non-owner gets a `404` (not a `403`, to
  avoid confirming the device exists).
- Hardware websocket connections require both the public `device_id` and a
  private `device_secret` generated at registration — the `device_id` alone
  is not sufficient to open a data-writing connection.
- Rotate a compromised `device_secret` via
  `POST /devices/{device_id}/regenerate-secret`.
