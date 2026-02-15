# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

RDP Lottery is a local network RDP scanner with a casino-themed web UI. It scans subnets for port 3389/tcp, performs full enumeration on discovered hosts, tracks everything in SQLite, and optionally announces discoveries to Bluesky via AT Protocol.

## Running the App

```bash
# Backend (from project root)
source .venv/bin/activate
uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend
npm run dev
```

Backend runs on :8000, frontend on :5173 with Vite proxying `/api` to the backend.

```bash
# Frontend type-check & build
cd frontend && npm run build

# Frontend lint
cd frontend && npm run lint
```

## Architecture

### Backend (Python/FastAPI)

Global singletons (`_config`, `_scanner`, `_announcer`) are initialized in `main.py`'s lifespan handler and accessed via `get_config()`, `get_scanner()`, `get_announcer()`. Routers import these via deferred imports from `backend.main`.

**Scan execution flow** (`routers/scans.py`): `POST /api/scans` creates a scan record, then spawns a `threading.Thread` (daemon) running `_run_scan()`. This is because python-nmap is synchronous/blocking. Each scan method in `scanner.py` creates its own `nmap.PortScanner()` instance for thread safety.

**Two-phase scanning** (`scanner.py`):
1. Discovery: `nmap -Pn -p 3389 --open` across the subnet
2. Full scan: `nmap -A -Pn` per discovered RDP host (OS, versions, scripts, traceroute)

The `-Pn` flag is critical — many hosts block ping probes and would be missed without it.

**Database** (`database.py`): Raw SQLite with `sqlite3.Row` factory, WAL mode. All CRUD is plain functions (no ORM). Hosts use `UNIQUE(ip, subnet_id)` with upsert logic. On startup, orphaned running/pending scans are marked as failed via `cleanup_orphaned_scans()`.

**Live logging**: `main.py` has a `BufferHandler` that captures log lines into a `deque(maxlen=500)`. Exposed via `GET /api/logs` (polling) and `GET /api/logs/stream` (SSE).

### Frontend (Vite + React + TypeScript)

- Tailwind CSS v4 (CSS-based config in `index.css` via `@theme`, no `tailwind.config.js`)
- `@tanstack/react-query` with 10s auto-refetch for live updates
- `react-router-dom` for client-side routing
- Casino theme: green felt background, gold/neon accents, custom `.casino-card`, `.btn-neon`, `.badge-*` CSS classes defined in `index.css`
- `SlotMachineLog` component connects to the SSE endpoint for live log streaming
- All API calls go through `api.ts` fetch wrapper

### AT Protocol / Bluesky (`atproto_client.py`)

Uses `atproto` SDK: `Client()` → `client.login()` → `client.send_post()`. Disabled by default in `config.toml`. The `announced` flag on hosts prevents duplicate posts.

## Config

`config.toml` at project root. Loaded via `tomllib` (stdlib since 3.11). Dataclass structure in `config.py`: `AppConfig`, `ScannerConfig`, `AtprotoConfig`.

## Key Gotchas

- Server reload during a scan kills the scan thread silently — orphan cleanup on startup handles this
- Scanning a /24 with `-Pn` probes all 256 IPs without ping, so it's slower than default nmap
- The Vite proxy for `/api/logs/stream` (SSE) needs a specific entry before the general `/api` proxy rule to avoid buffering issues
- `python-nmap` requires `nmap` binary installed on the system (`brew install nmap`)
