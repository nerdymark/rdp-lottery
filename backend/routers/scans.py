"""Scan trigger and history endpoints."""

import json
import logging
import concurrent.futures
import urllib.request
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend import database as db
import ipaddress

from backend.models import ScanTrigger, ScanResponse, FeedTarget, VncRandomHost

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["scans"])

MAX_CONCURRENT_SCANS = 4
_scan_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_SCANS,
    thread_name_prefix="scan",
)


def _get_db_path() -> str:
    from backend.main import get_config
    return get_config().app.database_path


def _get_scanner():
    from backend.main import get_scanner
    return get_scanner()


def _get_announcer():
    from backend.main import get_announcer
    return get_announcer()


def _run_scan(scan_id: int, subnet: dict, db_path: str) -> None:
    """Execute a scan in a background thread."""
    scanner = _get_scanner()
    announcer = _get_announcer()

    db.update_scan(db_path, scan_id, status="running", started_at=db._now())

    try:
        # Phase 1: Host discovery (RDP + VNC)
        discovered = scanner.discover_hosts(subnet["cidr"])
        rdp_hosts = [h for h in discovered if h["rdp_open"]]
        vnc_hosts = [h for h in discovered if h.get("vnc_open")]

        # Phase 2: Full scan on RDP hosts
        full_scanned_ips = set()
        for host_info in rdp_hosts:
            rdp_port = host_info.get("rdp_port", 3389)
            try:
                full_data = scanner.full_scan(host_info["ip"])
                host_info.update(full_data)
                full_scanned_ips.add(host_info["ip"])
                # Verify RDP port is actually open — discovery can give false
                # positives (e.g. firewalls responding on all ports)
                open_ports = {p["port"] for p in host_info.get("all_ports", [])}
                if rdp_port not in open_ports:
                    logger.info(f"Port {rdp_port} not confirmed open for {host_info['ip']} "
                                f"(ports: {open_ports}), clearing rdp_open")
                    host_info["rdp_open"] = 0
                    continue  # Skip NLA/cert/screenshot for non-RDP hosts
            except Exception as e:
                logger.error(f"Full scan failed for {host_info['ip']}: {e}")

            # Phase 2.25: SSL certificate hostname/domain (fallback only)
            try:
                cert_info = scanner.check_ssl_cert(host_info["ip"], port=rdp_port)
                if cert_info.get("hostname"):
                    logger.info(f"SSL cert for {host_info['ip']}: hostname={cert_info.get('hostname')}, "
                                f"domain={cert_info.get('domain')}")
                    if not host_info.get("hostname"):
                        host_info["hostname"] = cert_info["hostname"]
                if cert_info.get("domain") and not host_info.get("domain"):
                    host_info["domain"] = cert_info["domain"]
            except Exception as e:
                logger.error(f"SSL cert check failed for {host_info['ip']}: {e}")

            # Phase 2.5: NLA check
            try:
                nla_info = scanner.check_nla(host_info["ip"], port=rdp_port)
                host_info.update(nla_info)
            except Exception as e:
                logger.error(f"NLA check failed for {host_info['ip']}: {e}")

            # Phase 3: Screenshot non-NLA hosts
            if host_info.get("nla_required") == 0:
                try:
                    screenshot = scanner.capture_screenshot(host_info["ip"], "screenshots", port=rdp_port)
                    if screenshot:
                        host_info["screenshot_path"] = screenshot
                except Exception as e:
                    logger.error(f"Screenshot failed for {host_info['ip']}: {e}")

        # Phase 4: VNC host processing
        for host_info in vnc_hosts:
            # Full scan VNC-only hosts that weren't already scanned
            if host_info["ip"] not in full_scanned_ips:
                try:
                    full_data = scanner.full_scan(host_info["ip"])
                    host_info.update(full_data)
                    full_scanned_ips.add(host_info["ip"])
                except Exception as e:
                    logger.error(f"Full scan failed for VNC host {host_info['ip']}: {e}")

            # Check each open VNC port — a host may have multiple displays
            vnc_ports = host_info.get("vnc_ports", [5900])
            for vnc_port in vnc_ports:
                # VNC auth check
                try:
                    vnc_info = scanner.check_vnc_auth(host_info["ip"], port=vnc_port)
                    # Merge results — keep the most interesting (no-auth wins over auth)
                    if host_info.get("vnc_auth_required") != 0:
                        host_info.update(vnc_info)
                except Exception as e:
                    logger.error(f"VNC auth check failed for {host_info['ip']}:{vnc_port}: {e}")

                # VNC screenshot for no-auth or inconclusive port (vncdo fails gracefully if auth required)
                if vnc_info.get("vnc_auth_required") != 1 and not host_info.get("vnc_screenshot_path"):
                    try:
                        vnc_screenshot = scanner.capture_vnc_screenshot(host_info["ip"], "screenshots", port=vnc_port)
                        if vnc_screenshot:
                            host_info["vnc_screenshot_path"] = vnc_screenshot
                    except Exception as e:
                        logger.error(f"VNC screenshot failed for {host_info['ip']}:{vnc_port}: {e}")

        # Phase 4.5: Web screenshots
        for host_info in discovered:
            all_ports = host_info.get("all_ports", [])
            web_ports = scanner.detect_web_ports(all_ports)
            if web_ports:
                web_screenshots = []
                for wp in web_ports:
                    try:
                        result = scanner.capture_web_screenshot(
                            host_info["ip"], wp["port"], wp["ssl"], "screenshots"
                        )
                        if result:
                            web_screenshots.append(result)
                    except Exception as e:
                        logger.error(f"Web screenshot failed for {host_info['ip']}:{wp['port']}: {e}")
                if web_screenshots:
                    host_info["web_screenshots"] = web_screenshots

        # Phase 5: Host enrichment (ASN, GeoIP, reverse DNS, IP type)
        for host_info in discovered:
            try:
                enrichment = scanner.enrich_host(host_info["ip"])
                host_info.update(enrichment)
            except Exception as e:
                logger.error(f"Enrichment failed for {host_info['ip']}: {e}")

        # Upsert all discovered hosts
        for host_info in discovered:
            host_record = db.upsert_host(
                db_path, scan_id, subnet["id"], host_info["ip"],
                hostname=host_info.get("hostname", ""),
                netbios_name=host_info.get("netbios_name", ""),
                domain=host_info.get("domain", ""),
                os_guess=host_info.get("os_guess", ""),
                rdp_open=host_info.get("rdp_open", 0),
                all_ports=host_info.get("all_ports", []),
                mac_address=host_info.get("mac_address", ""),
                nla_required=host_info.get("nla_required"),
                security_protocols=host_info.get("security_protocols", []),
                screenshot_path=host_info.get("screenshot_path", ""),
                asn=host_info.get("asn", ""),
                isp=host_info.get("isp", ""),
                org=host_info.get("org", ""),
                country=host_info.get("country", ""),
                country_code=host_info.get("country_code", ""),
                city=host_info.get("city", ""),
                latitude=host_info.get("latitude"),
                longitude=host_info.get("longitude"),
                ip_type=host_info.get("ip_type", ""),
                reverse_dns=host_info.get("reverse_dns", ""),
                vnc_open=host_info.get("vnc_open", 0),
                vnc_auth_required=host_info.get("vnc_auth_required"),
                vnc_desktop_name=host_info.get("vnc_desktop_name", ""),
                vnc_screenshot_path=host_info.get("vnc_screenshot_path", ""),
                web_screenshots=host_info.get("web_screenshots", []),
            )

            # Announce new RDP/VNC hosts via Bluesky
            if host_info.get("rdp_open") and not host_record.get("announced") and announcer:
                if announcer.announce_host(host_info, screenshot_path=host_info.get("screenshot_path"), proto="RDP"):
                    db.mark_host_announced(db_path, host_record["id"])
            elif host_info.get("vnc_open") and not host_record.get("announced") and announcer:
                if announcer.announce_host(host_info, screenshot_path=host_info.get("vnc_screenshot_path"), proto="VNC"):
                    db.mark_host_announced(db_path, host_record["id"])

        verified_rdp = sum(1 for h in discovered if h.get("rdp_open"))
        verified_vnc = sum(1 for h in discovered if h.get("vnc_open"))
        db.update_scan(
            db_path, scan_id,
            status="completed",
            hosts_found=len(discovered),
            rdp_found=verified_rdp,
            vnc_found=verified_vnc,
            finished_at=db._now(),
        )
        logger.info(f"Scan {scan_id} completed: {len(discovered)} hosts, "
                     f"{verified_rdp} RDP, {verified_vnc} VNC")

    except Exception as e:
        logger.error(f"Scan {scan_id} failed: {e}")
        db.update_scan(
            db_path, scan_id,
            status="failed",
            error=str(e),
            finished_at=db._now(),
        )


