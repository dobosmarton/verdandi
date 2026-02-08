# Verdandi

**Autonomous product validation factory.** Verdandi discovers product ideas, validates them through market research, builds landing pages, deploys them, and monitors conversion metrics to make go/no-go decisions — all autonomously.

Named after the Norse Norn of the present, Verdandi turns "what is happening right now" in the market into validated product opportunities.

## How It Works

Verdandi runs a sequential 11-step pipeline for each product experiment:

```
Step 0:  Idea Discovery      → Find promising product ideas from market signals
Step 1:  Deep Research        → Multi-source market research (Tavily, Serper, Exa, Perplexity)
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

Each step produces a validated Pydantic model consumed by the next — `IdeaCandidate` feeds into `MarketResearch`, which feeds into `PreBuildScore` (the first gate — NO_GO halts the pipeline). Approved experiments continue through `MVPDefinition` and `LandingPageContent` into `DeploymentResult` (shared across Steps 6-8), then `DistributionResult`, and finally `ValidationReport` (the second gate — GO/ITERATE/NO_GO). Steps read prior outputs via `db.get_step_result()`.

Results are checkpointed to SQLite after every step, so the pipeline can resume from where it left off if interrupted.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLI (Click)          │  API (FastAPI + Uvicorn)    │
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
- **PydanticAI** for LLM-facing steps (structured outputs via `Agent` + `run_sync` + `result_type`).
- **SQLAlchemy 2.0+ ORM** for all database access. Frozen Pydantic models for domain objects, separate ORM models for persistence.
- **SQLite + WAL mode** for state storage. Huey task queue with a separate SQLite broker for background jobs.
- **Template-fill for landing pages** — Pre-built HTML + Tailwind templates with `{{TOKEN}}` placeholders. Near-zero failure rate vs. ~15% breakage from LLM-generated full HTML.
- **structlog** with correlation IDs for request tracing across pipeline steps.

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
| `LLM_MODEL` | `claude-sonnet-4-5-20250929` | Claude model for reasoning |
| `LLM_MAX_TOKENS` | `4096` | Max output tokens per LLM call |
| `LLM_TEMPERATURE` | `0.7` | LLM temperature |
| `DATA_DIR` | `./data` | Directory for SQLite databases |

### Monitoring Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_EMAIL_SIGNUP_GO` | `10.0` | Email signup rate % for GO signal |
| `MONITOR_EMAIL_SIGNUP_NOGO` | `3.0` | Email signup rate % below = NO_GO |
| `MONITOR_BOUNCE_RATE_MAX` | `80.0` | Max acceptable bounce rate % |
| `MONITOR_MIN_VISITORS` | `200` | Minimum visitors before deciding |

## CLI Reference

```
verdandi                                    # Show help
verdandi discover [--max-ideas N] [--dry-run]     # Discover product ideas
verdandi run <ID> [--dry-run]               # Run pipeline for one experiment
verdandi run --all [--dry-run]              # Run all pending experiments
verdandi ls [--status STATUS]               # List experiments
verdandi inspect <ID>                       # Show experiment summary + completed steps
verdandi inspect <ID> --step scoring        # Show specific step result as JSON
verdandi inspect <ID> --log                 # Show pipeline execution log
verdandi review <ID> --approve [--notes ""] # Approve experiment for deployment
verdandi review <ID> --reject [--notes ""]  # Reject experiment
verdandi monitor [--all-live]               # Show running experiments
verdandi archive <ID>                       # Archive an experiment
verdandi check                              # Verify API key configuration
verdandi reservations [--active-only/--all] # Show topic reservations
verdandi serve [--host H] [--port P]        # Start the FastAPI API server
verdandi worker [--workers N]               # Start Huey task queue consumer
verdandi enqueue discover [--max-ideas N]   # Enqueue discovery job to worker
verdandi enqueue run <ID> [--dry-run]       # Enqueue pipeline run to worker
```

Add `-v` / `--verbose` to any command for debug-level logging.

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

