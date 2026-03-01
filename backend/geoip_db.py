"""GeoIP database: download, import, and query DB-IP City Lite data."""

import csv
import gzip
import ipaddress
import json
import logging
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_geoip_db(db_path: str) -> None:
    """Create the GeoIP tables and indexes if they don't exist."""
    conn = _get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS geoip_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ip_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_start_int INTEGER NOT NULL,
            ip_end_int INTEGER NOT NULL,
            ip_start TEXT NOT NULL,
            ip_end TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '',
            latitude REAL,
            longitude REAL
        );

        CREATE INDEX IF NOT EXISTS idx_ip_blocks_country
            ON ip_blocks(country);
        CREATE INDEX IF NOT EXISTS idx_ip_blocks_country_state
            ON ip_blocks(country, state);
        CREATE INDEX IF NOT EXISTS idx_ip_blocks_country_state_city
            ON ip_blocks(country, state, city);
    """)
    conn.commit()

    # Migrate: add enrichment columns if missing
    for col, col_type, default in [
        ("asn", "TEXT", "''"),
        ("isp", "TEXT", "''"),
        ("ip_type", "TEXT", "''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE ip_blocks ADD COLUMN {col} {col_type} DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.close()


def get_status(db_path: str) -> dict:
    """Return import status info."""
    if not Path(db_path).exists():
        return {"imported": False, "csv_date": None, "last_updated": None, "total_blocks": 0}

    conn = _get_conn(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM ip_blocks").fetchone()[0]
        meta = {}
        for row in conn.execute("SELECT key, value FROM geoip_meta").fetchall():
            meta[row["key"]] = row["value"]
        return {
            "imported": total > 0,
            "csv_date": meta.get("csv_date"),
            "last_updated": meta.get("last_updated"),
            "total_blocks": total,
        }
    finally:
        conn.close()


def download_csv(url_template: str, dest_dir: str = ".") -> str:
    """Download the DB-IP CSV gz file. Returns path to downloaded file."""
    now = datetime.now(timezone.utc)
    url = url_template.replace("{YYYY}", str(now.year)).replace("{MM}", f"{now.month:02d}")
    filename = f"dbip-city-lite-{now.year}-{now.month:02d}.csv.gz"
    dest_path = str(Path(dest_dir) / filename)

    logger.info(f"Downloading GeoIP database from {url}")
    try:
        _do_download(url, dest_path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Try previous month
            prev_month = now.month - 1 if now.month > 1 else 12
            prev_year = now.year if now.month > 1 else now.year - 1
            url = url_template.replace("{YYYY}", str(prev_year)).replace("{MM}", f"{prev_month:02d}")
            filename = f"dbip-city-lite-{prev_year}-{prev_month:02d}.csv.gz"
            dest_path = str(Path(dest_dir) / filename)
            logger.info(f"Current month not available, trying previous: {url}")
            _do_download(url, dest_path)
        else:
            raise

    logger.info(f"Download complete: {dest_path}")
    return dest_path


def _do_download(url: str, dest_path: str) -> None:
    """Stream-download a URL to a file with progress logging."""
    req = urllib.request.Request(url, headers={"User-Agent": "RDP-Lottery/1.0"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as f:
        total = resp.headers.get("Content-Length")
        total = int(total) if total else None
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB
        last_pct = -1
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = int(downloaded * 100 / total)
                if pct >= last_pct + 5:
                    last_pct = pct
                    logger.info(f"Download progress: {pct}% ({downloaded // (1024*1024)}MB / {total // (1024*1024)}MB)")


def import_csv(db_path: str, csv_gz_path: str, progress_cb=None) -> int:
    """Import a gzipped CSV into the GeoIP database. Returns number of IPv4 blocks imported."""
    conn = _get_conn(db_path)
    conn.execute("PRAGMA synchronous=OFF")

    # Full refresh: delete existing data
    conn.execute("DELETE FROM ip_blocks")
    conn.commit()

    batch = []
    batch_size = 10000
    total_imported = 0
    total_lines = 0

    logger.info(f"Importing GeoIP data from {csv_gz_path}")

    with gzip.open(csv_gz_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            total_lines += 1
            if len(row) < 8:
                continue

            ip_start, ip_end, continent, country, state, city, lat, lon = row[:8]

            # Skip IPv6 rows
            if ":" in ip_start:
                continue

            try:
                ip_start_int = int(ipaddress.IPv4Address(ip_start))
                ip_end_int = int(ipaddress.IPv4Address(ip_end))
                latitude = float(lat) if lat else None
                longitude = float(lon) if lon else None
            except (ValueError, ipaddress.AddressValueError):
                continue

            batch.append((
                ip_start_int, ip_end_int, ip_start, ip_end,
                country, state, city, latitude, longitude,
            ))

            if len(batch) >= batch_size:
                conn.executemany(
                    "INSERT INTO ip_blocks (ip_start_int, ip_end_int, ip_start, ip_end, "
                    "country, state, city, latitude, longitude) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                conn.commit()
                total_imported += len(batch)
                batch.clear()

                if total_imported % 100000 == 0:
                    logger.info(f"Imported {total_imported:,} IPv4 blocks...")
                    if progress_cb:
                        progress_cb(total_imported)

    # Flush remaining
    if batch:
        conn.executemany(
            "INSERT INTO ip_blocks (ip_start_int, ip_end_int, ip_start, ip_end, "
            "country, state, city, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        conn.commit()
        total_imported += len(batch)

    # Update metadata
    now = datetime.now(timezone.utc).isoformat()
    # Extract date from filename
    csv_name = Path(csv_gz_path).name
    csv_date = csv_name.replace("dbip-city-lite-", "").replace(".csv.gz", "")

    conn.execute("INSERT OR REPLACE INTO geoip_meta (key, value) VALUES ('last_updated', ?)", (now,))
    conn.execute("INSERT OR REPLACE INTO geoip_meta (key, value) VALUES ('csv_date', ?)", (csv_date,))
    conn.commit()

    conn.execute("PRAGMA synchronous=FULL")
    conn.close()

    logger.info(f"GeoIP import complete: {total_imported:,} IPv4 blocks from {total_lines:,} total rows")
    return total_imported


def list_countries(db_path: str) -> list[dict]:
    """List all countries with their block counts."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT country, COUNT(*) as block_count FROM ip_blocks "
            "WHERE country != '' GROUP BY country ORDER BY country"
        ).fetchall()
        return [{"country": r["country"], "block_count": r["block_count"]} for r in rows]
    finally:
        conn.close()


