# complex-sim-platform — Backend

Robust FastAPI backend for the complex simulation platform: multi-kind simulation
engine (particles, fluids, physics, neural, bio) with JWT auth, WebSocket
real-time stepping, file export and auto-generated reports. Runs with **zero
external services** (in-memory + JSON files) and exposes a storage seam ready
for Postgres / Timescale / Mongo via `DATABASE_URL`.

## Stack

`fastapi` · `uvicorn` · `pydantic` · `python-jose` (JWT, HS256) · `passlib`+`bcrypt`
(passlib is part of the stack; the auth module self-tests it and automatically
falls back to direct bcrypt when passlib 1.7.4 + bcrypt>=4.1 misbehave).

```
backend/
├── app/
│   ├── main.py          # app factory, middleware stack, /health, /metrics
│   ├── auth.py          # JWT + bcrypt (passlib w/ fallback), dependencies
│   ├── store.py         # StorageBackend interface + JSON-file persistence
│   ├── sim_service.py   # simcore loader (mock fallback), engines, export, report
│   ├── routes_auth.py   # /api/auth/register, /login, /me
│   ├── routes_sim.py    # /api/simulations/*
│   ├── ws.py            # /ws/simulations/{id} with multi-client broadcast
│   ├── ratelimit.py     # in-memory per-IP rate limiting middleware
│   ├── cache.py         # thread-safe LRU cache with TTL
│   ├── monitoring.py    # JSON-lines logging + metrics registry + middleware
│   └── config.py        # env-driven settings
├── export_openapi.py    # python export_openapi.py -> openapi.yaml
├── requirements.txt
├── Dockerfile
├── .env.example
└── data/                # durable JSON (users.json, simulations.json)
```

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # adjust SECRET_KEY!
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Interactive docs: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json (static copy: `openapi.yaml`)
- Health: `GET /health` · Metrics: `GET /metrics` (simple JSON)

## API contract

| Method | Path | Auth | Body → Response |
|---|---|---|---|
| POST | `/api/auth/register` | no | `{username, password}` → `{access_token, token_type, role, username}` |
| POST | `/api/auth/login` | no | `OAuth2PasswordRequestForm` (`username`, `password`) → `{access_token, ...}` |
| GET | `/api/auth/me` | yes | → `{username, role, created_at}` |
| GET | `/api/simulations/kinds` | no | → `["particles","fluids","physics","neural","bio"]` |
| GET | `/api/simulations` | yes | list (users: own, admins: all) |
| POST | `/api/simulations` | yes | `{kind, params}` → `{id, kind, params, ...}` |
| GET | `/api/simulations/{id}` | owner/admin | → full record incl. `state` (cached 60 s) |
| POST | `/api/simulations/{id}/step` | owner/admin | `{dt, steps}` → `{state, steps_done, dt, steps, t}` |
| GET | `/api/simulations/{id}/export?format=csv\|json\|parquet\|hdf5` | owner/admin | → file download (`sim_{id}.<ext>`) |
| POST | `/api/simulations/{id}/report` | owner/admin | → `{summary, stats, charts_data}` |
| DELETE | `/api/simulations/{id}` | owner/admin | → `{deleted, id}` |
| WS | `/ws/simulations/{id}?token=<jwt>` | token | send `{"dt":0.016,"steps":1}` → broadcast `{"type":"state", ...}` |

### WebSocket example

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws/simulations/<id>?token=<jwt>") as ws:
        print(await ws.recv())                       # {"type":"init", "state":...}
        await ws.send(json.dumps({"dt": 0.016, "steps": 5}))
        while True:
            msg = json.loads(await ws.recv())        # {"type":"state","state":...}
            print(msg["state"]["t"], msg["steps_done"])

asyncio.run(main())
```

Every client connected to the same simulation receives every tick
(multi-client broadcast). `{"action":"get_state"}` returns the current state
without stepping. `{"dt": ..., "steps": ...}` messages are throttled per
connection (default 120/min, `WS_MESSAGE_LIMIT_PER_MINUTE`).

### Auth example

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"wanda","password":"s3cret-pass"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s http://127.0.0.1:8000/api/simulations/kinds
curl -s -X POST http://127.0.0.1:8000/api/simulations \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"kind":"bio","params":{"prey0":40,"predator0":9}}'
```

