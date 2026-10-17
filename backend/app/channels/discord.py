import logging

from app.channels.base import AlertChannel
from app.collectors.base import post_json, CollectorHTTPError
from app.config import settings
from app.models.alert import Alert

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🟡"}


class DiscordChannel(AlertChannel):
    name = "discord"

    def is_configured(self) -> bool:
        return bool(settings.discord_webhook_url)

    def send(self, alert: Alert, coin_label: str, trade_url: str | None = None) -> bool:
        if not self.is_configured():
            return False

        emoji = SEVERITY_EMOJI.get(alert.severity, "⚪")
        content = f"{emoji} **{coin_label}** — {alert.message}"
        if trade_url:
            content += f"\n{trade_url}"

        try:
            post_json(settings.discord_webhook_url, {"content": content})
            return True
        except CollectorHTTPError as e:
            logger.warning("Discord alert delivery failed: %s", e)
            return False
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected Discord alert delivery failure")
            return False
