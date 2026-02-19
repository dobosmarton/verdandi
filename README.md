# Verdandi

**Autonomous product validation factory.** Verdandi discovers product ideas, validates them through market research, builds landing pages, deploys them, and monitors conversion metrics to make go/no-go decisions — all autonomously.

Named after the Norse Norn of the present, Verdandi turns "what is happening right now" in the market into validated product opportunities.

## How It Works

Verdandi runs a sequential 11-step pipeline for each product experiment:

```
Step 0:  Idea Discovery      → Find promising product ideas from market signals
Step 1:  Deep Research        → Multi-turn market research with LLM gap analysis (Tavily, Serper, Exa, Perplexity, HN, Twitter/X)
Step 2:  Pre-Build Scoring    → Quantified GO / NO_GO / ITERATE decision
Step 3:  MVP Definition       → Product spec, features, pricing, domain suggestions
Step 4:  Landing Page Gen     → HTML + Tailwind CSS from template + LLM-generated copy
Step 5:  Human Review         → Optional approval checkpoint before spending money
Step 6:  Domain Purchase      → Register domain via Porkbun API
Step 7:  Deploy               → Deploy to Cloudflare Pages
Step 8:  Analytics Setup      → Inject Umami tracking script
Step 9:  Distribution         → Post to LinkedIn, X, Reddit, Bluesky
Step 10: Monitor              → Poll analytics, calculate conversion, decide GO/ITERATE/NO_GO
```

Each step produces a validated Pydantic model consumed by the next — `IdeaCandidate` feeds into `MarketResearch`, which feeds into `PreBuildScore` (the first gate — NO_GO halts the pipeline). Approved experiments continue through `MVPDefinition` and `LandingPageContent` into `DeploymentResult` (shared across Steps 6-8), then `DistributionResult`, and finally `ValidationReport` (the second gate — GO/ITERATE/NO_GO). Agents read prior outputs via `ctx.prior_results.get_typed("step_name", Model)` — the orchestrator pre-loads all step results before invoking each agent, enforcing a clean separation where agents never access the database directly.

Results are checkpointed to SQLite after every step, so the pipeline can resume from where it left off if interrupted.

## Architecture

```
              Local                          Remote
┌──────────────────────┐        ┌──────────────────────────────┐
│  CLI (Click)         │───or──▶│  CLI ──(httpx)──▶ API Server │
│  ├─ Database (local) │        │                              │
│  └─ ApiClient (http) │        └──────────────────────────────┘
├──────────────────────┴──────────────────────────────┐
│  API Server (FastAPI + Uvicorn)                     │
├─────────────────────────────────────────────────────┤
│              PipelineRunner (orchestrator)           │
│         Step Registry  ·  Retry + Circuit Breaker   │
├─────────────────────────────────────────────────────┤
│  Steps 0–10            │  PydanticAI Agents (LLM)   │
├─────────────────────────────────────────────────────┤
│  Database (SQLAlchemy ORM)  │  API Clients (httpx)  │
├─────────────────────────────────────────────────────┤
│  SQLite + WAL mode     │  Huey Task Queue           │
└─────────────────────────────────────────────────────┘
```

Key design decisions:

