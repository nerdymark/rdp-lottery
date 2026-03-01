"""FastAPI application entry point."""

import asyncio
import collections
import logging
from contextlib import asynccontextmanager
from typing import Optional

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import Config, load_config
from backend.database import init_db, cleanup_orphaned_scans
from backend.geoip_db import init_geoip_db
from backend.scanner import NetworkScanner
from backend.atproto_client import BlueskyAnnouncer

# --- In-memory log ring buffer ---
LOG_BUFFER: collections.deque[str] = collections.deque(maxlen=500)
_log_event: asyncio.Event | None = None


def get_log_event() -> asyncio.Event:
    global _log_event
    if _log_event is None:
        _log_event = asyncio.Event()
    return _log_event


class BufferHandler(logging.Handler):
    """Captures log lines into a ring buffer and signals SSE waiters."""

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        LOG_BUFFER.append(line)
        evt = _log_event
        if evt is not None:
            evt.set()


# Set up logging with both console and buffer output
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_console = logging.StreamHandler()
_console.setFormatter(_formatter)

_buffer_handler = BufferHandler()
_buffer_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_console, _buffer_handler])

_config: Optional[Config] = None
_scanner: Optional[NetworkScanner] = None
_announcer: Optional[BlueskyAnnouncer] = None


def get_config() -> Config:
    assert _config is not None
    return _config


def get_scanner() -> NetworkScanner:
    assert _scanner is not None
    return _scanner


def get_announcer() -> Optional[BlueskyAnnouncer]:
    return _announcer


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _scanner, _announcer

    _config = load_config()
    init_db(_config.app.database_path)
    if _config.geoip.enabled:
        init_geoip_db(_config.geoip.database_path)
    orphaned = cleanup_orphaned_scans(_config.app.database_path)
    if orphaned:
        logging.getLogger(__name__).warning(f"Cleaned up {orphaned} orphaned scan(s)")
    _scanner = NetworkScanner(_config.scanner)
    _announcer = BlueskyAnnouncer(_config.atproto)

    logging.getLogger(__name__).info(
        f"RDP Lottery started on {_config.app.host}:{_config.app.port}"
    )
    yield


app = FastAPI(title="RDP Lottery", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers import subnets, scans, hosts, geoip  # noqa: E402

app.include_router(subnets.router)
app.include_router(scans.router)
app.include_router(hosts.router)
app.include_router(geoip.router)


# --- Screenshot endpoint ---

@app.get("/api/screenshots/{filename}")
def get_screenshot(filename: str):
    """Serve screenshot PNG files."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    filepath = Path("screenshots") / safe_name
    if not filepath.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "Screenshot not found")
    return FileResponse(filepath, media_type="image/png")


# --- Log endpoints ---

@app.get("/api/logs")
def get_logs():
    """Return recent log lines."""
    return {"logs": list(LOG_BUFFER)}


@app.get("/api/logs/stream")
async def stream_logs():
    """SSE endpoint for live log streaming."""

    async def event_generator():
        idx = len(LOG_BUFFER)
        yield f"data: {{'type':'init','count':{idx}}}\n\n"
        while True:
            evt = get_log_event()
            evt.clear()
            buf = list(LOG_BUFFER)
            if len(buf) > idx:
                for line in buf[idx:]:
                    escaped = line.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
                    yield f"data: {{\"type\":\"log\",\"line\":\"{escaped}\"}}\n\n"
                idx = len(buf)
            elif len(buf) < idx:
                # Buffer wrapped
                idx = 0
                continue
            try:
                await asyncio.wait_for(evt.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