### Experiments
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/experiments` | List experiments (optional `?status=pending`) |
| `GET` | `/experiments/{id}` | Get experiment details |

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

## Pipeline Models

Each step produces a frozen Pydantic model stored as JSON in SQLite:

| Step | Output Model | Key Fields |
|------|-------------|------------|
| 0 - Idea Discovery | `IdeaCandidate` | title, one_liner, problem_statement, target_audience, pain_points, existing_solutions |
| 1 - Deep Research | `MarketResearch` | tam_estimate, competitors, demand_signals, willingness_to_pay, key_findings |
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
2. **Semantic pass**: Embedding similarity (stubbed; requires sentence-transformers)

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
│   ├── cli.py                  # Click CLI (all commands)
│   ├── config.py               # pydantic-settings configuration
│   ├── db.py                   # Database facade (SQLAlchemy sessions + CRUD helpers)
│   ├── engine.py               # SQLAlchemy engine factory + session maker
│   ├── orm.py                  # ORM table models (ExperimentRow, StepResultRow, etc.)
│   ├── orchestrator.py         # PipelineRunner, step execution, checkpoint/resume
│   ├── llm.py                  # PydanticAI agent wrapper
│   ├── logging.py              # structlog configuration
│   ├── protocols.py            # Protocol interfaces (StepProtocol, etc.)
│   ├── retry.py                # Exponential backoff + circuit breaker
│   ├── coordination.py         # Topic reservations, deduplication, worker identity
│   ├── notifications.py        # Console/email notification stubs
│   ├── tasks.py                # Huey task queue definitions
│   ├── models/                 # Frozen Pydantic models for every pipeline stage
│   │   ├── base.py             # BaseStepResult
│   │   ├── experiment.py       # Experiment + ExperimentStatus enum
│   │   ├── idea.py             # IdeaCandidate, PainPoint
│   │   ├── research.py         # MarketResearch, Competitor, SearchResult
│   │   ├── scoring.py          # PreBuildScore, ScoreComponent, Decision
│   │   ├── mvp.py              # MVPDefinition, Feature
│   │   ├── landing_page.py     # LandingPageContent, Testimonial, FAQItem
│   │   ├── deployment.py       # DeploymentResult, DomainInfo, CloudflareDeployment
│   │   ├── distribution.py     # DistributionResult, SocialPost, SEOSubmission
│   │   └── validation.py       # ValidationReport, MetricsSnapshot, ValidationDecision
│   ├── steps/                  # Pipeline step implementations (each with dry-run mock)
│   │   ├── base.py             # AbstractStep, StepContext, @register_step
│   │   ├── s0_idea_discovery.py  through  s10_monitor.py
│   │   └── __init__.py         # Imports all steps to trigger registration
│   ├── clients/                # External API clients (with mock fallbacks)
│   │   ├── tavily.py, serper.py, exa.py, perplexity.py, hn_algolia.py
│   │   ├── porkbun.py, cloudflare.py, umami.py, emailoctopus.py
│   │   └── social/             # twitter.py, linkedin.py, reddit.py, bluesky.py
│   ├── api/                    # FastAPI REST API
│   │   ├── app.py              # Application factory + lifespan
│   │   ├── middleware.py       # Correlation ID middleware, exception handlers
│   │   ├── deps.py             # Dependency injection (DbDep, SettingsDep)
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   └── routes/             # 6 route modules (experiments, steps, reviews, actions, system, reservations)
│   └── templates/
│       └── landing_v1.html     # Tailwind CDN template with {{TOKEN}} placeholders
└── tests/
    ├── conftest.py             # Shared fixtures (tmp SQLite, sample experiments)
    ├── test_models.py          # Pydantic model validation tests
    ├── test_db.py              # Database CRUD tests
    ├── test_orchestrator.py    # Pipeline execution tests
    ├── test_coordination.py    # Topic reservation + dedup tests
    ├── test_retry.py           # Retry + circuit breaker tests
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

1. Create `verdandi/steps/s11_your_step.py`:

```python
from verdandi.steps.base import AbstractStep, StepContext, register_step

@register_step
class YourStep(AbstractStep):
    name = "your_step"
    step_number = 11

    def run(self, ctx: StepContext) -> YourModel:
        if ctx.dry_run:
            return YourModel(...)  # Mock data
        # Real implementation
        return YourModel(...)
```

2. Create the output model in `verdandi/models/your_model.py`
3. Import the step in `verdandi/steps/__init__.py`

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
