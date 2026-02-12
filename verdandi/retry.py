"""Exponential backoff retry and circuit breaker utilities."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

import structlog

from verdandi.metrics import (
    circuit_breaker_state,
    retry_attempts_total,
    retry_exhausted_total,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """All retry attempts failed."""


class CircuitOpenError(Exception):
    """Circuit breaker is open — service assumed unavailable."""


def with_retry(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Execute *fn* with exponential backoff retries.

    Uses full jitter (delay * random(0.5, 1.5)) when *jitter* is True
    to prevent thundering herd on concurrent retries.

    Raises RetryExhaustedError after *max_retries* consecutive failures.
    """
    last_exc: Exception | None = None
    fn_label = fn.__name__ if hasattr(fn, "__name__") else "fn"
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retryable as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            retry_attempts_total.labels(fn_name=fn_label).inc()
            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random())
            logger.warning(
                "Retry attempt",
                attempt=attempt + 1,
                max_retries=max_retries,
                fn=fn_label,
                delay_s=round(delay, 2),
                error=str(exc),
            )
            time.sleep(delay)
    retry_exhausted_total.labels(fn_name=fn_label).inc()
    raise RetryExhaustedError(f"Failed after {max_retries + 1} attempts") from last_exc


async def async_with_retry(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Async variant of with_retry using asyncio.sleep."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            delay = min(base_delay * (2**attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random())
            logger.warning(
                "Async retry attempt",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_s=round(delay, 2),
                error=str(exc),
            )
            await asyncio.sleep(delay)
    raise RetryExhaustedError(f"Failed after {max_retries + 1} attempts") from last_exc


@dataclass
class CircuitBreaker:
    """Per-service circuit breaker.

    Trips after *failure_threshold* consecutive failures.
    Auto-resets after *reset_timeout* seconds.
    """

    name: str
    failure_threshold: int = 5
    reset_timeout: float = 60.0

    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _is_open: bool = field(default=False, init=False, repr=False)

    @property
    def is_open(self) -> bool:
        if self._is_open and (time.time() - self._last_failure_time) > self.reset_timeout:
            logger.info("Circuit breaker auto-reset", breaker=self.name)
            self._is_open = False
            self._failure_count = 0
            circuit_breaker_state.labels(name=self.name).set(0)
        return self._is_open

    def record_success(self) -> None:
        self._failure_count = 0
        self._is_open = False
        circuit_breaker_state.labels(name=self.name).set(0)

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            logger.warning(
                "Circuit breaker tripped",
                breaker=self.name,
                failures=self._failure_count,
            )
            self._is_open = True
            circuit_breaker_state.labels(name=self.name).set(1)

    def call(self, fn: Callable[[], T]) -> T:
        """Execute *fn* if the circuit is closed. Raises CircuitOpenError otherwise."""
        if self.is_open:
            raise CircuitOpenError(f"Circuit breaker '{self.name}' is open")
        try:
            result = fn()
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise
