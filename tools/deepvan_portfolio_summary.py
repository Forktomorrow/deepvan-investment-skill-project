#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(x: str) -> str:
    try:
        return f"{float(x):.2%}"
    except Exception:
        return str(x)


def group_holdings(rows: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    return groups


def latest_groups_by_portfolio(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    best = {}
    for gid, rows in groups.items():
        first = rows[0]
        key = first["portfolio_id"]
        old = best.get(key)
        # Prefer newer date, then higher row count, then totals closer to 100%.
        score = (first["date"], len(rows), -abs(float(first.get("table_total") or 0) - 1.0))
        old_score = ("", 0, -999.0)
        if old:
            old_first = old[0]
            old_score = (old_first["date"], len(old), -abs(float(old_first.get("table_total") or 0) - 1.0))
        if score > old_score:
            best[key] = rows
    return best


def write_summary() -> Path:
    holdings = read_csv(DATA_DIR / "portfolio_timeline.holdings.csv")
    events = read_csv(DATA_DIR / "portfolio_timeline.events.csv")
    groups = group_holdings(holdings)
    latest = latest_groups_by_portfolio(groups)
    path = REPORT_DIR / f"portfolio_summary_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Deepvan 组合抽取摘要",
        "",
        "口径：只使用已确认 Deep Van 本人公开原文。完整组合优先采用 OCR 持仓表；文本调仓只作为候选事件。",
        "",
        "## 当前抽取状态",
        "",
        f"- 完整组合表：{len(groups)} 组",
        f"- 持仓行：{len(holdings)} 条",
        f"- 调仓/净值候选事件：{len(events)} 条",
        "- 国际版和内地版分开维护，分别要求组分加总约 100%。",
        "",
        "## 最新组合快照",
        "",
    ]
    for portfolio_id, rows in sorted(latest.items()):
        first = rows[0]
        lines += [
            f"### {portfolio_id}",
            "",
            f"- 日期：{first['date']}",
            f"- 合计：{pct(first['table_total'])}",
            f"- 来源：[{first['source_title']}]({first['source_url']})",
            "",
            "| 标的/模块 | 权重 | 证据 |",
            "|---|---:|---|",
        ]
        for row in sorted(rows, key=lambda r: -float(r["weight"])):
            lines.append(f"| {row['asset']} | {pct(row['weight'])} | {row['evidence']} |")
        lines.append("")

    lines += ["## 最近调仓候选", "", "| 日期 | 组合 | 动作 | 标的 | 变化 | 证据句 | 来源 |", "|---|---|---|---|---|---|---|"]
    recent_events = [e for e in events if e.get("date")]
    for e in sorted(recent_events, key=lambda r: r["date"], reverse=True)[:40]:
        change = ""
        if e.get("from_weight") or e.get("to_weight"):
            change = f"{e.get('from_weight')} -> {e.get('to_weight')}"
        lines.append(
            f"| {e['date']} | {e['portfolio_id']} | {e['action']} | {e['asset']} | {change} | {e.get('sentence','')[:90]} | [link]({e['source_url']}) |"
        )

    lines += [
        "",
        "## 需要继续清洗",
        "",
        "- OCR 仍有少量字符误识别，例如 `Q901/Q9Q1/QQQ1` 都应归并到卖备兑纳指 ETF，`G00GL` 应归并到 `GOOGL`。",
        "- 2026-03-15 同一来源中出现调仓前/调仓后两张表，目前都保留；后续要根据正文判断哪张是最终组合。",
        "- 内地版目前先还原为模块级权重；如果要做基金级回测，需要继续把模块内子基金比例拆出来。",
        "- 文本事件表仍是候选层，回测时应优先以完整组合表重建净值。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)
    return path


if __name__ == "__main__":
    write_summary()
