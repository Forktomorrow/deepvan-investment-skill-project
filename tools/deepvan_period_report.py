#!/usr/bin/env python3
"""
Build period and monthly Deep Van portfolio/research reports from stored items.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

import deepvan_monitor as monitor


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def item_date(item: dict) -> dt.date | None:
    ts = item.get("EditTime")
    if not ts:
        return None
    return dt.datetime.fromtimestamp(int(ts)).date()


def month_range(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    out = []
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        nxt = dt.date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
        out.append((cur, min(end, nxt - dt.timedelta(days=1))))
        cur = nxt
    return out


def build_queries(start: dt.date, end: dt.date) -> list[str]:
    terms = [
        "持仓", "仓位", "组合", "调仓", "叫兽指数", "加仓", "减仓", "清仓", "止盈", "止损",
        "A股行情", "美股", "黄金", "钨", "半导体", "AI 算力", "XBI", "Meta CapEx", "内需", "出海",
    ]
    names = ["Deep Van", "Deepvan"]
    queries = []
    for m_start, _ in month_range(start, end):
        month_tokens = [f"{m_start.year}.{m_start.month:02d}", f"{m_start.year}年{m_start.month}月"]
        for name in names:
            for token in month_tokens:
                queries.append(f"{name} {token}")
                for term in terms:
                    queries.append(f"{name} {token} {term}")
    return list(dict.fromkeys(queries))


def backfill_period(config: dict, start: dt.date, end: dt.date, limit: int | None) -> None:
    queries = build_queries(start, end)
    if limit:
        queries = queries[:limit]
    rows = monitor.search_many(config, queries, f"period_{start}_{end}")
    deduped = monitor.dedupe_store()
    print(f"period backfill fetched={len(rows)} deduped_store={len(deduped)}")


def collect_records(items: list[dict], config: dict, start: dt.date, end: dt.date) -> list[dict]:
    records = []
    for item in items:
        d = item_date(item)
        if not d or d < start or d > end:
            continue
        for record in monitor.extract_rebalance_records(item, config):
            records.append(record)
    seen = set()
    out = []
    for r in sorted(records, key=lambda x: (x.get("date") or "", x.get("source_url") or ""), reverse=True):
        key = json.dumps({k: r.get(k) for k in ["date", "action", "asset", "weight", "source_url"]}, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            out.append(r)
            seen.add(key)
    return out


def summarize_records(records: list[dict]) -> dict:
    by_market: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_asset: dict[str, int] = {}
    for r in records:
        by_market[r.get("market") or "未分类"] = by_market.get(r.get("market") or "未分类", 0) + 1
        by_action[r.get("action") or "未知"] = by_action.get(r.get("action") or "未知", 0) + 1
        by_asset[r.get("asset") or "未知"] = by_asset.get(r.get("asset") or "未知", 0) + 1
    return {"market": by_market, "action": by_action, "asset": by_asset}


def fmt_weight(w) -> str:
    if w is None:
        return "未知"
    return f"{float(w) * 100:.1f}%"


def report_block(title: str, records: list[dict]) -> list[str]:
    summary = summarize_records(records)
    lines = [f"## {title}", "", f"- 调仓/持仓信号数：{len(records)}"]
    if summary["market"]:
        lines.append("- 市场分布：" + "；".join(f"{k} {v}" for k, v in sorted(summary["market"].items())))
    if summary["action"]:
        top_actions = sorted(summary["action"].items(), key=lambda kv: kv[1], reverse=True)[:8]
        lines.append("- 动作分布：" + "；".join(f"{k} {v}" for k, v in top_actions))
    if summary["asset"]:
        top_assets = sorted(summary["asset"].items(), key=lambda kv: kv[1], reverse=True)[:10]
        lines.append("- 高频资产：" + "；".join(f"{k} {v}" for k, v in top_assets))
    lines += ["", "### 明细", ""]
    for r in records[:30]:
        symbol = f" {r.get('symbol')}" if r.get("symbol") else ""
        weight = f"，仓位 {fmt_weight(r.get('weight'))}" if r.get("weight") is not None else ""
        lines.append(f"- {r.get('date')} [{r.get('market')}] {r.get('action')} {r.get('asset')}{symbol}{weight}")
        lines.append(f"  原因：{r.get('reason') or '未抽取到明确原因'}")
        lines.append(f"  证据：Tier {r.get('evidence_tier')}，来源：{r.get('source_title')}，{r.get('source_url')}")
    if not records:
        lines.append("- 暂无可抽取调仓信号。")
    lines.append("")
    return lines


def build_report(config: dict, items_path: Path, start: dt.date, end: dt.date) -> Path:
    items = read_jsonl(items_path)
    all_records = collect_records(items, config, start, end)
    lines = [
        f"# Deep Van 调仓与投研监控样稿（{start} 至 {end}）",
        "",
        "说明：本报告基于知乎搜索 API 返回的公开结果和第三方汇总抽取，非全量原文审计；Tier B 多为 NEVEN 等汇总，Tier C 为第三方讨论。",
        "",
    ]
    lines += report_block("2026年1-6月整体", all_records)
    for m_start, m_end in month_range(start, end):
        monthly = [r for r in all_records if r.get("date") and m_start <= parse_date(r["date"]) <= m_end]
        lines += report_block(f"{m_start.year}年{m_start.month}月", monthly)
    path = REPORT_DIR / f"period_report_{start}_{end}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    write_jsonl(DATA_DIR / f"period_records_{start}_{end}.jsonl", all_records)
    print(path)
    return path


def push_recent(config: dict, items_path: Path, start: dt.date, end: dt.date, count: int) -> None:
    items = read_jsonl(items_path)
    records = collect_records(items, config, start, end)[:count]
    snapshot, changes = monitor.apply_rebalance_records(records)
    text = monitor.format_rebalance_alert(changes, snapshot) if changes else "Deep Van 调仓监控：暂无近期期调仓信号。"
    path = REPORT_DIR / f"pushed_recent_rebalances_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text(text + "\n", encoding="utf-8")
    monitor.send_webhook(text, config)
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backfill", "report", "push-recent"])
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--items", default=str(DATA_DIR / "items_deduped.jsonl"))
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--count", type=int, default=8)
    args = parser.parse_args()
    config = monitor.load_json(Path(args.config), {})
    start, end = parse_date(args.start), parse_date(args.end)
    if args.command == "backfill":
        backfill_period(config, start, end, args.limit)
    elif args.command == "report":
        build_report(config, Path(args.items), start, end)
    elif args.command == "push-recent":
        push_recent(config, Path(args.items), start, end, args.count)


if __name__ == "__main__":
    main()
