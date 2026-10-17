from celery import Celery
from celery.schedules import schedule

from app.config import settings

celery_app = Celery(
    "narrative_hunter",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Real bug found via live diagnosis (Celery `inspect active` showing
    # a task with redelivered=True, still running many hours later):
    # Redis's DEFAULT visibility_timeout is 3600s (1 hour), but a full
    # price-refresh pass at current scale (~7,500 active coins, batched
    # 30/call with real rate-limit pacing - see
    # discovery_service.py/refresh_existing_prices docstring) genuinely
    # takes closer to 4.5-5 hours. After that first hour, Redis assumed
    # the still-legitimately-running task was lost and redelivered it to
    # a fresh worker slot - repeating roughly every hour, wasting worker
    # capacity on redundant redeliveries (each one correctly self-skips
    # via task_lock, so no duplicate work happened, but it's still
    # noise this project has now outgrown). Set comfortably above the
    # realistic worst case, with real margin for further coin growth.
    broker_transport_options={"visibility_timeout": 21600},  # 6 hours
)

celery_app.conf.beat_schedule = {
    "run-discovery-cycle": {
        "task": "app.workers.tasks.run_discovery_cycle",
        "schedule": schedule(run_every=settings.discovery_interval_seconds),
    },
    "run-price-refresh-cycle": {
        "task": "app.workers.tasks.run_price_refresh_cycle",
        "schedule": schedule(run_every=settings.price_refresh_interval_seconds),
    },
    "run-social-reenrichment-cycle": {
        "task": "app.workers.tasks.run_social_reenrichment_cycle",
        "schedule": schedule(run_every=settings.social_reenrichment_interval_seconds),
    },
    "run-risk-cycle": {
        "task": "app.workers.tasks.run_risk_cycle",
        "schedule": schedule(run_every=settings.risk_interval_seconds),
    },
    "run-trend-cycle": {
        "task": "app.workers.tasks.run_trend_cycle",
        "schedule": schedule(run_every=settings.trend_interval_seconds),
    },
    "run-wallet-cycle": {
        "task": "app.workers.tasks.run_wallet_cycle",
        "schedule": schedule(run_every=settings.wallet_interval_seconds),
    },
    "run-solana-wallet-cycle": {
        "task": "app.workers.tasks.run_solana_wallet_cycle",
        "schedule": schedule(run_every=settings.solana_wallet_interval_seconds),
    },
    "run-pool-migration-cycle": {
        "task": "app.workers.tasks.run_pool_migration_cycle",
        "schedule": schedule(run_every=settings.pool_migration_interval_seconds),
    },
    "run-youtube-cycle": {
        "task": "app.workers.tasks.run_youtube_cycle",
        "schedule": schedule(run_every=settings.youtube_interval_seconds),
    },
    "run-narrative-cycle": {
        "task": "app.workers.tasks.run_narrative_cycle",
        "schedule": schedule(run_every=settings.narrative_interval_seconds),
    },
    "run-community-cycle": {
        "task": "app.workers.tasks.run_community_cycle",
        "schedule": schedule(run_every=settings.community_interval_seconds),
    },
    "run-scoring-cycle": {
        "task": "app.workers.tasks.run_scoring_cycle",
        "schedule": schedule(run_every=settings.scoring_interval_seconds),
    },
    "run-alert-cycle": {
        "task": "app.workers.tasks.run_alert_cycle",
        "schedule": schedule(run_every=settings.alert_interval_seconds),
    },
    "run-alert-cleanup-cycle": {
        "task": "app.workers.tasks.run_alert_cleanup_cycle",
        "schedule": schedule(run_every=settings.alert_cleanup_interval_seconds),
    },
    "run-paper-trading-cycle": {
        "task": "app.workers.tasks.run_paper_trading_cycle",
        "schedule": schedule(run_every=settings.paper_trading_interval_seconds),
    },
}