- **No agent framework** — Custom Python orchestrator with step registry. Frameworks add debugging complexity dangerous for unattended autonomous operation.
- **PydanticAI** for LLM-facing steps (structured outputs via `Agent` + `output_type` + streaming).
- **SQLAlchemy 2.0+ ORM** for all database access. Frozen Pydantic models for domain objects, separate ORM models for persistence.
- **SQLite + WAL mode** for state storage. Huey task queue with a separate SQLite broker for background jobs.
- **Template-fill for landing pages** — Pre-built HTML + Tailwind templates with `{{TOKEN}}` placeholders. Near-zero failure rate vs. ~15% breakage from LLM-generated full HTML.
- **structlog** with correlation IDs for request tracing across pipeline steps.
- **Agent Council** for multi-model scoring — When enabled (`COUNCIL_ENABLED=true`), Step 2 runs the same scoring prompt across Anthropic, OpenAI, and Google models. Uses a quorum-based early-exit strategy: a random initial quorum of `N//2+1` providers runs in parallel; if consensus is locked (majority can no longer be overturned), remaining providers are skipped. Otherwise reserves are added one-by-one until the decision is final. Votes are aggregated via majority rule with median component scores.
- **Multi-turn research** — Step 1 performs iterative collection: a broad initial pass across all providers, then an LLM gap analysis scores confidence across 5 dimensions (pain severity, market size, competitors, demand evidence, willingness to pay). If evidence is weak, targeted follow-up queries run through Tavily + Perplexity only. Stops early when confidence exceeds the threshold, no queries are generated, or follow-ups return no new data.
- **Pluggable research providers** via `ResearchProviderPort` protocol — 6 providers (Tavily, Serper, Exa, Perplexity, HN Algolia, SocialData) run in parallel. Adding a new source requires only a client and a provider class.
- **Long-term memory** via Qdrant vector DB — Optional semantic dedup and memory using all-MiniLM-L6-v2 embeddings (384-dim). Degrades gracefully: Qdrant -> SQLite Python-loop fallback -> fingerprint-only.

## Quick Start

### Prerequisites

- Python 3.11+
- An Anthropic API key

### Installation

```bash
# Clone the repository
git clone <your-repository-url>
cd verdandi

# Install in development mode
pip install -e ".[dev]"

# Optional: install interactive TUI
pip install -e ".[dev,tui]"

# Copy and configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY at minimum
```

### First Run (Dry-Run Mode)

Dry-run mode uses mock data for all external services, so you can test the full pipeline without any API keys:

```bash
# Discover 3 product ideas (mock data)
verdandi discover --max-ideas 3 --dry-run -v

# List created experiments
verdandi ls

# Run the full pipeline for experiment #2
verdandi run 2 --dry-run -v

# Inspect results
verdandi inspect 2
verdandi inspect 2 --log
verdandi inspect 2 --step scoring

# Or browse experiments interactively
verdandi tui
```

### Real Pipeline Run

Once API keys are configured:

```bash
# Verify which API keys are set
verdandi check

# Discover ideas using real research
verdandi discover --max-ideas 3

# Review and approve an experiment
verdandi review 2 --approve --notes "Looks promising"

# Run the pipeline
verdandi run 2
```

## Configuration

All configuration is via environment variables (loaded from `.env`):

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |

### Research APIs (Optional)

| Variable | Description | Free Tier |
|----------|-------------|-----------|
| `TAVILY_API_KEY` | Primary AI search | 1,000 searches/month |
| `SERPER_API_KEY` | Google SERP data | 2,500 queries (one-time) |
| `EXA_API_KEY` | Neural/semantic search | $10 one-time credit |
| `PERPLEXITY_API_KEY` | AI-synthesized research | ~$0.006/query |
| `SOCIALDATA_API_KEY` | Twitter/X social signals | Paid (per query) |

### Deployment APIs (Optional)

| Variable | Description |
|----------|-------------|
| `PORKBUN_API_KEY` | Domain registration |
| `PORKBUN_SECRET_KEY` | Porkbun secret key |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Pages deployment |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

### Analytics & Email (Optional)

| Variable | Description |
|----------|-------------|
| `UMAMI_URL` | Self-hosted Umami URL |
| `UMAMI_API_KEY` | Umami API key |
| `EMAILOCTOPUS_API_KEY` | Email collection (2,500 free subs) |

### Social Distribution (Optional)

| Variable | Description |
|----------|-------------|
| `TWITTER_BEARER_TOKEN` | X/Twitter posting |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn posting |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit posting |
| `BLUESKY_HANDLE` / `BLUESKY_APP_PASSWORD` | Bluesky posting |

