#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import deepvan_candidate_filter as candidate_filter
import deepvan_monitor as monitor
import deepvan_profile_report as profile_report


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_candidates(limit: int) -> list[dict]:
    profile_dir = DATA_DIR / "profile_lists"
    rows = candidate_filter.load_profile_lists(
        [
            profile_dir / "activity.json",
            profile_dir / "answers.json",
            profile_dir / "posts.json",
            profile_dir / "pins_deep_scroll.json",
        ]
    )
    candidates = candidate_filter.filter_candidates(rows, limit)
    write_json(DATA_DIR / "profile_candidates.json", candidates)
    return candidates


def original_cache_index() -> dict[str, Path]:
    idx = {}
    for base in [DATA_DIR / "original_pages_recent", DATA_DIR / "original_pages"]:
        if not base.exists():
            continue
        for article in base.glob("*/article.json"):
            try:
                data = json.loads(article.read_text(encoding="utf-8"))
            except Exception:
                continue
            url = (data.get("url") or "").split("?")[0]
            if url:
                idx[url] = article
    return idx


def cost_plan(candidates: list[dict], fetch_budget: int) -> dict:
    cache = original_cache_index()
    cached = []
    to_fetch = []
    for c in candidates:
        key = c["url"].split("?")[0]
        if key in cache:
            cached.append({**c, "cache_file": str(cache[key])})
        elif len(to_fetch) < fetch_budget:
            to_fetch.append(c)
    return {
        "candidate_count": len(candidates),
        "cached_fulltext_count": len(cached),
        "new_fetch_budget": fetch_budget,
        "new_fetch_count": len(to_fetch),
        "estimated_browser_opens": len(to_fetch),
        "cached": cached,
        "to_fetch": to_fetch,
    }


