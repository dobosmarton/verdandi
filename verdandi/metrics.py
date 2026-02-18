"""Prometheus metric definitions for the Verdandi pipeline."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- Step execution ---

step_duration_seconds = Histogram(
    "verdandi_step_duration_seconds",
    "Time spent executing a pipeline step",
    labelnames=["step_name"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

step_executions_total = Counter(
    "verdandi_step_executions_total",
    "Total pipeline step executions",
    labelnames=["step_name", "status"],
)

# --- Retry ---

retry_attempts_total = Counter(
    "verdandi_retry_attempts_total",
    "Total retry attempts across all steps",
    labelnames=["fn_name"],
)

retry_exhausted_total = Counter(
    "verdandi_retry_exhausted_total",
    "Total times retries were exhausted",
    labelnames=["fn_name"],
)

# --- Circuit breaker ---

circuit_breaker_state = Gauge(
    "verdandi_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
    labelnames=["name"],
)

# --- LLM tokens ---

llm_tokens_total = Counter(
    "verdandi_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=["model", "token_type"],
)

# --- Agent Council ---

council_votes_total = Counter(
    "verdandi_council_votes_total",
    "Council votes by provider and decision",
    labelnames=["provider", "decision"],
)

council_evaluations_total = Counter(
    "verdandi_council_evaluations_total",
    "Council evaluations by final decision",
    labelnames=["decision", "num_providers"],
)

council_early_exits_total = Counter(
    "verdandi_council_early_exits_total",
    "Council evaluations that short-circuited via first-two agreement",
    labelnames=["decision"],
)

# --- Experiments ---

experiments_total = Counter(
    "verdandi_experiments_total",
    "Total experiments created or transitioned",
    labelnames=["status"],
)
