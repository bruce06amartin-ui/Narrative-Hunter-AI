"""
MODULE 6: Trend Detection.

Replaces the previous simplified proxy (a single 1h/24h price-change blend)
with the spec's actual four signals, computed from multi-timeframe
comparisons across price_history snapshots:

  - Velocity:     rate of price change, normalized to %/hour, computed over
                   three windows (15min, 1h, 4h) so a short burst can be told
                   apart from a sustained multi-hour trend.
  - Acceleration:  whether the short-term velocity is higher or lower than
                   the longer-term velocity - i.e. is the move speeding up
                   or slowing down right now, not just "is it up or down."
  - Decay:         a specific case of negative acceleration: a move that WAS
                   trending up over the 4h window but has clearly lost pace
                   in the most recent 15min - an early warning that a pump
                   is running out of steam, distinct from a move that's
                   simply reversing into a dump (which shows up as negative
                   velocity, not decay).
  - Momentum:      the composite 0-100 score combining all of the above,
                   plus a matching volume-side computation (rising volume
                   confirms a price move; falling volume on a price move is
                   a weaker signal).

Data quality note: this is only as good as snapshot density. Discovery/
scoring cycles run every ~2-3 minutes by default (see .env), giving
reasonable resolution for the 15min window, but a coin only tracked for
20 minutes won't have a real 4h reading yet - those windows fall back to
a neutral (unknown) contribution rather than being guessed at.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.price_history import PriceHistory
from app.models.score import Score

logger = logging.getLogger(__name__)

# (window_minutes, weight in the velocity/acceleration blend)
WINDOWS = [("short", 15), ("medium", 60), ("long", 240)]


class TrendDetectionService:
    def __init__(self, db: Session):
        self.db = db

    def score_all_active(self) -> dict:
        coins = self.db.query(Coin).filter(Coin.is_active.is_(True)).all()
        scored = 0
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                self.score_coin(coin)
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                scored += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Trend detection failed for coin id=%s", coin_id_for_logging)
        return {"scored": scored, "total_active": len(coins), "ran_at": datetime.utcnow().isoformat()}

    def score_coin(self, coin: Coin) -> float | None:
        snapshots = (
            self.db.query(PriceHistory)
            .filter(PriceHistory.coin_id == coin.id)
            .order_by(PriceHistory.recorded_at.asc())
            .all()
        )
        trend_score = self._compute_trend_score(snapshots)

        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.trend_score = trend_score
        self.db.flush()
        return trend_score

    def _compute_trend_score(self, snapshots: list[PriceHistory]) -> float | None:
        if len(snapshots) < 2:
            # None, not a neutral 50.0 - there genuinely isn't enough history
            # yet to say anything about trend. Returning a placeholder
            # number here used to get treated by ScoringService as "real
            # data confirming neutral," letting a coin's overall_score look
            # more confident than it actually was on liquidity alone. None
            # correctly signals "not yet available" so the confidence-based
            # shrinkage in ScoringService applies.
            return None

        now = snapshots[-1].recorded_at
        current_price = snapshots[-1].price_usd
        current_volume = snapshots[-1].volume_24h_usd

        price_rates = self._hourly_rates(snapshots, now, current_price, lambda s: s.price_usd)
        volume_rates = self._hourly_rates(snapshots, now, current_volume, lambda s: s.volume_24h_usd)

        velocity = price_rates.get("medium")  # the "primary" reading: 1h %/hour rate
        acceleration = self._acceleration(price_rates)
        decay = self._decay(price_rates)
        volume_confirmation = self._acceleration(volume_rates)  # is volume also picking up?

        if velocity is None and acceleration is None and volume_confirmation is None:
            # Every sub-signal is missing - this happens for coins that are
            # only minutes/a couple hours old: they technically have >=2
            # price_history snapshots (passing the check above), but not
            # enough ELAPSED TIME for the 15min/1h/4h windows to populate
            # with real data. Without this guard, _momentum_score would
            # receive None for all three inputs, default each one to its
            # own internal neutral 50, and combine them into an ostensibly
            # "computed" trend_score of exactly 50.0 - which ScoringService
            # then treats as real data confirming neutral, rather than
            # data that simply isn't available yet. This is the same class
            # of bug fixed at the top level (ScoringService's confidence
            # shrinkage), recurring one layer deeper - confirmed by real
            # production data showing nearly every new coin landing on
            # trend_score=50 "included" rather than genuinely absent.
            return None

        return self._momentum_score(velocity, acceleration, decay, volume_confirmation)

    def _hourly_rates(self, snapshots, now, current_value, getter) -> dict:
        """For each window, find the nearest snapshot at/before now-window
        and return the %/hour rate of change to `current_value`. Missing
        windows (not enough history yet) are simply absent from the dict."""
        rates = {}
        if current_value is None:
            return rates

        for label, minutes in WINDOWS:
            target_time = now - timedelta(minutes=minutes)
            reference = self._nearest_at_or_before(snapshots, target_time, getter)
            if reference is None or reference <= 0:
                continue
            pct_change = (current_value - reference) / reference * 100
            hours = minutes / 60
            rates[label] = pct_change / hours  # normalize to %/hour for comparability
        return rates

    def _nearest_at_or_before(self, snapshots: list[PriceHistory], target_time: datetime, getter):
        candidate = None
        for s in snapshots:
            if s.recorded_at <= target_time:
                value = getter(s)
                if value is not None:
                    candidate = value
            else:
                break
        return candidate

    def _acceleration(self, rates: dict) -> float | None:
        """Short-term rate minus a longer-term rate: positive means the
        move is speeding up right now; negative means it's slowing down.
        Prefers short-vs-medium; falls back to medium-vs-long if the
        short window isn't available yet."""
        if "short" in rates and "medium" in rates:
            return rates["short"] - rates["medium"]
        if "medium" in rates and "long" in rates:
            return rates["medium"] - rates["long"]
        return None

    def _decay(self, rates: dict) -> float:
        """0-1 decay magnitude: how much a previously-positive longer-term
        trend has lost pace in the short term. Zero if the long-term trend
        wasn't positive to begin with (nothing to decay from), or if data
        is insufficient."""
        long_rate = rates.get("long")
        short_rate = rates.get("short")
        if long_rate is None or short_rate is None or long_rate <= 0:
            return 0.0
        if short_rate >= long_rate:
            return 0.0  # still keeping pace or accelerating - no decay
        # How much of the long-term rate has been lost, clipped to [0, 1].
        # A short_rate that's gone negative counts as full decay (1.0).
        lost_fraction = (long_rate - max(short_rate, 0)) / long_rate
        return max(0.0, min(1.0, lost_fraction))

    def _momentum_score(
        self,
        velocity: float | None,
        acceleration: float | None,
        decay: float,
        volume_confirmation: float | None,
    ) -> float:
        # Velocity component: primary direction signal (1h %/hour rate).
        # Centered so 0%/hour (no movement) maps to a neutral 50.
        if velocity is None:
            velocity_component = 50.0  # neutral - no reading yet
        else:
            velocity_component = _clip(50 + velocity / 2, 0, 100)

        # Acceleration component: rewards speeding up, penalizes slowing down.
        if acceleration is None:
            acceleration_component = 50.0
        else:
            acceleration_component = _clip(50 + acceleration, 0, 100)

        # Volume confirmation: rising volume alongside the move adds
        # confidence; this is a smaller-weight modifier, not a primary signal.
        if volume_confirmation is None:
            volume_component = 50.0
        else:
            volume_component = _clip(50 + volume_confirmation * 0.5, 0, 100)

        raw = 0.45 * velocity_component + 0.30 * acceleration_component + 0.25 * volume_component

        # Decay is a direct penalty on top - a pump that's clearly losing
        # steam should score lower even if velocity is still nominally positive.
        decay_penalty = decay * 20  # up to -20 points for full decay
        return round(_clip(raw - decay_penalty, 0, 100), 1)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
