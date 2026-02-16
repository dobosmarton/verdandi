# Building an autonomous product validation factory

**The optimal stack for a fully autonomous product validation agent costs $35–85/month and requires no framework — just custom Python scripts orchestrating Claude API calls, Porkbun for .com domains, Cloudflare Pages for deployment, and Umami for analytics.** No existing open-source project or SaaS tool implements this full pipeline, making it a genuinely novel system. The architecture is a sequential pipeline with JSON checkpointing, where each step produces a validated Pydantic model consumed by the next. At roughly **$0.75–$2.00 per product validation** (excluding domains), the agent can test 30–100+ ideas monthly within budget.

This report covers every pipeline stage with specific tool recommendations, pricing, API availability, and a concrete implementation plan based on extensive research across 50+ tools and platforms.

---

## The orchestration layer: keep it simple

The single most important architectural decision is **not** to use a framework. For a sequential 11-step pipeline running periodically, custom Python scripts with the Claude API and PydanticAI for structured outputs outperform every agent framework evaluated — LangGraph, CrewAI, AutoGen, and the OpenAI Agents SDK all add abstraction overhead without proportional benefit.

**Why custom scripts win here:** The pipeline is fundamentally linear (research → build → deploy → monitor), the user is a solo Python developer comfortable with Claude Code, and frameworks introduce debugging complexity that's dangerous for unattended autonomous operation. CrewAI's logging is broken inside Tasks. LangGraph's graph abstractions require significant upfront investment. AutoGen merged into Microsoft's Agent Framework (now in preview, GA target Q1 2026) and carries Azure ecosystem baggage. The OpenAI Agents SDK optimizes for OpenAI models, not Claude.

The recommended architecture uses **Pydantic state models** with **PydanticAI** for structured LLM outputs, **SQLite checkpointing** (via SQLAlchemy ORM) after each step, and **cron scheduling** on a $5–10/month VPS. Each pipeline step is an idempotent function that checks completion status before executing, with exponential backoff retries and circuit breakers. Claude Sonnet 4.5 ($3/$15 per million tokens input/output) handles all reasoning. The Claude Agent SDK — renamed from Claude Code SDK in September 2025 to reflect broader capabilities — can alternatively serve as the harness, supporting subagent spawning, YOLO mode for fully autonomous execution, and 30+ hour autonomous sessions.

```
CRON / Huey worker → Pipeline Orchestrator (Python)
  → Step 0:  Idea Discovery (Claude + Tavily + Serper + Exa + HN Algolia)
  → Step 1:  Deep Research (Claude + multi-source intelligence)
  → Step 2:  Pre-Build Scoring (Claude → GO/NO_GO gate)
  → Step 3:  MVP Definition (Claude + PydanticAI → Pydantic model)
  → Step 4:  Landing Page Generation (template-fill → HTML+Tailwind)
  → Step 5:  Human Review (optional approval checkpoint)
  → Step 6:  Domain Purchase (Porkbun API)
  → Step 7:  Deploy (Cloudflare Pages API)
  → Step 8:  Analytics Setup (inject Umami script)
  → Step 9:  Distribution (LinkedIn + X + Reddit + Bluesky APIs)
  → Step 10: Monitor (poll analytics → GO/ITERATE/NO_GO decision)
```

If observability needs grow, **Prefect** (free self-hosted, Python-native) or **Windmill** (open-source, 128MB orchestrator) are the best graduation paths. n8n deserves mention for its "Instant MVP Builder" workflow template that covers idea → code → GitHub → Vercel deployment — a useful reference implementation, though it skips research and distribution.

---

## Deep research: the $10–45/month intelligence stack

The research layer is the most critical component — the agent should refuse to build unless evidence strongly supports the opportunity. No single tool covers all research needs, but a combination of four free/cheap APIs provides remarkable depth.

**Tavily** is the primary search API. Purpose-built for AI agents, it returns clean, LLM-optimized structured output with native LangChain/MCP integration. The free tier provides **1,000 searches/month** — enough for ~50 deep research sessions. At $0.008 per basic search, even the paid tier ($30/month for 4,000 credits) is economical. Its `/research` endpoint performs multi-step agent-mode research for complex queries.

