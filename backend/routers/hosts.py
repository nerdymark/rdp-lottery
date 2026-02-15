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
