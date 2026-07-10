# Skill Output Example

## Corpus Inventory

- items: 101 canonical original URLs from profile lists
- full_text: 106 cached originals
- coverage: 100% of current canonical profile URLs
- missing: 0 current profile URLs
- OCR_items: 53
- parsed_cached_date_range: 2024-07-23 to 2026-07-10
- known_gaps: current profile list is fully cached; deeper 2-3Y profile pagination is still needed

## Portfolio Snapshot

portfolio_id: `叫兽指数国际版/全球配置版`  
as_of: `2025-07-25`  
completeness: `complete`  
total_weight: `100.0%`

| Asset | Weight |
|---|---:|
| SHV（美国短期国债ETF） | 10.0% |
| 纳斯达克100（QDII） | 17.5% |
| 标普500（QDII） | 17.5% |
| 摩根日本精选（QDII） | 7.5% |
| 工银全球股票精选（QDII） | 10.0% |
| 恒生医药ETF | 7.5% |
| 印度基金LOF | 7.5% |
| 摩根欧洲动力 | 7.5% |
| 黄金 | 5.0% |
| 国金量化多因子 | 5.0% |
| 博时恒生高股息率ETF | 5.0% |
| 现金 | 0.0% |

## Research Skill

Skill name: Portfolio-first expression  
Trigger: creator gives multiple assets, account versions, or weights  
Decision rules:

- Keep each portfolio version independent.
- Complete tables overwrite the portfolio version.
- Event-only posts remain rebalance events until explicit new weights appear.
- Do not double count sector buckets and underlying stocks.

Falsifier:

- weights cannot reconcile to 100%
- source is not Tier A
- industry bucket and individual names are mixed at the same level
