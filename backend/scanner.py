"""Network scanner using python-nmap for RDP discovery and full host enumeration."""

import ipaddress
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

import nmap

from backend.config import ScannerConfig

logger = logging.getLogger(__name__)


class NetworkScanner:
    """Two-phase scanner: RDP discovery then full enumeration."""

    def __init__(self, config: ScannerConfig):
        self.config = config

    def discover_rdp(self, cidr: str) -> list[dict]:
        """Legacy wrapper — calls discover_hosts for backwards compat."""
        return self.discover_hosts(cidr)

    def discover_hosts(self, cidr: str) -> list[dict]:
        """Phase 1: Fast scan for RDP (3389-3390) and VNC (5900-5901) across subnet.

        Returns list of dicts with ip, hostname, rdp_open, rdp_port, vnc_open, vnc_port.
        """
        nm = nmap.PortScanner()
        logger.info(f"Starting host discovery scan on {cidr} (RDP+VNC)")
        try:
            nm.scan(
                hosts=cidr,
                ports="3389-3390,5900-5901",
                arguments=f"-Pn -T{self.config.timing_template} --open",
            )
        except nmap.PortScannerError as e:
            logger.error(f"nmap scan failed: {e}")
            raise

        hosts = []
        for host in nm.all_hosts():
            host_info = {
                "ip": host,
                "hostname": nm[host].hostname() or "",
                "rdp_open": 0,
                "rdp_port": None,
                "vnc_open": 0,
                "vnc_ports": [],
            }
            tcp = nm[host].get("tcp", {})
            # Check RDP ports — prefer 3389 over 3390
            for rdp_port in (3389, 3390):
                if rdp_port in tcp and tcp[rdp_port].get("state") == "open":
                    host_info["rdp_open"] = 1
                    host_info["rdp_port"] = rdp_port
                    break
            # Check all VNC ports — a host can run multiple displays
            for vnc_port in (5900, 5901):
                if vnc_port in tcp and tcp[vnc_port].get("state") == "open":
                    host_info["vnc_open"] = 1
                    host_info["vnc_ports"].append(vnc_port)
            hosts.append(host_info)

        rdp_count = sum(h["rdp_open"] for h in hosts)
        vnc_count = sum(h["vnc_open"] for h in hosts)
        logger.info(f"Discovery complete: {len(hosts)} hosts found, "
                     f"{rdp_count} with RDP open, {vnc_count} with VNC open")
        return hosts

    def full_scan(self, ip: str) -> dict:
        """Phase 2: Full enumeration of a single host with -A flag.

        Returns dict with hostname, netbios_name, domain, os_guess,
        all_ports, mac_address.
        """
        nm = nmap.PortScanner()
        logger.info(f"Starting full scan on {ip}")
        try:
            nm.scan(
                hosts=ip,
                arguments=f"-A -Pn -T{self.config.timing_template} "
                          f"--host-timeout {self.config.host_timeout_seconds}s",
            )
        except nmap.PortScannerError as e:
            logger.error(f"Full scan failed for {ip}: {e}")
            raise

        if ip not in nm.all_hosts():
            logger.warning(f"Host {ip} not found in scan results")
            return {"hostname": "", "netbios_name": "", "domain": "",
                    "os_guess": "", "all_ports": [], "mac_address": ""}

        host_data = nm[ip]
        result = {
            "hostname": host_data.hostname() or "",
            "netbios_name": "",
            "domain": "",
            "os_guess": "",
            "all_ports": [],
            "mac_address": "",
        }

        # Extract all open ports
        for proto in host_data.all_protocols():
            ports = host_data[proto].keys()
            for port in ports:
                port_info = host_data[proto][port]
                if port_info.get("state") == "open":
                    result["all_ports"].append({
                        "port": port,
                        "protocol": proto,
                        "service": port_info.get("name", ""),
                        "version": port_info.get("version", ""),
                        "product": port_info.get("product", ""),
                    })

        # OS detection
        if "osmatch" in host_data and host_data["osmatch"]:
            result["os_guess"] = host_data["osmatch"][0].get("name", "")

        # MAC address
        if "addresses" in host_data and "mac" in host_data["addresses"]:
            result["mac_address"] = host_data["addresses"]["mac"]

        # NETBIOS / domain / hostname from nmap scripts
        hostscript = host_data.get("hostscript", [])
        for script in hostscript:
            script_id = script.get("id", "")
            output = script.get("output", "")
            if script_id == "nbstat":
                result["netbios_name"] = _parse_netbios(output)
            elif script_id == "rdp-ntlm-info":
                ntlm = _parse_ntlm_info(output)
                if ntlm.get("domain"):
                    result["domain"] = ntlm["domain"]
                if ntlm.get("hostname") and not result["hostname"]:
                    result["hostname"] = ntlm["hostname"]

        # Also check TCP script results for rdp-ntlm-info
        tcp = host_data.get("tcp", {})
        for port_num, port_data in tcp.items():
            script_results = port_data.get("script", {})
            if "rdp-ntlm-info" in script_results:
                ntlm = _parse_ntlm_info(script_results["rdp-ntlm-info"])
                if ntlm.get("domain"):
                    result["domain"] = ntlm["domain"]
                if ntlm.get("hostname") and not result["hostname"]:
                    result["hostname"] = ntlm["hostname"]

        logger.info(f"Full scan complete for {ip}: "
                     f"{len(result['all_ports'])} open ports, "
                     f"OS: {result['os_guess']}")
        return result

    def check_nla(self, ip: str, port: int = 3389) -> dict:
        """Phase 2.5: Check NLA requirements via rdp-enum-encryption script.

        Returns dict with nla_required (0|1) and security_protocols list.
        """
        nm = nmap.PortScanner()
        logger.info(f"Checking NLA status for {ip}:{port}")
        try:
            nm.scan(
                hosts=ip,
                ports=str(port),
                arguments=f"-Pn --script rdp-enum-encryption -T{self.config.timing_template}",
            )
        except nmap.PortScannerError as e:
            logger.error(f"NLA check failed for {ip}: {e}")
            return {"nla_required": None, "security_protocols": []}

        if ip not in nm.all_hosts():
            return {"nla_required": None, "security_protocols": []}

        tcp = nm[ip].get("tcp", {})
        port_data = tcp.get(port, {})
        script_results = port_data.get("script", {})
        script_output = script_results.get("rdp-enum-encryption", "")

        succeeded = []
        nla_required = None  # None = inconclusive (script produced no output)

        for line in script_output.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Lines look like: "Native RDP: SUCCESS" or "CredSSP (NLA): SUCCESS"
            if "SUCCESS" in line.upper():
                # Extract protocol name (everything before the colon or SUCCESS)
                proto_name = line.split(":")[0].strip() if ":" in line else line.split("SUCCESS")[0].strip()
                # Clean up leading symbols like |, _, etc.
                proto_name = proto_name.lstrip("|_ ")
                if proto_name:
                    succeeded.append(proto_name)
                    if "credssp" in proto_name.lower() or "nla" in proto_name.lower():
                        nla_required = 1

        # Only set nla_required=0 if we got results but none were NLA
        if succeeded and nla_required is None:
            nla_required = 0

        logger.info(f"NLA check for {ip}: nla_required={nla_required}, protocols={succeeded}")
        return {"nla_required": nla_required, "security_protocols": succeeded}

    def check_ssl_cert(self, ip: str, port: int = 3389) -> dict:
        """Check the SSL certificate on the RDP port for hostname/domain info.

        Returns dict with hostname and domain parsed from the certificate.
        """
        nm = nmap.PortScanner()
        logger.info(f"Checking SSL certificate for {ip}:{port}")
        try:
            nm.scan(
                hosts=ip,
                ports=str(port),
                arguments=f"-Pn --script ssl-cert -T{self.config.timing_template}",
            )
        except nmap.PortScannerError as e:
            logger.error(f"SSL cert check failed for {ip}: {e}")
            return {}

        if ip not in nm.all_hosts():
            return {}

        tcp = nm[ip].get("tcp", {})
        port_data = tcp.get(port, {})
        script_results = port_data.get("script", {})
        cert_output = script_results.get("ssl-cert", "")

        if not cert_output:
            logger.info(f"No SSL cert data returned for {ip}")
            return {}

        result = _parse_ssl_cert(cert_output)
        logger.info(f"SSL cert parsed for {ip}: {result}")
        return result

    def enrich_host(self, ip: str) -> dict:
        """Enrich host with ASN, GeoIP, reverse DNS, and IP type.

        Uses ip-api.com for public IPs, skips API call for private IPs.
        Returns dict with enrichment fields.
        """
        addr = ipaddress.ip_address(ip)
        rdns = ""
        try:
            rdns = socket.getfqdn(ip)
            if rdns == ip:
                rdns = ""
        except Exception:
            pass

        if addr.is_private:
            logger.debug(f"Skipping API enrichment for private IP {ip}")
            return {"ip_type": "Private", "reverse_dns": rdns}

        # Query ip-api.com for public IPs
        url = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,isp,org,as,hosting,mobile,proxy"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
        except Exception as e:
            logger.warning(f"ip-api.com lookup failed for {ip}: {e}")
            return {"reverse_dns": rdns}

        if data.get("status") != "success":
            logger.warning(f"ip-api.com returned non-success for {ip}: {data.get('message', '')}")
            return {"reverse_dns": rdns}

        ip_type = "Datacenter" if data.get("hosting") else ("Mobile" if data.get("mobile") else "Residential")
        as_field = data.get("as", "")

        result = {
            "asn": as_field.split()[0] if as_field else "",
            "isp": data.get("isp", ""),
            "org": data.get("org", ""),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "city": data.get("city", ""),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "ip_type": ip_type,
            "reverse_dns": rdns,
        }
        logger.info(f"Enrichment for {ip}: {result['country_code']} / {result['ip_type']} / {result['asn']}")
        return result

    def capture_screenshot(self, ip: str, output_dir: str, port: int = 3389) -> Optional[str]:
        """Capture a screenshot of the RDP login screen for non-NLA hosts.

        Uses xfreerdp3/xfreerdp to connect, waits for the login screen to render,
        then captures the window with macOS screencapture.

        Returns relative path to screenshot PNG, or None on failure.
        """
        # Prefer sdl-freerdp (SDL3, no X11 needed) over xfreerdp (X11, needs XQuartz)
        xfreerdp = shutil.which("sdl-freerdp") or shutil.which("xfreerdp3") or shutil.which("xfreerdp")
        if not xfreerdp:
            logger.warning("FreeRDP not installed (xfreerdp3/xfreerdp not found), skipping screenshot")
            return None

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        screenshot_file = os.path.join(output_dir, f"{ip}.png")

        # FreeRDP /v: accepts host:port
        target = f"{ip}:{port}" if port != 3389 else ip
        logger.info(f"Capturing RDP login screen for {target}")

        # Connection strategies — try in order until one stays alive.
        # Empty creds (/u:""/p:"") make FreeRDP connect through to the remote
        # login screen instead of showing its own credential dialog.
        # Strategy 1: skip X.224 negotiation + relaxed TLS (best for most non-NLA hosts)
        # Strategy 2: force legacy RDP security (for very old hosts)
        strategies = [
            [xfreerdp, f"/v:{target}", "/cert:ignore", "-nego",
             "/tls:seclevel:0", "/sec:nla:off", "/u:", "/p:",
             "/timeout:15000", "/w:1024", "/h:768"],
            [xfreerdp, f"/v:{target}", "/cert:ignore", "/sec:rdp",
             "/u:", "/p:", "/timeout:10000", "/w:1024", "/h:768"],
        ]

        proc = None
        for i, cmd in enumerate(strategies):
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
                # Wait for login screen to render
                time.sleep(5)

                if proc.poll() is None:
                    logger.info(f"FreeRDP connected to {ip} (strategy {i + 1})")
                    break
                else:
                    logger.info(f"FreeRDP strategy {i + 1} exited early for {ip} "
                                f"(code {proc.returncode}), trying next")
                    proc = None
            except Exception as e:
                logger.warning(f"FreeRDP strategy {i + 1} failed for {ip}: {e}")
                proc = None

        if proc is None or proc.poll() is not None:
            logger.warning(f"FreeRDP all strategies failed for {ip}")
            return None

        # Find the FreeRDP window ID so we capture only that window
        window_id = _find_window_id(proc.pid)
        if window_id:
            logger.info(f"Found FreeRDP window ID {window_id} for {ip}")

        if not window_id:
            logger.warning(f"Could not find FreeRDP window ID for {ip}, skipping screenshot")
            # Kill FreeRDP before returning
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            return None

        try:
            cap_cmd = ["screencapture", "-x", "-o", "-l", str(window_id), screenshot_file]
            cap_result = subprocess.run(
                cap_cmd, capture_output=True, text=True, timeout=10,
            )
            if cap_result.returncode != 0:
                logger.warning(f"screencapture returned {cap_result.returncode} for {ip}: "
                               f"{cap_result.stderr.strip()}")
            elif not os.path.exists(screenshot_file):
                logger.warning(
                    f"screencapture exited 0 but no file created for {ip} — "
                    "grant Screen Recording permission to Terminal/Python in "
                    "System Settings > Privacy & Security > Screen Recording"
                )
        except Exception as e:
            logger.warning(f"screencapture failed for {ip}: {e}")

        # Always kill FreeRDP — SIGTERM then SIGKILL fallback
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=3)
            except Exception:
                pass

        # Check result regardless of how cleanup went
        if os.path.exists(screenshot_file) and os.path.getsize(screenshot_file) > 0:
            logger.info(f"Screenshot saved: {screenshot_file}")
            return screenshot_file
        else:
            logger.warning(f"Screenshot file not created for {ip}")
            return None


    def check_vnc_auth(self, ip: str, port: int = 5900) -> dict:
        """Check VNC authentication requirements via vnc-info and vnc-title scripts.

        Returns dict with vnc_auth_required (0=no auth, 1=auth required, None=inconclusive)
        and vnc_desktop_name.
        """
        nm = nmap.PortScanner()
        logger.info(f"Checking VNC auth for {ip}:{port}")
        try:
            nm.scan(
                hosts=ip,
                ports=str(port),
                arguments=f"-Pn --script vnc-info,vnc-title -T{self.config.timing_template}",
            )
        except nmap.PortScannerError as e:
            logger.error(f"VNC auth check failed for {ip}: {e}")
            return {"vnc_auth_required": None, "vnc_desktop_name": ""}

        if ip not in nm.all_hosts():
            return {"vnc_auth_required": None, "vnc_desktop_name": ""}

        tcp = nm[ip].get("tcp", {})
        port_data = tcp.get(port, {})
        script_results = port_data.get("script", {})

        vnc_info = script_results.get("vnc-info", "")
        vnc_title = script_results.get("vnc-title", "")

        vnc_auth_required = None  # None = inconclusive
        vnc_desktop_name = ""

        if vnc_info:
            # Check for no-auth indicators
            info_lower = vnc_info.lower()
            if "none" in info_lower or "no authentication" in info_lower:
                vnc_auth_required = 0
            elif "security type" in info_lower or "authentication" in info_lower:
                # Has security info but not "None" — auth is required
                vnc_auth_required = 1

        # Also check hostscript output for vnc-info WARNING
        hostscript = nm[ip].get("hostscript", [])
        for script in hostscript:
            if script.get("id") == "vnc-info":
                output = script.get("output", "").lower()
                if "none" in output or "no authentication" in output:
                    vnc_auth_required = 0

        # Parse desktop name from vnc-title
        if vnc_title:
            for line in vnc_title.split("\n"):
                line = line.strip().lstrip("|_ ")
                if line.startswith("name:"):
                    vnc_desktop_name = line.split(":", 1)[1].strip()
                elif line and not line.startswith("ERROR") and "resolution" not in line.lower():
                    # Some vnc-title output is just the name directly
                    if not vnc_desktop_name:
                        vnc_desktop_name = line

        logger.info(f"VNC auth for {ip}: auth_required={vnc_auth_required}, desktop={vnc_desktop_name}")
        return {"vnc_auth_required": vnc_auth_required, "vnc_desktop_name": vnc_desktop_name}

    def capture_vnc_screenshot(self, ip: str, output_dir: str, port: int = 5900) -> Optional[str]:
        """Capture a screenshot of a VNC desktop using vncdotool.

        Uses vncdo CLI to avoid Twisted reactor issues in threads.
        Returns path to screenshot PNG, or None on failure.
        """
        vncdo = shutil.which("vncdo")
        if not vncdo:
            logger.warning("vncdotool not installed (vncdo not found), skipping VNC screenshot")
            return None

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        screenshot_file = os.path.join(output_dir, f"vnc_{ip}.png")

        logger.info(f"Capturing VNC screenshot for {ip}:{port}")
        try:
            result = subprocess.run(
                [vncdo, "-s", f"{ip}::{port}", "capture", screenshot_file],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.warning(f"vncdo failed for {ip} (code {result.returncode}): {result.stderr.strip()}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"VNC screenshot timed out for {ip}")
            return None
        except Exception as e:
            logger.warning(f"VNC screenshot failed for {ip}: {e}")
            return None

        if os.path.exists(screenshot_file) and os.path.getsize(screenshot_file) > 0:
            logger.info(f"VNC screenshot saved: {screenshot_file}")
            return screenshot_file
        else:
            logger.warning(f"VNC screenshot file not created for {ip}")
            return None


_SWIFT_HELPER = Path("/tmp/rdp_lottery_find_window.swift")
_SWIFT_HELPER_CODE = """\
import CoreGraphics
import Foundation
let pid = Int(CommandLine.arguments[1])!
let wins = CGWindowListCopyWindowInfo(.optionAll, kCGNullWindowID) as! [[String: Any]]
for w in wins {
    if w["kCGWindowOwnerPID"] as? Int == pid && w["kCGWindowLayer"] as? Int == 0 {
        print(w["kCGWindowNumber"] as! Int)
        break
    }
}
"""


def _find_window_id(pid: int) -> Optional[int]:
    """Find the macOS window ID for a process using CoreGraphics via Swift.

    Uses a persistent Swift script file to avoid recompilation overhead.
    Retries once after a short delay in case the window isn't ready yet.
    """
    if not _SWIFT_HELPER.exists() or _SWIFT_HELPER.read_text() != _SWIFT_HELPER_CODE:
        _SWIFT_HELPER.write_text(_SWIFT_HELPER_CODE)

    for attempt in range(2):
        try:
            result = subprocess.run(
                ["swift", str(_SWIFT_HELPER), str(pid)],
                capture_output=True, text=True, timeout=8,
            )
            wid_str = result.stdout.strip()
            if wid_str:
                return int(wid_str)
            if result.stderr.strip():
                logger.debug(f"Swift window lookup stderr: {result.stderr.strip()}")
            if attempt == 0:
                # Window may not be ready yet, wait and retry
                time.sleep(2)
        except subprocess.TimeoutExpired:
            logger.debug(f"Swift window lookup timed out for PID {pid}")
        except Exception as e:
            logger.debug(f"Swift window lookup error for PID {pid}: {e}")
            break
    return None


def _parse_netbios(output: str) -> str:
    """Extract NetBIOS name from nbstat script output."""
    for line in output.split("\n"):
        line = line.strip()
        if "<00>" in line and "UNIQUE" in line.upper():
            return line.split("<")[0].strip()
    return ""


def _parse_ntlm_info(output: str) -> dict:
    """Extract domain and hostname from rdp-ntlm-info script output.

    DNS_Domain_Name → domain (e.g. corp.example.com)
    DNS_Computer_Name → hostname FQDN (e.g. DC01.corp.example.com)
    Target_Name → fallback hostname (e.g. DC01)
    """
    result: dict[str, str] = {}
    for line in output.split("\n"):
        line = line.strip().lstrip("|_ ")
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            continue
        if key == "DNS_Domain_Name":
            result["domain"] = value
        elif key == "DNS_Computer_Name":
            result["hostname"] = value
        elif key == "Target_Name" and "hostname" not in result:
            result["hostname"] = value
    return result


def _parse_ssl_cert(output: str) -> dict:
    """Extract hostname and domain from ssl-cert nmap script output.

    Parses commonName and Subject Alternative Name (SAN) DNS entries.
    """
    result: dict[str, str] = {}
    for line in output.split("\n"):
        line = line.strip().lstrip("|_ ")
        if line.startswith("Subject:") and "commonName=" in line:
            cn = line.split("commonName=")[1].split("/")[0].strip()
            if cn:
                result["hostname"] = cn
        elif "Subject Alternative Name:" in line or line.startswith("DNS:"):
            # SAN line like: "Subject Alternative Name: DNS:Berry, DNS:Berry.local"
            san_part = line.split("Subject Alternative Name:")[-1] if "Subject Alternative Name:" in line else line
            for entry in san_part.split(","):
                entry = entry.strip()
                if entry.startswith("DNS:"):
                    name = entry[4:].strip()
                    if "." in name:
                        # FQDN — use as hostname, extract domain
                        result["hostname"] = name
                        parts = name.split(".", 1)
                        if len(parts) == 2:
                            result["domain"] = parts[1]
                        break
                    elif "hostname" not in result:
                        result["hostname"] = name
    return result