**Serper.dev** provides structured Google SERP data at the best price in the market — **2,500 free queries** (one-time, no credit card), then $1 per 1,000 queries. The critical capability here is `site:reddit.com` queries that extract Reddit discussions without touching the Reddit API's commercial restrictions. The "People Also Ask" data from SERPs directly reveals common pain points. Combine with `site:news.ycombinator.com` for developer-specific problems.

**Exa.ai** fills a unique niche with **neural/semantic search** — finding results by meaning rather than keywords. This is invaluable for competitor discovery ("companies similar to X in Y industry") and finding niche communities discussing specific problems. The $10 one-time free credit covers roughly 2,000 searches. At $5 per 1,000 requests, ongoing costs are modest.

**Perplexity Sonar** synthesizes multi-source research answers with citations in a single API call. At roughly **$0.006 per basic query**, it's the cheapest way to get AI-synthesized market intelligence. The Deep Research mode (~$0.41–$1.32 per query) is worth using for TAM estimation and competitive landscape synthesis. No dedicated "TAM estimation API" exists — the practical approach is Perplexity/Claude synthesizing analyst reports, validated with US Census Bureau data (free API) and Crunchbase company counts.

Supporting tools round out the stack: **Firecrawl** (500 free page scrapes/month, open-source self-hostable) for deep competitor website analysis, **Apify** ($5/month free tier) with pre-built scrapers for G2, Trustpilot, Reddit, and Product Hunt, and the **HackerNews Algolia API** (free, unlimited) for developer pain points. For full page content extraction, **Jina AI Reader** is entirely free — prefix any URL with `r.jina.ai/` for clean markdown output.

Expensive tools like SimilarWeb ($199+/month) and Crunchbase Pro ($49+/month) are unnecessary. Claude with web search ($10 per 1,000 searches) can approximate competitor traffic data and funding information at a fraction of the cost.

| Tool | Monthly Cost | Usage | Role |
|------|-------------|-------|------|
| Tavily (free tier) | $0 | 1,000 searches | Primary agent search |
| Serper.dev (free) | $0 | 2,500 queries (one-time) | SERP data, Reddit via site: queries |
| Exa.ai | $0–10 | ~2,000 searches | Semantic competitor discovery |
| Perplexity Sonar | $5–15 | 1,000–2,500 queries | Synthesized research answers |
| Firecrawl (free) | $0 | 500 pages | Deep competitor scraping |
| HN Algolia API | $0 | Unlimited | Developer pain points |
| Claude Haiku 4.5 | $5–20 | ~5M tokens | LLM reasoning layer |
| **Total** | **$10–45** | | **~50–100 validations/month** |

---

## Landing pages: template-fill beats AI builders

Most AI landing page builders cannot be automated. **Lovable, Bolt.new, Framer, Mixo, Carrd, Typedream, and Durable all lack public APIs** for programmatic page creation. Only v0.dev ($20/month) and Unicorn Platform ($18–29/month) offer API access, but both add cost and complexity without clear benefit over the simpler approach.

**The winning strategy is template-fill + Vercel/Cloudflare deployment.** Pre-build 2–3 HTML+Tailwind CSS landing page templates with placeholder tokens (`{{HEADLINE}}`, `{{SUBHEADLINE}}`, `{{CTA_TEXT}}`, `{{FEATURES}}`). The LLM generates structured copy via PydanticAI, a Python script performs string interpolation, and the result deploys via API. This approach is **100% reliable** — no build step failures, no module resolution errors, no framework compatibility issues.

The template approach works because LLMs generating full HTML from scratch produce broken code roughly 15% of the time, while template-fill has a near-zero failure rate. Open-source templates like **Landwind** (MIT-licensed, single `index.html` with Tailwind+Flowbite, includes hero/features/testimonials/pricing/FAQ/CTA sections) provide excellent starting points. The Tailwind CSS CDN (`<script src="https://cdn.tailwindcss.com">`) eliminates build steps entirely.

For higher design quality at the cost of $20/month, **v0.dev's API** generates React+Tailwind+shadcn/ui components that deploy natively to Vercel. This is the best premium option but unnecessary for validation — a clean template with strong copy validates just as well as a designer-crafted page.

The deployment API call is straightforward — Vercel's REST API accepts inline file data (`POST /v13/deployments` with HTML content in the request body), returning a live URL instantly. No Git repository required. Cloudflare Pages offers the same via `wrangler pages deploy` or its Direct Upload API.

