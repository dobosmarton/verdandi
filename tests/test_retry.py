"""Tests for retry and circuit breaker utilities."""

from __future__ import annotations

import pytest

from verdandi.retry import CircuitBreaker, CircuitOpenError, RetryExhaustedError, with_retry


class TestWithRetry:
    def test_succeeds_first_try(self):
        result = with_retry(lambda: 42, max_retries=3, base_delay=0.01)
        assert result == 42

    def test_succeeds_after_failures(self):
        attempts = {"count": 0}

        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("not yet")
            return "ok"

        result = with_retry(flaky, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert attempts["count"] == 3

    def test_exhausted_raises(self):
        def always_fail():
            raise ValueError("fail")

        with pytest.raises(RetryExhaustedError, match="Failed after 4 attempts"):
            with_retry(always_fail, max_retries=3, base_delay=0.01)

    def test_non_retryable_raises_immediately(self):
        attempts = {"count": 0}

        def fail_type_error():
            attempts["count"] += 1
            raise TypeError("bad type")

        with pytest.raises(TypeError):
            with_retry(
                fail_type_error,
                max_retries=3,
                base_delay=0.01,
                retryable=(ValueError,),
            )
        assert attempts["count"] == 1  # No retries

    def test_jitter_varies_delay(self):
        """Verify jitter produces non-deterministic delays by running multiple retries."""
        # This is a smoke test — we just verify it doesn't crash with jitter=True
        attempts = {"count": 0}

        def fail_twice():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("retry")
            return "done"

        result = with_retry(fail_twice, max_retries=3, base_delay=0.01, jitter=True)
        assert result == "done"

    def test_no_jitter(self):
        attempts = {"count": 0}

        def fail_once():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise ValueError("retry")
            return "done"

        result = with_retry(fail_once, max_retries=3, base_delay=0.01, jitter=False)
        assert result == "done"


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.is_open is False

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker(name="test")
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.is_open is False

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open is True

    def test_open_circuit_raises(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open is True
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: 42)

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)

        # Two failures
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # One success resets
        cb.call(lambda: "ok")
        assert cb.is_open is False

        # Need 3 more failures to trip
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.is_open is False  # Still only 2 after reset

    def test_auto_reset_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.0)

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb._is_open is True
        # With reset_timeout=0, should auto-reset on next is_open check
        assert cb.is_open is False
