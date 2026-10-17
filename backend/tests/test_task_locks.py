from unittest.mock import patch

from app.workers.locks import task_lock


def test_lock_acquired_when_free():
    with patch("app.workers.locks._redis_client") as mock_redis:
        mock_redis.set.return_value = True  # SET NX succeeded - lock was free
        with task_lock("test_task") as acquired:
            assert acquired is True
        mock_redis.delete.assert_called_once_with("task_lock:test_task")


def test_lock_skipped_when_already_held():
    with patch("app.workers.locks._redis_client") as mock_redis:
        mock_redis.set.return_value = False  # SET NX failed - someone else holds it
        with task_lock("test_task") as acquired:
            assert acquired is False
        # Never held the lock, so must never try to release someone else's
        mock_redis.delete.assert_not_called()


def test_lock_released_even_if_task_body_raises():
    with patch("app.workers.locks._redis_client") as mock_redis:
        mock_redis.set.return_value = True
        try:
            with task_lock("test_task") as acquired:
                assert acquired is True
                raise ValueError("simulated task failure")
        except ValueError:
            pass
        # Even though the task body raised, the lock must still be released -
        # otherwise every subsequent run of this task would be permanently
        # skipped until the TTL happens to expire.
        mock_redis.delete.assert_called_once_with("task_lock:test_task")


def test_lock_uses_correct_key_and_ttl():
    with patch("app.workers.locks._redis_client") as mock_redis:
        mock_redis.set.return_value = True
        with task_lock("wallet_cycle"):
            pass
        args, kwargs = mock_redis.set.call_args
        assert args[0] == "task_lock:wallet_cycle"
        assert kwargs.get("nx") is True
        assert kwargs.get("ex") == 1800


def test_lock_release_failure_does_not_raise():
    """If Redis itself is unreachable when releasing, the task shouldn't
    crash on top of whatever already happened - the lock just expires via
    its own TTL instead."""
    with patch("app.workers.locks._redis_client") as mock_redis:
        mock_redis.set.return_value = True
        mock_redis.delete.side_effect = ConnectionError("redis unreachable")
        with task_lock("test_task") as acquired:
            assert acquired is True
        # No exception should propagate out of the context manager despite
        # the delete() call failing internally.
