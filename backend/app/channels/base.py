"""
MODULE 9: Alerts - notification channel interface.

Each channel is independently optional: if its config isn't set, it's
simply skipped (not treated as an error) so you can run with e.g. only
Discord configured. AlertService only records a channel in
Alert.channels_delivered if send() returns True.
"""

from app.models.alert import Alert


class AlertChannel:
    name: str = "base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def send(self, alert: Alert, coin_label: str, trade_url: str | None = None) -> bool:
        """Send the alert. Returns True on confirmed delivery, False on any
        failure - failures are logged by the implementation, not raised,
        so one channel's outage doesn't block the others or the DB commit.
        trade_url, when provided, links directly to the coin's DexScreener
        pair page - built from the same chain-slug mapping already proven
        correct by collectors/dexscreener.py's live enrichment calls."""
        raise NotImplementedError
