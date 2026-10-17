import time

from app.collectors.base import _throttle, _last_request_time, _MIN_INTERVAL_SECONDS


def test_throttle_enforces_minimum_interval():
    host_url = "https://api.geckoterminal.com/api/v2/some/path"
    _last_request_time.pop("api.geckoterminal.com", None)  # reset state from any prior test

    start = time.monotonic()
    _throttle(host_url)  # first call - should not wait, no prior recorded request
    first_elapsed = time.monotonic() - start

    _throttle(host_url)  # second call - should wait ~_MIN_INTERVAL_SECONDS
    second_elapsed = time.monotonic() - start

    min_interval = _MIN_INTERVAL_SECONDS["api.geckoterminal.com"]
    assert first_elapsed < 0.1, "first call should not be throttled"
    assert second_elapsed >= min_interval * 0.9, "second call should have waited close to the minimum interval"


def test_throttle_ignores_unconfigured_hosts():
    start = time.monotonic()
    _throttle("https://api.dexscreener.com/latest/dex/pairs/eth/0xabc")
    _throttle("https://api.dexscreener.com/latest/dex/pairs/eth/0xabc")
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, "hosts with no configured throttle should never wait"
