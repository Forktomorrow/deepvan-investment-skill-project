# Data Strategy

Use this reference when planning backfills and cost control.

## Corpus Inventory

Always report:

- raw list items discovered
- full-text pages cached
- unique original rows after dedupe
- OCR-bearing rows
- date range
- year/month distribution
- source mix: answers, articles, pins, videos, third-party summaries
- known gaps

## Backfill Windows

Recommended windows:

- `30D`: current portfolio and near-term trading logic.
- `90D`: recent skill extraction and active themes.
- `365D`: annual skill review and credibility scoring.
- `2-3Y`: archive mode. Store text and OCR text, but avoid heavy image retention.

For building a serious skill, candidate-only sampling is not enough. Use the candidate filter only to prioritize the next browser/API fetches. The target state is full original text coverage for all accessible original posts in the chosen window.

## Completeness Targets

Track these numbers before claiming the skill is corpus-backed:

- profile/list items discovered
- canonical original URLs discovered
- full-text originals cached
- full-text coverage ratio
- OCR attempted images
- OCR-bearing originals
- date min/max
- monthly distribution
- source types: answer, article, pin, video/transcript

Minimum recommendation:

- current monitor: 90D full-text coverage
- skill extraction: 365D full-text coverage
- style/thinking abstraction: 2-3Y text archive when accessible

## Recency Weighting

Do not use one fixed weight for every task.

- Current monitoring: 30D window, half-life 30-45 days.
- Skill abstraction: 365D window, half-life 60-90 days.
- Long-term style prior: 2-3Y archive, old items capped at low influence.
- Credibility backtest: no recency weighting inside each period; report by period.

If the user says 120 days is too long, use 60 days as the default skill half-life and show 90D/365D sensitivity.

## Storage Policy

- Keep: canonical URL, title, author, publish time, full text, OCR text, image source URL, extracted records.
- Optional temporary: downloaded images for OCR.
- Drop or ignore after OCR: raw images, ads, avatars, decorative images.
- Never commit API keys, cookies, webhooks, or login state.

## Cost Controls

1. Discover via profile lists or official search APIs.
2. Score candidates with investment/portfolio keywords.
3. Open only high-value missing originals.
4. Cache by canonical URL.
5. OCR only relevant images with table/chart/holding keywords.
6. Run expensive market-data backtests after extraction has stable claim records.
