"""
Pool migration detector (MODULE 1 extension).

Real gap this closes: discovery and price-refresh (see
collectors/geckoterminal.py) only ever look at the ONE pool address a
coin was first found on. A coin discovered early - e.g. on a thin,
low-liquidity pool right as it launches - can have its REAL trading
activity move to a completely different, healthier pool later (a pump.fun
token graduating to a real Raydium pool is the clearest example, but this
can happen on any chain/DEX). Nothing in the existing pipeline would ever
notice this: refresh_prices() only re-checks the SAME pair_address a coin
already has, so a coin whose real activity has moved elsewhere just looks
increasingly dead over time, even though the token itself may be thriving
under a different pool address.

This service periodically re-checks coins whose CURRENT pool looks thin
or stale, asks GeckoTerminal for every pool currently trading that same
underlying token contract, and switches the coin's pair_address (and
refreshes its liquidity/volume/price) if a genuinely, substantially
better pool is found.

Bounded exactly like every other collector in this project: a modest
per-cycle cap and a recheck cooldown, both configurable in config.py.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.collectors.geckoterminal import GeckoTerminalCollector
from app.config import settings
from app.models.coin import Coin

logger = logging.getLogger(__name__)


class PoolMigrationService:
    def __init__(self, db: Session, collector: GeckoTerminalCollector | None = None):
        self.db = db
        self.collector = collector or GeckoTerminalCollector(networks=["solana", "eth", "base"])

    def run_cycle(self) -> dict:
        cutoff = datetime.utcnow() - timedelta(hours=settings.pool_migration_recheck_hours)

        candidates = (
            self.db.query(Coin)
            .filter(
                Coin.is_active == True,  # noqa: E712
                Coin.liquidity_usd < settings.pool_migration_stale_liquidity_threshold_usd,
                (Coin.pool_migration_checked_at.is_(None)) | (Coin.pool_migration_checked_at < cutoff),
            )
            .order_by(Coin.last_updated_at.asc())
            .limit(settings.pool_migration_max_coins_per_cycle)
            .all()
        )

        migrated = 0
        checked = 0
        for coin in candidates:
            checked += 1
            try:
                if self._check_and_migrate(coin):
                    migrated += 1
            except Exception as e:  # noqa: BLE001 - one bad coin shouldn't kill the cycle
                logger.exception("Pool migration check failed for coin id=%s: %s", coin.id, e)
            coin.pool_migration_checked_at = datetime.utcnow()

        self.db.commit()
        return {
            "checked": checked,
            "migrated": migrated,
            "due_for_check_this_cycle": len(candidates),
            "ran_at": datetime.utcnow().isoformat(),
        }

    def _check_and_migrate(self, coin: Coin) -> bool:
        if not coin.contract_address:
            return False

        pools = self.collector.get_all_pools_for_token(coin.chain, coin.contract_address)
        if not pools:
            return False

        current_liquidity = coin.liquidity_usd or 0.0
        best = max(pools, key=lambda p: p.get("liquidity_usd") or 0.0)
        best_liquidity = best.get("liquidity_usd") or 0.0

        # Already on the best available pool - nothing to migrate to.
        if best.get("pair_address") == coin.pair_address:
            return False

        # Require a MEANINGFUL improvement, not noise - same
        # "don't trust a number just because it's bigger" discipline as
        # the liquidity manipulation and whale-entry plausibility checks
        # elsewhere in this project.
        threshold = max(current_liquidity, 1.0) * settings.pool_migration_improvement_multiple
        if best_liquidity < threshold:
            return False

        logger.info(
            "Pool migration found for coin id=%s (%s): %s -> %s, liquidity $%.2f -> $%.2f",
            coin.id, coin.symbol, coin.pair_address, best.get("pair_address"),
            current_liquidity, best_liquidity,
        )

        coin.pair_address = best.get("pair_address")
        coin.liquidity_usd = best.get("liquidity_usd")
        coin.volume_24h_usd = best.get("volume_24h_usd")
        coin.price_usd = best.get("price_usd")
        coin.market_cap_usd = best.get("market_cap_usd")
        coin.fdv_usd = best.get("fdv_usd")
        coin.price_change_1h = best.get("price_change_1h")
        coin.price_change_24h = best.get("price_change_24h")
        coin.last_updated_at = datetime.utcnow()
        return True
