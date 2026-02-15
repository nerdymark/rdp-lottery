# RDP Lottery 🎰

A local network scanner with a casino-themed web UI that discovers RDP and VNC servers, checks authentication requirements, captures screenshots of unauthenticated desktops, and optionally announces discoveries to Bluesky.

## What It Does

- **Discovery** — Scans subnets for RDP (3389–3390) and VNC (5900–5901) in a single nmap pass
- **Full Enumeration** — OS detection, open ports, NetBIOS names, domain info, SSL certs, MAC addresses
- **Auth Checking** — Determines NLA status for RDP and authentication type for VNC (None/password)
- **Screenshots** — Captures login screens from non-NLA RDP hosts (via FreeRDP) and unauthenticated VNC desktops (via vncdotool)
- **Enrichment** — ASN, GeoIP, reverse DNS, and IP type classification for every host
- **Bluesky Announcements** — Posts discoveries with screenshots to Bluesky via AT Protocol (opt-in)
- **Live Logging** — Real-time scan output streamed to the browser via SSE
- **External Feeds** — Import scan targets from an external host feed or VNC Resolver's random endpoint

## Architecture

```
┌─────────────────┐     /api proxy      ┌──────────────────┐
│   Vite + React   │ ◄────────────────► │  FastAPI (uvicorn) │
│   :5173          │                     │  :8000             │
└─────────────────┘                     └────────┬─────────┘
                                                 │
                                    ┌────────────┼────────────┐
                                    │            │            │
                               SQLite DB    nmap binary   vncdotool
                              (WAL mode)                  / FreeRDP
```

**Backend** — Python/FastAPI with raw SQLite (no ORM). Scans run in daemon threads because python-nmap is synchronous. Each nmap call creates its own `PortScanner()` instance for thread safety.

**Frontend** — React 19 + TypeScript + Tailwind CSS v4 + TanStack Query (10s auto-refetch). Casino theme with green felt background, gold/neon accents, and a slot machine–styled live log viewer.

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **nmap** — `brew install nmap` / `apt install nmap`
- **FreeRDP** (optional, for RDP screenshots) — `brew install freerdp3`
- **vncdotool** (installed automatically via pip)

## Quick Start

```bash
# Clone and set up Python environment
git clone <repo-url> && cd rdp-lottery
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Copy config template
cp config.example.toml config.toml

# Install frontend dependencies
cd frontend && npm install && cd ..

# Start backend
uvicorn backend.main:app --reload

# Start frontend (separate terminal)
cd frontend && npm run dev
```

Backend runs on http://localhost:8000, frontend on http://localhost:5173 with Vite proxying `/api` to the backend.

## Configuration

All config lives in `config.toml` at the project root:

```toml
[app]
host = "127.0.0.1"
port = 8000
database_path = "rdp_lottery.db"

[scanner]
timing_template = 4          # nmap -T flag (1–5)
host_timeout_seconds = 120

[atproto]
enabled = false
service_url = "https://bsky.social"
username = ""
app_password = ""
post_template = "Jackpot! Found an open {proto} host{hostname_suffix}\n{asn}\n{ip_type}"
```

### Bluesky Announcements

