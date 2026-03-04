# Verdandi — Autonomous Product Validation Factory

## Quick start

```bash
# Install (Python 3.11+ required)
pip install -e ".[dev]"

# Verify API keys
verdandi check

# Run discovery (real APIs)
verdandi discover --max-ideas 3

# Run discovery (offline mock)
verdandi discover --max-ideas 3 --dry-run

# List experiments
verdandi ls

# Run full pipeline for one experiment
verdandi run <ID>

# Inspect results
verdandi inspect <ID>
verdandi inspect <ID> --log
```

## What this project does

An 11-step pipeline that autonomously discovers product ideas, validates them through market research, builds landing pages, deploys them, and monitors conversion metrics.

```
Step 0:  Idea Discovery     → IdeaCandidate
Step 1:  Deep Research       → MarketResearch
Step 2:  Pre-Build Scoring   → PreBuildScore (GO/NO_GO gate)
Step 3:  MVP Definition      → MVPDefinition
Step 4:  Landing Page Gen    → LandingPageContent (rendered HTML)
Step 5:  Human Review        → approval checkpoint
Step 6:  Domain Purchase     → DeploymentResult.domain
Step 7:  Deploy              → DeploymentResult.cloudflare
Step 8:  Analytics Setup     → DeploymentResult.analytics
Step 9:  Distribution        → DistributionResult
Step 10: Monitor             → ValidationReport (GO/ITERATE/NO_GO)
```

## Environment variables (.env)

Settings are loaded by `pydantic-settings` from `.env` in the project root.

### Required for discovery

```
ANTHROPIC_API_KEY=sk-ant-...       # The only strictly required key
```

### Research APIs (optional but recommended — more sources = better ideas)

```
TAVILY_API_KEY=tvly-...            # Primary search (1K free/month)
SERPER_API_KEY=...                 # Google SERP + Reddit via site: queries
EXA_API_KEY=...                    # Semantic/neural search
PERPLEXITY_API_KEY=pplx-...        # Synthesized research answers
SOCIALDATA_API_KEY=...             # Twitter/X data
FIRECRAWL_API_KEY=...              # Competitor page scraping
```

HN Algolia requires no key and is always available.

If no research API keys are set, discovery falls back to LLM-only mode (Claude generates ideas without external research data).

### Optional infrastructure

```
REDIS_URL=redis://localhost:6379/0    # Research response caching (empty = disabled)
QDRANT_URL=http://localhost:6333      # Vector dedup / long-term memory (empty = disabled)
QDRANT_API_KEY=                       # Only if Qdrant auth is enabled
```

Start Redis + Qdrant via: `docker compose up -d`

Both are optional — Redis caching and Qdrant vector dedup degrade gracefully when unavailable.

### Multi-model council (optional scoring in Step 2)

```
COUNCIL_ENABLED=false
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
GOOGLE_API_KEY=...
GOOGLE_MODEL=gemini-2.5-flash
```

### Deployment APIs (Steps 6–9 only — not needed for discovery)

```
PORKBUN_API_KEY=...
PORKBUN_SECRET_KEY=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
UMAMI_URL=...
UMAMI_API_KEY=...
EMAILOCTOPUS_API_KEY=...
TWITTER_BEARER_TOKEN=...
LINKEDIN_ACCESS_TOKEN=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
BLUESKY_HANDLE=...
BLUESKY_APP_PASSWORD=...
```

### Pipeline tuning (all have defaults)

```
REQUIRE_HUMAN_REVIEW=true              # Pause at Step 5 for approval
LLM_MODEL=claude-sonnet-4-5-20250929   # Model for all LLM calls
LLM_TEMPERATURE=0.7
SCORE_GO_THRESHOLD=70                  # Min score for GO decision
DISCOVERY_DISRUPTION_RATIO=0.7         # 70% disruption / 30% moonshot
DATA_DIR=./data                        # SQLite DB + Huey queue location
STRATEGIES_DIR=./strategies            # Discovery strategy YAML files
RESEARCH_MAX_ROUNDS=2                  # Max research rounds per experiment
RESEARCH_CONFIDENCE_THRESHOLD=0.7
LOG_LEVEL=INFO
```

## Database

SQLite with WAL mode at `./data/verdandi.db`. Auto-created on first CLI command — no explicit init needed. Huey task broker uses a separate `./data/huey_queue.db`.

Alembic is configured for schema migrations on existing databases (`alembic/` directory).

## Discovery strategies

Two built-in strategies in `./strategies/`:

- **disruption.yaml** — Problem-first: finds broken workflows, user complaints. Produces `ProblemReport`. Prioritizes Reddit + HN.
- **moonshot.yaml** — Futures-first: spots emerging tech, new capabilities. Produces `OpportunityReport`. Prioritizes HN + Twitter.

Example templates in `./strategies/examples/`: `b2b-saas.yaml`, `climate-tech.yaml`, `vertical-ai.yaml`.

### Strategy selection

```bash
verdandi discover                              # auto: 70% disruption / 30% moonshot
verdandi discover --strategy disruption        # only disruption
verdandi discover --strategy moonshot          # only moonshot
verdandi discover --strategy my-custom-name    # custom YAML from strategies_dir
```