## Robustness & security features

- **JWT auth** — HS256, 60 min expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`), roles
  `user`/`admin`; `ADMIN_USERS` promotes listed usernames at registration.
  Admins list/step/export/delete every simulation; users only their own
  (foreign ids surface as 404 — no enumeration).
- **bcrypt passwords** — 72-byte pre-truncation, direct-bcrypt fallback if
  passlib is broken in the installed combination.
- **Rate limiting** — in-memory sliding window, 100 req/min/IP
  (`RATE_LIMIT_PER_MINUTE`), HTTP 429 + `Retry-After`. Exempt:
  `/health,/docs,/redoc,/openapi.json`.
- **LRU cache** — GETs cached 60 s (`CACHE_TTL_SECONDS`, `CACHE_MAXSIZE`);
  invalidated on step/delete. Hit/miss stats in `/metrics`.
- **Input validation** — pydantic constraints: username regex
  `^[A-Za-z0-9_.-]{3,32}$`, password 8–128, params depth ≤ 4 / ≤ 64 keys /
  strict key charset / finite numbers / bounded strings & lists.
- **Protective headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, `Referrer-Policy`, CSP (`default-src 'none'` on the API; permissive
  only for `/docs`), `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- **Structured logs** — every request as one JSON line (method, path, status,
  duration, IP, request id; `X-Request-Id` echoed in responses).
- **CORS wide open** (`*`, no credentials) by default; set `CORS_ORIGINS` to
  lock down.
- **Work budget** — `steps × engine cells ≤ SIM_MAX_WORK` (20 M) guards
  against pathological step payloads (422).
- **Corrupt-data resilience** — unreadable JSON files are quarantined
  (`.corrupt-<ts>.json`) and the store starts empty instead of crashing.

## Storage: JSON today, Postgres/Timescale/Mongo when ready

The default backend is in-memory dicts mirrored to `DATA_DIR/users.json` and
`DATA_DIR/simulations.json` (atomic writes via temp file + rename), so nothing
breaks without a database. All persistence goes through the `StorageBackend`
interface in `app/store.py`; a Postgres/Timescale/Mongo adapter implements the
same five methods (`get/put/delete/all/flush`) and is selected when
`DATABASE_URL` is set — no other module changes. `/metrics` and `/health`
report the active storage mode.

## Simulation engine: simcore with mock fallback

`sim_service.py` adds `SIM_CORE_PATH` (default `../simulation-core`) to
`sys.path` and imports `simcore`. Because the real package is still being
built out, the import commonly fails — the service **never crashes on
startup**: it logs the failure and activates five built-in mock engines that
implement the same `Simulatable` interface (`step`, `get_state`, `set_state`,
`get_params`, `set_params`) with genuine numeric behaviour:

| kind | model | history series |
|---|---|---|
| `particles` | bouncing particles, unit square | kinetic_energy, mean_speed |
| `fluids` | scalar-field diffusion on a grid | total_mass, max_density |
| `physics` | damped pendulum | theta, omega, energy |
| `neural` | rate-coded recurrent network | mean_rate, mean_activity, spikes |
| `bio` | Lotka–Volterra predator/prey | prey, predators |

States are JSON-safe, persisted after every step, and each kind keeps a rolling
history used by `/report` (`charts_data.series`) and by CSV/parquet/HDF5
exports.

## Export formats

- `csv` — pandas table of the flattened state (stdlib fallback if pandas is
  missing).
- `json` — full state document.
- `parquet` — pandas + pyarrow.
- `hdf5` — h5py file (`state/*` datasets + `history_json`/`params_json`
  attributes). Returns 501 with a clear message if the library is absent.

## Docker

```bash
docker build -t complex-sim-backend .
docker run -d -p 8000:8000 \
  -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')" \
  -v sim_data:/app/data \
  complex-sim-backend
```

## Validation

```bash
python -m py_compile app/*.py export_openapi.py        # all files compile
python export_openapi.py                                # regenerate openapi.yaml
python -c "from app.main import app; print(app.openapi()['info']['title'])"
```