def list_states(db_path: str, country: str) -> list[dict]:
    """List states/regions for a country with block counts."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT state, COUNT(*) as block_count FROM ip_blocks "
            "WHERE country = ? AND state != '' GROUP BY state ORDER BY state",
            (country,),
        ).fetchall()
        return [{"state": r["state"], "block_count": r["block_count"]} for r in rows]
    finally:
        conn.close()


def list_cities(db_path: str, country: str, state: str) -> list[dict]:
    """List cities for a country+state with block counts."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT city, COUNT(*) as block_count FROM ip_blocks "
            "WHERE country = ? AND state = ? AND city != '' GROUP BY city ORDER BY city",
            (country, state),
        ).fetchall()
        return [{"city": r["city"], "block_count": r["block_count"]} for r in rows]
    finally:
        conn.close()


def _enrich_blocks(db_path: str, rows: list[sqlite3.Row]) -> None:
    """Batch-enrich unenriched blocks via ip-api.com batch endpoint."""
    unenriched = [(r["id"], r["ip_start"]) for r in rows if not r["ip_type"]]
    if not unenriched:
        return

    # ip-api.com batch endpoint: max 100 per request
    batch_payload = [
        {"query": ip, "fields": "status,as,isp,hosting,mobile"}
        for _, ip in unenriched
    ]

    try:
        req = urllib.request.Request(
            "http://ip-api.com/batch?fields=status,as,isp,hosting,mobile",
            data=json.dumps(batch_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        results = json.loads(resp.read())
    except Exception as e:
        logger.warning(f"ip-api.com batch lookup failed: {e}")
        return

    conn = _get_conn(db_path)
    try:
        for (block_id, _ip), data in zip(unenriched, results):
            if data.get("status") != "success":
                continue
            ip_type = "Datacenter" if data.get("hosting") else ("Mobile" if data.get("mobile") else "Residential")
            as_field = data.get("as", "")
            asn = as_field.split()[0] if as_field else ""
            isp = data.get("isp", "")
            conn.execute(
                "UPDATE ip_blocks SET asn = ?, isp = ?, ip_type = ? WHERE id = ?",
                (asn, isp, ip_type, block_id),
            )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"Enriched {len(unenriched)} GeoIP blocks via ip-api.com batch")


def list_blocks(db_path: str, country: str, state: str, city: str,
                page: int = 1, page_size: int = 50) -> dict:
    """List IP blocks for a location, with CIDR conversion. Returns paginated results."""
    conn = _get_conn(db_path)
    try:
        # Get total count
        total = conn.execute(
            "SELECT COUNT(*) FROM ip_blocks WHERE country = ? AND state = ? AND city = ?",
            (country, state, city),
        ).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM ip_blocks WHERE country = ? AND state = ? AND city = ? "
            "ORDER BY ip_start_int LIMIT ? OFFSET ?",
            (country, state, city, page_size, offset),
        ).fetchall()

        # Enrich unenriched blocks in this page
        _enrich_blocks(db_path, rows)

        # Re-read to get enriched data
        if rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT * FROM ip_blocks WHERE id IN ({placeholders}) ORDER BY ip_start_int",
                ids,
            ).fetchall()

        blocks = []
        for r in rows:
            start = ipaddress.IPv4Address(r["ip_start_int"])
            end = ipaddress.IPv4Address(r["ip_end_int"])
            total_ips = r["ip_end_int"] - r["ip_start_int"] + 1

            # Convert to CIDRs, filter to /24 or smaller
            cidrs = [str(net) for net in ipaddress.summarize_address_range(start, end)]

            blocks.append({
                "ip_start": r["ip_start"],
                "ip_end": r["ip_end"],
                "total_ips": total_ips,
                "cidrs": cidrs,
                "cidr_count": len(cidrs),
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "asn": r["asn"] or "",
                "isp": r["isp"] or "",
                "ip_type": r["ip_type"] or "",
            })

        return {
            "blocks": blocks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }
    finally:
        conn.close()