### Pipeline Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUIRE_HUMAN_REVIEW` | `true` | Pause pipeline at Step 5 for approval |
| `MAX_RETRIES` | `3` | Max retry attempts per step |
| `SCORE_GO_THRESHOLD` | `70` | Minimum score for GO decision (0-100) |
| `RESEARCH_MAX_ROUNDS` | `2` | Max research collection rounds (1 = single-pass, 2 = initial + follow-up) |
| `RESEARCH_CONFIDENCE_THRESHOLD` | `0.7` | Skip follow-up rounds if gap analysis confidence >= this |
| `LLM_MODEL` | `claude-sonnet-4-5-20250929` | Claude model for reasoning |
| `LLM_MAX_TOKENS` | *(unset — 16384 fallback)* | Max output tokens per LLM call. Leave unset for generous default |
| `LLM_TEMPERATURE` | `0.7` | LLM temperature |
| `DATA_DIR` | `./data` | Directory for SQLite databases |
| `VERDANDI_API_URL` | *(empty)* | Remote API URL — if set, CLI talks to HTTP instead of local SQLite |

### Agent Council (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `COUNCIL_ENABLED` | `false` | Enable multi-model scoring panel |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key for council voting |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model for council |
| `GOOGLE_API_KEY` | *(empty)* | Google AI API key for council voting |
| `GOOGLE_MODEL` | `gemini-2.5-flash` | Google model for council |

### Research Cache (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | *(empty)* | Redis connection URL. If empty, caching is disabled |
| `RESEARCH_CACHE_TTL_HOURS` | `24` | Cache TTL for research API results |

### Long-Term Memory (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | *(empty)* | Qdrant vector DB URL. If empty, falls back to SQLite/fingerprint dedup |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key |

### Monitoring Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_EMAIL_SIGNUP_GO` | `10.0` | Email signup rate % for GO signal |
| `MONITOR_EMAIL_SIGNUP_NOGO` | `3.0` | Email signup rate % below = NO_GO |
| `MONITOR_BOUNCE_RATE_MAX` | `80.0` | Max acceptable bounce rate % |
| `MONITOR_MIN_VISITORS` | `200` | Minimum visitors before deciding |

## CLI Reference

```
verdandi                                         # Show help
verdandi discover [--max-ideas N] [--strategy auto|disruption|moonshot] [--dry-run]
verdandi run <ID> [--dry-run] [--stop-after N]   # Run pipeline for one experiment
verdandi run --all [--dry-run]                   # Run all pending experiments
verdandi research [--max-ideas N] [--dry-run]    # Discover + research + score (stops at Step 2)
verdandi ls [--status STATUS]                    # List experiments
verdandi inspect <ID>                            # Show experiment summary + completed steps
verdandi inspect <ID> --step scoring             # Show specific step result as JSON
verdandi inspect <ID> --log                      # Show pipeline execution log
verdandi report <ID>                             # Show structured research report
verdandi review <ID> --approve [--notes ""]      # Approve experiment for deployment
verdandi review <ID> --reject [--notes ""]       # Reject experiment
verdandi monitor [--all-live]                    # Show running experiments
verdandi archive <ID>                            # Archive an experiment
verdandi check                                   # Verify API key configuration
verdandi reservations [--active-only/--all]      # Show topic reservations
verdandi cache ping                              # Check Redis connectivity
verdandi cache stats                             # Show research cache statistics
verdandi cache purge                             # Delete all research cache entries
verdandi tui                                     # Interactive experiment browser (requires [tui] extra)
verdandi serve [--host H] [--port P]             # Start the FastAPI API server
verdandi worker [--workers N]                    # Start Huey task queue consumer
verdandi enqueue discover [--max-ideas N]        # Enqueue discovery job to worker
verdandi enqueue run <ID> [--dry-run]            # Enqueue pipeline run to worker
```

