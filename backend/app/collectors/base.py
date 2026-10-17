import logging
import threading
import time
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Minimum seconds between requests to a given host, applied across ALL
# callers collectively (not per-call-site). This exists because a single
# discovery cycle can hit the same host many times - e.g. GeckoTerminal is
# called once per network for `new_pools` AND once per newly-discovered coin
# for social-handle enrichment, all sharing the same ~30 req/min free-tier
# limit. Throttling per call-site alone wouldn't catch that combined load;
# this tracks the actual wall-clock gap between requests to each host,
# regardless of which collector or code path is making them.
_MIN_INTERVAL_SECONDS = {
    "api.geckoterminal.com": 2.2,   # ~27 req/min, safely under the ~30/min free limit
    "api.gopluslabs.io": 0.5,        # conservative gap - called once per coin per risk cycle
    "api.etherscan.io": 0.25,        # Etherscan's free tier is ~5 req/sec, this stays well under
    "api.dexscreener.com": 0.2,      # generous free tier (~300/min) but avoid bursty spikes
    "data.solanatracker.io": 1.0,    # no documented per-second limit found - conservative default pacing
    "www.googleapis.com": 0.5,       # YouTube Data API - no documented per-second limit found, conservative pacing
    "api.rugcheck.xyz": 0.5,          # no documented per-second limit found - conservative default pacing
}
_last_request_time: dict[str, float] = {}
_throttle_lock = threading.Lock()


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    min_interval = _MIN_INTERVAL_SECONDS.get(host)
    if not min_interval:
        return
    with _throttle_lock:
        last = _last_request_time.get(host, 0.0)
        wait = min_interval - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_time[host] = time.time()


class CollectorHTTPError(Exception):
    """Raised when a collector's upstream API call fails after retries."""


def _is_retryable_error(exception: BaseException) -> bool:
    """Only retry genuinely transient failures: network-level errors
    (timeouts, connection issues) and 5xx server errors. A 4xx client
    error (404 not found, 400 bad request, 401 unauthorized, etc.) will
    NEVER succeed no matter how many times the exact same request is
    retried - the request itself is what's wrong, not a transient
    condition. Found via real production logs: a 404 "token not found"
    was being retried 3 times before finally failing, needlessly tripling
    request cost against tightly-budgeted free-tier APIs like Solana
    Tracker (2,500/month) where every wasted request directly eats into
    an already-tight ceiling."""
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code >= 500
    return isinstance(exception, httpx.HTTPError)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_error),
)
def _get_with_retry(url: str, params: dict | None, headers: dict | None) -> dict:
    _throttle(url)
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=headers)
        if resp.status_code >= 400:
            logger.warning("Collector GET %s failed: %s %s", url, resp.status_code, resp.text[:300])
            resp.raise_for_status()
        return resp.json()


def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    """GET a URL and return parsed JSON, retrying transient failures with
    exponential backoff. Raises CollectorHTTPError (not the raw httpx
    exception) once retries are exhausted, so every collector's existing
    `except CollectorHTTPError:` handling actually works.

    MAJOR BUG FIXED HERE: CollectorHTTPError was defined but never
    actually raised anywhere - every collector across the whole project
    (9 files) had an `except CollectorHTTPError:` block that could NEVER
    catch anything, since the real exception (httpx.HTTPStatusError) was
    propagating straight past it. This meant every "graceful no-data"
    path was dead code: a routine 404 (a coin simply not being indexed by
    an API, an entirely normal outcome) always escaped all the way up to
    the outer per-coin exception handler in each service instead of being
    handled where it was meant to be. The concrete, measurable
    consequence: a coin whose "no data" case never completes gracefully
    also never gets its checked_at timestamp recorded, so it can NEVER
    rotate out of the bounded-recheck "due" pool - it gets retried every
    single cycle, forever, burning through tightly-budgeted free-tier
    APIs (like Solana Tracker's 2,500/month) on the same permanently
    unindexed coins instead of ever making progress on new ones. Found by
    reading real production logs showing the exact same 3 coins stuck in
    the "due" list across consecutive cycles."""
    try:
        return _get_with_retry(url, params, headers)
    except httpx.HTTPStatusError as e:
        raise CollectorHTTPError(f"{e.response.status_code} for {url}: {e.response.text[:300]}") from e
    except httpx.HTTPError as e:
        raise CollectorHTTPError(f"Network error for {url}: {e}") from e


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_error),
)
def _post_with_retry(url: str, json_body: dict, headers: dict | None) -> dict | None:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=json_body, headers=headers)
        if resp.status_code >= 400:
            logger.warning("POST %s failed: %s %s", url, resp.status_code, resp.text[:300])
            resp.raise_for_status()
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None


def post_json(url: str, json_body: dict, headers: dict | None = None) -> dict | None:
    """POST a JSON body and return parsed JSON if the response has a body,
    else None. Used both by collectors and by MODULE 9 alert channels
    (Discord/Telegram webhooks). Same CollectorHTTPError-wrapping fix as
    get_json above - see its docstring for the full explanation."""
    try:
        return _post_with_retry(url, json_body, headers)
    except httpx.HTTPStatusError as e:
        raise CollectorHTTPError(f"{e.response.status_code} for {url}: {e.response.text[:300]}") from e
    except httpx.HTTPError as e:
        raise CollectorHTTPError(f"Network error for {url}: {e}") from e


class BaseCollector:
    """Common interface every discovery/enrichment collector implements."""

    name: str = "base"

    def discover(self) -> list[dict]:
        """Return a list of normalized coin dicts (see NormalizedCoin fields
        in dexscreener.py/geckoterminal.py docstrings). Must not raise on a
        single bad item — log and skip it instead so one bad record doesn't
        kill a whole polling cycle."""
        raise NotImplementedError
