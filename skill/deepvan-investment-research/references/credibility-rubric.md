# Credibility Rubric

Use this reference when scoring Deepvan-style investment claims.

## Total Score

```text
total =
  direction_accuracy * 30%
+ excess_return * 25%
+ drawdown_control * 15%
+ variable_validation * 15%
+ executability * 10%
+ evidence_quality * 5%
```

Each component is scored from 0 to 100. Keep pending items out of aggregate scores unless the user asks for mark-to-date scoring.

## Yes/No Record Format

For each claim, produce a compact audit row:

```json
{
  "claim_id": "",
  "date": "",
  "topic": "AI / 半导体",
  "asset": "",
  "direction": "bullish/bearish/neutral",
  "benchmark": "",
  "horizon": "20D",
  "direction_win": "yes/no/pending/invalid",
  "excess_return_win": "yes/no/pending/invalid",
  "drawdown_ok": "yes/no/pending/invalid",
  "variable_validated": "yes/no/mixed/pending/invalid",
  "executability_ok": "yes/no/mixed",
  "evidence_quality": "A/B/C",
  "short_reason": ""
}
```

## Topic Metrics

- `AI / 半导体`: win rate, excess return, max drawdown, capex/storage/HBM validation.
- `黄金`: win rate, average return, TIPS/BEI/real-rate validation.
- `钨 / 有色`: theme hit rate, holding-period return, supply/export-control validation.
- `XBI / 创新药`: interest-rate sensitivity validation, relative return vs XBI/IBB.
- `A股内需`: bearish accuracy, policy/consumption/data validation.
- `全球配置 / 叫兽指数`: portfolio Sharpe, max drawdown, benchmark-relative return.

## Benchmark Selection

Prefer a benchmark that matches the tradable expression:

- A-share broad market: CSI 300, CSI 500, Wind All A, or a user-selected ETF.
- A-share semiconductor: semiconductor ETF or comparable index.
- US large-cap: SPY or QQQ.
- Biotech: XBI or IBB.
- Gold: GLD, XAU, or domestic gold ETF.
- Multi-asset portfolio: blended benchmark matching starting weights when possible.

If no benchmark is available, mark excess-return fields `pending` or `invalid`.

## Evidence Quality

- `A`: original full text, screenshot/OCR table, or transcript.
- `B`: original metadata, snippet, title, homepage list.
- `C`: third-party summary or inferred claim.

Portfolio facts should use only A by default.
