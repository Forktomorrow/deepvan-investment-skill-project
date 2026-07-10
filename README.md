# Deepvan Investment Research Skill

A Codex skill and companion toolset for turning investment creator content into:

- portfolio snapshots
- rebalance events
- OCR-extracted holding tables
- recency-weighted research skills
- credibility/backtest-ready claim records
- Feishu bot monitoring messages

The project is designed around Deepvan-style Zhihu content, but the schema can be reused for other public investment creators.

## Current Local Corpus Status

As of the local run on 2026-07-10, there are two inventory views:

Loose captured rows:

- profile list rows captured: 126
- cached original files: 47
- deduped original rows: 46
- observed range in mixed cache: 2024-02-01 to 2026-07-10

Strict canonical URL coverage:

- canonical original URLs discovered from profile lists: 101
- cached originals: 106
- full-text coverage: 100% for the currently discovered canonical profile URLs; cache is 104.95% of the current profile list because it includes extra previously discovered originals
- missing canonical originals: 0
- parsed cached date range: 2024-07-23 to 2026-07-10
- cached text: about 271,264 characters
- image URLs observed: 2,078
- OCR-bearing rows: 53
- OCR text: about 59,222 characters
- current known gap: profile pagination itself may still need extension for a deeper two-to-three-year archive

Recommended next backfill: extend profile discovery itself to one year and later two to three years. For old archive mode, keep text and OCR text only.

## Repository Layout

```text
skill/deepvan-investment-research/
  SKILL.md
  references/
    portfolio-schema.md
    research-skill-taxonomy.md
    credibility-rubric.md
    data-strategy.md

tools/
  deepvan_candidate_filter.py
  deepvan_monitor.py
  deepvan_image_ocr.py
  deepvan_pipeline.py
  deepvan_profile_report.py
  deepvan_evaluator.py
  deepvan_period_report.py
  scripts/vision_ocr.swift

config.example.json
credibility_config.example.json
examples/
```

## Install The Skill Locally

Copy the skill folder into Codex skills:

```bash
mkdir -p ~/.codex/skills
cp -R skill/deepvan-investment-research ~/.codex/skills/
```

Then invoke it in Codex:

```text
Use $deepvan-investment-research to extract portfolio changes and research skills from this post.
```

## Dependencies

Required:

- Python 3.11+
- Standard library only for the core extraction pipeline

Optional:

- macOS Command Line Tools with `swiftc`, for local Vision OCR
- `curl` and `sips`, used by the OCR helper on macOS
- Feishu incoming webhook, passed through `DEEPVAN_NOTIFY_WEBHOOK`
- Zhihu developer/search token if using official search, passed through an environment variable

Do not commit API keys, cookies, login state, or webhook URLs.

## Data Strategy

Use a cost-controlled pipeline:

1. Discover profile/list items.
2. Canonicalize original URLs.
3. Cache all accessible original full text for the chosen window.
4. Score investment and portfolio candidates for analysis priority.
5. OCR relevant images once.
6. Store OCR text, not raw images.
7. Extract portfolio snapshots and events.
8. Generate thinking/style skills and credibility reports.

Weighting guidance:

- monitoring: 30D window, 30-45 day half-life
- skill abstraction: 365D window, 60-90 day half-life
- archive study: 2-3Y text-only corpus, old evidence capped as style prior
- credibility scoring: report by period rather than recency-weighted aggregate

## Example Commands

```bash
cd tools
python3 -m py_compile *.py
python3 deepvan_candidate_filter.py --profile-dir ../data/profile_lists --limit 80 --out ../data/profile_candidates.json
python3 deepvan_image_ocr.py --dirs ../data/original_pages_recent --max-images-per-article 4 --limit 20
python3 deepvan_pipeline.py --config ../config.example.json --candidate-limit 80 --fetch-budget 10
python3 deepvan_corpus_inventory.py --root .. --out data/corpus_inventory.json --missing-out data/backfill_missing_urls.json
```

Send a Feishu test message:

```bash
DEEPVAN_NOTIFY_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/...' \
python3 tools/deepvan_pipeline.py --config config.example.json --candidate-limit 80 --fetch-budget 10 --send detailed
```

## Publishing Notes

For GitHub, commit the skill, tools, config examples, and documentation. Do not commit local `data/`, `state/`, downloaded images, OCR binaries, report caches, API keys, cookies, or webhooks unless they are sanitized examples.

## Disclaimer

This project structures public creator research and historical claims. It is not investment advice.
