"""Bluesky AT Protocol client for announcing RDP discoveries."""

import logging
from typing import Optional

from atproto import Client
from atproto.exceptions import AtProtocolError

from backend.config import AtprotoConfig

logger = logging.getLogger(__name__)


class BlueskyAnnouncer:
    """Announces RDP host discoveries to Bluesky."""

    def __init__(self, config: AtprotoConfig):
        self.config = config
        self.client: Optional[Client] = None
        self.profile = None

        if config.enabled and config.username and config.app_password:
            self.authenticate()

    def authenticate(self) -> bool:
        try:
            self.client = Client(base_url=self.config.service_url)
            self.profile = self.client.login(
                self.config.username, self.config.app_password
            )
            logger.info(f"Authenticated to Bluesky as {self.profile.handle}")
            return True
        except AtProtocolError as e:
            logger.error(f"Bluesky authentication failed: {e}")
            self.client = None
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Bluesky auth: {e}")
            self.client = None
            return False

    def announce_host(self, host: dict, screenshot_path: Optional[str] = None, proto: str = "RDP") -> bool:
        """Post a discovery announcement for a host.

        Only announces if a screenshot is available. Never exposes IP, domain, or ports.

        Args:
            host: Dict with host data keys.
            screenshot_path: Path to screenshot PNG (required).
            proto: Protocol name for template (e.g. "RDP", "VNC").

        Returns:
            True if posted successfully.
        """
        if not self.config.enabled:
            logger.debug("Bluesky announcements disabled")
            return False

        if not self.client:
            logger.warning("Bluesky client not authenticated, skipping announcement")
            return False

        # Only announce if we have a screenshot
        import os
        if not screenshot_path or not os.path.exists(screenshot_path):
            logger.info(f"Skipping announcement for {host.get('ip')} — no screenshot")
            return False

        try:
            hostname = host.get("hostname", "").strip()
            hostname_suffix = f": {hostname}" if hostname else ""
            asn = host.get("asn", "").strip()
            ip_type = host.get("ip_type", "").strip()

            text = self.config.post_template.format(
                proto=proto,
                hostname_suffix=hostname_suffix,
                asn=asn,
                ip_type=ip_type,
            )

            # Truncate to 300 char limit
            if len(text) > 300:
                text = text[:297] + "..."

            with open(screenshot_path, "rb") as f:
                image_data = f.read()
            self.client.send_image(
                text=text,
                image=image_data,
                image_alt=f"{proto} login screen",
            )
            logger.info(f"Announced {proto} host to Bluesky with screenshot")
            return True
        except AtProtocolError as e:
            logger.error(f"Failed to post to Bluesky: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error posting to Bluesky: {e}")
            return False
