"""Bluesky AT Protocol client for announcing RDP discoveries."""

import logging
from typing import Optional

from atproto import Client, models
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
            isp = host.get("isp", "").strip()
            ip_type = host.get("ip_type", "").strip()
            city = host.get("city", "").strip()
            country_code = host.get("country_code", "").strip()

            # Build full location string: "Hayward / US / AS6167 Verizon Business"
            location_parts = []
            if city:
                location_parts.append(city)
            if country_code:
                location_parts.append(country_code)
            asn_full = f"{asn} {isp}".strip() if asn else isp
            if asn_full:
                location_parts.append(asn_full)
            location = " / ".join(location_parts)

            text = self.config.post_template.format(
                proto=proto,
                hostname_suffix=hostname_suffix,
                asn=asn,
                ip_type=ip_type,
                location=location,
            )

            # Truncate to 300 char limit
            if len(text) > 300:
                text = text[:297] + "..."

            with open(screenshot_path, "rb") as f:
                image_data = f.read()
            post_ref = self.client.send_image(
                text=text,
                image=image_data,
                image_alt=f"{proto} login screen",
            )
            logger.info(f"Announced {proto} host to Bluesky with screenshot")

            # Post follow-up reply if configured
            if self.config.follow_up_template and post_ref:
                self._send_follow_up(post_ref, proto)

            return True
        except AtProtocolError as e:
            logger.error(f"Failed to post to Bluesky: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error posting to Bluesky: {e}")
            return False

    def _send_follow_up(self, parent_ref, proto: str) -> None:
        """Post a follow-up reply to an announcement."""
        try:
            owner = self.config.owner_username.strip()
            mention_text = f"@{owner}" if owner else ""
            text = self.config.follow_up_template.format(
                owner_username=mention_text,
                proto=proto,
            )
            if len(text) > 300:
                text = text[:297] + "..."

            # Build mention facet so @handle becomes a clickable mention
            facets = []
            if owner and mention_text in text:
                try:
                    resolved = self.client.resolve_handle(owner)
                    mention_start = text.index(mention_text)
                    byte_start = len(text[:mention_start].encode("utf-8"))
                    byte_end = byte_start + len(mention_text.encode("utf-8"))
                    facets.append(models.AppBskyRichtextFacet.Main(
                        index=models.AppBskyRichtextFacet.ByteSlice(
                            byte_start=byte_start,
                            byte_end=byte_end,
                        ),
                        features=[models.AppBskyRichtextFacet.Mention(did=resolved.did)],
                    ))
                except Exception as e:
                    logger.warning(f"Could not resolve handle {owner} for mention: {e}")

            strong_ref = models.ComAtprotoRepoStrongRef.Main(
                uri=parent_ref.uri,
                cid=parent_ref.cid,
            )
            reply_ref = models.AppBskyFeedPost.ReplyRef(
                root=strong_ref,
                parent=strong_ref,
            )
            self.client.send_post(text=text, reply_to=reply_ref, facets=facets or None)
            logger.info("Posted follow-up reply to announcement")
        except Exception as e:
            logger.error(f"Failed to post follow-up reply: {e}")