@router.get("", response_model=list[ScanResponse])
def list_scans(subnet_id: Optional[int] = Query(None)):
    return db.list_scans(_get_db_path(), subnet_id)


@router.post("", response_model=list[ScanResponse], status_code=201)
def trigger_scan(body: ScanTrigger, background_tasks: BackgroundTasks):
    db_path = _get_db_path()

    if body.subnet_id:
        subnet = db.get_subnet(db_path, body.subnet_id)
        if not subnet:
            raise HTTPException(404, "Subnet not found")
        subnets = [subnet]
    else:
        subnets = [s for s in db.list_subnets(db_path) if s["is_active"]]
        if not subnets:
            raise HTTPException(400, "No active subnets to scan")

    scans = []
    for subnet in subnets:
        scan = db.create_scan(db_path, subnet["id"])
        scans.append(scan)
        _scan_pool.submit(_run_scan, scan["id"], subnet, db_path)

    return scans


@router.get("/active", response_model=list[ScanResponse])
def active_scans():
    return db.get_active_scans(_get_db_path())


FEED_URL = "https://nerdymark.com/404"


@router.get("/feed-targets", response_model=list[FeedTarget])
def feed_targets():
    """Fetch external host feed and return scannable IPs."""
    try:
        resp = urllib.request.urlopen(FEED_URL, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        logger.error(f"Failed to fetch feed from {FEED_URL}: {e}")
        raise HTTPException(502, f"Failed to fetch feed: {e}")

    target_ips: set[str] = set()
    for entry in data:
        for src_ip in entry:
            target_ips.add(src_ip)

    remaining = sorted(target_ips)
    logger.info(f"Feed: {len(remaining)} unique target IPs")
    return [FeedTarget(ip=ip, label="Feed target") for ip in remaining]


VNC_RANDOM_URL = "https://computernewb.com/vncresolver/api/v1/random"


@router.get("/vnc-random", response_model=VncRandomHost)
def vnc_random():
    """Fetch a random host from VNC Resolver and return its /24 subnet."""
    try:
        req = urllib.request.Request(VNC_RANDOM_URL, headers={"User-Agent": "RDP-Lottery/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        logger.error(f"Failed to fetch from VNC Resolver: {e}")
        raise HTTPException(502, f"VNC Resolver unavailable: {e}")

    ip = data.get("ip_address", "")
    if not ip:
        raise HTTPException(502, "VNC Resolver returned no IP")

    # Compute /24 subnet
    network = ipaddress.ip_network(f"{ip}/24", strict=False)
    subnet_cidr = str(network)

    return VncRandomHost(
        ip=ip,
        subnet_cidr=subnet_cidr,
        country=data.get("geo_country", ""),
        city=data.get("geo_city", ""),
        asn=data.get("asn", ""),
        desktop_name=data.get("desktop_name", ""),
    )
