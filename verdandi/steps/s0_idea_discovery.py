"""Step 0: Idea Discovery — find product ideas worth validating."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from verdandi.models.idea import IdeaCandidate, PainPoint
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel

_MOCK_IDEAS = [
    {
        "title": "DevLog — Automated Developer Changelog",
        "one_liner": "Automatically generate beautiful changelogs from git commits and PRs",
        "problem_statement": "Developers hate writing changelogs manually but users need them. Most projects either skip changelogs entirely or produce low-quality ones.",
        "target_audience": "Open-source maintainers and small SaaS teams (1-20 devs)",
        "category": "developer-tools",
        "pain_points": [
            {
                "description": "Writing changelogs is tedious and often skipped",
                "severity": 6,
                "frequency": "weekly",
                "source": "HackerNews",
                "quote": "I just stopped maintaining a changelog after v2",
            },
            {
                "description": "Auto-generated changelogs from commits are unreadable",
                "severity": 7,
                "frequency": "weekly",
                "source": "Reddit r/programming",
                "quote": "",
            },
        ],
        "existing_solutions": ["release-please", "conventional-changelog", "changelog.md manual"],
        "differentiation": "AI-powered summarization that produces human-quality prose, not just commit lists",
    },
    {
        "title": "FormShield — AI-Powered Form Spam Detection",
        "one_liner": "Block spam form submissions without CAPTCHAs using AI content analysis",
        "problem_statement": "Contact forms and signup forms get flooded with spam. CAPTCHAs hurt conversion rates. Honeypots catch only basic bots.",
        "target_audience": "Small business owners and indie developers with public-facing forms",
        "category": "security",
        "pain_points": [
            {
                "description": "Spam submissions waste time and pollute databases",
                "severity": 7,
                "frequency": "daily",
                "source": "Reddit r/webdev",
                "quote": "I get 50+ spam submissions a day on my contact form",
            },
            {
                "description": "CAPTCHAs reduce form completion rates by 10-30%",
                "severity": 8,
                "frequency": "daily",
                "source": "Baymard Institute",
                "quote": "",
            },
        ],
        "existing_solutions": ["reCAPTCHA", "Akismet", "Honeypot fields", "Turnstile"],
        "differentiation": "Zero-friction for users, analyzes content semantically rather than behavior patterns",
    },
    {
        "title": "PriceTrack — Competitor Pricing Monitor",
        "one_liner": "Get instant alerts when competitors change their pricing pages",
        "problem_statement": "SaaS companies need to monitor competitor pricing but checking manually is impractical. Most change detection tools are too generic.",
        "target_audience": "SaaS founders and product managers at companies with 5+ competitors",
        "category": "competitive-intelligence",
        "pain_points": [
            {
                "description": "Missing competitor price changes leads to lost revenue",
                "severity": 8,
                "frequency": "monthly",
                "source": "Reddit r/SaaS",
                "quote": "Our competitor dropped prices 30% and we didn't notice for 2 months",
            },
            {
                "description": "Generic monitoring tools produce too many false positives",
                "severity": 6,
                "frequency": "weekly",
                "source": "HackerNews",
                "quote": "",
            },
        ],
        "existing_solutions": ["Visualping", "Kompyte", "Crayon", "manual checking"],
        "differentiation": "Specifically designed for pricing pages with structured data extraction",
    },
    {
        "title": "MeetingBrief — Pre-Meeting Context Generator",
        "one_liner": "Get a one-page brief about everyone you're meeting with, auto-generated before each call",
        "problem_statement": "Salespeople and founders waste time researching meeting participants or go in blind. LinkedIn stalking before each call is tedious.",
        "target_audience": "B2B salespeople, founders, and account managers with 5+ external meetings per week",
        "category": "sales-tools",
        "pain_points": [
            {
                "description": "Going into meetings without context wastes the first 10 minutes",
                "severity": 7,
                "frequency": "daily",
                "source": "Reddit r/sales",
                "quote": "",
            },
            {
                "description": "Manually researching each participant takes 15-20 minutes",
                "severity": 6,
                "frequency": "daily",
                "source": "HackerNews",
                "quote": "I spend an hour a day just prepping for calls",
            },
        ],
        "existing_solutions": ["LinkedIn Sales Navigator", "Clearbit", "manual research"],
        "differentiation": "Fully automated, integrates with calendar, delivers brief 30 min before meeting",
    },
    {
        "title": "StatusSnap — Beautiful Status Pages in 60 Seconds",
        "one_liner": "Create a professional status page for your product without any configuration",
        "problem_statement": "Every SaaS needs a status page but setting one up is surprisingly complex. Existing solutions are either expensive or require significant setup.",
        "target_audience": "Indie hackers and small SaaS teams who need a status page but don't want to manage one",
        "category": "developer-tools",
        "pain_points": [
            {
                "description": "Existing status page tools cost $29-99/month for basic features",
                "severity": 6,
                "frequency": "monthly",
                "source": "Reddit r/SaaS",
                "quote": "Statuspage.io wants $79/month for what should be a simple page",
            },
            {
                "description": "Self-hosted alternatives require DevOps knowledge",
                "severity": 7,
                "frequency": "monthly",
                "source": "HackerNews",
                "quote": "",
            },
        ],
        "existing_solutions": ["Statuspage.io", "Instatus", "Cachet (self-hosted)", "Upptime"],
        "differentiation": "Zero-config setup: connect your monitoring tool and get a beautiful page instantly",
    },
]


@register_step
class IdeaDiscoveryStep(AbstractStep):
    name = "idea_discovery"
    step_number = 0

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_idea(ctx)
        # Real implementation will use research APIs + LLM
        return self._mock_idea(ctx)

    def _mock_idea(self, ctx: StepContext) -> IdeaCandidate:
        mock = random.choice(_MOCK_IDEAS)
        return IdeaCandidate(
            experiment_id=ctx.experiment.id or 0,
            title=mock["title"],
            one_liner=mock["one_liner"],
            problem_statement=mock["problem_statement"],
            target_audience=mock["target_audience"],
            category=mock["category"],
            pain_points=[PainPoint(**pp) for pp in mock["pain_points"]],
            existing_solutions=mock["existing_solutions"],
            differentiation=mock["differentiation"],
            worker_id=ctx.worker_id,
        )
