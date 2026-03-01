"""Host listing and detail endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend import database as db
from backend.models import HostResponse, HostStats

router = APIRouter(prefix="/api/hosts", tags=["hosts"])


def _get_db_path() -> str:
    from backend.main import get_config
    return get_config().app.database_path


@router.get("/stats", response_model=HostStats)
def host_stats():
    return db.get_host_stats(_get_db_path())


@router.get("", response_model=list[HostResponse])
def list_hosts(
    subnet_id: Optional[int] = Query(None),
    rdp_only: bool = Query(False),
    vnc_only: bool = Query(False),
):
    return db.list_hosts(_get_db_path(), subnet_id, rdp_only, vnc_only)


@router.get("/{host_id}", response_model=HostResponse)
def get_host(host_id: int):
    host = db.get_host(_get_db_path(), host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    return host


@router.post("/{host_id}/reannounce")
def reannounce_host(host_id: int):
    """Re-announce a host to Bluesky. Requires a screenshot."""
    from backend.main import get_announcer

    host = db.get_host(_get_db_path(), host_id)
    if not host:
        raise HTTPException(404, "Host not found")

    announcer = get_announcer()
    if not announcer:
        raise HTTPException(400, "Bluesky announcer not configured")

    # Pick the best screenshot and protocol
    screenshot_path = None
    proto = "RDP"
    if host.get("screenshot_path"):
        screenshot_path = host["screenshot_path"]
        proto = "RDP"
    elif host.get("vnc_screenshot_path"):
        screenshot_path = host["vnc_screenshot_path"]
        proto = "VNC"

    if not screenshot_path:
        raise HTTPException(400, "No screenshot available for this host")

    success = announcer.announce_host(host, screenshot_path=screenshot_path, proto=proto)
    if not success:
        raise HTTPException(500, "Failed to announce host")

    db.mark_host_announced(_get_db_path(), host_id)
    return {"message": f"Host re-announced as {proto}"}
