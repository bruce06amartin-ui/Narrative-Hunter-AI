import httpx
import pytest
from unittest.mock import patch, MagicMock

from app.collectors.base import get_json, _is_retryable_error, CollectorHTTPError


def _make_response(status_code, text="error"):
    request = httpx.Request("GET", "https://example.com/test")
    return httpx.Response(status_code=status_code, text=text, request=request)


def test_is_retryable_error_404_is_not_retryable():
    resp = _make_response(404)
    exc = httpx.HTTPStatusError("not found", request=resp.request, response=resp)
    assert _is_retryable_error(exc) is False


def test_is_retryable_error_400_is_not_retryable():
    resp = _make_response(400)
    exc = httpx.HTTPStatusError("bad request", request=resp.request, response=resp)
    assert _is_retryable_error(exc) is False


def test_is_retryable_error_401_is_not_retryable():
    resp = _make_response(401)
    exc = httpx.HTTPStatusError("unauthorized", request=resp.request, response=resp)
    assert _is_retryable_error(exc) is False


def test_is_retryable_error_500_is_retryable():
    resp = _make_response(500)
    exc = httpx.HTTPStatusError("server error", request=resp.request, response=resp)
    assert _is_retryable_error(exc) is True


def test_is_retryable_error_503_is_retryable():
    resp = _make_response(503)
    exc = httpx.HTTPStatusError("service unavailable", request=resp.request, response=resp)
    assert _is_retryable_error(exc) is True


def test_is_retryable_error_network_timeout_is_retryable():
    exc = httpx.TimeoutException("timed out")
    assert _is_retryable_error(exc) is True


def test_is_retryable_error_connection_error_is_retryable():
    exc = httpx.ConnectError("connection refused")
    assert _is_retryable_error(exc) is True


def test_get_json_404_fails_after_exactly_one_attempt():
    call_count = {"n": 0}

    def fake_get(*args, **kwargs):
        call_count["n"] += 1
        return _make_response(404, text='{"error": "not found"}')

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(side_effect=fake_get)

    with patch("app.collectors.base.httpx.Client", return_value=mock_client), \
         patch("app.collectors.base._throttle"):
        with pytest.raises(CollectorHTTPError):
            get_json("https://example.com/missing-token")

    assert call_count["n"] == 1


def test_get_json_500_retries_up_to_three_times():
    """A genuinely transient server error SHOULD still retry - confirming
    the fix didn't accidentally disable retries entirely, only for
    non-retryable 4xx errors.

    NOTE: this test takes a few real seconds to run - tenacity manages its
    own internal sleep timing for the exponential backoff between
    retries, separate from this module's own time.sleep import, so it
    isn't mocked away here. The assertion is still correct, just not
    instant."""
    call_count = {"n": 0}

    def fake_get(*args, **kwargs):
        call_count["n"] += 1
        return _make_response(500, text="server error")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(side_effect=fake_get)

    with patch("app.collectors.base.httpx.Client", return_value=mock_client), \
         patch("app.collectors.base._throttle"):
        with pytest.raises(CollectorHTTPError):
            get_json("https://example.com/flaky-endpoint")

    assert call_count["n"] == 3


def test_get_json_wraps_httpx_error_with_original_status_code_in_message():
    """The CollectorHTTPError message should preserve the real status code
    and response body, so a caller (or a log line) can still see what
    actually went wrong, not just a generic wrapper message."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=_make_response(404, text='{"error":"Token not found"}'))

    with patch("app.collectors.base.httpx.Client", return_value=mock_client), \
         patch("app.collectors.base._throttle"):
        with pytest.raises(CollectorHTTPError) as exc_info:
            get_json("https://example.com/missing-token")

    assert "404" in str(exc_info.value)
    assert "Token not found" in str(exc_info.value)
