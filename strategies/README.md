# Discovery Strategies

This directory contains all discovery strategies — both the built-in defaults (`disruption.yaml`, `moonshot.yaml`) and user-defined custom strategies.

## What is a Discovery Strategy?

A discovery strategy defines the complete "personality" of a discovery agent:
- **Research queries** — what to search for
- **LLM prompts** — how to analyze and synthesize ideas
- **Source preferences** — which platforms to prioritize (Reddit, HN, Twitter)
- **Scoring guidance** — how to weight different factors

## Built-in Strategies

Verdandi ships with two default strategies defined as YAML files in this directory:
- **disruption.yaml** — Problem-first discovery (broken workflows, user complaints)
- **moonshot.yaml** — Futures-first discovery (emerging tech, new capabilities)

You can edit these files directly to customize the defaults.

## Creating Custom Strategies

### Quick Start

```bash
# Interactive wizard
verdandi strategy create

# Or copy a template
cp strategies/examples/b2b-saas.yaml strategies/my-strategy.yaml
verdandi strategy validate strategies/my-strategy.yaml
```

### Strategy File Format

Strategies are defined in YAML files with the following structure:

```yaml
name: "B2B SaaS Hunter"
discovery_type: "disruption"  # or "moonshot"

# Phase 1: Research queries
discovery_queries:
  - "B2B SaaS pain points in {industry}"
  - "{industry} software market trends 2024"
  - "Enterprise software adoption {industry}"

discovery_perplexity_question: |
  What specific workflows or processes do B2B companies in niche
  industries constantly complain about being manual or broken?

# Phase 1: LLM prompts for discovery
discovery_system_prompt: |
  You are a B2B-focused problem discovery agent...

discovery_user_preamble: |
  Analyze the research data below to find ONE specific problem...

# Phase 2: LLM prompt for idea synthesis
synthesis_system_prompt: |
  Based on the following problem report, propose ONE specific product...

# Source preferences
prioritize_reddit: true
prioritize_hn: true
prioritize_twitter: false

# Scoring guidance
scoring_guidance: |
  This is a B2B SaaS idea. Prioritize pain_severity (0.35) and
  tam_size (0.30) over other factors.

# Output model type
discovery_output_model: "ProblemReport"  # or "OpportunityReport"
```

### Field Reference

#### Required Fields

- **name** (string) — Human-readable label for logging
- **discovery_type** (string) — Either "disruption" or "moonshot"
- **discovery_queries** (list) — Search queries for research phase
- **discovery_perplexity_question** (string) — Synthesis question for Perplexity
- **discovery_system_prompt** (string) — System prompt for Phase 1 discovery
- **synthesis_system_prompt** (string) — System prompt for Phase 2 idea synthesis
- **discovery_output_model** (string) — Either "ProblemReport" or "OpportunityReport"

#### Optional Fields

- **discovery_user_preamble** (string) — Prepended to Phase 1 user prompt (default: "")
- **prioritize_reddit** (bool) — Include Reddit searches (default: true)
- **prioritize_hn** (bool) — Include HackerNews searches (default: true)
- **prioritize_twitter** (bool) — Include Twitter/X searches (default: true)
- **scoring_guidance** (string) — Guidance for scoring step (default: "")

### Query Templates

Discovery queries can use placeholder variables:
- `{industry}` — Replaced with target industry
- `{keyword}` — Replaced with keyword
- `{year}` — Replaced with current year

Example:
```yaml
discovery_queries:
  - "AI applications in {industry} {year}"
  - "Regulatory compliance {industry} 2024"
```

### Scoring Guidance

The `scoring_guidance` field lets you customize how ideas are scored. Mention which scoring components to prioritize:

- **pain_severity** — How painful is the problem?
- **tam_size** — Total addressable market size
- **solution_clarity** — How clear is the solution?
- **market_timing** — Is now the right time?
- **team_capability** — Can a solo dev build this?
- **competitive_advantage** — How defensible is it?

Example:
```yaml
scoring_guidance: |
  This is a climate tech idea. Prioritize market_timing (0.25)
  due to regulatory drivers, and tam_size (0.25) for impact potential.
  Pain severity matters less than growth trajectory.
```

## Using Custom Strategies

```bash
# List all strategies
verdandi strategy list

# View strategy details
verdandi strategy show my-strategy

# Validate a strategy file
verdandi strategy validate strategies/my-strategy.yaml

# Use in discovery
verdandi discover --strategy my-strategy --max-ideas 5
```

## Example Strategies

See the `examples/` subdirectory for templates:
- **b2b-saas.yaml** — B2B SaaS focus with Reddit prioritization
- **climate-tech.yaml** — Climate and sustainability opportunities
- **vertical-ai.yaml** — AI applications in specific verticals

## Strategy Naming

- File names should be lowercase with hyphens: `my-strategy.yaml`
- Strategy names can be more readable: "My Strategy Name"
- Custom strategies with the same name as built-ins will override them

## Tips

1. **Start specific** — Target one industry or user group, not "businesses" broadly
2. **Customize prompts** — The discovery and synthesis prompts are the most powerful levers
3. **Match discovery_type** — Use "disruption" for problem-focused, "moonshot" for trend-focused
4. **Test with dry-run** — `verdandi discover --strategy my-strategy --dry-run` to validate
5. **Iterate on scoring** — Adjust `scoring_guidance` based on results

## Troubleshooting

**Strategy not found:**
```bash
verdandi strategy list  # Check available strategies
verdandi strategy validate strategies/my-strategy.yaml  # Check validation
```

**YAML errors:**
- Use `|` for multi-line strings
- Quote strings with special characters
- Check indentation (2 spaces, no tabs)

**Validation errors:**
```bash
verdandi strategy validate strategies/my-strategy.yaml
```
Will show exactly which fields are missing or invalid.
