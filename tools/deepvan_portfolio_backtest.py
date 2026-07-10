#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import ssl
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
CACHE_DIR = DATA_DIR / "market_cache"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def pct(x: float | None) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "NA"
    return f"{x:.2%}"


def yahoo_symbol(proxy: str) -> str:
    if proxy.endswith(".SH"):
        return proxy[:-3] + ".SS"
    return proxy


def fetch_yahoo_daily(symbol: str, start: dt.date, end: dt.date) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ysym = yahoo_symbol(symbol)
    cache = CACHE_DIR / f"{ysym.replace('/', '_')}_{start}_{end}.json"
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached:
            return cached
    p1 = int(time.mktime(start.timetuple()))
    p2 = int(time.mktime((end + dt.timedelta(days=1)).timetuple()))
    qs = urllib.parse.urlencode({"period1": p1, "period2": p2, "interval": "1d", "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ysym)}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        cache.write_text("[]", encoding="utf-8")
        return []
    try:
        result = data["chart"]["result"][0]
        stamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        cache.write_text("[]", encoding="utf-8")
        return []
    rows = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        rows.append({"date": dt.datetime.utcfromtimestamp(ts).date().isoformat(), "close": float(close)})
    cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def group_holdings(rows: list[dict]) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    return dict(groups)


def select_snapshots(rows: list[dict], portfolio_id: str) -> list[list[dict]]:
    groups = [g for g in group_holdings(rows).values() if g and g[0]["portfolio_id"] == portfolio_id and g[0]["date"]]
    groups.sort(key=lambda g: (g[0]["date"], len(g), -abs(float(g[0]["table_total"]) - 1.0)))
    selected = []
    seen_dates = set()
    for group in groups:
        d = group[0]["date"]
        # Keep the best same-day table; OCR may contain a before and after table.
        if d in seen_dates:
            old = selected[-1]
            old_score = (len(old), -abs(float(old[0]["table_total"]) - 1.0))
            new_score = (len(group), -abs(float(group[0]["table_total"]) - 1.0))
            if new_score > old_score:
                selected[-1] = group
            continue
        selected.append(group)
        seen_dates.add(d)
    return selected


def period_return(series: list[dict], start: dt.date, end: dt.date) -> float | None:
    if not series:
        return None
    points = [(parse_date(r["date"]), r["close"]) for r in series]
    points = [p for p in points if start <= p[0] <= end]
    if len(points) < 2:
        return None
    return points[-1][1] / points[0][1] - 1.0


def max_drawdown(navs: list[float]) -> float:
    peak = navs[0] if navs else 1.0
    worst = 0.0
    for nav in navs:
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst


def run_backtest() -> Path:
    holdings = read_csv(DATA_DIR / "portfolio_timeline.holdings.csv")
    if not holdings:
        raise SystemExit("No holdings CSV found.")
    dates = [parse_date(r["date"]) for r in holdings if r.get("date")]
    start = min(dates) - dt.timedelta(days=7)
    end = dt.date.today()
    proxies = sorted({r["proxy"] for r in holdings if r.get("proxy") and not r["proxy"].startswith("MODULE_") and r["proxy"] != "CASH"})

    prices = {proxy: fetch_yahoo_daily(proxy, start, end) for proxy in proxies}
    price_ok = {proxy for proxy, rows in prices.items() if rows}

    portfolio_reports = []
    decisions = []
    for portfolio_id in sorted({r["portfolio_id"] for r in holdings}):
        snapshots = select_snapshots(holdings, portfolio_id)
        nav = 1.0
        navs = [nav]
        period_rows = []
        for i, group in enumerate(snapshots):
            start_date = parse_date(group[0]["date"])
            end_date = parse_date(snapshots[i + 1][0]["date"]) if i + 1 < len(snapshots) else end
            if end_date <= start_date:
                continue
            covered_weight = 0.0
            weighted_return = 0.0
            missing = []
            leg_returns = []
            for row in group:
                weight = float(row["weight"])
                proxy = row.get("proxy", "")
                if proxy == "CASH":
                    ret = 0.0
                    covered_weight += weight
                elif proxy.startswith("MODULE_"):
                    missing.append(f"{row['asset']}({pct(weight)})")
                    continue
                elif proxy in price_ok:
                    ret = period_return(prices[proxy], start_date, end_date)
                    if ret is None:
                        missing.append(f"{row['asset']}({pct(weight)})")
                        continue
                    covered_weight += weight
                else:
                    missing.append(f"{row['asset']}({pct(weight)})")
                    continue
                weighted_return += weight * ret
                leg_returns.append((row["canonical_asset"], row["asset"], weight, ret, row["source_title"], row["source_url"]))
            period_ret = weighted_return / covered_weight if covered_weight >= 0.5 else None
            if period_ret is not None:
                nav *= 1.0 + period_ret
                navs.append(nav)
            period_rows.append(
                {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "source": group[0]["source_title"],
                    "coverage": covered_weight,
                    "return": period_ret,
                    "missing": "; ".join(missing[:8]),
                }
            )
            for canonical, asset, weight, ret, title, url in leg_returns:
                decisions.append(
                    {
                        "portfolio_id": portfolio_id,
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "asset": canonical,
                        "raw_asset": asset,
                        "weight": weight,
                        "return": ret,
                        "contribution": weight * ret,
                        "source_title": title,
                        "source_url": url,
                    }
                )
        rets = [r["return"] for r in period_rows if r["return"] is not None]
        win_rate = sum(1 for r in rets if r > 0) / len(rets) if rets else None
        avg = statistics.mean(rets) if rets else None
        vol = statistics.pstdev(rets) if len(rets) > 1 else None
        sharpe_like = avg / vol * math.sqrt(len(rets)) if avg is not None and vol and vol > 0 else None
        portfolio_reports.append(
            {
                "portfolio_id": portfolio_id,
                "periods": period_rows,
                "nav": nav if rets else None,
                "win_rate": win_rate,
                "avg_period_return": avg,
                "max_drawdown": max_drawdown(navs),
                "sharpe_like": sharpe_like,
            }
        )

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = DATA_DIR / "portfolio_backtest.decisions.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        fields = ["portfolio_id", "start", "end", "asset", "raw_asset", "weight", "return", "contribution", "source_title", "source_url"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(decisions)

    report = REPORT_DIR / f"portfolio_backtest_{ts}.md"
    lines = [
        "# Deepvan 组合回测初稿",
        "",
        "口径：只使用 OCR 完整持仓表重建组合。行情先用 Yahoo Chart 可取到的代理价格；公募基金净值、模块型组合和缺行情资产不硬算。",
        "",
        "## 行情覆盖",
        "",
        f"- 待取行情代理：{len(proxies)} 个",
        f"- 成功取到：{len(price_ok)} 个",
        f"- 未取到：{len(proxies) - len(price_ok)} 个",
        "",
    ]
    missing_prices = [p for p in proxies if p not in price_ok]
    if missing_prices:
        lines += ["未取到行情的代理：`" + "`, `".join(missing_prices[:40]) + "`", ""]
    lines += ["## 组合结果", ""]
    for pr in portfolio_reports:
        lines += [
            f"### {pr['portfolio_id']}",
            "",
            f"- 可计算净值：{pr['nav']:.4f}" if pr["nav"] is not None else "- 可计算净值：NA",
            f"- 胜率：{pct(pr['win_rate'])}",
            f"- 平均区间收益：{pct(pr['avg_period_return'])}",
            f"- 最大回撤：{pct(pr['max_drawdown'])}",
            f"- Sharpe-like：{pr['sharpe_like']:.2f}" if pr["sharpe_like"] is not None else "- Sharpe-like：NA",
            "",
            "| 区间 | 覆盖权重 | 区间收益 | 缺口 | 来源 |",
            "|---|---:|---:|---|---|",
        ]
        for row in pr["periods"]:
            lines.append(f"| {row['start']} ~ {row['end']} | {pct(row['coverage'])} | {pct(row['return'])} | {row['missing']} | {row['source']} |")
        lines.append("")

    top = sorted(decisions, key=lambda r: r["contribution"], reverse=True)[:12]
    bottom = sorted(decisions, key=lambda r: r["contribution"])[:12]
    lines += ["## 单腿贡献", "", "### 贡献靠前", "", "| 区间 | 组合 | 标的 | 权重 | 收益 | 贡献 |", "|---|---|---|---:|---:|---:|"]
    for r in top:
        lines.append(f"| {r['start']} ~ {r['end']} | {r['portfolio_id']} | {r['asset']} | {pct(r['weight'])} | {pct(r['return'])} | {pct(r['contribution'])} |")
    lines += ["", "### 贡献靠后", "", "| 区间 | 组合 | 标的 | 权重 | 收益 | 贡献 |", "|---|---|---|---:|---:|---:|"]
    for r in bottom:
        lines.append(f"| {r['start']} ~ {r['end']} | {r['portfolio_id']} | {r['asset']} | {pct(r['weight'])} | {pct(r['return'])} | {pct(r['contribution'])} |")
    lines += [
        "",
        "## 重要限制",
        "",
        "- 这是第一版可复核回测，不是最终业绩归因。区间收益按调仓表之间的持有期估算，没有处理日内成交、税费、汇率、分红再投资和 QDII 净值滞后。",
        "- 内地版 2026-06-29 的 `QDII主线组合` 仍是 75% 模块权重，必须继续拆子组合，否则该期国内组合不能算完整净值。",
        "- 同一篇原文里若有调仓前后两张表，当前按同日较完整表去重；后续还要用正文语义确认最终表。",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(report), "decisions": str(csv_path), "price_ok": len(price_ok), "price_total": len(proxies)}, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run_backtest()