Set `enabled = true` and fill in your Bluesky handle and an [app password](https://bsky.app/settings/app-passwords). The `post_template` supports these variables:

| Variable | Example |
|----------|---------|
| `{proto}` | `RDP` or `VNC` |
| `{hostname_suffix}` | `: SERVER01` (empty if no hostname) |
| `{asn}` | `AS13335` |
| `{ip_type}` | `Datacenter`, `Residential`, `Mobile`, `Private` |

Posts are only created when a screenshot is available. IPs, domains, and ports are never included.

## Scan Pipeline

Each scan executes these phases sequentially per subnet:

| Phase | What | Scope |
|-------|------|-------|
| 1 | **Discovery** — `nmap -Pn --open -p 3389-3390,5900-5901` | All IPs in subnet |
| 2 | **Full scan** — `nmap -A -Pn` (OS, ports, scripts) | Each RDP host, then VNC-only hosts |
| 2.25 | **SSL cert** — `nmap --script ssl-cert` | Each RDP host |
| 2.5 | **NLA check** — `nmap --script rdp-enum-encryption` | Each RDP host |
| 3 | **RDP screenshot** — FreeRDP + screencapture | Non-NLA RDP hosts |
| 4 | **VNC auth** — `nmap --script vnc-info,vnc-title` | Each VNC port per host |
| 4.1 | **VNC screenshot** — `vncdo capture` | No-auth VNC ports |
| 5 | **Enrichment** — ip-api.com + reverse DNS | All discovered hosts |

The `-Pn` flag is used everywhere because many hosts block ICMP probes.

## Pages

### Dashboard (`/`)
Stats cards, scan-all button, live log feed (SSE-powered slot machine), and recent scan history with clickable hit counts that link to filtered host views.

### Subnets (`/subnets`)
Add/remove target subnets, toggle active/inactive, trigger per-subnet scans. Includes **Lucky Draw** (random VNC Resolver host → scan its /24) and **Hot Tips from the Wire** (external feed import).

### Hosts (`/hosts`)
Sortable table of all discovered hosts with RDP/VNC/NLA badges, filterable by subnet, RDP-only, or VNC-only. Supports deep-linking via query params (`?subnet_id=1&rdp_only=true`).

### Host Detail (`/hosts/:id`)
Full host dossier: identity (hostname, NetBIOS, domain, MAC, OS), metadata (NLA, VNC auth, scan info), network intelligence (ASN, ISP, GeoIP, coordinates, IP type), security protocols, RDP/VNC screenshots, and open port table with color-coded RDP (green) and VNC (purple) ports.

### Scan Log (`/scans`)
Complete scan history with duration, host/RDP/VNC counts, and error details.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/hosts` | List hosts (query: `subnet_id`, `rdp_only`, `vnc_only`) |
| `GET` | `/api/hosts/stats` | Aggregate stats |
| `GET` | `/api/hosts/:id` | Host detail |
| `GET` | `/api/subnets` | List subnets |
| `POST` | `/api/subnets` | Create subnet |
| `PATCH` | `/api/subnets/:id` | Update subnet |
| `DELETE` | `/api/subnets/:id` | Delete subnet + all hosts/scans |
| `GET` | `/api/scans` | List scans (query: `subnet_id`) |
| `POST` | `/api/scans` | Trigger scan (body: `subnet_id` or omit for all) |
| `GET` | `/api/scans/active` | Currently running scans |
| `GET` | `/api/scans/feed-targets` | External feed IPs |
| `GET` | `/api/scans/vnc-random` | Random host from VNC Resolver |
| `GET` | `/api/screenshots/:file` | Serve screenshot PNG |
| `GET` | `/api/logs` | Recent log lines |
| `GET` | `/api/logs/stream` | SSE live log stream |

## Database

SQLite with WAL mode. Schema auto-creates on first run. New columns are added via idempotent `ALTER TABLE` migrations — no migration tool needed.

**Tables:** `subnets`, `scans`, `hosts`

The `hosts` table uses `UNIQUE(ip, subnet_id)` with upsert logic so rescans merge data rather than creating duplicates.

## Project Structure

```
rdp-lottery/
├── backend/
│   ├── main.py             # FastAPI app, lifespan, log buffer, SSE
│   ├── config.py           # TOML config loader, dataclasses
│   ├── database.py         # SQLite schema, CRUD, migrations
│   ├── scanner.py          # NetworkScanner (nmap, FreeRDP, vncdotool)
│   ├── atproto_client.py   # Bluesky announcer
│   ├── models.py           # Pydantic request/response models
│   └── routers/
│       ├── subnets.py      # Subnet CRUD endpoints
│       ├── scans.py        # Scan trigger, history, feed, VNC resolver
│       └── hosts.py        # Host list, detail, stats
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Routes
│   │   ├── api.ts          # Typed fetch wrapper
│   │   ├── types.ts        # TypeScript interfaces
│   │   ├── index.css       # Tailwind v4 theme + casino CSS
│   │   └── components/
│   │       ├── Layout.tsx          # Nav + shell
│   │       ├── Dashboard.tsx       # Stats, scan button, recent rolls
│   │       ├── SubnetManager.tsx   # Subnet CRUD, Lucky Draw, feed
│   │       ├── HostTable.tsx       # Filterable/sortable host list
│   │       ├── HostDetail.tsx      # Full host dossier
│   │       ├── ScanHistory.tsx     # Scan log table
│   │       └── SlotMachineLog.tsx  # SSE live log viewer
│   └── vite.config.ts     # Vite + proxy config
├── config.toml             # Runtime configuration
├── pyproject.toml          # Python dependencies
└── CLAUDE.md               # AI assistant instructions
```

## Gotchas

- **Server reload kills scans** — Orphaned running/pending scans are automatically marked as failed on startup
- **`-Pn` is slow** — A /24 probes all 256 IPs without ping, which is slower than default nmap but necessary because many hosts block ICMP
- **SSE proxy ordering** — The Vite config has a specific entry for `/api/logs/stream` before the general `/api` proxy to prevent buffering issues
- **nmap must be installed** — `python-nmap` is just a wrapper; the `nmap` binary must be on PATH
- **macOS screenshots** — FreeRDP screenshot capture requires Screen Recording permission for Terminal/Python in System Settings > Privacy & Security
- **VNC displays** — VNC servers can run on non-default ports (5901 for display :1); both 5900 and 5901 are scanned
- **RDP on alternate ports** — ms-wbt-server sometimes runs on 3390; both 3389 and 3390 are scanned

## License

Private project. Not licensed for redistribution.