---

## Domains and deployment: Porkbun + Cloudflare Pages

**Porkbun is the clear winner for automated domain purchase.** It offers a modern JSON REST API supporting full programmatic domain registration (`POST /api/json/v3/domain/create/DOMAIN`), DNS record management, and SSL certificate retrieval. Pricing is competitive at **$7.97 first year for .com** ($11.08 renewal), with free WHOIS privacy, email forwarding, and Let's Encrypt SSL included. A Postman collection is available for rapid integration.

The critical finding about Cloudflare Registrar is that it **does not offer a public API for domain registration** — only for managing existing domains. This eliminates the seemingly ideal Cloudflare-only pipeline. The workaround is registering via Porkbun's API, then pointing nameservers to Cloudflare for DNS management and Pages deployment.

**Name.com** is the strong runner-up with an excellent modern API, OpenAPI specs, and notably **MCP server support** designed for AI agent integration. Namecheap's API supports full purchase but uses XML format and requires either 20+ domains or $50+ account balance — barriers for a new automation setup.

For validation experiments, **.com domains (~$8–10/year via Porkbun) are the recommended default** for credibility. Cheaper TLDs like .dev (~$12/year) or .app (~$14/year) are acceptable alternatives with better trust signals than bargain TLDs.

**Cloudflare Pages wins for deployment** with **unlimited bandwidth and unlimited sites on the free tier** — no other platform matches this generosity. The Direct Upload API requires no Git setup, SSL is automatic, and the 300+ global edge locations ensure fast loading worldwide. Vercel Hobby (also free, unlimited sites) is the top alternative with a slightly better REST API for inline file deployment.

The automated pipeline flow:

1. Porkbun API → check availability → purchase .com domain (~$8–10)
2. Porkbun API → set nameservers to Cloudflare
3. Cloudflare API → add zone → configure DNS CNAME to Pages project
4. Cloudflare Pages → deploy HTML via Direct Upload API
5. Automatic SSL provisioning → **landing page live in ~2–5 minutes**

Cost per experiment: **$8–13 for .com domain + $0 for hosting**.

---

## Analytics and email: zero-cost validation infrastructure

**Umami** (self-hosted) is the optimal analytics choice — completely free, unlimited sites, full REST API for programmatic data retrieval, custom event tracking for CTA clicks and form submissions, and GDPR-compliant with no cookies. It runs on a minimal $5/month VPS via Docker Compose with PostgreSQL. Setup is a single script tag: `<script defer src="https://your-umami.com/script.js" data-website-id="UUID"></script>`. The API exposes `GET /api/websites/{id}/stats` for visitor counts, pageviews, bounce rate, and custom events — everything needed for automated go/no-go decisions.

**PostHog's cloud free tier** (1M analytics events/month, 5K session recordings, 6 projects) is the alternative if self-hosting isn't desired. It offers autocapture of all DOM interactions, feature flags, and A/B testing — more powerful but heavier. Self-hosting PostHog requires 4 vCPU and 16GB RAM minimum, making it impractical for budget VPS hosting.

For email collection, **EmailOctopus** provides the most generous free tier: **2,500 subscribers and 10,000 emails/month** with full REST API access. This is more than sufficient for landing page validation. **Buttondown** offers the best API quality (API-first architecture, free on all tiers as of 2025) but limits free accounts to 100 subscribers. Use EmailOctopus for collection and **Resend** (3,000 free transactional emails/month) for confirmation emails.

Event tracking for CTA clicks is trivial across all tools — a single JavaScript call (`umami.track('cta-click')` or `posthog.capture('cta_click')`) embedded in the landing page template's button onclick handler.

---

## Distribution strategy and go/no-go automation

The cheapest effective distribution combines **LinkedIn API** (free, high-quality B2B reach), **Twitter/X free tier** (500 posts/month write-only access), and targeted **Reddit posts** (free API, but strict 10% self-promotion rule and karma requirements). **Bluesky** via the AT Protocol is completely free and open for automated posting. For unified multi-platform posting, **Late** (getlate.dev) offers a single API call to post across 13 platforms.

