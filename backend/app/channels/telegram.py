import logging

from app.channels.base import AlertChannel
from app.collectors.base import post_json, CollectorHTTPError
from app.config import settings
from app.models.alert import Alert

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🟡"}


class TelegramChannel(AlertChannel):
    name = "telegram"

    def is_configured(self) -> bool:
        return bool(settings.telegram_bot_token and settings.telegram_chat_id)

    def send(self, alert: Alert, coin_label: str, trade_url: str | None = None) -> bool:
        if not self.is_configured():
            return False

        emoji = SEVERITY_EMOJI.get(alert.severity, "⚪")
        text = f"{emoji} {coin_label} — {alert.message}"
        if trade_url:
            text += f"\n{trade_url}"
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

        try:
            post_json(url, {"chat_id": settings.telegram_chat_id, "text": text})
            return True
        except CollectorHTTPError as e:
            logger.warning("Telegram alert delivery failed: %s", e)
            return False
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected Telegram alert delivery failure")
            return False
