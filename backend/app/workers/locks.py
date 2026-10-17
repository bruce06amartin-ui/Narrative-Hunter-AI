"""
Task overlap protection.

At small scale, every Celery Beat cycle finishes well within its own
scheduled interval. At real scale this stops being true - e.g. wallet
intelligence makes one throttled Etherscan call per active EVM coin
(see collectors/base.py's per-host throttle); with hundreds of EVM coins,
a single wallet cycle can genuinely take longer than
WALLET_INTERVAL_SECONDS. Without protection, Celery Beat happily dispatches
a second overlapping instance of the same task - wasting API calls,
creating unnecessary database lock contention on the same rows, and (before
tonight's per-coin commit fixes) would have been a real correctness risk on
top of the wasted work.

This uses a simple Redis SET-if-not-exists lock, not a queue or semaphore:
if a task can't acquire its own lock, it just skips this run entirely and
logs why, rather than blocking or queueing - the next scheduled attempt
will pick up wherever the currently-running instance leaves off. The lock
has a generous TTL as a safety net: if a worker process crashes while
holding a lock (without reaching the `finally` release), the lock expires
on its own after LOCK_TTL_SECONDS rather than permanently blocking every
future run of that task.
"""

import logging
from contextlib import contextmanager

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client = redis.from_url(settings.redis_url)

LOCK_TTL_SECONDS = 21600  # 6 hour ceiling
# Real bug found via live diagnosis (Celery `inspect active` showing
# THREE simultaneous, non-redelivered instances of run_price_refresh_cycle
# all running concurrently): the original 1800s (30 min) TTL was genuinely
# generous when this was written, but a full price-refresh pass at
# current scale (~7,500 active coins, real rate-limit pacing - see
# discovery_service.py/refresh_existing_prices) now takes ~4.6 hours. The
# lock was silently expiring roughly every 30 minutes while the original
# task was still legitimately working, letting each new scheduled attempt
# acquire a fresh lock and start a fully concurrent duplicate instance -
# wasting worker slots and API quota on redundant, overlapping work. Same
# underlying root cause as the Celery broker visibility_timeout fix
# (celery_app.py) - a fixed timeout that was fine at the original ~1,700
# coin design scale became genuinely too short as the project grew.
# Matched to the same 6-hour value there for consistency.


@contextmanager
def task_lock(task_name: str):
    """Usage:
        with task_lock("wallet_cycle") as acquired:
            if not acquired:
                return {"skipped": True, "reason": "previous run still in progress"}
            ... do the actual work ...
    """
    lock_key = f"task_lock:{task_name}"
    acquired = False
    try:
        acquired = bool(_redis_client.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS))
        if not acquired:
            logger.info("Skipping %s - a previous run is still in progress (lock held)", task_name)
        yield acquired
    finally:
        if acquired:
            try:
                _redis_client.delete(lock_key)
            except Exception:  # noqa: BLE001 - releasing the lock failing shouldn't crash the task
                logger.exception("Failed to release lock for %s (will expire via TTL)", task_name)
