import logging
import smtplib
import ssl
from email.mime.text import MIMEText

from app.channels.base import AlertChannel
from app.config import settings
from app.models.alert import Alert

logger = logging.getLogger(__name__)


class EmailChannel(AlertChannel):
    name = "email"

    def is_configured(self) -> bool:
        return bool(
            settings.smtp_host
            and settings.smtp_username
            and settings.smtp_password
            and settings.alert_email_from
            and settings.alert_email_to
        )

    def send(self, alert: Alert, coin_label: str, trade_url: str | None = None) -> bool:
        if not self.is_configured():
            return False

        subject = f"[Narrative Hunter AI] {alert.severity.upper()}: {coin_label}"
        body = alert.message
        if trade_url:
            body += f"\n\n{trade_url}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.alert_email_from
        msg["To"] = settings.alert_email_to

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                server.starttls(context=context)
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(settings.alert_email_from, [settings.alert_email_to], msg.as_string())
            return True
        except Exception:  # noqa: BLE001 - any SMTP failure just means this channel didn't deliver
            logger.exception("Email alert delivery failed")
            return False