SEO is fully automatable: generate `<title>`, `<meta description>`, Open Graph tags, JSON-LD structured data, and XML sitemap programmatically, then submit to Google Search Console via its free API. Product Hunt launches cannot be automated (community-moderated), and Hacker News has no posting API — both require manual intervention.

**Automated go/no-go decisions** follow this framework after driving 200–500 visitors to the page:

- **GO signal**: Email signup rate **>10%**, CTA click rate >15%, bounce rate <60%. Based on Unbounce's analysis of 57M+ conversions, these rates indicate strong interest
- **ITERATE signal**: Email signup 3–10%, bounce 60–75% — the agent should tweak copy, CTA, or offer and retest
- **NO-GO signal**: Email signup **<3%** after 500+ visitors, bounce >80% — kill the experiment

The monitoring agent polls the Umami API and EmailOctopus API every 6–12 hours, calculates conversion rates, and applies threshold logic. No special monitoring tool is needed — the pipeline agent *is* the monitoring tool. After collecting 50+ email signups, a follow-up email asking about willingness to pay provides the strongest validation signal: >40% open rate indicates an engaged audience, >5% click-through on pricing confirms demand.

---

## The complete recommended stack

| Pipeline Stage | Tool | Monthly Cost |
|---------------|------|-------------|
| **Orchestration** | Custom Python + Claude API + PydanticAI + Huey | $0 (framework) |
| **LLM reasoning** | Claude Sonnet 4.5 via Anthropic API | $10–30 |
| **Web research** | Tavily (free) + Serper.dev (free) + Exa.ai + Perplexity Sonar | $5–15 |
| **Content scraping** | Firecrawl (free) + Jina Reader (free) + HN API (free) | $0 |
| **Landing pages** | HTML+Tailwind templates, LLM-generated copy | $0 |
| **Domains** | Porkbun API (.com at ~$10/domain) | $8–13/domain |
| **Deployment** | Cloudflare Pages (free, unlimited) | $0 |
| **DNS/CDN** | Cloudflare (free tier) | $0 |
| **Analytics** | Umami self-hosted on VPS | $0–5 |
| **Email collection** | EmailOctopus (free, 2,500 subs) | $0 |
| **Distribution** | LinkedIn + X + Reddit APIs | $0 |
| **Hosting (VPS)** | Hetzner CX22 or DigitalOcean Basic | $5–10 |
| **Total** | | **$28–83/month** + ~$8–13 per domain |

This stack supports **30–100 product validations per month** at roughly $0.75–$2.00 per validation (excluding domain costs), well within the $20–100/month budget.

---

## Implementation roadmap in five weeks

**Week 1** — Build the pipeline skeleton: define Pydantic state models for each step (`MarketResearch`, `MVPDefinition`, `LandingPage`, `DeploymentResult`, `ValidationReport`), implement the orchestrator with JSON checkpointing, and set up the development environment (Python 3.11+, `anthropic`, `pydantic-ai`, `pydantic`, `sqlalchemy`, `httpx` libraries).

**Week 2** — Implement Steps 1–3 (Research → MVP → Landing Page): wire up Tavily, Serper.dev, and Exa.ai for the research step, build the Claude+PydanticAI pipeline for MVP definition and copy generation, create 2–3 HTML+Tailwind template variants with placeholder tokens, and test the full research-to-HTML flow.

**Week 3** — Implement Steps 4–6 (Domain → Deploy → Analytics): integrate Porkbun API for domain purchase, set up Cloudflare Pages deployment via Direct Upload API, configure Cloudflare DNS zone management, deploy Umami on VPS, and automate analytics script injection into templates.

**Week 4** — Implement Steps 7–8 (Distribute → Monitor): integrate social media posting APIs (LinkedIn, X, Reddit), build the analytics polling and conversion calculation logic, implement go/no-go threshold automation, and wire up EmailOctopus for subscriber tracking.

**Week 5** — Production hardening: add exponential backoff retries and circuit breakers, implement optional human-review checkpoints (email notification with approval link), set up cron scheduling, add Slack/email notifications for pipeline completion and failures, run end-to-end test with a real product idea.

---

Verdandi: Implementation Plan

