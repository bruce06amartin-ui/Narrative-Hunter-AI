from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.alert_service import AlertService
from app.services.community_service import CommunityIntelligenceService
from app.services.discovery_service import DiscoveryService
from app.services.narrative_scanner_service import NarrativeScannerService
from app.services.pool_migration_service import PoolMigrationService
from app.services.risk_service import RiskService
from app.services.solana_wallet_service import SolanaWalletIntelligenceService
from app.services.trend_service import TrendDetectionService
from app.services.youtube_scanner_service import YouTubeScannerService
from app.services.scoring_service import ScoringService
from app.services.wallet_service import WalletIntelligenceService
from app.workers.locks import task_lock

router = APIRouter(prefix="/api", tags=["ops"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/discovery/run")
def run_discovery(db: Session = Depends(get_db)):
    """Manually trigger a discovery cycle synchronously - useful for local
    testing without waiting on the Celery beat schedule. Shares a lock with
    the scheduled version of this task, so triggering this manually while
    the background scheduler happens to be mid-run of the same cycle
    won't cause the two to collide - it'll just report itself as skipped."""
    with task_lock("discovery_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a discovery cycle (scheduled or manual) is already running"}
        service = DiscoveryService(db, networks=settings.discovery_network_list)
        return service.run_cycle()


@router.post("/price-refresh/run")
def run_price_refresh(db: Session = Depends(get_db)):
    """Manually trigger a price refresh for already-known active coins,
    independent of the new_pools discovery feed. Closes a real gap: without
    this, a coin only ever gets a fresh price reading if it happens to
    still appear in new_pools - which stops being true within its first
    hour or so of existence, freezing price_history (and therefore MODULE
    6 trend detection) forever. Run this before /api/trend/run so trend
    reflects genuinely current price movement, not stale first-hour data."""
    with task_lock("price_refresh_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a price refresh cycle (scheduled or manual) is already running"}
        service = DiscoveryService(db, networks=settings.discovery_network_list)
        return service.refresh_existing_prices()


@router.post("/social-reenrichment/run")
def run_social_reenrichment(db: Session = Depends(get_db)):
    """Manually trigger a social-handle re-enrichment sweep - retries
    coins that had no Telegram handle at discovery time (many projects add
    their Telegram link a few hours/days after launch, not at the exact
    moment we first discover them). This directly increases how many coins
    have real, free (Telegram-sourced) posts available for MODULE 4
    (Community Intelligence), which does NOT require ANTHROPIC_API_KEY -
    only MODULE 7's AI narrative analysis does. Now runs on its own
    schedule, decoupled from discovery's tighter time budget."""
    with task_lock("social_reenrichment_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a social re-enrichment cycle (scheduled or manual) is already running"}
        service = DiscoveryService(db, networks=settings.discovery_network_list)
        return service.re_enrich_missing_social_handles()


@router.post("/risk/run")
def run_risk_check(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 5 rug-detection pass synchronously.
    Run this before /api/scoring/run so overall_score reflects fresh risk data."""
    with task_lock("risk_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a risk cycle (scheduled or manual) is already running"}
        service = RiskService(db)
        return service.check_all_active()


@router.post("/trend/run")
def run_trend_detection(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 6 trend-detection pass synchronously
    (velocity/acceleration/decay/momentum from price_history). Run this
    before /api/scoring/run so overall_score reflects fresh trend_score data."""
    with task_lock("trend_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a trend cycle (scheduled or manual) is already running"}
        service = TrendDetectionService(db)
        return service.score_all_active()


@router.post("/wallets/run")
def run_wallet_check(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 3 wallet-intelligence pass synchronously
    (EVM chains only - requires ETHERSCAN_API_KEY). Run this before
    /api/scoring/run so overall_score reflects fresh wallet_score data."""
    with task_lock("wallet_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a wallet cycle (scheduled or manual) is already running"}
        service = WalletIntelligenceService(db)
        return service.check_all_active()


@router.post("/solana-wallets/run")
def run_solana_wallet_check(db: Session = Depends(get_db)):
    """Manually trigger the Solana extension of MODULE 3 (requires
    SOLANATRACKER_API_KEY). Uses real per-token PnL data from top holders -
    see solana_wallet_service.py docstring for how this differs in kind
    from the EVM version. Writes to the same wallet_score field."""
    with task_lock("solana_wallet_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a Solana wallet cycle (scheduled or manual) is already running"}
        service = SolanaWalletIntelligenceService(db)
        return service.check_all_active()


@router.post("/pool-migration/run")
def run_pool_migration_check(db: Session = Depends(get_db)):
    """Manually trigger the pool migration detector (MODULE 1 extension).
    Re-checks coins whose CURRENT pool looks thin/stale against every
    other pool GeckoTerminal reports for that same token contract, and
    switches pair_address/liquidity/volume/price if a genuinely,
    substantially better pool is found. See pool_migration_service.py
    for the full reasoning."""
    with task_lock("pool_migration_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a pool migration cycle (scheduled or manual) is already running"}
        service = PoolMigrationService(db)
        return service.run_cycle()


@router.post("/youtube/run")
def run_youtube_scan(db: Session = Depends(get_db)):
    """Manually trigger the YouTube extension of MODULE 2 (requires
    YOUTUBE_API_KEY). Feeds the same SocialPost/community_score/
    narrative_score pipeline Telegram and RSS already feed."""
    with task_lock("youtube_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a YouTube cycle (scheduled or manual) is already running"}
        service = YouTubeScannerService(db)
        return service.scan_cycle()


@router.post("/scoring/run")
def run_scoring(db: Session = Depends(get_db)):
    """Manually trigger a scoring pass synchronously."""
    with task_lock("scoring_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a scoring cycle (scheduled or manual) is already running"}
        service = ScoringService(db)
        return service.score_all_active()


@router.post("/narratives/run")
def run_narrative_scan(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 2/7 narrative-scan pass synchronously
    (requires at least one of Reddit/CryptoPanic/X configured, plus
    ANTHROPIC_API_KEY for the AI analysis step). Run this before
    /api/scoring/run so overall_score reflects fresh narrative_score data."""
    with task_lock("narrative_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a narrative cycle (scheduled or manual) is already running"}
        service = NarrativeScannerService(db)
        return service.check_all_active()


@router.post("/community/run")
def run_community_analysis(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 4 community-analysis pass synchronously.
    Analyzes SocialPost rows already collected by /api/narratives/run - run
    that first, then this, then /api/scoring/run so overall_score reflects
    fresh community_score data."""
    with task_lock("community_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a community cycle (scheduled or manual) is already running"}
        service = CommunityIntelligenceService(db)
        return service.check_all_active()


@router.post("/alerts/run")
def run_alert_check(db: Session = Depends(get_db)):
    """Manually trigger a MODULE 9 alert-check pass synchronously.
    Run this after /api/scoring/run so there's fresh history to diff against."""
    with task_lock("alert_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "an alert cycle (scheduled or manual) is already running"}
        service = AlertService(db)
        return service.check_all_active()


@router.post("/alerts/cleanup")
def run_alert_cleanup(retention_days: int | None = None, db: Session = Depends(get_db)):
    """Manually trigger alert cleanup - permanently deletes alerts older
    than the retention window (default: ALERT_RETENTION_DAYS, 30 days).
    Pass a different retention_days to test with a shorter window."""
    with task_lock("alert_cleanup_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "an alert cleanup cycle (scheduled or manual) is already running"}
        service = AlertService(db)
        return service.cleanup_old_alerts(retention_days)
