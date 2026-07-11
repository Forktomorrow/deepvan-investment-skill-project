#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepvan_portfolio_backtest import fetch_yahoo_daily, parse_date  # noqa: E402


def pct(x: float) -> str:
    return f"{x:.2%}"


def source(article_id: str) -> tuple[str, str]:
    for base in [DATA_DIR / "original_pages_recent", DATA_DIR / "original_pages"]:
        p = base / article_id / "article.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("title", ""), (data.get("url", "") or "").split("?")[0]
    return article_id, ""


def domestic_rows() -> list[dict]:
    rows: list[dict] = []

    def add(date: str, article_id: str, asset: str, weight: float, proxy: str, evidence: str, note: str, constituents: str = "") -> None:
        title, url = source(article_id)
        rows.append(
            {
                "date": date,
                "portfolio_id": "叫兽指数内地版/公募基金版",
                "asset": asset,
                "weight": weight,
                "proxy": proxy,
                "evidence": evidence,
                "source_id": article_id,
                "source_title": title,
                "source_url": url,
                "note": note,
                "constituents": constituents,
            }
        )

    global_qdii = "招商纳斯达克100ETF; 嘉实美国成长人民币; 景顺长城纳斯达克科技市值加权; 广发纳斯达克生物科技; 标普生物科技LOF; 东亚联丰环球股票基金R; 浦银安盛全球智能科技A; 工银全球精选; 广发全球精选"
    asia_qdii = "摩根日经ETF; 华泰柏瑞中证韩交所半导体ETF; 南方富时亚太低碳精选ETF联接A/C; 博时大中华亚太精选股票QDII; 国富亚洲机会股票(QDII)C"
    global_qdii_0629 = "汇添富纳斯达克100; 摩根标普500指数; 嘉实美国成长人民币; 景顺长城纳斯达克科技市值加权; 工银全球精选; 广发全球精选; 东亚联丰环球股票基金; 银华海外数字经济量化选股混合"
    asia_qdii_0629 = "摩根日经ETF; 南方亚太精选ETF联接; 天弘全球高端制造; 国富亚洲机会股票(QDII)A/C; 富国全球互联网股票(QDII)A/C; 摩根太平洋科技人民币对冲累计; 华夏新时代灵活配置混合QDII"

    # 2026-03-09 final OCR table after the emergency rebalance.
    aid = "2014269142774072915"
    add("2026-03-09", aid, "纳斯达克100+标普500+全球QDII", 0.15, "QQQ", "ocr_domestic_detail", "子成分累加到 15%；原图备注为比例自定义。", global_qdii)
    add("2026-03-09", aid, "日韩QDII", 0.15, "DXJ", "ocr_domestic_detail", "从 40% 止损到 15%；子成分比例自定义。", asia_qdii)
    add("2026-03-09", aid, "华夏黄金ETF", 0.12, "GLD", "ocr_domestic_detail", "追踪黄金现货。")
    add("2026-03-09", aid, "华夏有色金属ETF联接C", 0.03, "PICK", "ocr_domestic_detail", "OCR 代码 016708；后续 3/19 文中清空。")
    add("2026-03-09", aid, "摩根全球天然资源", 0.15, "XLE", "ocr_domestic_detail", "OCR 备注能源占比约 35%，可用中海油平替。")
    add("2026-03-09", aid, "国泰大宗商品", 0.05, "COM", "ocr_domestic_detail", "OCR 代码 025162。")
    add("2026-03-09", aid, "富国国有企业债券/现金短债", 0.20, "CASH", "ocr_domestic_detail", "OCR 备注 000139，纯现金/短债，等抄底。")
    add("2026-03-09", aid, "国金量化多因子", 0.10, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")
    add("2026-03-09", aid, "大成动态量化配置", 0.025, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")
    add("2026-03-09", aid, "诺安多策略混合", 0.025, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")

    # 2026-03-19 final OCR table. Text says clear 3% colored metals, keep commodity 3%, raise cash/bond to 25%.
    aid = "2017962413476033586"
    add("2026-03-19", aid, "纳斯达克100+标普500+全球QDII", 0.15, "QQQ", "ocr_domestic_detail", "子成分累加到 15%；原图备注为比例自定义。", global_qdii)
    add("2026-03-19", aid, "日韩QDII", 0.15, "DXJ", "ocr_domestic_detail", "子成分累加到 15%；原图备注为比例自定义。", asia_qdii)
    add("2026-03-19", aid, "华夏黄金ETF", 0.12, "GLD", "ocr_domestic_detail", "追踪黄金现货。")
    add("2026-03-19", aid, "摩根全球天然资源", 0.15, "XLE", "ocr_domestic_detail", "能源占比约 35%，可用中海油平替。")
    add("2026-03-19", aid, "国泰大宗商品", 0.03, "COM", "ocr_domestic_detail", "战争长期化/滞涨风险对冲。")
    add("2026-03-19", aid, "富国国有企业债券/现金短债", 0.25, "CASH", "ocr_domestic_detail", "保留现金/短债仓，等抄底。")
    add("2026-03-19", aid, "国金量化多因子", 0.10, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")
    add("2026-03-19", aid, "大成动态量化配置", 0.025, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")
    add("2026-03-19", aid, "诺安多策略混合", 0.025, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")

    # 2026-06-29 low-turnover public-fund version. The image gives a 75% combined QDII bucket.
    aid = "2054914732071695921"
    add("2026-06-29", aid, "台美日韩港混合QDII", 0.75, "MODULE_QDII_MAIN", "ocr_domestic_detail", "原图只给 75% 合并桶；底层基金列表给出，但各基金比例自定义，不能精确拆到单基金。", global_qdii_0629 + "; " + asia_qdii_0629)
    add("2026-06-29", aid, "华夏黄金ETF", 0.10, "GLD", "ocr_domestic_detail", "追踪黄金现货。")
    add("2026-06-29", aid, "国金量化多因子", 0.10, "ASHR", "ocr_domestic_detail", "可以用国金量化精选平替；暂用 ASHR 作为可取价 A股代理。")
    add("2026-06-29", aid, "大成动态量化配置", 0.05, "ASHR", "ocr_domestic_detail", "A股量化，暂用 ASHR 作为可取价 A股代理。")
    return rows


def write_outputs() -> Path:
    rows = domestic_rows()
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / "domestic_portfolio_detail.csv"
    fields = ["date", "portfolio_id", "asset", "weight", "proxy", "evidence", "source_id", "source_title", "source_url", "note", "constituents"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = REPORT_DIR / f"domestic_portfolio_detail_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Deepvan 国内版持仓 OCR 明细",
        "",
        "口径：只使用 Deep Van 本人公开原文图片 OCR。`比例自定义` 的子池不拆到单只基金，先保留为子模块和可选基金清单。",
        "",
    ]
    for date in sorted({r["date"] for r in rows}):
        day = [r for r in rows if r["date"] == date]
        total = sum(float(r["weight"]) for r in day)
        lines += [f"## {date} · 合计 {pct(total)}", "", "| 组分 | 权重 | 回测代理 | 说明 |", "|---|---:|---|---|"]
        for r in day:
            lines.append(f"| {r['asset']} | {pct(float(r['weight']))} | `{r['proxy']}` | {r['note']} |")
        lines.append("")
        with_const = [r for r in day if r["constituents"]]
        if with_const:
            lines += ["可选底层基金清单：", ""]
            for r in with_const:
                lines.append(f"- {r['asset']}：{r['constituents']}")
            lines.append("")
    lines += domestic_proxy_backtest(rows)
    lines += [
        "## 当前卡点",
        "",
        "- 2026-03-09 和 2026-03-19 已经能从图中拆到子模块，足够做一个代理回测。",
        "- 2026-06-29 的图只给 `台美日韩港混合QDII 75%`，底层基金比例写的是自定义；如果不引入假设，无法精确拆到单基金。",
        "- 后续国内版回撤可以做两档：`严格口径` 只算图中明确权重；`代理口径` 用 QQQ/DXJ/XLE/GLD/COM/中证500/现金近似子模块。",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"csv": str(csv_path), "report": str(report), "rows": len(rows)}, ensure_ascii=False, indent=2))
    return report


def domestic_proxy_backtest(rows: list[dict]) -> list[str]:
    usable = [r for r in rows if r["proxy"] and not r["proxy"].startswith("MODULE_")]
    start = dt.date(2026, 3, 9)
    end = dt.date(2026, 6, 29)
    proxies = sorted({r["proxy"] for r in usable if r["proxy"] != "CASH"})
    prices = {p: fetch_yahoo_daily(p, start - dt.timedelta(days=7), end) for p in proxies}
    px = {}
    for proxy, series in prices.items():
        px[proxy] = {parse_date(r["date"]): float(r["close"]) for r in series}

    def price_on_or_before(proxy: str, day: dt.date) -> float | None:
        if proxy == "CASH":
            return 1.0
        series = px.get(proxy) or {}
        for delta in range(0, 8):
            val = series.get(day - dt.timedelta(days=delta))
            if val is not None:
                return val
        return None

    snapshots = {}
    for day in ["2026-03-09", "2026-03-19"]:
        snapshots[parse_date(day)] = [r for r in rows if r["date"] == day]

    nav = 1.0
    navs = [(start, nav)]
    periods = []
    dates = sorted(snapshots)
    for i, rebalance_day in enumerate(dates):
        next_day = dates[i + 1] if i + 1 < len(dates) else end
        holdings = snapshots[rebalance_day]
        covered = sum(float(r["weight"]) for r in holdings if not r["proxy"].startswith("MODULE_"))
        start_prices = {r["proxy"]: price_on_or_before(r["proxy"], rebalance_day) for r in holdings}
        daily_navs = []
        day = rebalance_day + dt.timedelta(days=1)
        while day <= next_day:
            value = 0.0
            ok_weight = 0.0
            for r in holdings:
                w = float(r["weight"])
                proxy = r["proxy"]
                if proxy.startswith("MODULE_"):
                    continue
                p0 = start_prices.get(proxy)
                p1 = price_on_or_before(proxy, day)
                if p0 is None or p1 is None:
                    continue
                ok_weight += w
                value += w * (p1 / p0)
            if ok_weight >= 0.95:
                daily_navs.append((day, nav * value / ok_weight))
            day += dt.timedelta(days=1)
        if daily_navs:
            nav = daily_navs[-1][1]
            navs.extend(daily_navs)
            period_ret = daily_navs[-1][1] / navs[-len(daily_navs)-1][1] - 1.0 if len(navs) > len(daily_navs) else daily_navs[-1][1] - 1.0
        else:
            period_ret = math.nan
        periods.append((rebalance_day, next_day, covered, period_ret))

    peak = navs[0][1]
    max_dd = 0.0
    max_dd_day = navs[0][0]
    for day, value in navs:
        peak = max(peak, value)
        dd = value / peak - 1.0
        if dd < max_dd:
            max_dd = dd
            max_dd_day = day
    lines = [
        "## 代理口径回测",
        "",
        "这不是最终净值口径，而是把 OCR 明确权重的子模块映射到可取行情代理后得到的近似回测。现金/短债按 0 收益处理；国内量化暂用 ASHR 作为可取价 A股代理；QDII 子池用 QQQ/DXJ/XLE 等代理。",
        "",
        f"- 可算区间：2026-03-09 至 2026-06-29",
        f"- 代理净值：{nav:.4f}",
        f"- 区间收益：{pct(nav - 1.0)}",
        f"- 最大回撤：{pct(max_dd)}，发生在 {max_dd_day.isoformat()} 附近",
        "",
        "| 区间 | 覆盖权重 | 区间收益 |",
        "|---|---:|---:|",
    ]
    for start_day, end_day, covered, ret in periods:
        ret_text = "NA" if math.isnan(ret) else pct(ret)
        lines.append(f"| {start_day.isoformat()} ~ {end_day.isoformat()} | {pct(covered)} | {ret_text} |")
    lines.append("")
    return lines


if __name__ == "__main__":
    write_outputs()