> **Note (Feb 2026):** The implementation plan below was the original skeleton design. The project has since migrated from Instructor to **PydanticAI**, from raw sqlite3 to **SQLAlchemy 2.0+ ORM**, and added a **FastAPI** REST API layer and **structlog** structured logging. See README.md for current architecture. The plan is retained for historical context.

 Context

 The Verdandi project is a greenfield autonomous product validation factory. Only a strategy document (CLAUDE.md) exists — no code. The goal is to build a Python pipeline that
 autonomously discovers product ideas, validates them through market research, builds landing pages, deploys them, and monitors conversion metrics to make go/no-go decisions.

 This plan covers the first deliverable: a complete skeleton with orchestrator, all Pydantic models, SQLite state management, CLI, and stub implementations for every pipeline step.
 After the skeleton works end-to-end with --dry-run, real API integrations get added one at a time.

 Key user decisions

 - Idea sourcing: Agent discovers ideas autonomously (Step 0 added)
 - Human review: Required before domain purchase, configurable via REQUIRE_HUMAN_REVIEW=true
 - State storage: SQLite from the start
 - Pre-build scoring: Market signals priority (pain severity, frequency, willingness to pay, competitor gaps, TAM)
 - Product focus: Unrestricted — agent decides what categories to explore
 - API keys: Only Anthropic available now; others added incrementally

 ---
 Project Structure

 verdandi/
 ├── CLAUDE.md
 ├── pyproject.toml
 ├── .env.example
 ├── .gitignore
 ├── verdandi/
 │   ├── __init__.py
 │   ├── cli.py              # Click CLI entry point
 │   ├── config.py            # pydantic-settings from .env
 │   ├── db.py                # Database facade (SQLAlchemy sessions + CRUD helpers)
 │   ├── engine.py            # SQLAlchemy engine factory + session maker
 │   ├── orm.py               # ORM table models (replaces schema.sql)
 │   ├── orchestrator.py      # PipelineRunner, step registry, checkpoint/resume
 │   ├── llm.py               # PydanticAI agent wrapper
 │   ├── retry.py             # Exponential backoff + circuit breaker
 │   ├── notifications.py     # Console/email notifications
 │   ├── coordination.py      # TopicReservationManager, dedup, worker identity
 │   ├── tasks.py             # Huey app + task definitions (discover, run_pipeline)
 │   ├── models/
 │   │   ├── __init__.py      # Re-exports all models
 │   │   ├── base.py          # BaseStepResult (id, experiment_id, step_name, timestamps)
 │   │   ├── experiment.py    # Experiment + ExperimentStatus enum
 │   │   ├── idea.py          # IdeaCandidate, PainPoint
 │   │   ├── research.py      # MarketResearch, Competitor, SearchResult
 │   │   ├── scoring.py       # PreBuildScore, ScoreComponent, Decision enum
 │   │   ├── mvp.py           # MVPDefinition, Feature
 │   │   ├── landing_page.py  # LandingPageContent, Testimonial, FAQItem
 │   │   ├── deployment.py    # DeploymentResult, DomainInfo, CloudflareDeployment, AnalyticsSetup
 │   │   ├── distribution.py  # DistributionResult, SocialPost, SEOSubmission
 │   │   └── validation.py    # ValidationReport, MetricsSnapshot, ValidationDecision enum
 │   ├── steps/
 │   │   ├── __init__.py      # Imports all steps (triggers registration)
 │   │   ├── base.py          # AbstractStep + StepContext
 │   │   ├── s0_idea_discovery.py
 │   │   ├── s1_deep_research.py
 │   │   ├── s2_scoring.py
 │   │   ├── s3_mvp_definition.py
 │   │   ├── s4_landing_page.py
 │   │   ├── s5_human_review.py
 │   │   ├── s6_domain_purchase.py
 │   │   ├── s7_deploy.py
 │   │   ├── s8_analytics_setup.py
 │   │   ├── s9_distribution.py
 │   │   └── s10_monitor.py
 │   ├── clients/
 │   │   ├── __init__.py
 │   │   ├── tavily.py
 │   │   ├── serper.py
 │   │   ├── exa.py
 │   │   ├── perplexity.py
 │   │   ├── hn_algolia.py
 │   │   ├── porkbun.py
 │   │   ├── cloudflare.py
 │   │   ├── umami.py
 │   │   ├── emailoctopus.py
 │   │   └── social/
 │   │       ├── __init__.py
 │   │       ├── twitter.py
 │   │       ├── linkedin.py
 │   │       ├── reddit.py
 │   │       └── bluesky.py
 │   ├── api/                 # FastAPI REST API
 │   │   ├── app.py           # Application factory + lifespan
 │   │   ├── middleware.py    # Correlation ID middleware
 │   │   ├── deps.py          # Dependency injection (DbDep, SettingsDep)
 │   │   ├── schemas.py       # Request/response schemas
 │   │   └── routes/          # 6 route modules
 │   └── templates/
 │       └── landing_v1.html  # Tailwind CDN, placeholder tokens
 └── tests/
     ├── conftest.py          # Fixtures: tmp SQLite, mock models
     ├── test_models.py
     ├── test_db.py
     ├── test_orchestrator.py
     ├── test_coordination.py
     ├── test_retry.py
     └── test_api/            # API endpoint tests

 ---
 The 11-Step Pipeline

 Step 0:  Idea Discovery     → IdeaCandidate
 Step 1:  Deep Research       → MarketResearch
 Step 2:  Pre-Build Scoring   → PreBuildScore (GO/NO_GO gate)
 Step 3:  MVP Definition      → MVPDefinition
 Step 4:  Landing Page Gen    → LandingPageContent (rendered HTML)
 Step 5:  Human Review        → blocks pipeline, CLI approval
 Step 6:  Domain Purchase     → DeploymentResult.domain
 Step 7:  Deploy              → DeploymentResult.cloudflare
 Step 8:  Analytics Setup     → DeploymentResult.analytics
 Step 9:  Distribution        → DistributionResult
 Step 10: Monitor             → ValidationReport (GO/ITERATE/NO_GO)

 ---
 Core Architecture

 Orchestrator (orchestrator.py)

 - @register_step decorator registers steps in pipeline order at import time
 - PipelineRunner.run_experiment() iterates steps, checks is_complete() for idempotency, saves results via db.save_step_result()
 - Pipeline pauses at Step 5 (human review) when require_human_review=True — sets status to awaiting_review, sends notification, returns
 - Resumes from last checkpoint on next run via experiment.current_step
 - run_discovery_batch() runs Step 0 only, creates new Experiment for each idea

 Step base class (steps/base.py)

 - AbstractStep with name, step_number, run(ctx), is_complete(ctx), should_skip(ctx)
 - StepContext bundles db, settings, experiment, dry_run, worker_id, correlation_id
 - Each step returns a Pydantic model, saved to SQLite as JSON

 Database schema (orm.py via SQLAlchemy ORM)

 Four tables:
 - experiments — central state: id, status (ExperimentStatus enum), current_step, worker_id, review fields
 - step_results — one row per step per experiment: data_json TEXT stores the full Pydantic model via model_dump_json()
 - pipeline_log — append-only audit trail: experiment_id, step_name, event, message, worker_id, timestamp
 - topic_reservations — coordination: topic_key (unique when active), worker_id, embedding_json, fingerprint, expires_at, status (active/expired/released/completed). Prevents multiple
  workers from pursuing the same idea.

 Config (config.py)

 - pydantic-settings BaseSettings loading from .env
 - All API keys optional except ANTHROPIC_API_KEY
 - Pipeline behavior settings: require_human_review, max_retries, score_go_threshold, monitoring thresholds
 - LLM settings: model, max_tokens, temperature

 CLI (cli.py via Click)

 verdandi discover [--max-ideas N] [--dry-run]
 verdandi run <EXPERIMENT_ID> [--step N] [--stop-after N] [--dry-run]
 verdandi run --all [--dry-run]
 verdandi ls [--status STATUS]
 verdandi inspect <EXPERIMENT_ID> [--step NAME] [--log]
 verdandi review <EXPERIMENT_ID> --approve|--reject [--notes TEXT]
 verdandi monitor [--all-live]
 verdandi archive <EXPERIMENT_ID> [--teardown]
 verdandi check                          # Verify API keys
 verdandi worker [--workers N]           # Start Huey consumer (N worker processes)
 verdandi enqueue discover [--max-ideas N] [--dry-run]   # Enqueue discovery job
 verdandi enqueue run <EXPERIMENT_ID> [--dry-run]        # Enqueue pipeline job
 verdandi reservations [--active-only]   # Show topic reservations
 verdandi serve [--host H] [--port P]   # Start FastAPI API server

 Task queue (tasks.py via Huey)

 - SqliteHuey with broker DB at {data_dir}/huey_queue.db (separate from main DB)
 - discover_ideas_task(max_ideas, dry_run) — enqueued by CLI or periodic schedule
 - run_pipeline_task(experiment_id, dry_run) — enqueued by CLI or after discovery
 - @huey.periodic_task(crontab(hour='*/6')) for automatic discovery (configurable)
 - @huey.lock_task('discovery-lock') prevents concurrent discovery batches
 - Workers started via verdandi worker --workers 4 (wraps huey_consumer)

 Dry-run mode

 - --dry-run flag on CLI → ctx.dry_run = True
 - Each step returns realistic mock data; steps 2-4 run real logic on mock inputs
 - Human review skipped; domain purchase only checks availability; deploy writes HTML locally; no social posts sent
 - Each API client falls back to mock when dry_run=True or API key missing

 Error handling (retry.py)

 - with_retry(): exponential backoff (base_delay * 2^attempt), configurable max_retries
 - CircuitBreaker: per-service, trips after N consecutive failures, auto-resets after timeout
 - Research step (Step 1) degrades gracefully — collects from whichever APIs respond, fails only if all sources fail

 Multi-instance coordination (coordination.py)

 Multiple pipeline workers can run concurrently (3-5 on a single VPS). Coordination prevents duplicate work via a topic reservation table in the shared SQLite database.

 Architecture decisions:
 - SQLite + WAL mode for the skeleton (single machine, 3-5 workers). Migrate to PostgreSQL with FOR UPDATE SKIP LOCKED if scaling beyond that.
 - Huey task queue with SQLite broker — zero extra infrastructure. Workers consume from the queue; each job is one pipeline run for one experiment.
 - Docker Compose for deployment on a Hetzner CX32 (~$7/month, 4 vCPU, 8GB RAM).

 Topic reservation table (TopicReservationRow in orm.py):
 - Workers register topic + embedding before starting Step 0 (Idea Discovery)
 - UNIQUE(topic_key, status) constraint + BEGIN IMMEDIATE = atomic claim (SQLite equivalent of Redis SETNX)
 - TTL-based expiration (default 24h) — if a worker crashes, its reservation expires and another worker can pick up the topic
 - Heartbeat renewal every 6 hours for long-running experiments

 Two-pass idea deduplication (in Step 0):
 1. Fast pass: Normalized keyword fingerprint (Jaccard similarity > 0.6 = candidate duplicate). Zero dependencies.
 2. Semantic pass: Embedding similarity using all-MiniLM-L6-v2 (22MB model, cosine similarity > 0.82 = likely duplicate). Optional dependency.
 3. Confirmation (borderline cases only): Claude structured output comparison via PydanticAI. ~$0.003 per comparison.

 Worker identity: Each worker gets a unique worker_id (hostname + PID or UUID). Stored in reservations and pipeline logs for traceability.

 For the skeleton: We implement the reservation table schema + TopicReservationManager class with try_reserve(), release(), renew(), find_similar_active(). The fingerprint-based dedup
  is included. Embedding similarity is stubbed (returns empty matches) — real implementation added when sentence-transformers is integrated.

 ---
 Build Order (8 phases)

 Phase 0: Update CLAUDE.md

 Append this implementation plan to CLAUDE.md so it serves as the single source of truth for the project. Initialize git repo.

 Phase 1: Foundation

 1. pyproject.toml + .env.example + .gitignore
 2. verdandi/config.py — Settings class (includes worker_id generation)
 3. verdandi/models/base.py — BaseStepResult
 4. verdandi/models/experiment.py — Experiment + ExperimentStatus
 5. verdandi/engine.py + verdandi/orm.py + verdandi/db.py — SQLAlchemy engine, ORM models, Database facade with CRUD (WAL mode, busy_timeout)
 6. verdandi/retry.py — Retry + CircuitBreaker
 7. verdandi/coordination.py — TopicReservationManager (try_reserve, release, renew, find_similar_active, keyword fingerprint dedup)
 8. verdandi/tasks.py — Huey app with SqliteHuey broker, task definitions: discover_ideas_task, run_pipeline_task, periodic discovery via @huey.periodic_task

 Phase 2: All Pydantic models

 7. idea.py, research.py, scoring.py, mvp.py, landing_page.py, deployment.py, distribution.py, validation.py
 8. verdandi/models/__init__.py — re-exports

 Phase 3: Orchestrator + steps framework

 9. verdandi/steps/base.py — AbstractStep, StepContext
 10. verdandi/orchestrator.py — PipelineRunner, register_step
 10a. verdandi/logging.py — structlog configuration
 10b. verdandi/protocols.py — Protocol interfaces (StepProtocol, etc.)
 11. verdandi/llm.py — LLMClient (PydanticAI + Anthropic)
 12. verdandi/notifications.py — console + email stubs

 Phase 4: Step stubs (all return mock data)

 13. s0_idea_discovery.py through s10_monitor.py — each with run() returning mock Pydantic models
 14. verdandi/steps/__init__.py — import all to trigger registration

 Phase 5: API client stubs

 15. All files in verdandi/clients/ — each with real interface, mock fallbacks

 Phase 6: CLI + template + REST API

 16. verdandi/cli.py — all commands (including `serve` for FastAPI)
 17. verdandi/templates/landing_v1.html — one Tailwind template with {{TOKEN}} placeholders
 17a. verdandi/api/ — FastAPI application factory, middleware, deps, schemas, 6 route modules

 Phase 7: Tests

 18. tests/conftest.py — fixtures (tmp SQLite, mock models)
 19. tests/test_models.py, test_db.py, test_orchestrator.py

 ---
 Dependencies

 anthropic>=0.40.0
 pydantic-ai[anthropic,logfire]>=1.56.0
 pydantic>=2.10.0
 pydantic-settings>=2.7.0
 sqlalchemy>=2.0.0
 click>=8.1.0
 httpx>=0.28.0
 python-dotenv>=1.0.0
 huey>=2.5.0
 structlog>=24.0.0
 fastapi>=0.115.0
 uvicorn>=0.34.0

 Dev: pytest>=8.0.0, pytest-asyncio, hypothesis, ruff>=0.8.0, mypy>=1.10

 ---
 Verification

 After implementation, the following should work:

 # Install
 pip install -e ".[dev]"

 # Dry-run: discover ideas (mock data)
 verdandi discover --max-ideas 3 --dry-run -v

 # List created experiments
 verdandi ls

 # Run full pipeline in dry-run for one experiment
 verdandi run <ID> --dry-run -v

 # Inspect results
 verdandi inspect <ID>
 verdandi inspect <ID> --log

 # Approve review (when not in dry-run)
 verdandi review <ID> --approve

 # View topic reservations
 verdandi reservations

 # Start worker (Huey consumer with 2 processes)
 verdandi worker --workers 2

 # Enqueue jobs (in another terminal)
 verdandi enqueue discover --max-ideas 3 --dry-run
 verdandi enqueue run <ID> --dry-run

 # Run tests
 pytest tests/ -v

 # Verify API key config
 verdandi check

 All commands should complete without errors. The pipeline should log each step's execution, save mock results to SQLite, and the experiment should progress through all statuses.
 Tests should pass with in-memory SQLite. The worker command should start Huey consumer processes that pick up enqueued jobs. Topic reservations should be visible and prevent
 duplicate idea claims across workers.

 ---

## Conclusion

The product validation factory is architecturally straightforward but tooling-choice-critical. **Three non-obvious findings** emerged from this research. First, Cloudflare Registrar — despite having the best pricing and DNS — cannot automate domain purchases, making Porkbun the correct choice. Second, nearly every AI landing page builder lacks an API, making the humble template-fill approach not just cheapest but most automatable. Third, no existing project implements this full pipeline — Startup Blueprint covers research-to-landing-page manually, n8n's MVP Builder covers idea-to-deployment without research, but the autonomous loop from deep research through monitoring and go/no-go decisions is genuinely novel territory.

The key technical insight is that **reliability beats sophistication** for autonomous operation. Template-fill beats AI page generators (zero failure rate vs. ~85%). Custom Python scripts beat agent frameworks (full debuggability, no abstraction leaks). Cron beats workflow engines (the pipeline runs weekly, not continuously). The entire system can be built by a single engineer in 5 weeks and run for under $85/month while validating dozens of product ideas autonomously.