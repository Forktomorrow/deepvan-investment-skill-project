#!/usr/bin/env python3
"""
Deep Van credibility evaluator.

It turns monitor search items into scored opinion/portfolio events and fetches
historical prices from Yahoo chart API when possible.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
PRICE_DIR = DATA_DIR / "prices"
DEFAULT_CONFIG = ROOT / "credibility_config.json"
DEFAULT_ITEMS = DATA_DIR / "items_deduped.jsonl"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def date_from_ts(ts: int | None) -> dt.date | None:
    if not ts:
        return None
    return dt.datetime.fromtimestamp(int(ts)).date()


def item_text(item: dict) -> str:
    return "\n".join([item.get("Title", ""), item.get("ContentText", ""), item.get("Url", "")])


SECTION_BOUNDARIES = [
    "水又三人禾",
    "一棵低姿态的韭菜",
    "派大星皮皮",
    "奥特之父",
    "MR Dang",
    "洛阳小散户",
    "黄彦臻",
    "Alex",
    "alex",
]


def deepvan_relevant_text(item: dict) -> str:
    text = item_text(item)
    lower = text.lower()
    starts = [i for i in [text.find("Deep Van"), text.find("Deepvan"), lower.find("deep van"), lower.find("deepvan")] if i >= 0]
    if not starts:
        return text
    start = min(starts)
    section = text[start:]
    ends = [section.find(boundary) for boundary in SECTION_BOUNDARIES if section.find(boundary) > 20]
    if ends:
        section = section[: min(ends)]
    return item.get("Title", "") + "\n" + section + "\n" + item.get("Url", "")


def evidence_quality(item: dict) -> tuple[str, float]:
    author = item.get("AuthorName", "")
    text = deepvan_relevant_text(item)
    if author == "Deep Van":
        return "A", 1.0
    if text.startswith("Deep Van") or "\nDeep Van\n" in text or re.search(r"Deep Van\s*\n?\d+\.\[", text):
        return "B", 0.78
    if "Deep Van" in text or "deepvan" in text.lower():
        return "C", 0.55
    return "D", 0.35


def normalize_action_direction(text: str, asset: str) -> tuple[str, int]:
    window = text[max(0, text.find(asset) - 80) : text.find(asset) + len(asset) + 80] if asset in text else text[:200]
    bearish = ["减仓", "清仓", "止盈", "止损", "看空", "不看好", "规避", "卖出", "风险", "下跌", "泡沫破裂"]
    bullish = ["加仓", "买入", "重仓", "低位抄底", "看好", "配置", "保留", "新增", "上涨", "主线", "利好"]
    if any(k in window for k in bearish) and not any(k in window for k in bullish):
        return "bearish", -1
    if any(k in window for k in bullish) and not any(k in window for k in bearish):
        return "bullish", 1
    if any(k in window for k in bearish) and any(k in window for k in bullish):
        if min([window.find(k) for k in bearish if k in window] or [999]) < min([window.find(k) for k in bullish if k in window] or [999]):
            return "bearish", -1
        return "bullish", 1
    return "neutral", 0


def find_assets(text: str, config: dict) -> list[str]:
    names = sorted(config["asset_map"].keys(), key=len, reverse=True)
    found = []
    for name in names:
        if name in text:
            found.append(name)
    return found


def pct_for_asset(text: str, asset: str) -> float | None:
    patterns = [
        rf"{re.escape(asset)}[^\d%]{{0,12}}(?P<pct>\d{{1,2}}(?:\.\d+)?)%",
        rf"(?P<pct>\d{{1,2}}(?:\.\d+)?)%[^\n，,。；;]{{0,12}}{re.escape(asset)}",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return float(m.group("pct")) / 100.0
    return None


def normalize_event_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\d{4}[./年-]\d{1,2}(?:[./月-]\d{1,2}日?)?", "", text)
    text = re.sub(r"\d+(?:\.\d+)?%", "", text)
    text = re.sub(r"\s+", "", text)
    return text[:80]


def event_cluster_key(event: dict) -> tuple:
    symbol_or_asset = event.get("symbol") or event.get("asset")
    return (event.get("date"), symbol_or_asset, event.get("direction"), event.get("topic"))


def better_primary_event(old: dict, new: dict) -> dict:
    tier_rank = {"A": 4, "B": 3, "C": 2, "D": 1}
    old_score = (tier_rank.get(old.get("evidence_tier"), 0), old.get("weight") is not None, len(old.get("snippet", "")))
    new_score = (tier_rank.get(new.get("evidence_tier"), 0), new.get("weight") is not None, len(new.get("snippet", "")))
    return new if new_score > old_score else old


def merge_duplicate_events(events: list[dict]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for event in events:
        key = event_cluster_key(event)
        source = {"title": event.get("source_title", ""), "url": event.get("source_url", ""), "tier": event.get("evidence_tier", "")}
        if key not in grouped:
            grouped[key] = {**event, "supporting_sources": [source], "duplicate_count": 1}
            continue
        primary = better_primary_event(grouped[key], event)
        existing_sources = grouped[key].get("supporting_sources", [])
        source_urls = {s.get("url") for s in existing_sources}
        if source.get("url") not in source_urls:
            existing_sources.append(source)
        merged = {**primary, "supporting_sources": existing_sources, "duplicate_count": grouped[key].get("duplicate_count", 1) + 1}
        if merged.get("weight") is None:
            merged["weight"] = grouped[key].get("weight") if grouped[key].get("weight") is not None else event.get("weight")
        grouped[key] = merged
    return list(grouped.values())


def classify_event(item: dict, asset: str, config: dict) -> dict:
    text = deepvan_relevant_text(item)
    meta = config["asset_map"][asset]
    direction_label, direction = normalize_action_direction(text, asset)
    ev_tier, ev_score = evidence_quality(item)
    topic = meta.get("topic", "Other")
    vars_ = config.get("topic_variable_keywords", {}).get(topic, [])
    variable_hits = [v for v in vars_ if v.lower() in text.lower()]
    pct = pct_for_asset(text, asset)
    executable = 0.45
    if pct is not None:
        executable += 0.3
    if direction != 0:
        executable += 0.2
    if meta.get("symbol"):
        executable += 0.05
    return {
        "date": str(date_from_ts(item.get("EditTime")) or ""),
        "asset": asset,
        "symbol": meta.get("symbol"),
        "topic": topic,
        "benchmark": meta.get("benchmark") or config.get("topic_benchmarks", {}).get(topic) or config.get("default_benchmark", "SPY"),
        "direction": direction,
        "direction_label": direction_label,
        "weight": pct,
        "evidence_tier": ev_tier,
        "evidence_score": ev_score,
        "executability_score": min(executable, 1.0),
        "variable_hits": variable_hits,
        "variable_score": min(1.0, len(variable_hits) / 3.0) if vars_ else 0.5,
        "source_title": item.get("Title", ""),
        "source_url": item.get("Url", ""),
        "source_author": item.get("AuthorName", ""),
        "snippet": text[:700],
    }


def extract_opinion_events(items: list[dict], config: dict) -> list[dict]:
    events = []
    for item in items:
        text = deepvan_relevant_text(item)
        if "Deep Van" not in text and "deepvan" not in text.lower():
            continue
        for asset in find_assets(text, config):
            event = classify_event(item, asset, config)
            if not event["date"] or event["direction"] == 0:
                continue
            events.append(event)
    events = merge_duplicate_events(events)
    events.sort(key=lambda x: (x["date"], x["topic"], x["asset"]), reverse=True)
    return events


def yahoo_prices(symbol: str, start: dt.date, end: dt.date) -> dict[str, float]:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    cache = PRICE_DIR / f"{symbol.replace('^', '_')}_{start}_{end}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    p1 = int(time.mktime(start.timetuple()))
    p2 = int(time.mktime((end + dt.timedelta(days=1)).timetuple()))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=history"
    try:
        proc = subprocess.run(["curl", "-sS", "-L", "--max-time", "6", url], capture_output=True, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        return {}
    try:
        data = json.loads(proc.stdout)
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return {}
    out = {}
    for ts, close in zip(timestamps, closes):
        if close is not None:
            out[str(dt.datetime.fromtimestamp(ts).date())] = float(close)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def tencent_symbol(symbol: str) -> str | None:
    if symbol.endswith(".SS"):
        return "sh" + symbol[:-3]
    if symbol.endswith(".SZ"):
        return "sz" + symbol[:-3]
    if symbol in {"SPY", "XBI", "QQQ", "IBB", "GLD", "SOXX"}:
        return "us" + symbol
    return None


def tencent_prices(symbol: str, start: dt.date, end: dt.date) -> dict[str, float]:
    market_symbol = tencent_symbol(symbol)
    if not market_symbol:
        return {}
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    cache = PRICE_DIR / f"tencent_{symbol.replace('.', '_')}_{start}_{end}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    start_s = start.isoformat()
    end_s = end.isoformat()
    # Tencent's A-share endpoint supports date ranges. US ETF support is limited
    # in this environment, but keeping it here lets recent quotes fill when available.
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market_symbol},day,{start_s},{end_s},500,qfq"
    try:
        proc = subprocess.run(
            ["curl", "--http1.1", "-sS", "-L", "--max-time", "10", "-A", "Mozilla/5.0", url],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}
    try:
        data = json.loads(proc.stdout)
        node = data["data"][market_symbol]
        rows = node.get("qfqday") or node.get("day") or []
    except Exception:
        return {}
    out = {}
    for row in rows:
        if len(row) >= 3:
            d = row[0]
            try:
                close = float(row[2])
            except Exception:
                continue
            if str(start) <= d <= str(end):
                out[d] = close
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def csv_prices(symbol: str, start: dt.date, end: dt.date, csv_dir: Path) -> dict[str, float]:
    candidates = [
        csv_dir / f"{symbol}.csv",
        csv_dir / f"{symbol.replace('.', '_')}.csv",
        csv_dir / f"{symbol.lower()}.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        return {}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return {}
    header = [h.strip().lower() for h in lines[0].split(",")]
    try:
        date_i = header.index("date")
    except ValueError:
        return {}
    close_i = None
    for name in ["adj close", "adj_close", "close"]:
        if name in header:
            close_i = header.index(name)
            break
    if close_i is None:
        return {}
    out = {}
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) <= max(date_i, close_i):
            continue
        try:
            d = dt.date.fromisoformat(parts[date_i])
            close = float(parts[close_i])
        except Exception:
            continue
        if start <= d <= end:
            out[str(d)] = close
    return out


def nearest_price(prices: dict[str, float], date: dt.date, direction: int = 1) -> tuple[dt.date, float] | None:
    for i in range(0, 10):
        d = date + dt.timedelta(days=i * direction)
        key = str(d)
        if key in prices:
            return d, prices[key]
    return None


def max_drawdown(path: list[float], direction: int) -> float | None:
    if len(path) < 2:
        return None
    wealth = [(1.0 + x) if direction > 0 else (1.0 - x) for x in path]
    peak = wealth[0]
    worst = 0.0
    for value in wealth:
        peak = max(peak, value)
        if peak != 0:
            worst = min(worst, value / peak - 1.0)
    return abs(worst)


def score_event(event: dict, config: dict, price_cache: dict[str, dict[str, float]], price_provider: str, csv_dir: Path | None) -> dict:
    start = dt.date.fromisoformat(event["date"])
    horizon = int(config.get("default_horizon_days", 20))
    target = start + dt.timedelta(days=horizon)
    if target > dt.date.today():
        event["status"] = "pending"
        return event
    end = target + dt.timedelta(days=7)
    if price_provider == "none":
        event["status"] = "no_price"
        return event

    symbols = [event["symbol"], event["benchmark"]]
    for symbol in symbols:
        if symbol and symbol not in price_cache:
            if price_provider == "csv" and csv_dir:
                price_cache[symbol] = csv_prices(symbol, start - dt.timedelta(days=7), end + dt.timedelta(days=7), csv_dir)
            elif price_provider == "tencent":
                price_cache[symbol] = tencent_prices(symbol, start - dt.timedelta(days=7), end + dt.timedelta(days=7))
            elif price_provider == "auto":
                prices = tencent_prices(symbol, start - dt.timedelta(days=7), end + dt.timedelta(days=7))
                if not prices and csv_dir:
                    prices = csv_prices(symbol, start - dt.timedelta(days=7), end + dt.timedelta(days=7), csv_dir)
                price_cache[symbol] = prices
            elif price_provider == "yahoo":
                price_cache[symbol] = yahoo_prices(symbol, start - dt.timedelta(days=7), end + dt.timedelta(days=7))
            else:
                price_cache[symbol] = {}
    prices = price_cache.get(event["symbol"], {})
    bench = price_cache.get(event["benchmark"], {})
    p0 = nearest_price(prices, start, 1)
    p1 = nearest_price(prices, start + dt.timedelta(days=horizon), -1)
    b0 = nearest_price(bench, start, 1)
    b1 = nearest_price(bench, start + dt.timedelta(days=horizon), -1)
    if not p0 or not p1:
        event["status"] = "no_price"
        return event

    ret = p1[1] / p0[1] - 1.0
    signed_ret = ret * event["direction"]
    bench_ret = None
    signed_excess = None
    if b0 and b1:
        bench_ret = b1[1] / b0[1] - 1.0
        signed_excess = (ret - bench_ret) * event["direction"]
    dates = sorted(d for d in prices if str(p0[0]) <= d <= str(p1[0]))
    path = [prices[d] / p0[1] - 1.0 for d in dates]
    dd = max_drawdown(path, event["direction"])
    event.update(
        {
            "status": "scored",
            "horizon_days": horizon,
            "entry_date": str(p0[0]),
            "exit_date": str(p1[0]),
            "asset_return": ret,
            "signed_return": signed_ret,
            "benchmark_return": bench_ret,
            "signed_excess_return": signed_excess,
            "max_drawdown": dd,
            "direction_hit": signed_ret > 0,
            "excess_hit": signed_excess is not None and signed_excess > 0,
        }
    )
    return event


def norm_return(x: float | None, scale: float = 0.08) -> float:
    if x is None:
        return 0.5
    return max(0.0, min(1.0, 0.5 + x / (2 * scale)))


def norm_drawdown(dd: float | None) -> float:
    if dd is None:
        return 0.5
    return max(0.0, min(1.0, 1.0 - dd / 0.20))


def composite_score(event: dict, config: dict) -> float | None:
    if event.get("status") != "scored":
        return None
    w = config["score_weights"]
    direction_score = 1.0 if event.get("direction_hit") else 0.0
    excess_score = norm_return(event.get("signed_excess_return"))
    drawdown_score = norm_drawdown(event.get("max_drawdown"))
    total = (
        direction_score * w["direction_accuracy"]
        + excess_score * w["excess_return"]
        + drawdown_score * w["drawdown_control"]
        + event.get("variable_score", 0.5) * w["variable_validation"]
        + event.get("executability_score", 0.5) * w["executability"]
        + event.get("evidence_score", 0.5) * w["evidence_quality"]
    )
    return round(total * 100, 2)


def event_verdict(event: dict) -> str:
    if event.get("status") != "scored":
        return f"未评分：{event.get('status', 'unknown')}"
    direction_yes = "Yes" if event.get("direction_hit") else "No"
    excess_yes = "Yes" if event.get("excess_hit") else "No"
    action = "看多" if event.get("direction", 0) > 0 else "看空"
    ret = fmt_pct(event.get("asset_return"))
    signed = fmt_pct(event.get("signed_return"))
    bench = fmt_pct(event.get("benchmark_return"))
    excess = fmt_pct(event.get("signed_excess_return"))
    return (
        f"方向胜={direction_yes}，超额胜={excess_yes}。"
        f"{action}后 {event.get('entry_date')}->{event.get('exit_date')} 标的收益 {ret}，"
        f"方向收益 {signed}，基准 {bench}，方向超额 {excess}。"
    )


def group_stats(events: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for e in events:
        groups.setdefault(e["topic"], []).append(e)
    out = {}
    for topic, rows in groups.items():
        scored = [r for r in rows if r.get("status") == "scored"]
        returns = [r["signed_return"] for r in scored if r.get("signed_return") is not None]
        excess = [r["signed_excess_return"] for r in scored if r.get("signed_excess_return") is not None]
        scores = [r["credibility_score"] for r in scored if r.get("credibility_score") is not None]
        if returns:
            vol = statistics.pstdev(returns) if len(returns) > 1 else 0.0
            sharpe_like = (statistics.mean(returns) / vol * math.sqrt(252 / 20)) if vol else None
        else:
            sharpe_like = None
        out[topic] = {
            "events": len(rows),
            "scored": len(scored),
            "direction_win_rate": sum(1 for r in scored if r.get("direction_hit")) / len(scored) if scored else None,
            "excess_win_rate": sum(1 for r in scored if r.get("excess_hit")) / len(scored) if scored else None,
            "avg_signed_return": statistics.mean(returns) if returns else None,
            "avg_signed_excess": statistics.mean(excess) if excess else None,
            "avg_max_drawdown": statistics.mean([r["max_drawdown"] for r in scored if r.get("max_drawdown") is not None]) if scored else None,
            "avg_score": statistics.mean(scores) if scores else None,
            "sharpe_like": sharpe_like,
        }
    return out


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x * 100:.2f}%"


def fmt_num(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:.2f}"


def write_report(events: list[dict], stats: dict[str, dict]) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"credibility_report_{stamp}.md"
    lines = [
        "# Deepvan Credibility Evaluation",
        "",
        "This is a quantitative first pass based on Zhihu search results and public summaries. It is not investment advice and not a complete audit of all original Deep Van posts.",
        "",
        "## Topic Scores",
        "",
        "| Topic | Events | Scored | Direction Win | Excess Win | Avg Signed Return | Avg Signed Excess | Avg Drawdown | Avg Score | Sharpe-like |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for topic, s in sorted(stats.items(), key=lambda kv: (kv[1].get("avg_score") is not None, kv[1].get("avg_score") or 0), reverse=True):
        lines.append(
            f"| {topic} | {s['events']} | {s['scored']} | {fmt_pct(s['direction_win_rate'])} | {fmt_pct(s['excess_win_rate'])} | "
            f"{fmt_pct(s['avg_signed_return'])} | {fmt_pct(s['avg_signed_excess'])} | {fmt_pct(s['avg_max_drawdown'])} | "
            f"{fmt_num(s['avg_score'])} | {fmt_num(s['sharpe_like'])} |"
        )
    lines += ["", "## Recent Scored Events", ""]
    for e in sorted([x for x in events if x.get("status") == "scored"], key=lambda x: x.get("date", ""), reverse=True)[:80]:
        supporting = e.get("supporting_sources") or []
        dup = f", merged {e.get('duplicate_count')} snippets" if e.get("duplicate_count", 1) > 1 else ""
        lines.append(
            f"- {e['date']} {e['topic']} {e['direction_label']} {e['asset']} ({e['symbol']}): "
            f"return {fmt_pct(e.get('asset_return'))}, excess {fmt_pct(e.get('signed_excess_return'))}, "
            f"score {fmt_num(e.get('credibility_score'))}, evidence {e['evidence_tier']}{dup} | {e['source_url']}\n"
            f"  - 判定：{event_verdict(e)}\n"
            f"  - 证据摘要：{e.get('snippet', '')[:180]}"
        )
        if len(supporting) > 1:
            lines.append(f"  - 合并来源数：{len(supporting)}")
    lines += ["", "## Unscored Events", ""]
    for e in [x for x in events if x.get("status") != "scored"][:40]:
        lines.append(f"- {e.get('date')} {e.get('asset')} {e.get('status')} | {e.get('source_url')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    parser.add_argument("--out-events", default=str(DATA_DIR / "credibility_events.jsonl"))
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--horizon-days", type=int, help="override default scoring horizon")
    parser.add_argument("--price-provider", choices=["none", "csv", "tencent", "auto", "yahoo"], default="none")
    parser.add_argument("--price-csv-dir", default=str(DATA_DIR / "price_csv"))
    args = parser.parse_args()

    config = load_json(Path(args.config), {})
    if args.horizon_days:
        config["default_horizon_days"] = args.horizon_days
    items = read_jsonl(Path(args.items))
    events = extract_opinion_events(items, config)
    price_cache: dict[str, dict[str, float]] = {}
    if not args.extract_only:
        csv_dir = Path(args.price_csv_dir) if args.price_csv_dir else None
        events = [score_event(e, config, price_cache, args.price_provider, csv_dir) for e in events]
        for e in events:
            e["credibility_score"] = composite_score(e, config)
    write_jsonl(Path(args.out_events), events)
    stats = group_stats(events)
    report = write_report(events, stats)
    print(f"events={len(events)} scored={sum(1 for e in events if e.get('status') == 'scored')} report={report}")


if __name__ == "__main__":
    main()
