---
name: deepvan-investment-research
description: Extract portfolio changes, portfolio snapshots, investment-research skills, thinking structures, answer style patterns, and credibility-evaluation fields from Deepvan-style creator posts, Zhihu answers/articles/pins, screenshots, OCR text, and creator-monitoring corpora. Use when Codex needs to turn Chinese investment creator content into structured holdings, rebalance events, recency-weighted research logic, falsifiable variables, style-aware analysis, or backtest-ready scoring records.
---

# Deepvan Investment Research

Use this skill to process creator investment content into a research-grade dataset and reusable投研框架. Treat it as an extraction and reasoning workflow, not as financial advice.

Do not claim to be Deepvan or imitate a living creator verbatim. You may use a Deepvan-inspired analytical structure: direct, causal, skeptical of vague narratives, portfolio-aware, and explicit about falsifiers.

## Evidence Rules

Label every extracted fact:

- `Tier A`: original creator text, original screenshot/OCR table, or original video transcript.
- `Tier B`: original title, snippet, metadata, or visible homepage list item.
- `Tier C`: third-party summary, comment, repost, or inferred pattern.

Use only `Tier A` for portfolio facts unless the user explicitly allows provisional sources. Use `Tier B/C` for discovery and candidate ranking only.

## Core Workflow

1. Build the corpus inventory.
   - Count raw list items, cached full-text items, OCR-bearing items, date range, source types, and gaps.
   - For serious skill extraction, prefer full original backfill over candidate-only sampling.
   - For long backfills, store text and OCR text; do not keep images after OCR unless the user asks.

2. Extract portfolio records.
   - Read `references/portfolio-schema.md` before extracting holdings or rebalance events.
   - Maintain separate `portfolio_id` values. Do not merge domestic and international versions.
   - Complete portfolio tables override that portfolio version. Event-only posts do not rewrite full weights unless new weights are explicit.

3. Extract research skills.
   - Read `references/research-skill-taxonomy.md` before summarizing methodology.
   - Produce reusable skills as operational instructions with inputs, decision rules, outputs, falsifiers, and examples.
   - Do not only output theme labels or vague summaries.

4. Extract thinking and answer style.
   - Read `references/thinking-and-style.md` before producing a style-aware answer or "how this creator would reason" output.
   - Emulate the reasoning pattern, not the exact voice. Avoid catchphrases, insults, or personal identity claims.
   - Include how the answer should be structured: traded question, dominant variable, mapping, portfolio action, falsifier, review plan.

5. Weight evidence by time.
   - Report at least three windows when enough data exists: 30D, 90D, and 365D.
   - Default half-life for method abstraction: 60-90 days. Use older posts as style priors, not dominant evidence.
   - If the user asks for a multi-year review, keep old records but show a separate "legacy evidence" section.

6. Prepare credibility scoring.
   - Read `references/credibility-rubric.md` before scoring.
   - Convert claims into backtest-ready records with asset, direction, start date, benchmark, horizon, and variable checks.
   - Mark records `pending` or `invalid` if price data, timing, or asset mapping is insufficient.

## Output Contract

For a normal extraction task, return:

```text
Corpus inventory:
- items:
- full_text:
- OCR_items:
- date_range:
- source_mix:
- known_gaps:

Portfolio snapshots:
- portfolio_id:
- as_of:
- completeness:
- total_weight:
- holdings:

Rebalance events:
- date / action / asset / old_weight / new_weight / reason / evidence_tier / source_url

Research skills:
- skill_name:
- trigger:
- inputs:
- decision_rules:
- output:
- falsifier:
- evidence_examples:

Thinking/style:
- answer_structure:
- tone_constraints:
- recurring_moves:
- forbidden_mimicry:

Credibility records:
- claim_id / topic / asset / direction / date / benchmark / horizons / status
```

## Data Strategy

For Zhihu-style corpora:

- Use official APIs, user-provided exports, or logged-in visible browser pages. Do not bypass platform access controls.
- Prefer homepage lists for discovery, then open only high-value candidates.
- Cache by canonical URL. Reuse cached full text.
- OCR only images likely to contain tables, charts, holdings, or text screenshots.
- After OCR, save extracted text and source URL; images can be deleted or ignored.

For project automation, use scripts in `scripts/` when present instead of rewriting extraction logic.

## Reference Map

- `references/portfolio-schema.md`: portfolio IDs, complete tables, event-only rules, anti-duplication.
- `references/research-skill-taxonomy.md`: detailed Deepvan-style skill taxonomy and templates.
- `references/thinking-and-style.md`: thought process, answer architecture, and style constraints.
- `references/credibility-rubric.md`: scoring dimensions, Yes/No record format, benchmarks.
- `references/data-strategy.md`: crawl windows, recency weights, cache and OCR policy.