def extract_records(rows: list[dict], config: dict) -> list[dict]:
    records = []
    for row in rows:
        item = profile_report.make_monitor_item(row, config)
        records.extend(monitor.extract_rebalance_records(item, config))
    seen = set()
    out = []
    for r in sorted(records, key=lambda x: (x.get("date") or "", x.get("source_url") or "", x.get("asset") or ""), reverse=True):
        reason = (r.get("reason") or r.get("snippet") or "")[:80]
        key = json.dumps({k: r.get(k) for k in ["date", "action", "asset", "weight"]} | {"reason": reason}, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def summarize_portfolio(records: list[dict]) -> dict:
    snapshot, changes = monitor.apply_rebalance_records(records, reset=True)
    return {"snapshot": snapshot, "changes": changes}


def message_variants(records: list[dict], snapshot: dict, skills: list[dict], cost: dict, half_life_days: int = 60) -> dict[str, str]:
    recent = records[:12]
    short_lines = [
        "Deep Van 原文监控测试 v1",
        f"候选 {cost['candidate_count']} 条；已缓存全文 {cost['cached_fulltext_count']} 条；本轮需新打开 {cost['new_fetch_count']} 条。",
        "最近调仓/持仓信号：",
    ]
    for r in recent[:5]:
        short_lines.append(f"- {r.get('date') or '未知日期'} {r.get('action')} {r.get('asset')} {monitor.format_weight(r.get('weight'))}")

    detailed_lines = [
        "Deep Van 调仓监控测试 v2（原文优先）",
        "",
        f"采集策略：主页列表 -> 投资关键词筛选 -> 缓存全文复用 -> 少量原文展开/OCR。",
        f"成本控制：候选 {cost['candidate_count']}，缓存命中 {cost['cached_fulltext_count']}，待新抓 {cost['new_fetch_count']}。",
        "",
        "调仓/持仓明细：",
    ]
    for r in recent[:10]:
        detailed_lines.append(f"- {r.get('date') or '未知日期'} [{r.get('market')}] {r.get('action')} {r.get('asset')} {monitor.format_weight(r.get('weight'))}")
        detailed_lines.append(f"  依据：{(r.get('reason') or r.get('snippet') or '')[:120]}")
        detailed_lines.append(f"  来源：{r.get('source_title')} {r.get('source_url')}")
    snap_lines = monitor.format_snapshot(snapshot)
    if snap_lines:
        detailed_lines += ["", "当前快照：", *snap_lines]

    skill_lines = [
        "Deep Van 投研 skill 测试 v1（按时效加权）",
        "",
        f"近因权重：越接近今天权重越高，半衰期约 {half_life_days} 天；旧文保留为风格背景。",
    ]
    for s in skills[:6]:
        skill_lines.append(f"- {s['skill']}：score={s['score']}")
        if s.get("evidence"):
            e = s["evidence"][0]
            skill_lines.append(f"  近证据：{e['date']} {e['snippet'][:90]}")
    return {"short": "\n".join(short_lines), "detailed": "\n".join(detailed_lines), "skills": "\n".join(skill_lines)}


def write_pipeline_report(candidates: list[dict], cost: dict, rows: list[dict], records: list[dict], snapshot: dict, skills: list[dict], messages: dict[str, str]) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"pipeline_test_{stamp}.md"
    lines = [
        "# Deep Van Pipeline Test",
        "",
        "## Cost Controls",
        "",
        f"- Profile candidates: {cost['candidate_count']}",
        f"- Cached fulltext: {cost['cached_fulltext_count']}",
        f"- New browser opens needed: {cost['new_fetch_count']}",
        f"- Cached corpus rows used: {len(rows)}",
        "",
        "## Top Candidates",
        "",
        "| Score | Time | Title | Hits | URL |",
        "|---:|---|---|---|---|",
    ]
    for c in candidates[:20]:
        lines.append(f"| {c['score']} | {c['time']} | {c['title']} | {'、'.join(c['hits'][:8])} | {c['url']} |")
    lines += ["", "## Recent Portfolio Events", "", "| Date | Action | Asset | Weight | Evidence |", "|---|---|---|---:|---|"]
    for r in records[:30]:
        lines.append(f"| {r.get('date') or ''} | {r.get('action')} | {r.get('asset')} | {monitor.format_weight(r.get('weight'))} | {(r.get('reason') or r.get('snippet') or '')[:100]} |")
    lines += ["", "## Snapshot", "", *monitor.format_snapshot(snapshot)]
    lines += ["", "## Skills", ""]
    for s in skills[:8]:
        lines.append(f"- {s['skill']}: {s['score']}")
    lines += ["", "## Feishu Message Variants", ""]
    for name, text in messages.items():
        lines.append(f"### {name}")
        lines.append("```text")
        lines.append(text)
        lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def send_if_requested(messages: dict[str, str], config: dict, variant: str) -> bool:
    if variant not in messages:
        raise SystemExit(f"Unknown message variant: {variant}")
    monitor.send_webhook(messages[variant], config)
    return bool(os.environ.get(config.get("alert", {}).get("webhook_url_env", "DEEPVAN_NOTIFY_WEBHOOK")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--candidate-limit", type=int, default=40)
    parser.add_argument("--fetch-budget", type=int, default=8)
    parser.add_argument("--send", choices=["short", "detailed", "skills"])
    args = parser.parse_args()
    config = monitor.load_json(Path(args.config), {})
    candidates = build_candidates(args.candidate_limit)
    cost = cost_plan(candidates, args.fetch_budget)
    rows = profile_report.iter_original_pages([DATA_DIR / "original_pages_recent", DATA_DIR / "original_pages"])
    records = extract_records(rows, config)
    portfolio = summarize_portfolio(records)
    half_life_days = int(config.get("skill_recency_half_life_days", 60))
    skills = profile_report.skill_hits(rows, dt.date(2026, 7, 10), half_life_days)
    messages = message_variants(records, portfolio["snapshot"], skills, cost, half_life_days)
    write_json(DATA_DIR / "pipeline_cost_plan.json", cost)
    write_json(DATA_DIR / "pipeline_message_variants.json", messages)
    report = write_pipeline_report(candidates, cost, rows, records, portfolio["snapshot"], skills, messages)
    sent = False
    if args.send:
        sent = send_if_requested(messages, config, args.send)
    print(f"report={report} candidates={len(candidates)} cached={cost['cached_fulltext_count']} fetch_needed={cost['new_fetch_count']} sent={sent}")


if __name__ == "__main__":
    main()