Add `-v` / `--verbose` to any command for debug-level logging.
Add `--remote <URL>` to any command to target a remote API server (see [Remote Mode](#remote-mode)).

## Interactive TUI

An interactive terminal browser for experiments, combining `ls` + `report` into a single navigable interface. Requires the optional `[tui]` extra:

```bash
pip install -e ".[tui]"
verdandi tui
```

**List view** — all experiments in a navigable table:

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `Enter` | Open experiment details |
| `r` | Refresh the list |
| `q` | Quit |

**Detail view** — scrollable research report (same data as `verdandi report`):

| Key | Action |
|-----|--------|
| `↑` / `↓` | Scroll |
| `f` | Toggle full / truncated display |
| `Escape` | Back to list |
| `q` | Quit |

Sections shown: header, idea, market research, competitors table, scoring breakdown, completed steps. Sections for steps not yet run display a placeholder.

Works with `--remote` for browsing experiments on a remote API server.

## REST API

Start the API server:

```bash
verdandi serve
# or
verdandi serve --host 0.0.0.0 --port 8080
```

All endpoints are under `/api/v1`:

### System
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (DB connectivity) |
| `GET` | `/config/check` | Show which API keys are configured |
| `GET` | `/metrics` | Prometheus metrics (step durations, LLM tokens, council votes) |

### Experiments
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/experiments` | List experiments (optional `?status=pending`) |
| `GET` | `/experiments/{id}` | Get experiment details |
| `GET` | `/experiments/{id}/report` | Structured research report (idea + market + scoring) |
| `POST` | `/experiments/{id}/archive` | Archive an experiment |

### Steps & Logs
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/experiments/{id}/steps` | All step results for an experiment |
| `GET` | `/experiments/{id}/steps/{name}` | Specific step result |
| `GET` | `/experiments/{id}/log` | Pipeline execution log |

### Reviews
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reviews/pending` | List experiments awaiting review |
| `POST` | `/reviews/{id}` | Submit review (approve/reject) |

### Actions
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/actions/discover` | Trigger idea discovery |
| `POST` | `/actions/run/{id}` | Trigger pipeline run |

### Reservations
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reservations` | List topic reservations |
| `DELETE` | `/reservations/{id}` | Release a reservation |

## Remote Mode

When Verdandi runs on a remote server, you can use the same CLI commands from your local machine without SSH. The CLI transparently switches between local SQLite access and HTTP calls to the remote API.

### Setup

**Option 1: Environment variable** (persistent)

```bash
# In your local .env or shell profile
export VERDANDI_API_URL=http://your-server:8000
verdandi ls
```

**Option 2: CLI flag** (one-off)

```bash
verdandi --remote http://your-server:8000 ls
verdandi --remote http://your-server:8000 report 4
verdandi --remote http://your-server:8000 review 2 --approve
```

The `--remote` flag takes precedence over the env var. If neither is set, the CLI uses local SQLite (default behavior, no change needed).

### How It Works

Both `Database` (local) and `ApiClient` (remote) implement the `CliBackend` protocol — a narrow 8-method interface covering reads, reviews, and archiving. The CLI calls `_get_backend()` which returns whichever implementation matches the current mode. Commands like `ls`, `inspect`, `report`, `review`, and `archive` work identically in both modes.

### Command Availability

| Category | Commands | Remote | Local |
|----------|----------|--------|-------|
| Read-only | `ls`, `inspect`, `monitor`, `report` | Yes | Yes |
| Write | `review`, `archive` | Yes | Yes |
| Actions | `discover`, `run`, `research` | Yes (enqueues on server) | Yes |
| Config | `check`, `reservations` | Yes | Yes |
| Local-only | `worker`, `cache`, `enqueue`, `serve` | No | Yes |

Commands marked "Local-only" will print an error if used in remote mode:

```
Error: 'worker' is not available in remote mode.
```

### Typical Workflow

```bash
# On your server: start the API + worker
verdandi serve --host 0.0.0.0 &
verdandi worker --workers 4 &

# On your local machine: interact remotely
export VERDANDI_API_URL=http://your-server:8000

verdandi discover --max-ideas 3        # Triggers discovery on the server
verdandi ls                            # Lists experiments from the server DB
verdandi report 2                      # Shows research report
verdandi review 2 --approve            # Approves experiment remotely
verdandi run 2                         # Triggers pipeline run on the server
```

## Pipeline Models

Each step produces a frozen Pydantic model stored as JSON in SQLite:

| Step | Output Model | Key Fields |
|------|-------------|------------|
| 0 - Idea Discovery | `IdeaCandidate` | title, one_liner, problem_statement, target_audience, pain_points, existing_solutions |
| 1 - Deep Research | `MarketResearch` | tam_estimate, competitors, demand_signals, willingness_to_pay, key_findings, research_rounds_completed, gap_analysis |
| 2 - Scoring | `PreBuildScore` | total_score (0-100), decision (GO/NO_GO/ITERATE), components, risks, opportunities |
| 3 - MVP Definition | `MVPDefinition` | product_name, tagline, features, pricing_model, cta_text, domain_suggestions |
| 4 - Landing Page | `LandingPageContent` | headline, subheadline, features, testimonials, FAQ, rendered_html |
| 5 - Human Review | `HumanReviewResult` | approved, skipped, reason |
| 6 - Domain Purchase | `DeploymentResult` | domain (name, registrar, cost), live_url |
| 7 - Deploy | `DeploymentResult` | cloudflare (deployment_url, ssl_active) |
| 8 - Analytics Setup | `DeploymentResult` | analytics (website_id, tracking_script_url) |
| 9 - Distribution | `DistributionResult` | social_posts, seo_submission, total_reach_estimate |
| 10 - Monitor | `ValidationReport` | metrics, decision (GO/ITERATE/NO_GO), reasoning, next_steps |

## Multi-Worker Support

Verdandi supports multiple concurrent workers on a single machine via the Huey task queue with SQLite broker:

```bash
# Terminal 1: Start the worker consumer
verdandi worker --workers 4

# Terminal 2: Enqueue jobs
verdandi enqueue discover --max-ideas 5
verdandi enqueue run 1
verdandi enqueue run 2
verdandi enqueue run 3
```

**Topic reservations** prevent duplicate work — when a worker starts exploring an idea, it atomically reserves the topic key using SQLite's `BEGIN IMMEDIATE`. Reservations expire after 24 hours (with 6-hour heartbeat renewal) so crashed workers don't permanently block topics.

**Idea deduplication** uses a two-pass approach:
1. **Fast pass**: Normalized keyword fingerprints with Jaccard similarity (threshold > 0.6)
2. **Semantic pass**: Embedding similarity via all-MiniLM-L6-v2 (384-dim, cosine threshold > 0.82). Optionally indexed in Qdrant for O(log n) lookups; falls back to SQLite Python-loop if Qdrant is unavailable.

## Error Handling & Resilience

Verdandi is designed for unattended autonomous operation — every external call is wrapped in defensive patterns:

- **Exponential backoff with jitter** — Retries follow `base_delay * 2^attempt + random_jitter`, preventing thundering herd on shared APIs. Configurable per step via `MAX_RETRIES` (default 3).
- **Circuit breakers** — Each external service has an independent breaker that trips after consecutive failures, auto-resets after a cooldown period, and enters a half-open probe state before fully closing. Prevents wasting time and tokens on a downed service.
- **Graceful degradation** — Research steps (Step 1) collect from whichever APIs respond and only fail if *all* sources are unavailable. A partial research result is better than no result.
- **Correlation ID tracing** — Every pipeline run and API request gets a unique correlation ID propagated through structlog context vars and FastAPI middleware, making it straightforward to trace a single experiment across log lines.
- **Structured logging** — All output goes through structlog with JSON or console rendering (configured via `LOG_FORMAT`). Every log entry includes experiment ID, step name, worker ID, and correlation ID.
- **Pipeline checkpointing** — Step results are persisted to SQLite immediately after completion. If the process crashes mid-pipeline, `verdandi run <ID>` resumes from the last completed step.

## Project Structure

```
verdandi/
├── pyproject.toml              # Build config, dependencies, ruff/mypy settings
├── .env.example                # All environment variables documented
├── CLAUDE.md                   # Strategy document and implementation plan
├── verdandi/
│   ├── __init__.py             # Package version
│   ├── py.typed                # PEP 561 typed package marker
│   ├── cli.py                  # Click CLI (all commands incl. cache, enqueue groups)
│   ├── config.py               # pydantic-settings configuration
│   ├── llm.py                  # PydanticAI agent wrapper (multi-provider: Anthropic, OpenAI, Google)
│   ├── logging.py              # structlog configuration
│   ├── protocols.py            # Protocol interfaces (StepProtocol, ResearchProviderPort, ReadOnlyMemory)
│   ├── retry.py                # Exponential backoff + circuit breaker
│   ├── notifications.py        # Console/email notification stubs
│   ├── research.py             # ResearchCollector: parallel provider orchestration + result merging
│   ├── strategies.py           # DiscoveryStrategy definitions (disruption, moonshot)
│   ├── cache.py                # Redis-backed research result cache
│   ├── metrics.py              # Prometheus metric definitions
│   ├── orchestrator/           # Pipeline execution + coordination
│   │   ├── runner.py           # PipelineRunner (pre-loads PriorResults, owns DB + Qdrant writes)
│   │   ├── coordination.py     # TopicReservationManager, dedup, worker identity
│   │   └── scheduler.py        # Huey task queue definitions
│   ├── agents/                 # Pipeline step implementations (read-only — no direct DB access)
│   │   ├── base.py             # AbstractStep, StepContext, PriorResults, @register_step
│   │   ├── council.py          # AgentCouncil: multi-model scoring panel
│   │   ├── discovery.py        # Step 0: Idea Discovery
│   │   ├── research.py         # Step 1: Deep Research
│   │   ├── scoring.py          # Step 2: Pre-Build Scoring (single-model or council)
│   │   ├── mvp.py              # Step 3: MVP Definition
│   │   ├── landing_page.py     # Step 4: Landing Page Generation
│   │   ├── human_review.py     # Step 5: Human Review checkpoint
│   │   ├── domain.py           # Step 6: Domain Purchase
│   │   ├── deploy.py           # Step 7: Cloudflare Pages Deployment
│   │   ├── analytics.py        # Step 8: Analytics Setup
│   │   ├── distribution.py     # Step 9: Social Distribution
│   │   └── monitor.py          # Step 10: Monitoring + go/no-go
│   ├── memory/                 # Embedding + vector DB for semantic dedup
│   │   ├── embeddings.py       # EmbeddingService (all-MiniLM-L6-v2, 384-dim)
│   │   ├── long_term.py        # LongTermMemory (Qdrant vector DB)
│   │   └── working.py          # ResearchSession — ephemeral dedup accumulator
│   ├── providers/              # Research data providers (one per external API)
│   │   ├── tavily.py, serper.py, exa.py, perplexity.py, hn.py, socialdata.py
│   │   └── __init__.py         # default_providers() factory
│   ├── db/                     # Database layer
│   │   ├── engine.py           # SQLAlchemy engine factory + session maker
│   │   ├── orm.py              # ORM table models (ExperimentRow, StepResultRow, etc.)
│   │   └── facade.py           # Database facade (sessions + CRUD helpers)
│   ├── models/                 # Frozen Pydantic models for every pipeline stage
│   │   ├── base.py             # BaseStepResult
│   │   ├── experiment.py       # Experiment + ExperimentStatus enum
│   │   ├── idea.py             # IdeaCandidate, PainPoint, DiscoveryType
│   │   ├── research.py         # MarketResearch, Competitor, SearchResult, ResearchGapAnalysis, DimensionConfidence
│   │   ├── scoring.py          # PreBuildScore, ScoreComponent, Decision, CouncilResult
│   │   ├── mvp.py              # MVPDefinition, Feature
│   │   ├── landing_page.py     # LandingPageContent, Testimonial, FAQItem
│   │   ├── deployment.py       # DeploymentResult, DomainInfo, CloudflareDeployment
│   │   ├── distribution.py     # DistributionResult, SocialPost, SEOSubmission
│   │   └── validation.py       # ValidationReport, MetricsSnapshot, ValidationDecision
│   ├── clients/                # External API clients (with mock fallbacks)
│   │   ├── tavily.py, serper.py, exa.py, perplexity.py, hn_algolia.py, socialdata.py
│   │   ├── porkbun.py, cloudflare.py, umami.py, emailoctopus.py
│   │   └── social/             # twitter.py, linkedin.py, reddit.py, bluesky.py
│   ├── api/                    # FastAPI REST API
│   │   ├── app.py              # Application factory + lifespan + Prometheus /metrics mount
│   │   ├── middleware.py       # Correlation ID middleware, exception handlers
│   │   ├── deps.py             # Dependency injection (DbDep, SettingsDep)
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   └── routes/             # 6 route modules (experiments, steps, reviews, actions, system, reservations)
│   ├── tui/                    # Interactive terminal browser (optional: [tui] extra)
│   │   ├── app.py              # Textual App subclass
│   │   ├── data.py             # Data bridge: CliBackend → display dataclasses
│   │   ├── screens/            # list_screen.py, detail_screen.py
│   │   └── styles/             # app.tcss, detail.tcss
│   └── templates/
│       └── landing_v1.html     # Tailwind CDN template with {{TOKEN}} placeholders
└── tests/
    ├── conftest.py             # Shared fixtures (tmp SQLite, sample experiments)
    ├── fixtures/               # JSON fixtures for API client mocking
    ├── test_models.py          # Pydantic model validation tests
    ├── test_db.py              # Database CRUD tests
    ├── test_orchestrator.py    # Pipeline execution tests
    ├── test_coordination.py    # Topic reservation + dedup tests
    ├── test_retry.py           # Retry + circuit breaker tests
    ├── test_clients.py         # httpx API client tests (respx mocking)
    ├── test_providers.py       # Research provider tests
    ├── test_research.py        # ResearchCollector integration tests
    ├── test_council.py         # Agent council tests (aggregation, parallel execution, consensus)
    ├── test_strategies.py      # Discovery strategy tests
    ├── test_cache.py           # Redis cache tests (fakeredis)
    ├── test_metrics.py         # Prometheus metric tests
    ├── test_embeddings.py      # Embedding service tests
    ├── test_memory_long_term.py  # Qdrant long-term memory tests
    ├── test_memory_working.py  # Working memory (ResearchSession + ingest_with_delta) tests
    ├── test_research_gap.py    # Multi-turn research helpers + gap analysis model tests
    ├── test_steps_real.py      # Real step integration tests (incl. multi-turn research scenarios)
    ├── test_llm_integration.py # LLM client tests
    ├── test_alembic.py         # Migration tests
    ├── test_tui/               # TUI data layer tests
    └── test_api/               # API endpoint tests
        ├── conftest.py         # FastAPI test client fixtures
        ├── test_experiments.py
        ├── test_system.py
        ├── test_reviews.py
        └── test_actions.py
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_db.py -v

# Run tests matching a pattern
pytest -k "test_retry" -v
```

### Code Quality

```bash
# Lint
ruff check verdandi/ tests/

# Format
ruff format verdandi/ tests/

# Type check
mypy verdandi/
```

### Adding a New Pipeline Step

1. Create `verdandi/agents/your_step.py`:

```python
from verdandi.agents.base import AbstractStep, StepContext, register_step

@register_step
class YourStep(AbstractStep):
    name = "your_step"
    step_number = 11

    def run(self, ctx: StepContext) -> YourModel:
        if ctx.dry_run:
            return YourModel(...)  # Mock data

        # Access prior step results (read-only, pre-loaded by orchestrator)
        mvp = ctx.prior_results.get_typed("mvp_definition", MVPDefinition)

        # Real implementation
        return YourModel(...)
```

2. Create the output model in `verdandi/models/your_model.py`
3. Import the step in `verdandi/agents/__init__.py`

The orchestrator will automatically pick it up via the `@register_step` decorator.

## Cost Estimates

| Component | Monthly Cost |
|-----------|-------------|
| Claude Sonnet 4.5 (LLM reasoning) | $10-30 |
| Research APIs (Tavily + Serper + Exa + Perplexity) | $5-15 |
| Domains (Porkbun, .com at ~$10 each) | $8-13/domain |
| Hosting (Cloudflare Pages, free tier) | $0 |
| Analytics (Umami self-hosted) | $0-5 |
| Email collection (EmailOctopus, free tier) | $0 |
| VPS (Hetzner CX22) | $5-10 |
| **Total** | **$28-83/month** |

At roughly **$0.75-$2.00 per product validation** (excluding domains), Verdandi can test 30-100+ ideas monthly.

## Experiment Lifecycle

```
PENDING ──────► RUNNING ──────► AWAITING_REVIEW ──────► APPROVED ──────► RUNNING ──► COMPLETED
                  │                                         │
                  │                                    REJECTED
                  │
                  ├──── NO_GO (score below threshold)
                  │
                  └──── FAILED (unrecoverable error)

Any state ──────► ARCHIVED
```
