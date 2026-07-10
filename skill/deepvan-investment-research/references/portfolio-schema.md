# Portfolio Schema

Use this reference when extracting holdings, portfolio snapshots, or rebalance events.

## Core Objects

`PortfolioSnapshot`:

```json
{
  "portfolio_id": "叫兽指数国际版/全球配置版",
  "as_of": "2025-07-25",
  "source_url": "",
  "evidence_tier": "A",
  "completeness": "complete",
  "total_weight": 1.0,
  "holdings": [
    {
      "asset": "纳斯达克100（QDII）",
      "symbol": "QQQ",
      "market": "domestic-access-global",
      "weight": 0.175,
      "source_text": "纳斯达克100（QDII） ... 17.5%"
    }
  ]
}
```

`RebalanceEvent`:

```json
{
  "date": "2026-07-10",
  "portfolio_id": "unknown_or_specific",
  "action": "trim/add/sell/stop_loss/hold/table_snapshot",
  "asset": "南方东西精选",
  "old_weight": null,
  "new_weight": null,
  "reason": "加到港股通标的南方东西精选...",
  "variable": "红利/股东回报/防守",
  "evidence_tier": "A",
  "source_url": ""
}
```

## Portfolio ID Rules

Keep portfolio versions separate:

- `叫兽指数国际版/全球配置版`: SHV, Nasdaq/QQQ, S&P/SPY, Japan, Europe, India, gold, global equity/QDII, XBI, Google, etc.
- `叫兽指数内地版/公募基金版`: domestic funds and ETFs that can be bought on mainland platforms.
- `纯A版`: A-share stocks, A-share ETFs, cash, or domestic quant products only.
- `Deepvan当前跟踪组合`: answer-level complete holdings when the post states "当前持仓" or equivalent.

Never make `国内 + 国际 = 100%` unless the source explicitly says it is one combined portfolio. Normally each `portfolio_id` must sum to 100% independently.

## Complete Table Rules

A table is complete when:

- It has a ratio/weight column.
- The recognized weights sum between 95% and 105%.
- It contains at least three assets.
- It is from Tier A evidence.

When a complete table appears, overwrite that `portfolio_id` snapshot as of the source date. Keep older snapshots for history and backtests.

## Event-Only Rules

If the source says "减仓", "止盈", "止损", "加到", "平出", "换入", or similar without explicit new weights:

- Record a `RebalanceEvent`.
- Do not update snapshot weights except for zero-weight actions such as clear/sell all/平出 when context clearly means closed.
- If the event names a portfolio version, attach the `portfolio_id`; otherwise set it to `unknown_or_specific`.

## Anti-Duplication Rules

- Do not double count sector buckets and underlying stocks. Example: `半导体 42.5%` is a bucket; its inner six stocks are not additional portfolio weights unless the post gives a separate sub-allocation.
- Do not merge a domestic-buyable QDII asset into a separate "international bucket" unless that portfolio version uses such a bucket.
- Canonicalize obvious aliases, but preserve raw names in `raw_asset`.
- Deduplicate by source URL, date, action, asset, weight, and a short evidence snippet.
