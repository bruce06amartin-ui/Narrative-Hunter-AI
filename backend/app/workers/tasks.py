import logging

from app.config import settings
from app.database import SessionLocal
from app.services.alert_service import AlertService
from app.services.community_service import CommunityIntelligenceService
from app.services.discovery_service import DiscoveryService
from app.services.narrative_scanner_service import NarrativeScannerService
from app.services.paper_trading_service import PaperTradingService
from app.services.pool_migration_service import PoolMigrationService
from app.services.risk_service import RiskService
from app.services.solana_wallet_service import SolanaWalletIntelligenceService
from app.services.trend_service import TrendDetectionService
from app.services.youtube_scanner_service import YouTubeScannerService
from app.services.scoring_service import ScoringService
from app.services.wallet_service import WalletIntelligenceService
from app.workers.celery_app import celery_app
from app.workers.locks import task_lock

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.run_discovery_cycle", bind=True, max_retries=3)
def run_discovery_cycle(self):
    with task_lock("discovery_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous discovery cycle still in progress"}
        db = SessionLocal()
        try:
            service = DiscoveryService(db, networks=settings.discovery_network_list)
            result = service.run_cycle()
            logger.info("Scheduled discovery cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Discovery cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_price_refresh_cycle", bind=True, max_retries=3)
def run_price_refresh_cycle(self):
    with task_lock("price_refresh_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous price refresh cycle still in progress"}
        db = SessionLocal()
        try:
            service = DiscoveryService(db, networks=settings.discovery_network_list)
            result = service.refresh_existing_prices()
            logger.info("Scheduled price refresh cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Price refresh cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_social_reenrichment_cycle", bind=True, max_retries=3)
def run_social_reenrichment_cycle(self):
    with task_lock("social_reenrichment_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous social re-enrichment cycle still in progress"}
        db = SessionLocal()
        try:
            service = DiscoveryService(db, networks=settings.discovery_network_list)
            result = service.re_enrich_missing_social_handles()
            logger.info("Scheduled social re-enrichment cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Social re-enrichment cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_risk_cycle", bind=True, max_retries=3)
def run_risk_cycle(self):
    with task_lock("risk_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous risk cycle still in progress"}
        db = SessionLocal()
        try:
            service = RiskService(db)
            result = service.check_all_active()
            logger.info("Scheduled risk cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Risk cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_trend_cycle", bind=True, max_retries=3)
def run_trend_cycle(self):
    with task_lock("trend_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous trend cycle still in progress"}
        db = SessionLocal()
        try:
            service = TrendDetectionService(db)
            result = service.score_all_active()
            logger.info("Scheduled trend cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Trend cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_wallet_cycle", bind=True, max_retries=3)
def run_wallet_cycle(self):
    with task_lock("wallet_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous wallet cycle still in progress"}
        db = SessionLocal()
        try:
            service = WalletIntelligenceService(db)
            result = service.check_all_active()
            logger.info("Scheduled wallet cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Wallet cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_pool_migration_cycle", bind=True, max_retries=3)
def run_pool_migration_cycle(self):
    with task_lock("pool_migration_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous pool migration cycle still in progress"}
        db = SessionLocal()
        try:
            service = PoolMigrationService(db)
            result = service.run_cycle()
            logger.info("Scheduled pool migration cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Pool migration cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_solana_wallet_cycle", bind=True, max_retries=3)
def run_solana_wallet_cycle(self):
    with task_lock("solana_wallet_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous Solana wallet cycle still in progress"}
        db = SessionLocal()
        try:
            service = SolanaWalletIntelligenceService(db)
            result = service.check_all_active()
            logger.info("Scheduled Solana wallet cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Solana wallet cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_youtube_cycle", bind=True, max_retries=3)
def run_youtube_cycle(self):
    with task_lock("youtube_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous YouTube cycle still in progress"}
        db = SessionLocal()
        try:
            service = YouTubeScannerService(db)
            result = service.scan_cycle()
            logger.info("Scheduled YouTube cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("YouTube cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_narrative_cycle", bind=True, max_retries=3)
def run_narrative_cycle(self):
    with task_lock("narrative_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous narrative cycle still in progress"}
        db = SessionLocal()
        try:
            service = NarrativeScannerService(db)
            result = service.check_all_active()
            logger.info("Scheduled narrative cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Narrative cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_community_cycle", bind=True, max_retries=3)
def run_community_cycle(self):
    with task_lock("community_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous community cycle still in progress"}
        db = SessionLocal()
        try:
            service = CommunityIntelligenceService(db)
            result = service.check_all_active()
            logger.info("Scheduled community cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Community cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_scoring_cycle", bind=True, max_retries=3)
def run_scoring_cycle(self):
    with task_lock("scoring_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous scoring cycle still in progress"}
        db = SessionLocal()
        try:
            service = ScoringService(db)
            result = service.score_all_active()
            logger.info("Scheduled scoring cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Scoring cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_alert_cycle", bind=True, max_retries=3)
def run_alert_cycle(self):
    with task_lock("alert_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous alert cycle still in progress"}
        db = SessionLocal()
        try:
            service = AlertService(db)
            result = service.check_all_active()
            logger.info("Scheduled alert cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Alert cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_alert_cleanup_cycle", bind=True, max_retries=3)
def run_alert_cleanup_cycle(self):
    with task_lock("alert_cleanup_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous alert cleanup cycle still in progress"}
        db = SessionLocal()
        try:
            service = AlertService(db)
            result = service.cleanup_old_alerts()
            logger.info("Scheduled alert cleanup result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Alert cleanup cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()


@celery_app.task(name="app.workers.tasks.run_paper_trading_cycle", bind=True, max_retries=3)
def run_paper_trading_cycle(self):
    with task_lock("paper_trading_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "previous paper trading cycle still in progress"}
        db = SessionLocal()
        try:
            service = PaperTradingService(db)
            result = service.check_all_active()
            logger.info("Scheduled paper trading cycle result: %s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("Paper trading cycle failed")
            raise self.retry(exc=exc, countdown=30)
        finally:
            db.close()
