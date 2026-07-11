#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
ASSET_DIR = ROOT / "assets"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepvan_portfolio_backtest import fetch_yahoo_daily, parse_date  # noqa: E402


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(x: float | None) -> str:
    return "NA" if x is None or math.isnan(x) else f"{x:.2%}"


def price_map(proxy: str, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    if proxy == "CASH":
        return {}
    rows = fetch_yahoo_daily(proxy, start - dt.timedelta(days=8), end + dt.timedelta(days=1))
    return {parse_date(r["date"]): float(r["close"]) for r in rows}


def price_on_or_before(series: dict[dt.date, float], day: dt.date, max_back: int = 10) -> float | None:
    for delta in range(max_back + 1):
        value = series.get(day - dt.timedelta(days=delta))
        if value is not None:
            return value
    return None


def group_by_snapshot(rows: list[dict], portfolio_id: str | None = None) -> list[list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if portfolio_id and row.get("portfolio_id") != portfolio_id:
            continue
        if not row.get("date"):
            continue
        if row.get("proxy", "").startswith("MODULE_"):
            continue
        groups.setdefault(row.get("group_id") or row["date"], []).append(row)
    snapshots = list(groups.values())
    snapshots.sort(key=lambda g: (g[0]["date"], len(g), -abs(float(g[0].get("table_total") or 1) - 1)))
    out: list[list[dict]] = []
    seen = {}
    for group in snapshots:
        day = group[0]["date"]
        if day in seen:
            old_i = seen[day]
            old = out[old_i]
            old_score = (len(old), -abs(float(old[0].get("table_total") or 1) - 1))
            new_score = (len(group), -abs(float(group[0].get("table_total") or 1) - 1))
            if new_score > old_score:
                out[old_i] = group
        else:
            seen[day] = len(out)
            out.append(group)
    return out


def holdings_nav(snapshots: list[list[dict]], end: dt.date) -> list[tuple[dt.date, float]]:
    if not snapshots:
        return []
    start = parse_date(snapshots[0][0]["date"])
    proxies = sorted({r["proxy"] for g in snapshots for r in g if r.get("proxy") and r["proxy"] != "CASH" and not r["proxy"].startswith("MODULE_")})
    prices = {p: price_map(p, start, end) for p in proxies}
    nav = 1.0
    navs = [(start, nav)]
    for i, group in enumerate(snapshots):
        rebalance_day = parse_date(group[0]["date"])
        next_day = parse_date(snapshots[i + 1][0]["date"]) if i + 1 < len(snapshots) else end
        start_nav = nav
        start_prices = {}
        for row in group:
            proxy = row.get("proxy", "")
            if proxy and proxy != "CASH" and not proxy.startswith("MODULE_"):
                start_prices[proxy] = price_on_or_before(prices.get(proxy, {}), rebalance_day)
        day = rebalance_day + dt.timedelta(days=1)
        while day <= next_day:
            value = 0.0
            covered = 0.0
            for row in group:
                weight = float(row["weight"])
                proxy = row.get("proxy", "")
                if proxy == "CASH":
                    value += weight
                    covered += weight
                    continue
                if not proxy or proxy.startswith("MODULE_"):
                    continue
                p0 = start_prices.get(proxy)
                p1 = price_on_or_before(prices.get(proxy, {}), day)
                if p0 is None or p1 is None:
                    continue
                value += weight * (p1 / p0)
                covered += weight
            if covered >= 0.75:
                navs.append((day, start_nav * value / covered))
                nav = navs[-1][1]
            day += dt.timedelta(days=1)
    return compress_daily(navs)


def domestic_snapshots() -> list[list[dict]]:
    rows = read_csv(DATA_DIR / "domestic_portfolio_detail.csv")
    groups = {}
    for row in rows:
        if row["proxy"].startswith("MODULE_"):
            continue
        groups.setdefault(row["date"], []).append(row)
    return [groups[d] for d in sorted(groups)]


def official_nav_series() -> list[tuple[dt.date, float]]:
    path = DATA_DIR / "official_calibrated_nav.csv"
    if not path.exists():
        path = DATA_DIR / "official_nav_points.csv"
    if not path.exists():
        return []
    rows = read_csv(path)
    best: dict[dt.date, float] = {}
    for row in rows:
        try:
            day = parse_date(row["date"])
            nav = float(row["nav"])
        except Exception:
            continue
        best[day] = nav if day not in best else max(best[day], nav)
    return sorted(best.items())


def compress_daily(navs: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    dedup = {}
    for day, value in navs:
        dedup[day] = value
    return sorted(dedup.items())


def metrics(navs: list[tuple[dt.date, float]]) -> dict:
    if len(navs) < 2:
        return {}
    values = [v for _, v in navs]
    returns = [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1] > 0]
    total = values[-1] / values[0] - 1
    days = max((navs[-1][0] - navs[0][0]).days, 1)
    annual = (1 + total) ** (365 / days) - 1
    vol = statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    sharpe = annual / vol if vol > 0 else None
    peak = values[0]
    max_dd = 0.0
    max_dd_day = navs[0][0]
    for day, value in navs:
        peak = max(peak, value)
        dd = value / peak - 1
        if dd < max_dd:
            max_dd = dd
            max_dd_day = day
    return {
        "start": navs[0][0].isoformat(),
        "end": navs[-1][0].isoformat(),
        "nav": values[-1],
        "total_return": total,
        "annual_return": annual,
        "annual_vol": vol,
        "sharpe_like": sharpe,
        "max_drawdown": max_dd,
        "max_drawdown_day": max_dd_day.isoformat(),
        "days": days,
    }


def svg_chart(series: dict[str, list[tuple[dt.date, float]]], out: Path) -> None:
    width, height = 1100, 560
    left, right, top, bottom = 80, 35, 45, 75
    all_points = [(d, v) for rows in series.values() for d, v in rows]
    min_day, max_day = min(d for d, _ in all_points), max(d for d, _ in all_points)
    min_v = min(v for _, v in all_points) * 0.98
    max_v = max(v for _, v in all_points) * 1.02
    span_days = max((max_day - min_day).days, 1)
    span_v = max(max_v - min_v, 0.01)

    def x(day: dt.date) -> float:
        return left + (day - min_day).days / span_days * (width - left - right)

    def y(value: float) -> float:
        return top + (max_v - value) / span_v * (height - top - bottom)

    colors = {"官方锚定细化曲线": "#111827", "国际版持仓重建": "#2563eb", "内地版代理口径": "#dc2626"}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="80" y="30" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111827">Deepvan 组合净值曲线</text>',
        '<text x="80" y="52" font-family="Arial, sans-serif" font-size="13" fill="#6b7280">黑线为官方锚定细化曲线；蓝线为国际版持仓重建；红线为内地版代理口径。</text>',
    ]
    for i in range(6):
        val = min_v + span_v * i / 5
        yy = y(val)
        lines.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        lines.append(f'<text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{val:.2f}</text>')
    for i in range(5):
        day = min_day + dt.timedelta(days=round(span_days * i / 4))
        xx = x(day)
        lines.append(f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{height-bottom}" stroke="#f3f4f6" stroke-width="1"/>')
        lines.append(f'<text x="{xx:.1f}" y="{height-bottom+25}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{day.isoformat()}</text>')
    lines.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#9ca3af"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#9ca3af"/>')
    legend_x = left
    for label, rows in series.items():
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in rows)
        color = colors.get(label, "#111827")
        lines.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
        lines.append(f'<circle cx="{x(rows[-1][0]):.1f}" cy="{y(rows[-1][1]):.1f}" r="4" fill="{color}"/>')
        lines.append(f'<rect x="{legend_x}" y="{height-35}" width="16" height="3" fill="{color}"/>')
        lines.append(f'<text x="{legend_x+24}" y="{height-30}" font-family="Arial, sans-serif" font-size="13" fill="#111827">{label}</text>')
        legend_x += 250
    lines.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def write_dashboard() -> None:
    end = dt.date(2026, 7, 10)
    holdings = read_csv(DATA_DIR / "portfolio_timeline.holdings.csv")
    intl = holdings_nav(group_by_snapshot(holdings, "叫兽指数国际版/全球版"), end)
    dom = holdings_nav(domestic_snapshots(), dt.date(2026, 6, 29))
    official = official_nav_series()
    series = {}
    if official:
        series["官方锚定细化曲线"] = official
    series["国际版持仓重建"] = intl
    series["内地版代理口径"] = dom
    stats = {name: metrics(rows) for name, rows in series.items()}
    ASSET_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    svg_path = ASSET_DIR / "portfolio_nav.svg"
    svg_chart(series, svg_path)
    (DATA_DIR / "portfolio_dashboard.metrics.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    report = REPORT_DIR / f"portfolio_dashboard_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Deepvan 组合展示面板",
        "",
        "![Deepvan 组合净值曲线](../assets/portfolio_nav.svg)",
        "",
        "## 指标",
        "",
        "| 组合 | 区间 | 净值 | 总收益 | 年化 | 年化波动 | 最大回撤 | Sharpe-like |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, m in stats.items():
        sharpe = "NA" if m.get("sharpe_like") is None else f"{m['sharpe_like']:.2f}"
        lines.append(
            f"| {name} | {m.get('start')} ~ {m.get('end')} | {m.get('nav', 0):.4f} | {pct(m.get('total_return'))} | {pct(m.get('annual_return'))} | {pct(m.get('annual_vol'))} | {pct(m.get('max_drawdown'))} | {sharpe} |"
        )
    lines += [
        "",
        "## 口径",
        "",
        "- 官方锚定细化曲线：官方净值点作为锚点，锚点之间用代理日线形状细化；若缺少持仓重建形状，则用线性连接。",
        "- 国际版持仓重建：使用 OCR 完整持仓表和可取行情代理重建，已覆盖主要美股/港股 ETF 与个股；最早稳定完整表为 2025-04-24，不代表组合成立日。",
        "- 内地版：使用图片 OCR 拆出的 2026-02-24、2026-03-09、2026-03-19 子模块；现金/短债按 0 收益，量化用 ASHR 代理，QDII 子池用 QQQ/DXJ/XLE 等代理。",
        "- 2026-06-29 内地版仍有 75% `台美日韩港混合QDII` 合并桶，底层比例为自定义，因此不把 6/29 之后硬接成精确净值。",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"svg": str(svg_path), "report": str(report), "metrics": str(DATA_DIR / "portfolio_dashboard.metrics.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    write_dashboard()
