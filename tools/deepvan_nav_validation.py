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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepvan_dashboard import group_by_snapshot, holdings_nav, read_csv  # noqa: E402
from deepvan_portfolio_backtest import parse_date  # noqa: E402


def pct(x: float | None) -> str:
    return "NA" if x is None or math.isnan(x) else f"{x:.2%}"


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


def official_points() -> list[tuple[dt.date, float, dict]]:
    rows = read_csv(DATA_DIR / "official_nav_points.csv")
    best: dict[dt.date, dict] = {}
    for row in rows:
        try:
            day = parse_date(row["date"])
            nav = float(row["nav"])
        except Exception:
            continue
        if day not in best or nav > float(best[day]["nav"]):
            best[day] = row
    return [(day, float(row["nav"]), row) for day, row in sorted(best.items())]


def nearest_value(series: list[tuple[dt.date, float]], day: dt.date, max_delta: int = 4) -> tuple[dt.date, float] | None:
    by_day = dict(series)
    for delta in range(max_delta + 1):
        for candidate in [day - dt.timedelta(days=delta), day + dt.timedelta(days=delta)]:
            if candidate in by_day:
                return candidate, by_day[candidate]
    return None


def calibrated_curve(official: list[tuple[dt.date, float, dict]], recon: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float, str]]:
    recon_by_day = dict(recon)
    out: dict[dt.date, tuple[float, str]] = {}
    for i, (start_day, start_nav, _) in enumerate(official[:-1]):
        end_day, end_nav, _ = official[i + 1]
        if end_day <= start_day:
            continue
        segment_days = [d for d, _ in recon if start_day <= d <= end_day]
        if len(segment_days) >= 3:
            base0 = nearest_value(recon, start_day, 7)
            base1 = nearest_value(recon, end_day, 7)
            if base0 and base1 and base1[1] > 0 and base0[1] > 0:
                raw_total = base1[1] / base0[1]
                target_total = end_nav / start_nav
                for day in segment_days:
                    raw_progress = recon_by_day[day] / base0[1]
                    if abs(raw_total - 1.0) < 1e-9:
                        t = (day - start_day).days / max((end_day - start_day).days, 1)
                        value = start_nav * ((target_total - 1) * t + 1)
                    else:
                        # Preserve the proxy cumulative shape and add a smooth
                        # time drift so the segment lands exactly on the
                        # official endpoint. This avoids exploding volatility
                        # when raw_total is close to 1.
                        t = (day - start_day).days / max((end_day - start_day).days, 1)
                        correction = target_total / raw_total
                        value = start_nav * raw_progress * (correction ** t)
                    out[day] = (value, "official_anchor_proxy_shape")
                continue
        # Fallback: linear interpolation between official anchors.
        day = start_day
        while day <= end_day:
            t = (day - start_day).days / max((end_day - start_day).days, 1)
            out[day] = (start_nav + (end_nav - start_nav) * t, "official_anchor_linear")
            day += dt.timedelta(days=1)
    # Include the last official point.
    if official:
        out[official[-1][0]] = (official[-1][1], "official_anchor")
    return [(day, value, method) for day, (value, method) in sorted(out.items())]


def write_outputs() -> None:
    holdings = read_csv(DATA_DIR / "portfolio_timeline.holdings.csv")
    recon = holdings_nav(group_by_snapshot(holdings, "叫兽指数国际版/全球版"), dt.date(2026, 7, 10))
    official = official_points()

    # Scale reconstructed series to the first official point in its coverage, so
    # comparison measures drift/shape error rather than arbitrary base=1.
    overlap = [(day, nav, meta) for day, nav, meta in official if nearest_value(recon, day, 7)]
    scale = 1.0
    if overlap:
        first_day, first_nav, _ = overlap[0]
        near = nearest_value(recon, first_day, 7)
        if near and near[1] > 0:
            scale = first_nav / near[1]
    scaled_recon = [(day, value * scale) for day, value in recon]

    comparison = []
    for day, nav, meta in official:
        near = nearest_value(scaled_recon, day, 7)
        comparison.append(
            {
                "date": day.isoformat(),
                "official_nav": nav,
                "reconstructed_date": near[0].isoformat() if near else "",
                "reconstructed_nav_scaled": near[1] if near else "",
                "diff": (near[1] / nav - 1) if near and nav else "",
                "source_title": meta.get("source_title", ""),
                "source_url": meta.get("source_url", ""),
            }
        )

    calibrated = calibrated_curve(official, scaled_recon)
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    comp_path = DATA_DIR / "nav_validation.comparison.csv"
    with comp_path.open("w", encoding="utf-8", newline="") as f:
        fields = ["date", "official_nav", "reconstructed_date", "reconstructed_nav_scaled", "diff", "source_title", "source_url"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(comparison)

    curve_path = DATA_DIR / "official_calibrated_nav.csv"
    with curve_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "nav", "method"])
        writer.writeheader()
        for day, value, method in calibrated:
            writer.writerow({"date": day.isoformat(), "nav": value, "method": method})

    stat = metrics([(day, value) for day, value, _ in calibrated])
    stat_path = DATA_DIR / "official_calibrated_metrics.json"
    stat_path.write_text(json.dumps(stat, ensure_ascii=False, indent=2), encoding="utf-8")

    report = REPORT_DIR / f"nav_validation_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Deepvan 官方净值校验与细化曲线",
        "",
        "口径：官方净值点作为锚点；持仓重建曲线只用于校验和锚点之间的日线形状。若同日偏差较大，优先复核 OCR 表、调仓前后表选择、分红复权和代理标的。",
        "",
        "## 官方锚定细化曲线指标",
        "",
        f"- 区间：{stat.get('start')} ~ {stat.get('end')}",
        f"- 净值：{stat.get('nav', 0):.4f}",
        f"- 总收益：{pct(stat.get('total_return'))}",
        f"- 年化收益：{pct(stat.get('annual_return'))}",
        f"- 年化波动：{pct(stat.get('annual_vol'))}",
        f"- 最大回撤：{pct(stat.get('max_drawdown'))}（{stat.get('max_drawdown_day')}）",
        f"- Sharpe-like：{'NA' if stat.get('sharpe_like') is None else format(stat.get('sharpe_like'), '.2f')}",
        "",
        "## 官方点 vs 持仓重建",
        "",
        "| 日期 | 官方净值 | 重建净值(缩放后) | 偏差 | 来源 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in comparison:
        recon_text = "" if row["reconstructed_nav_scaled"] == "" else f"{float(row['reconstructed_nav_scaled']):.4f}"
        diff_text = "" if row["diff"] == "" else pct(float(row["diff"]))
        lines.append(f"| {row['date']} | {float(row['official_nav']):.4f} | {recon_text} | {diff_text} | [{row['source_title']}]({row['source_url']}) |")
    lines += [
        "",
        "## 解释",
        "",
        "- 2025-04-24 以前没有足够稳定的完整持仓表，细化曲线主要靠官方净值点线性连接。",
        "- 2025-04-24 之后，代理曲线能提供日内/日线形状，但必须用官方点校准，因为 QDII 净值滞后、分红复权和备兑 ETF 收益结构都会造成偏差。",
        "- 如果偏差持续扩大，说明某个时间点的 OCR 表、调仓前后表或代理标的可能有误。",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"comparison": str(comp_path), "curve": str(curve_path), "metrics": str(stat_path), "report": str(report)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    write_outputs()
