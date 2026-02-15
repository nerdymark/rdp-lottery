"""TOML configuration loader."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: str = "rdp_lottery.db"


@dataclass
class ScannerConfig:
    timing_template: int = 4
    host_timeout_seconds: int = 120


@dataclass
class AtprotoConfig:
    enabled: bool = False
    service_url: str = "https://bsky.social"
    username: str = ""
    app_password: str = ""
    owner_username: str = ""
    post_template: str = "Jackpot! Found an open {proto} host{hostname_suffix}\n{asn}\n{ip_type}"
    follow_up_template: str = ""


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    atproto: AtprotoConfig = field(default_factory=AtprotoConfig)


def load_config(path: str = "config.toml") -> Config:
    """Load configuration from a TOML file."""
    config_path = Path(path)
    if not config_path.exists():
        return Config()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return Config(
        app=AppConfig(**data.get("app", {})),
        scanner=ScannerConfig(**data.get("scanner", {})),
        atproto=AtprotoConfig(**data.get("atproto", {})),
    )