### Strategy management

```bash
verdandi strategy list                  # List all available strategies
verdandi strategy show <NAME>           # View strategy details
verdandi strategy validate <FILE>       # Validate a YAML file
verdandi strategy create                # Interactive creation wizard
```

## How discovery works (Step 0)

Two-phase process per idea slot:

1. **Phase 1 — Research + Discovery Report**: Parallel calls to all available research providers (Tavily, Serper, Exa, Perplexity, SocialData, HN Algolia). Claude synthesizes into a `ProblemReport` or `OpportunityReport` using the strategy's prompts.
2. **Phase 2 — Idea Synthesis**: Claude converts the report into an `IdeaCandidate` with title, category, target audience, pain points, and proposed solution.
3. **Dedup**: Jaccard fingerprint (always) → sentence-transformer embedding similarity (always, 384-dim all-MiniLM-L6-v2) → Qdrant vector search (if configured, else SQLite fallback). Up to 3 retry attempts if duplicate detected.

Each idea creates a new `Experiment` row in SQLite at status `pending`.

## CLI reference

```bash
# Discovery
verdandi discover [--max-ideas N] [--strategy NAME] [--dry-run]

# Pipeline execution
verdandi run <ID> [--stop-after N] [--dry-run]
verdandi run --all [--dry-run]

# Experiment management
verdandi ls [--status STATUS]
verdandi inspect <ID> [--step NAME] [--log]
verdandi review <ID> --approve|--reject [--notes TEXT]
verdandi archive <ID> [--teardown]

# Infrastructure
verdandi check                         # Verify API keys
verdandi worker [--workers N]          # Start Huey consumer
verdandi enqueue discover [--max-ideas N] [--dry-run]
verdandi enqueue run <ID> [--dry-run]
verdandi serve [--host H] [--port P]   # Start FastAPI server
verdandi cache ping                    # Check Redis connectivity
verdandi reservations [--active-only]  # Topic reservations

# Strategies
verdandi strategy list|show|validate|create

# Interactive TUI (requires: pip install -e ".[tui]")
verdandi tui
```

## Project structure

```
verdandi/
├── orchestrator/           # Heavy deps: DB, Redis, Qdrant
│   ├── runner.py           # PipelineRunner
│   ├── coordination.py     # TopicReservationManager (dedup)
│   └── scheduler.py        # Huey tasks
├── agents/                 # Lightweight: PydanticAI + httpx (NO direct DB access)
│   ├── base.py             # AbstractStep, StepContext, PriorResults
│   └── discovery.py → monitor.py  # 11 pipeline steps (s0–s10)
├── memory/                 # Embedding + vector store abstractions
│   ├── embeddings.py       # EmbeddingService (all-MiniLM-L6-v2, 384-dim)
│   ├── long_term.py        # LongTermMemory (Qdrant)
│   └── working.py          # ResearchSession (ephemeral dedup)
├── providers/              # Research API adapters (ResearchProviderPort protocol)
│   ├── tavily.py, serper.py, exa.py, perplexity.py, hn.py, socialdata.py
├── clients/                # Low-level httpx API clients
├── models/                 # Pydantic domain models
├── db/                     # SQLAlchemy ORM + Database facade
│   ├── engine.py, orm.py, facade.py
├── api/                    # FastAPI REST API
├── tui/                    # Textual interactive TUI (optional)
├── templates/              # HTML+Tailwind landing page templates
├── config.py               # pydantic-settings (reads .env)
├── strategies.py           # DiscoveryStrategy model
├── strategy_loader.py      # YAML loader for strategies
├── research.py             # ResearchCollector
├── cache.py                # Redis research cache
├── retry.py                # Exponential backoff + circuit breaker
├── llm.py                  # PydanticAI agent wrapper
├── cli.py                  # Click CLI entry point
└── logging.py              # structlog configuration
```

## Architecture rules

- **Orchestrator/Agent separation**: Agents receive `PriorResults` (pre-loaded dict) + `ReadOnlyMemory`. Only the orchestrator writes to DB/Qdrant.
- **Frozen Pydantic models**: Mutate via `model.model_copy(update={...})`, not assignment.
- **PydanticAI for LLM calls**: `Agent + run_sync + output_type` for structured outputs.
- **SQLAlchemy 2.0+ ORM**: `ExperimentRow` (ORM) is distinct from `Experiment` (Pydantic domain model). The `Database` facade converts between them.
- **structlog** with `merge_contextvars` for correlation ID tracing.
- **Research providers** implement `ResearchProviderPort` protocol: `name`, `is_available`, `collect(config, cached_call) -> RawResearchData`.

## Testing

```bash
pytest tests/ -v                 # 441+ tests, ~2.5min
ruff check verdandi/ tests/      # Linting (0 errors expected)
ruff format --check verdandi/ tests/  # Formatting
mypy --strict verdandi/          # Type checking (0 errors expected)
```

## Reference docs

- Strategy research, tool evaluations, and implementation plan: see README.md "Strategy & Research" section
- Research pipeline design: `docs/plan-research-pipeline.md`
