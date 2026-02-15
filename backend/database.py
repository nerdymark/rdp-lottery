"""SQLite database schema and CRUD operations."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str) -> None:
    """Create tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subnets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cidr TEXT UNIQUE NOT NULL,
            label TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subnet_id INTEGER NOT NULL REFERENCES subnets(id),
            status TEXT NOT NULL DEFAULT 'pending',
            hosts_found INTEGER DEFAULT 0,
            rdp_found INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hosts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL REFERENCES scans(id),
            subnet_id INTEGER NOT NULL REFERENCES subnets(id),
            ip TEXT NOT NULL,
            hostname TEXT DEFAULT '',
            netbios_name TEXT DEFAULT '',
            domain TEXT DEFAULT '',
            os_guess TEXT DEFAULT '',
            rdp_open INTEGER DEFAULT 0,
            all_ports TEXT DEFAULT '[]',
            mac_address TEXT DEFAULT '',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            announced INTEGER DEFAULT 0,
            nla_required INTEGER DEFAULT NULL,
            security_protocols TEXT DEFAULT '[]',
            screenshot_path TEXT DEFAULT '',
            UNIQUE(ip, subnet_id)
        );
    """)
    conn.commit()

    # Migrate existing databases: add new columns if missing
    migrations = [
        ("nla_required", "INTEGER", "NULL"),
        ("security_protocols", "TEXT", "'[]'"),
        ("screenshot_path", "TEXT", "''"),
        ("asn", "TEXT", "''"),
        ("isp", "TEXT", "''"),
        ("org", "TEXT", "''"),
        ("country", "TEXT", "''"),
        ("country_code", "TEXT", "''"),
        ("city", "TEXT", "''"),
        ("latitude", "REAL", "NULL"),
        ("longitude", "REAL", "NULL"),
        ("ip_type", "TEXT", "''"),
        ("reverse_dns", "TEXT", "''"),
        ("vnc_open", "INTEGER", "0"),
        ("vnc_auth_required", "INTEGER", "NULL"),
        ("vnc_desktop_name", "TEXT", "''"),
        ("vnc_screenshot_path", "TEXT", "''"),
    ]
    for col, col_type, default in migrations:
        try:
            conn.execute(f"ALTER TABLE hosts ADD COLUMN {col} {col_type} DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Migrate scans table
    scans_migrations = [
        ("vnc_found", "INTEGER", "0"),
    ]
    for col, col_type, default in scans_migrations:
        try:
            conn.execute(f"ALTER TABLE scans ADD COLUMN {col} {col_type} DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Subnet CRUD ---

def create_subnet(db_path: str, cidr: str, label: str = "") -> dict:
    conn = get_connection(db_path)
    now = _now()
    try:
        cursor = conn.execute(
            "INSERT INTO subnets (cidr, label, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (cidr, label, now, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM subnets WHERE id = ?", (cursor.lastrowid,)).fetchone())
    finally:
        conn.close()


def list_subnets(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM subnets ORDER BY id").fetchall()]
    finally:
        conn.close()


def get_subnet(db_path: str, subnet_id: int) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM subnets WHERE id = ?", (subnet_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_subnet(db_path: str, subnet_id: int, **kwargs) -> Optional[dict]:
    conn = get_connection(db_path)
    allowed = {"cidr", "label", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        conn.close()
        return get_subnet(db_path, subnet_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [subnet_id]
    try:
        conn.execute(f"UPDATE subnets SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return get_subnet(db_path, subnet_id)
    finally:
        conn.close()


def delete_subnet(db_path: str, subnet_id: int) -> bool:
    conn = get_connection(db_path)
    try:
        # Delete dependent records first (hosts → scans → subnet)
        conn.execute("DELETE FROM hosts WHERE subnet_id = ?", (subnet_id,))
        conn.execute("DELETE FROM scans WHERE subnet_id = ?", (subnet_id,))
        cursor = conn.execute("DELETE FROM subnets WHERE id = ?", (subnet_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# --- Scan CRUD ---

def create_scan(db_path: str, subnet_id: int) -> dict:
    conn = get_connection(db_path)
    now = _now()
    try:
        cursor = conn.execute(
            "INSERT INTO scans (subnet_id, status, created_at) VALUES (?, 'pending', ?)",
            (subnet_id, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM scans WHERE id = ?", (cursor.lastrowid,)).fetchone())
    finally:
        conn.close()


def update_scan(db_path: str, scan_id: int, **kwargs) -> Optional[dict]:
    conn = get_connection(db_path)
    allowed = {"status", "hosts_found", "rdp_found", "vnc_found", "started_at", "finished_at", "error"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        conn.close()
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [scan_id]
    try:
        conn.execute(f"UPDATE scans SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_scans(db_path: str, subnet_id: Optional[int] = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        if subnet_id:
            rows = conn.execute(
                """SELECT scans.*, subnets.cidr AS subnet_cidr, subnets.label AS subnet_label
                   FROM scans LEFT JOIN subnets ON scans.subnet_id = subnets.id
                   WHERE scans.subnet_id = ? ORDER BY scans.id DESC""", (subnet_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT scans.*, subnets.cidr AS subnet_cidr, subnets.label AS subnet_label
                   FROM scans LEFT JOIN subnets ON scans.subnet_id = subnets.id
                   ORDER BY scans.id DESC"""
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_scans(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT scans.*, subnets.cidr AS subnet_cidr, subnets.label AS subnet_label
               FROM scans LEFT JOIN subnets ON scans.subnet_id = subnets.id
               WHERE scans.status IN ('pending', 'running') ORDER BY scans.id"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cleanup_orphaned_scans(db_path: str) -> int:
    """Mark any running/pending scans as failed on startup (orphaned by restart)."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE scans SET status = 'failed', error = 'Interrupted by server restart', "
            "finished_at = ? WHERE status IN ('pending', 'running')",
            (_now(),),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# --- Host CRUD ---

def upsert_host(db_path: str, scan_id: int, subnet_id: int, ip: str, **kwargs) -> dict:
    """Insert or update a host. On conflict (ip, subnet_id), update last_seen and merge data."""
    conn = get_connection(db_path)
    now = _now()
    try:
        existing = conn.execute(
            "SELECT * FROM hosts WHERE ip = ? AND subnet_id = ?", (ip, subnet_id)
        ).fetchone()

        if existing:
            updates = {
                "scan_id": scan_id,
                "last_seen_at": now,
            }
            for key in ("hostname", "netbios_name", "domain", "os_guess", "rdp_open",
                        "all_ports", "mac_address", "nla_required", "security_protocols", "screenshot_path",
                        "asn", "isp", "org", "country", "country_code", "city",
                        "latitude", "longitude", "ip_type", "reverse_dns",
                        "vnc_open", "vnc_auth_required", "vnc_desktop_name", "vnc_screenshot_path"):
                if key in kwargs and kwargs[key] is not None:
                    val = kwargs[key]
                    if key in ("all_ports", "security_protocols") and isinstance(val, list):
                        val = json.dumps(val)
                    updates[key] = val

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [existing["id"]]
            conn.execute(f"UPDATE hosts SET {set_clause} WHERE id = ?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM hosts WHERE id = ?", (existing["id"],)).fetchone()
        else:
            all_ports = kwargs.get("all_ports", [])
            if isinstance(all_ports, list):
                all_ports = json.dumps(all_ports)
            security_protocols = kwargs.get("security_protocols", [])
            if isinstance(security_protocols, list):
                security_protocols = json.dumps(security_protocols)
            cursor = conn.execute(
                """INSERT INTO hosts
                   (scan_id, subnet_id, ip, hostname, netbios_name, domain, os_guess,
                    rdp_open, all_ports, mac_address, first_seen_at, last_seen_at, announced,
                    nla_required, security_protocols, screenshot_path,
                    asn, isp, org, country, country_code, city,
                    latitude, longitude, ip_type, reverse_dns,
                    vnc_open, vnc_auth_required, vnc_desktop_name, vnc_screenshot_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?)""",
                (
                    scan_id, subnet_id, ip,
                    kwargs.get("hostname", ""),
                    kwargs.get("netbios_name", ""),
                    kwargs.get("domain", ""),
                    kwargs.get("os_guess", ""),
                    kwargs.get("rdp_open", 0),
                    all_ports,
                    kwargs.get("mac_address", ""),
                    now, now,
                    kwargs.get("nla_required"),
                    security_protocols,
                    kwargs.get("screenshot_path", ""),
                    kwargs.get("asn", ""),
                    kwargs.get("isp", ""),
                    kwargs.get("org", ""),
                    kwargs.get("country", ""),
                    kwargs.get("country_code", ""),
                    kwargs.get("city", ""),
                    kwargs.get("latitude"),
                    kwargs.get("longitude"),
                    kwargs.get("ip_type", ""),
                    kwargs.get("reverse_dns", ""),
                    kwargs.get("vnc_open", 0),
                    kwargs.get("vnc_auth_required"),
                    kwargs.get("vnc_desktop_name", ""),
                    kwargs.get("vnc_screenshot_path", ""),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM hosts WHERE id = ?", (cursor.lastrowid,)).fetchone()

        return dict(row)
    finally:
        conn.close()


def list_hosts(db_path: str, subnet_id: Optional[int] = None, rdp_only: bool = False, vnc_only: bool = False) -> list[dict]:
    conn = get_connection(db_path)
    try:
        query = "SELECT * FROM hosts WHERE 1=1"
        params: list = []
        if subnet_id:
            query += " AND subnet_id = ?"
            params.append(subnet_id)
        if rdp_only:
            query += " AND rdp_open = 1"
        if vnc_only:
            query += " AND vnc_open = 1"
        query += " ORDER BY last_seen_at DESC"
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d = _parse_host_json(d)
            result.append(d)
        return result
    finally:
        conn.close()


def get_host(db_path: str, host_id: int) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM hosts WHERE id = ?", (host_id,)).fetchone()
        if not row:
            return None
        return _parse_host_json(dict(row))
    finally:
        conn.close()


def _parse_host_json(d: dict) -> dict:
    """Parse JSON string fields in a host dict."""
    for key in ("all_ports", "security_protocols"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                d[key] = []
    return d


def get_host_stats(db_path: str) -> dict:
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM hosts").fetchone()[0]
        rdp_open = conn.execute("SELECT COUNT(*) FROM hosts WHERE rdp_open = 1").fetchone()[0]
        vnc_open = conn.execute("SELECT COUNT(*) FROM hosts WHERE vnc_open = 1").fetchone()[0]
        subnets_scanned = conn.execute("SELECT COUNT(DISTINCT subnet_id) FROM hosts").fetchone()[0]
        total_scans = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        announced = conn.execute("SELECT COUNT(*) FROM hosts WHERE announced = 1").fetchone()[0]
        return {
            "total_hosts": total,
            "rdp_open": rdp_open,
            "vnc_open": vnc_open,
            "subnets_scanned": subnets_scanned,
            "total_scans": total_scans,
            "announced": announced,
        }
    finally:
        conn.close()


def get_unannounced_rdp_hosts(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM hosts WHERE rdp_open = 1 AND announced = 0"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_host_announced(db_path: str, host_id: int) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE hosts SET announced = 1 WHERE id = ?", (host_id,))
        conn.commit()
    finally:
        conn.close()
