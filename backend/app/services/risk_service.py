import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.goplus import GoPlusCollector
from app.collectors.rugcheck import RugCheckCollector
from app.config import settings
from app.models.coin import Coin
from app.models.risk_flag import RiskFlag
from app.models.score import Score
from app.models.wallet_transaction import WalletTransaction

logger = logging.getLogger(__name__)

# Holder-concentration risk is applied above these thresholds (percent, 0-100).
TOP10_HOLDER_WARN_PCT = 40.0
TOP10_HOLDER_SEVERE_PCT = 70.0
LP_LOCK_WARN_PCT = 50.0  # below this % of LP locked is treated as a risk


class RiskService:
    """MODULE 5: Rug Detection.

    Covers what GoPlus Security's public API can verify: liquidity/holder
    concentration, mint/freeze authority, liquidity lock status, and known
    contract-level rug patterns (honeypot, hidden owner, self-destruct,
    etc). This is real, live risk data - not a placeholder.

    Also covers two of the three previously-pending checks, using data
    MODULE 3 already collects:
      - Sniper cluster detection: many distinct wallets buying within a
        short window of launch (WALLET_TRANSACTIONS data, EVM chains only -
        requires WalletIntelligenceService to have already ingested
        transfers for this coin, so this check improves over cycles as
        wallet data accumulates rather than being complete on the first pass).
      - Repeat deployer detection: cross-references GoPlus's creator_address
        (or, on Solana, mint authority as the closest equivalent) against
        every other coin THIS platform has tracked with the same creator on
        the same chain. A high count isn't automatically malicious - some
        legitimate projects launch many tokens - but it's a real, surfaced
        signal rather than a guess.

    NOT covered: bundle-wallet detection (tracing whether multiple holder
    wallets were funded from a common source address before their first
    buy). That needs native-currency transfer history per wallet - a
    separate Etherscan call (txlist) per wallet, not just token transfers -
    which wasn't built here to keep third-party API spend bounded.
    risk_score reflects only what's covered above; treat it as a partial
    risk signal, not a complete rug-pull guarantee either way.
    """

    def __init__(self, db: Session):
        self.db = db
        self.collector = GoPlusCollector()
        self.rugcheck = RugCheckCollector()

    def check_all_active(self) -> dict:
        total_active_coins = self.db.query(Coin).filter(Coin.is_active.is_(True)).count()

        recheck_cutoff = datetime.utcnow() - timedelta(hours=settings.risk_recheck_hours)
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                (Score.id.is_(None))
                | (Score.risk_checked_at.is_(None))
                | (Score.risk_checked_at < recheck_cutoff),
            )
            .all()
        )
        checked = 0
        no_data = 0
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                result = self.check_coin(coin)
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                if result is None:
                    no_data += 1
                else:
                    checked += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Risk check failed for coin id=%s", coin_id_for_logging)
        return {
            "checked": checked,
            "no_data": no_data,
            "due_for_check_this_cycle": len(coins),
            "total_active_coins": total_active_coins,
            "ran_at": datetime.utcnow().isoformat(),
        }

    def check_coin(self, coin: Coin) -> float | None:
        data = self.collector.check_token(coin.chain, coin.contract_address)

        # Clear previous flags regardless - we're about to replace them with
        # either fresh flags or a "no data" state.
        self.db.query(RiskFlag).filter(RiskFlag.coin_id == coin.id).delete()

        if data is None:
            if coin.chain == "solana":
                rugcheck_result = self.rugcheck.get_risk_summary(coin.contract_address)
                if rugcheck_result is not None:
                    risks_note = (
                        f" Flagged: {', '.join(rugcheck_result['risks'][:5])}."
                        if rugcheck_result["risks"]
                        else ""
                    )
                    self._set_risk_score(
                        coin,
                        rugcheck_result["risk_score"],
                        note=(
                            "No GoPlus data for this chain/token - using RugCheck "
                            f"(Solana-specific) as a fallback.{risks_note}"
                        ),
                    )
                    return rugcheck_result["risk_score"]
            self._set_risk_score(coin, None, note="No risk data available from GoPlus for this chain/token yet.")
            return None

        flags = self._evaluate(data)

        coin.creator_address = data.get("creator_address")
        self.db.flush()

        deployer_flag = self._check_repeat_deployer(coin)
        if deployer_flag:
            flags.append(deployer_flag)

        sniper_flag = self._check_sniper_cluster(coin)
        if sniper_flag:
            flags.append(sniper_flag)

        risk_score = min(100.0, sum(f["points"] for f in flags))

        for f in flags:
            self.db.add(
                RiskFlag(
                    coin_id=coin.id,
                    flag_type=f["flag_type"],
                    severity=f["severity"],
                    points=f["points"],
                    description=f["description"],
                )
            )

        note = f"{len(flags)} risk flag(s) detected." if flags else "No risk flags detected in available checks."
        self._set_risk_score(coin, risk_score, note=note)
        self.db.flush()
        return risk_score

    def _check_repeat_deployer(self, coin: Coin) -> dict | None:
        if not coin.creator_address:
            return None

        count = (
            self.db.query(Coin)
            .filter(
                Coin.creator_address == coin.creator_address,
                Coin.chain == coin.chain,
                Coin.id != coin.id,
            )
            .count()
        )
        if count < settings.repeat_deployer_min_other_coins:
            return None

        return {
            "flag_type": "repeat_deployer",
            "severity": "medium",
            "points": 15.0,
            "description": (
                f"This creator address has deployed {count + 1} tracked tokens on {coin.chain} "
                "- could be a serial launcher (not automatically malicious, but worth reviewing)."
            ),
        }

    def _check_sniper_cluster(self, coin: Coin) -> dict | None:
        if coin.launch_time is None:
            return None

        cutoff = coin.launch_time + timedelta(seconds=settings.sniper_cluster_window_seconds)
        rows = (
            self.db.query(WalletTransaction.wallet_id, func.min(WalletTransaction.block_timestamp).label("first_in"))
            .filter(WalletTransaction.coin_id == coin.id, WalletTransaction.direction == "in")
            .group_by(WalletTransaction.wallet_id)
            .all()
        )
        sniper_count = sum(1 for r in rows if r.first_in <= cutoff)
        if sniper_count < settings.sniper_cluster_min_wallets:
            return None

        return {
            "flag_type": "sniper_cluster_detected",
            "severity": "medium",
            "points": 15.0,
            "description": (
                f"{sniper_count} distinct wallets bought within "
                f"{settings.sniper_cluster_window_seconds}s of launch - possible coordinated sniping."
            ),
        }

    def _set_risk_score(self, coin: Coin, risk_score: float | None, note: str) -> None:
        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.risk_score = risk_score
        score.risk_notes = note
        score.risk_checked_at = datetime.utcnow()
        self.db.flush()

    def _evaluate(self, data: dict) -> list[dict]:
        flags: list[dict] = []

        def flag(flag_type: str, severity: str, points: float, description: str):
            flags.append({"flag_type": flag_type, "severity": severity, "points": points, "description": description})

        # Solana "trusted_token" is GoPlus's own allowlist for known-legit
        # tokens (e.g. USDC) - short-circuit to a minimal risk score rather
        # than penalizing intentional design choices like a trusted mint.
        if data.get("trusted_token"):
            flag("trusted_token", "low", 0, "GoPlus lists this token as a known/trusted asset.")
            return flags

        if data.get("is_honeypot"):
            flag("honeypot_suspected", "critical", 40,
                 "Contract shows signs of being a honeypot (tokens may not be sellable).")

        if data.get("non_transferable"):
            flag("non_transferable", "critical", 35, "Token is flagged as non-transferable.")

        if data.get("is_mintable"):
            flag("mint_authority_active", "high", 20,
                 "Mint authority is active - supply can be inflated at any time.")

        if data.get("is_freezable"):
            flag("freeze_authority_active", "high", 15,
                 "Freeze authority is active - holder accounts can be frozen.")

        if data.get("owner_change_balance"):
            flag("owner_can_change_balance", "high", 15,
                 "Contract owner can directly alter holder balances.")

        if data.get("hidden_owner"):
            flag("hidden_owner", "high", 15,
                 "Contract has a hidden owner - ownership may not actually be renounced.")

        if data.get("is_open_source") is False:
            flag("closed_source", "high", 15,
                 "Contract source is not verified/open - other checks may be unreliable.")

        if data.get("selfdestruct"):
            flag("selfdestruct_capable", "medium", 10, "Contract can self-destruct, erasing all assets.")

        if data.get("transfer_pausable"):
            flag("transfer_pausable", "medium", 10, "Owner can pause all trading at will.")

        if data.get("can_take_back_ownership"):
            flag("ownership_reclaimable", "medium", 10,
                 "Renounced ownership can reportedly be reclaimed by a hidden mechanism.")

        if data.get("is_blacklisted"):
            flag("blacklist_function", "low", 8, "Contract can blacklist addresses from trading.")

        for cap in ("slippage_modifiable", "anti_whale_modifiable", "trading_cooldown", "is_closable", "balance_mutable"):
            if data.get(cap):
                flag(cap, "low", 5, f"Contract has an active '{cap}' capability that adds owner discretion/risk.")

        for tax_field, label in (("buy_tax", "Buy"), ("sell_tax", "Sell")):
            tax = data.get(tax_field)
            if tax is not None and tax >= 0.10:
                severity = "high" if tax >= 0.25 else "medium"
                points = 20 if tax >= 0.25 else 10
                flag(f"{tax_field}_high", severity, points, f"{label} tax is {tax * 100:.0f}%.")

        top10 = data.get("top10_holder_percent")
        if top10 is not None and top10 >= TOP10_HOLDER_WARN_PCT:
            severity = "high" if top10 >= TOP10_HOLDER_SEVERE_PCT else "medium"
            points = 25 if top10 >= TOP10_HOLDER_SEVERE_PCT else 12
            flag("holder_concentration_high", severity, points,
                 f"Top 10 holders control {top10:.1f}% of supply.")

        lp_locked = data.get("lp_locked_percent")
        if lp_locked is not None and lp_locked < LP_LOCK_WARN_PCT:
            severity = "high" if lp_locked < 10 else "medium"
            points = 20 if lp_locked < 10 else 10
            flag("liquidity_not_locked", severity, points,
                 f"Only {lp_locked:.1f}% of tracked liquidity is locked.")

        return flags
