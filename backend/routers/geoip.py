"""GeoIP browser endpoints."""

import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query

from backend.models import (
    GeoipStatusResponse,
    GeoipCountryResponse,
    GeoipStateResponse,
    GeoipCityResponse,
    GeoipBlocksResponse,
    BulkSubnetCreate,
    BulkSubnetResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geoip", tags=["geoip"])

_import_executor = ThreadPoolExecutor(max_workers=1)
_import_lock = threading.Lock()
_import_state: dict = {"running": False, "progress": None, "error": None}


def _get_config():
    from backend.main import get_config
    return get_config()


def _run_import():
    """Background task: download and import the GeoIP CSV."""
    from backend.geoip_db import download_csv, import_csv

    config = _get_config()
    _import_state["running"] = True
    _import_state["progress"] = 0
    _import_state["error"] = None

    try:
        csv_path = download_csv(config.geoip.download_url_template)
        import_csv(
            config.geoip.database_path,
            csv_path,
            progress_cb=lambda n: _import_state.update(progress=n),
        )
        _import_state["progress"] = None
    except Exception as e:
        logger.error(f"GeoIP import failed: {e}")
        _import_state["error"] = str(e)
        raise
    finally:
        _import_state["running"] = False


@router.get("/status", response_model=GeoipStatusResponse)
def geoip_status():
    """Get GeoIP database import status."""
    from backend.geoip_db import get_status

    config = _get_config()
    status = get_status(config.geoip.database_path)
    return GeoipStatusResponse(
        imported=status["imported"],
        csv_date=status["csv_date"],
        last_updated=status["last_updated"],
        total_blocks=status["total_blocks"],
        import_running=_import_state["running"],
        import_progress=_import_state["progress"],
    )


@router.post("/import")
def trigger_import():
    """Trigger a background download and import of the GeoIP database."""
    if _import_state["running"]:
        raise HTTPException(409, "Import already running")

    _import_executor.submit(_run_import)
    return {"message": "Import started"}


@router.get("/countries", response_model=list[GeoipCountryResponse])
def get_countries():
    """List all countries with block counts."""
    from backend.geoip_db import list_countries

    config = _get_config()
    return list_countries(config.geoip.database_path)


@router.get("/states", response_model=list[GeoipStateResponse])
def get_states(country: str = Query(...)):
    """List states/regions for a country."""
    from backend.geoip_db import list_states

    config = _get_config()
    return list_states(config.geoip.database_path, country)


@router.get("/cities", response_model=list[GeoipCityResponse])
def get_cities(country: str = Query(...), state: str = Query(...)):
    """List cities for a country and state."""
    from backend.geoip_db import list_cities

    config = _get_config()
    return list_cities(config.geoip.database_path, country, state)


@router.get("/blocks", response_model=GeoipBlocksResponse)
def get_blocks(
    country: str = Query(...),
    state: str = Query(...),
    city: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List IP blocks for a location with CIDR conversion."""
    from backend.geoip_db import list_blocks

    config = _get_config()
    return list_blocks(config.geoip.database_path, country, state, city, page, page_size)


@router.post("/add-subnets", response_model=BulkSubnetResponse)
def add_subnets(body: BulkSubnetCreate):
    """Bulk-create subnets from GeoIP CIDR blocks, skip duplicates, and queue scans."""
    from backend.database import get_connection
    from backend.routers.scans import _scan_pool, _run_scan

    config = _get_config()
    db_path = config.app.database_path

    conn = get_connection(db_path)
    created = 0
    skipped = 0
    created_subnet_ids: list[int] = []
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for cidr in body.cidrs:
            try:
                cursor = conn.execute(
                    "INSERT INTO subnets (cidr, label, is_active, created_at, updated_at) "
                    "VALUES (?, ?, 1, ?, ?)",
                    (cidr, body.label, now, now),
                )
                created += 1
                created_subnet_ids.append(cursor.lastrowid)
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()

    # Queue scans for all newly created subnets
    import backend.database as db
    scans_queued = 0
    for subnet_id in created_subnet_ids:
        subnet = db.get_subnet(db_path, subnet_id)
        if subnet:
            scan = db.create_scan(db_path, subnet_id)
            _scan_pool.submit(_run_scan, scan["id"], subnet, db_path)
            scans_queued += 1

    logger.info(f"Bulk subnet add: {created} created, {skipped} duplicates skipped, {scans_queued} scans queued")
    return BulkSubnetResponse(created=created, skipped=skipped, scans_queued=scans_queued)
