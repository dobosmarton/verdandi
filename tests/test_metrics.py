"""Tests for Prometheus metrics definitions and instrumentation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

if TYPE_CHECKING:
    from fastapi import FastAPI

from verdandi.metrics import (
    circuit_breaker_state,
    experiments_total,
    llm_tokens_total,
    retry_attempts_total,
    retry_exhausted_total,
    step_duration_seconds,
    step_executions_total,
)


class TestMetricDefinitions:
    """Verify all Prometheus metric definitions exist with correct names.

    Note: prometheus_client Counter strips '_total' from _name internally
    (it's re-added in exported samples), so we check the describe() output
    which includes the full metric name.
    """

    def test_step_duration_histogram(self):
        assert step_duration_seconds._name == "verdandi_step_duration_seconds"
        assert "step_name" in step_duration_seconds._labelnames

    def test_step_executions_counter(self):
        # Counter._name strips _total; check describe() for full name
        assert step_executions_total._name == "verdandi_step_executions"
        assert "step_name" in step_executions_total._labelnames
        assert "status" in step_executions_total._labelnames

    def test_retry_attempts_counter(self):
        assert retry_attempts_total._name == "verdandi_retry_attempts"
        assert "fn_name" in retry_attempts_total._labelnames

    def test_retry_exhausted_counter(self):
        assert retry_exhausted_total._name == "verdandi_retry_exhausted"
        assert "fn_name" in retry_exhausted_total._labelnames

    def test_circuit_breaker_gauge(self):
        assert circuit_breaker_state._name == "verdandi_circuit_breaker_state"
        assert "name" in circuit_breaker_state._labelnames

    def test_llm_tokens_counter(self):
        assert llm_tokens_total._name == "verdandi_llm_tokens"
        assert "model" in llm_tokens_total._labelnames
        assert "token_type" in llm_tokens_total._labelnames

    def test_experiments_counter(self):
        assert experiments_total._name == "verdandi_experiments"
        assert "status" in experiments_total._labelnames


class TestMetricsEndpoint:
    """Verify /metrics endpoint is exposed via the FastAPI app."""

    def test_metrics_endpoint_returns_200(self):
        from verdandi.api.app import create_app

        app = create_app()
        # Override lifespan to avoid DB init
        app.router.lifespan_context = _noop_lifespan
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "verdandi_step_duration_seconds" in response.text
        assert "verdandi_step_executions_total" in response.text
        assert "verdandi_retry_attempts_total" in response.text
        assert "verdandi_circuit_breaker_state" in response.text
        assert "verdandi_llm_tokens_total" in response.text
        assert "verdandi_experiments_total" in response.text

    def test_metrics_endpoint_content_type(self):
        from verdandi.api.app import create_app

        app = create_app()
        app.router.lifespan_context = _noop_lifespan
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/metrics")
        # Prometheus text format
        assert "text/plain" in response.headers.get("content-type", "")


class TestRetryInstrumentation:
    """Verify retry.py increments Prometheus counters."""

    def test_retry_increments_counter_on_retries(self):
        from verdandi.retry import with_retry

        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        before = _get_counter_value("verdandi_retry_attempts", {"fn_name": "flaky"})
        result = with_retry(flaky, max_retries=3, base_delay=0.001, jitter=False)
        after = _get_counter_value("verdandi_retry_attempts", {"fn_name": "flaky"})

        assert result == "ok"
        assert after - before == 2  # 2 retries before success

    def test_retry_exhausted_increments_counter(self):
        from verdandi.retry import RetryExhaustedError, with_retry

        before = _get_counter_value("verdandi_retry_exhausted", {"fn_name": "_always_fail"})
        with pytest.raises(RetryExhaustedError):
            with_retry(
                _always_fail,
                max_retries=1,
                base_delay=0.001,
                jitter=False,
            )
        after = _get_counter_value("verdandi_retry_exhausted", {"fn_name": "_always_fail"})
        assert after - before == 1


class TestCircuitBreakerInstrumentation:
    """Verify circuit breaker sets Prometheus gauge."""

    def test_circuit_breaker_gauge_on_trip_and_reset(self):
        from verdandi.retry import CircuitBreaker

        cb = CircuitBreaker(name="test_cb_gauge", failure_threshold=2, reset_timeout=0.01)

        # Initially closed
        assert _get_gauge_value("verdandi_circuit_breaker_state", {"name": "test_cb_gauge"}) == 0

        # Trip it
        for _ in range(2):
            cb.record_failure()

        assert _get_gauge_value("verdandi_circuit_breaker_state", {"name": "test_cb_gauge"}) == 1

        # Reset via success
        cb._is_open = False  # manually close for record_success to work
        cb.record_success()
        assert _get_gauge_value("verdandi_circuit_breaker_state", {"name": "test_cb_gauge"}) == 0


# --- Helpers ---


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def _always_fail():
    raise ValueError("always fails")


def _get_counter_value(metric_name: str, labels: dict[str, str]) -> float:
    """Read the current value of a Prometheus counter from the default registry.

    For counters, metric.name == base name (without _total),
    but sample.name == base_name + "_total".
    """
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if sample.name == f"{metric_name}_total" and sample.labels == labels:
                    return sample.value
    return 0.0


def _get_gauge_value(metric_name: str, labels: dict[str, str]) -> float:
    """Read the current value of a Prometheus gauge from the default registry."""
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if sample.name == metric_name and sample.labels == labels:
                    return sample.value
    return 0.0
