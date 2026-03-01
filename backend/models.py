"""Pydantic request/response models."""

from typing import Optional
from pydantic import BaseModel


# --- Subnet ---

class SubnetCreate(BaseModel):
    cidr: str
    label: str = ""


class SubnetUpdate(BaseModel):
    cidr: Optional[str] = None
    label: Optional[str] = None
    is_active: Optional[int] = None


class SubnetResponse(BaseModel):
    id: int
    cidr: str
    label: str
    is_active: int
    created_at: str
    updated_at: str
    host_count: int = 0


# --- Scan ---

class ScanTrigger(BaseModel):
    subnet_id: Optional[int] = None  # None = scan all active subnets


class ScanResponse(BaseModel):
    id: int
    subnet_id: int
    subnet_cidr: Optional[str] = None
    subnet_label: Optional[str] = None
    status: str
    hosts_found: int
    rdp_found: int
    vnc_found: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    created_at: str


# --- Host ---

class HostResponse(BaseModel):
    id: int
    scan_id: int
    subnet_id: int
    ip: str
    hostname: str
    netbios_name: str
    domain: str
    os_guess: str
    rdp_open: int
    all_ports: list
    mac_address: str
    first_seen_at: str
    last_seen_at: str
    announced: int
    nla_required: Optional[int] = None
    security_protocols: list = []
    screenshot_path: str = ""
    asn: str = ""
    isp: str = ""
    org: str = ""
    country: str = ""
    country_code: str = ""
    city: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ip_type: str = ""
    reverse_dns: str = ""
    vnc_open: int = 0
    vnc_auth_required: Optional[int] = None
    vnc_desktop_name: str = ""
    vnc_screenshot_path: str = ""
    web_screenshots: list = []


class HostStats(BaseModel):
    total_hosts: int
    rdp_open: int
    vnc_open: int = 0
    subnets_scanned: int
    total_scans: int
    announced: int


# --- Feed ---

class FeedTarget(BaseModel):
    ip: str
    label: str = ""


class VncRandomHost(BaseModel):
    ip: str
    subnet_cidr: str
    country: str = ""
    city: str = ""
    asn: str = ""
    desktop_name: str = ""


# --- GeoIP ---

class GeoipStatusResponse(BaseModel):
    imported: bool
    csv_date: Optional[str] = None
    last_updated: Optional[str] = None
    total_blocks: int
    import_running: bool = False
    import_progress: Optional[int] = None


class GeoipCountryResponse(BaseModel):
    country: str
    block_count: int


class GeoipStateResponse(BaseModel):
    state: str
    block_count: int


class GeoipCityResponse(BaseModel):
    city: str
    block_count: int


class GeoipBlock(BaseModel):
    ip_start: str
    ip_end: str
    total_ips: int
    cidrs: list[str]
    cidr_count: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    asn: str = ""
    isp: str = ""
    ip_type: str = ""


class GeoipBlocksResponse(BaseModel):
    blocks: list[GeoipBlock]
    total: int
    page: int
    page_size: int
    total_pages: int


class BulkSubnetCreate(BaseModel):
    cidrs: list[str]
    label: str = ""


class BulkSubnetResponse(BaseModel):
    created: int
    skipped: int
    scans_queued: int = 0
