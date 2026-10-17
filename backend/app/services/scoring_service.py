import logging
import math
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.coin import Coin
from app.models.score import Score, HistoricalScore
from app.services.liquidity_sanity import is_liquidity_plausible

logger = logging.getLogger(__name__)

# Liquidity above this is treated as "fully scored" (100). This is a starting
# heuristic threshold, not a researched constant - tune once you have real
# outcome data to calibrate against.
LIQUIDITY_SATURATION_USD = 250_000


class ScoringService:
    """MODULE 8: Overall Scoring — this is now the FULL spec formula.

    Full spec weights: Narrative 25% / Community 20% / Wallets 20% /
    Risk -20% / Liquidity 10% / Trend 15%.

    Liquidity, Trend (MODULE 6, computed by TrendDetectionService - real
    velocity/acceleration/decay/momentum model, not an inline proxy),
    Wallet (MODULE 3, EVM chains only), Narrative (MODULE 2/7, requires a
    social source + ANTHROPIC_API_KEY), and Community (MODULE 4, requires
    the same social sources as Narrative) are computed as a weighted
    average using each one's spec weight (config.py: WEIGHT_LIQUIDITY=0.10,
    WEIGHT_TREND=0.15, WEIGHT_WALLET=0.20, WEIGHT_NARRATIVE=0.25,
    WEIGHT_COMMUNITY=0.20) - but only across whichever actually have data
    for a given coin.

    CONFIDENCE SHRINKAGE: a coin with only liquidity+trend data (e.g. a
    brand-new coin nothing else has run on yet) would otherwise reach the
    same scores as one fully backed by wallet/narrative/community evidence,
    purely because the formula renormalizes over whatever's available. A
    maxed-out liquidity score alone was enough to cross a 70-point alert
    threshold with zero evidence behind the other 4 signals - not a
    precision bug in the arithmetic, but a real problem in what the number
    was allowed to imply. The fix: the raw weighted average is pulled
    toward a neutral 50 in proportion to how much of the FULL five-signal
    weight pool is still missing (see _weighted_average_with_confidence).
    A coin backed by all five signals is unaffected (confidence=1.0, no
    shrinkage); a coin backed by only liquidity+trend gets pulled most of
    the way toward neutral, since 65% of the spec's positive weight
    (wallet+narrative+community) is simply unknown, not zero.

    Risk (MODULE 5, implemented in RiskService) is applied as a separate
    subtractive penalty rather than folded into the weighted-average pool -
    it's specified as a negative weight, not a positive share. Penalty
    strength is config.WEIGHT_RISK_PENALTY (default 0.20, matching the
    spec's "-20%" exactly).

    Every coin's overall_score reflects only what data was actually
    available for it - scoring_notes on the Score row always states which
    components were included and the resulting confidence level, so a
    "low-data" coin's score is never silently treated the same as a
    "fully analyzed" one.

    Ordering matters: this reads whatever trend_score/risk_score/
    wallet_score/narrative_score/community_score are already on the Score
    row, so run TrendDetectionService, RiskService, WalletIntelligenceService,
    NarrativeScannerService, and CommunityIntelligenceService before this in
    a given cycle to reflect fresh data (stale values from a previous cycle
    are used otherwise, which is fine - just not current).
    """

    NEUTRAL_SCORE = 50.0

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
                logger.exception("Failed to score coin id=%s", coin_id_for_logging)
        return {"scored": scored, "total_active": len(coins), "ran_at": datetime.utcnow().isoformat()}

    def _weighted_average_with_confidence(
        self, components: dict, available_components: list, weights: dict
    ) -> tuple[float, float]:
        """Returns (score, confidence). confidence is in [0, 1] and reflects
        what fraction of the FULL five-signal spec weight is actually backed
        by real data for this coin - not just the ratio among whatever's
        available (that's what total_weight/available already captures).
        The raw weighted average is shrunk toward NEUTRAL_SCORE by
        (1 - confidence), so missing signals count as "unknown" rather than
        silently vanishing from the picture."""
        total_weight = sum(weights[k] for k in available_components)
        full_weight = sum(weights.values())
        if total_weight <= 0 or full_weight <= 0:
            # Zero confirmed signals - shrink fully to neutral, matching
            # what the general formula below produces at confidence=0
            # (raw_score * 0 + NEUTRAL * 1 = NEUTRAL). This exact case was
            # previously unreachable in practice (liquidity used to be
            # unconditionally present in available_components no matter
            # what), but making liquidity conditional too (see
            # _liquidity_score) means a coin with implausible/manipulated
            # liquidity AND nothing else checked yet can now genuinely
            # have zero confirmed signals - it should read as "completely
            # unknown" (neutral), not as a confidently bad 0.
            return self.NEUTRAL_SCORE, 0.0

        raw_score = sum(components[k] * weights[k] for k in available_components) / total_weight
        confidence = min(1.0, total_weight / full_weight)
        shrunk_score = raw_score * confidence + self.NEUTRAL_SCORE * (1 - confidence)
        return shrunk_score, confidence

    def score_coin(self, coin: Coin) -> Score:
        liquidity_score = self._liquidity_score(coin)

        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)

        existing_trend_score = score.trend_score           # set by TrendDetectionService, if it has run
        existing_risk_score = score.risk_score              # set by RiskService, if it has run
        existing_wallet_score = score.wallet_score          # set by WalletIntelligenceService, if it has run
        existing_narrative_score = score.narrative_score    # set by NarrativeScannerService, if it has run
        existing_community_score = score.community_score    # set by CommunityIntelligenceService, if it has run

        components = {}
        available_components = []
        if liquidity_score is not None:
            components["liquidity"] = liquidity_score
            available_components.append("liquidity")
        if existing_trend_score is not None:
            components["trend"] = existing_trend_score
            available_components.append("trend")
        if existing_wallet_score is not None:
            components["wallet"] = existing_wallet_score
            available_components.append("wallet")
        if existing_narrative_score is not None:
            components["narrative"] = existing_narrative_score
            available_components.append("narrative")
        if existing_community_score is not None:
            components["community"] = existing_community_score
            available_components.append("community")

        weights = {
            "liquidity": settings.weight_liquidity,
            "trend": settings.weight_trend,
            "wallet": settings.weight_wallet,
            "narrative": settings.weight_narrative,
            "community": settings.weight_community,
        }

        overall_score, confidence = self._weighted_average_with_confidence(
            components, available_components, weights
        )
        if confidence == 0.0 and sum(weights.values()) <= 0:
            logger.warning(
                "All scoring weights are zero for coin id=%s - check your WEIGHT_* env vars",
                coin.id,
            )

        risk_note = score.risk_notes or "risk not yet checked"
        if existing_risk_score is not None:
            overall_score -= existing_risk_score * settings.weight_risk_penalty
            risk_note = f"risk penalty applied ({existing_risk_score:.0f}/100 risk)"
        overall_score = max(0.0, min(100.0, overall_score))

        if liquidity_score is not None:
            liquidity_note = "included"
        elif (coin.liquidity_usd or 0) <= 0:
            liquidity_note = "no liquidity data"
        else:
            liquidity_note = "excluded - claimed liquidity failed a manipulation sanity check"
        trend_note = "included" if existing_trend_score is not None else "not yet computed"
        if existing_wallet_score is not None:
            wallet_note = "included"
        elif coin.chain == "solana":
            wallet_note = "no Solana wallet data yet"
        else:
            wallet_note = "no EVM wallet data yet"
        narrative_note = "included" if existing_narrative_score is not None else "no narrative data yet"
        community_note = "included" if existing_community_score is not None else "no community data yet"
        notes = (
            f"Computed from: liquidity ({liquidity_note}), trend ({trend_note}), wallet ({wallet_note}), "
            f"narrative ({narrative_note}), community ({community_note}); {risk_note}. "
            f"Confidence: {confidence * 100:.0f}% of full signal set available "
            f"(score pulled toward neutral {self.NEUTRAL_SCORE:.0f} in proportion to what's missing)."
        )

        score.liquidity_score = liquidity_score
        score.overall_score = overall_score
        score.confidence = confidence
        score.scoring_notes = notes

        self.db.add(
            HistoricalScore(
                coin_id=coin.id,
                overall_score=overall_score,
                liquidity_score=liquidity_score,
                trend_score=existing_trend_score,
                risk_score=existing_risk_score,
                narrative_score=existing_narrative_score,
                community_score=existing_community_score,
            )
        )
        self.db.flush()
        return score

    def _liquidity_score(self, coin: Coin) -> float | None:
        """0-100, log-scaled so early liquidity differences matter more than
        differences at the high end. Returns None (not a confident number)
        when the claimed liquidity fails the manipulation sanity check -
        found via real production data: coins reporting hundreds of
        millions to billions in liquidity with near-zero real trading
        volume behind them (a known DeFi manipulation pattern - fake
        reserves reported to indexers). Liquidity was previously the ONE
        signal always treated as confirmed/trustworthy no matter what,
        unlike trend/wallet/narrative/community which already correctly
        return None when data is missing or unreliable - this brings
        liquidity in line with that same standard rather than letting a
        likely-fake number get full weight and confidence in scoring."""
        liquidity = coin.liquidity_usd or 0.0
        if liquidity <= 0:
            return 0.0
        if not is_liquidity_plausible(coin.liquidity_usd, coin.volume_24h_usd):
            return None
        score = 100 * math.log10(1 + liquidity) / math.log10(1 + LIQUIDITY_SATURATION_USD)
        return max(0.0, min(100.0, score))
