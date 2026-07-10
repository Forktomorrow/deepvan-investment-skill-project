#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
]

ACTION_WORDS = "大幅调仓|调仓|加仓|减仓|清仓|止盈|止损|平出|买入|卖出|换仓|换入|转入|配置|对冲|加到|砍掉|保留|新增"
PORTFOLIO_MARKERS = ["叫兽指数", "持仓", "仓位", "组合", "调仓", "净值"]
TABLE_SKIP_PREFIXES = (
    "模拟初始资金",
    "投入资金",
    "当前价",
    "现值",
    "涨幅",
    "净值",
    "说明",
    "加权",
    "初始值",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_alias_rules() -> list[dict]:
    path = DATA_DIR / "asset_aliases.json"
    if not path.exists():
        path = ROOT.parent / "config" / "asset_aliases.example.json"
    if not path.exists():
        return []
    return load_json(path).get("rules", [])


def normalize_asset(asset: str, rules: list[dict]) -> dict:
    raw = asset or ""
    for rule in rules:
        if re.search(rule["pattern"], raw, flags=re.I):
            return {
                "canonical_asset": rule["canonical"],
                "symbol": rule.get("symbol", ""),
                "asset_class": rule.get("asset_class", ""),
                "proxy": rule.get("proxy", ""),
                "data_status": "mapped" if rule.get("proxy") or rule.get("symbol") else "needs_data_mapping",
            }
    return {"canonical_asset": raw, "symbol": "", "asset_class": "Unknown", "proxy": "", "data_status": "unmapped"}


def parse_date(text: str) -> str:
    for pattern in DATE_PATTERNS:
        m = pattern.search(text or "")
        if not m:
            continue
        try:
            return str(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return ""


def clean_title(title: str) -> str:
    return re.sub(r"^\([^)]*\)\s*", "", title or "").replace(" - 知乎", "").strip()


def main_body_text(text: str) -> str:
    body = text or ""
    cut_markers = [
        "\n发布于",
        "\n编辑于",
        "\n赞同 ",
        "\n所属专栏",
        "\n理性发言",
        "\n关于作者",
        "\n推荐阅读",
        "\n腾讯AI",
        "\n揭秘美股",
    ]
    cut_points = [body.find(marker) for marker in cut_markers if body.find(marker) > 80]
    if cut_points:
        body = body[: min(cut_points)]
    return body.strip()


def pct_value(text: str) -> float | None:
    cleaned = (text or "").strip().replace("%6", "%").replace("％", "%")
    m = re.match(r"^(-?\d{1,3}(?:\.\d+)?)%\.?", cleaned)
    if not m:
        return None
    return float(m.group(1)) / 100.0


def iter_articles() -> list[dict]:
    rows = []
    for base_name in ["original_pages_recent", "original_pages"]:
        base = DATA_DIR / base_name
        if not base.exists():
            continue
        for article in sorted(base.glob("*/article.json")):
            data = load_json(article)
            text = data.get("text", "") or ""
            title = clean_title(data.get("title", ""))
            author = data.get("authorHint", "")
            original_hint = "Deep Van" in author or title.startswith("叫兽指数") or title.startswith("Deep Van 的想法") or "Deep Van\nDeep Van的逃生地牢" in text[:1200]
            third_party_hint = title.startswith("2026.7月周总结") or "NEVEN" in text[:120]
            if not original_hint or third_party_hint:
                continue
            ocr_path = article.parent / "ocr_relevant.txt"
            ocr = ocr_path.read_text(encoding="utf-8", errors="ignore") if ocr_path.exists() else ""
            date_text = data.get("published", "") or ((data.get("meta") or {}).get("timeText", "")) or title or text[:500]
            rows.append(
                {
                    "id": article.parent.name,
                    "title": title,
                    "url": (data.get("url") or "").split("?")[0],
                    "date": parse_date(date_text) or parse_date(title) or parse_date(text[:1000]),
                    "text": main_body_text(text),
                    "raw_text": text,
                    "ocr": ocr,
                    "path": str(article),
                }
            )
    unique = {}
    for row in rows:
        key = row["url"] or row["id"]
        old = unique.get(key)
        if not old or len(row["text"]) + len(row["ocr"]) > len(old["text"]) + len(old["ocr"]):
            unique[key] = row
    return sorted(unique.values(), key=lambda r: (r["date"], r["url"]))


def infer_portfolio_id(title: str, text: str) -> str:
    sample = f"{title}\n{text[:1200]}"
    if any(k in sample for k in ["GOOGL", "QQQ", "QQQI", "SPY", "SCHD", "DXJ", "EWY", "BRK", "XLE", "IAUI"]):
        return "叫兽指数国际版/全球版"
    if any(k in sample for k in ["内地版", "纯A", "公募基金版", "国内版"]):
        return "叫兽指数内地版/纯A版"
    if any(k in sample for k in ["全球版", "国际版", "全球配置"]):
        return "叫兽指数国际版/全球版"
    if "叫兽指数" in sample:
        return "叫兽指数国际版/全球版"
    return "未命名组合"


def clean_asset_name(line: str) -> str:
    s = re.sub(r"^\d+[:：]\s*", "", line.strip())
    s = s.replace("（QDI）", "（QDII）").replace("（QDll）", "（QDII）").replace("（QDIl）", "（QDII）")
    s = re.sub(r"\s+", "", s)
    return s.strip(" ，,。.；;|")


def looks_like_asset(line: str) -> bool:
    s = clean_asset_name(line)
    if not s or len(s) < 2:
        return False
    if any(s.startswith(p) for p in TABLE_SKIP_PREFIXES):
        return False
    if s in {"总和", "比例", "平仓利润调整", "剩余现金/平常利润调整"}:
        return True
    if pct_value(s) is not None:
        return False
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return False
    if re.fullmatch(r"[A-Za-z]?\d{2,}", s):
        return False
    return any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in s)


def extract_ocr_tables(row: dict, rules: list[dict]) -> list[dict]:
    lines = [ln.strip() for ln in row["ocr"].splitlines() if ln.strip()]
    tables = extract_domestic_module_table(row, lines, rules)
    tables.extend(extract_simulated_capital_tables(row, lines, rules))
    for total_idx, line in enumerate(lines):
        if clean_asset_name(line) != "总和":
            continue
        if any("模拟初始资金" in ln for ln in lines[max(0, total_idx - 40) : total_idx + 1]):
            continue
        ratio_candidates = [i for i in range(total_idx + 1, min(len(lines), total_idx + 120)) if clean_asset_name(lines[i]) == "比例"]
        if not ratio_candidates:
            continue
        ratio_idx = ratio_candidates[-1]
        asset_lines = []
        for ln in lines[max(0, total_idx - 35) : total_idx]:
            asset = clean_asset_name(ln)
            if not looks_like_asset(asset):
                continue
            if asset in {"平仓利润调整", "剩余现金/平常利润调整"}:
                continue
            asset_lines.append(asset)
        pcts = []
        for ln in lines[ratio_idx + 1 : min(len(lines), ratio_idx + 80)]:
            val = pct_value(ln)
            if val is not None:
                pcts.append((ln, val))
                continue
            if pcts and any(k in ln for k in ["说明", "加权", "评论", "赞同"]):
                break
        if len(asset_lines) < 3 or len(pcts) < 3:
            continue
        n = min(len(asset_lines), len(pcts))
        assets = asset_lines[-n:]
        weights = pcts[:n]
        total = sum(v for _, v in weights)
        if not (0.85 <= total <= 1.15):
            continue
        group_id = f"{row['id']}:ocr:{total_idx}:{ratio_idx}"
        portfolio_id = infer_portfolio_id(row["title"], "\n".join(lines[max(0, total_idx - 40) : min(len(lines), ratio_idx + 20)]))
        holdings = []
        for asset, (raw_pct, weight) in zip(assets, weights):
            norm = normalize_asset(asset, rules)
            holdings.append(
                {
                    "date": row["date"],
                    "portfolio_id": portfolio_id,
                    "asset": asset,
                    **norm,
                    "weight": round(weight, 6),
                    "weight_text": raw_pct.replace("%6", "%"),
                    "source_title": row["title"],
                    "source_url": row["url"],
                    "source_id": row["id"],
                    "group_id": group_id,
                    "evidence": "ocr_complete_table",
                    "confidence": "medium" if 0.95 <= total <= 1.05 else "low",
                    "table_total": round(total, 6),
                }
            )
        tables.append({"group_id": group_id, "date": row["date"], "portfolio_id": portfolio_id, "total": total, "holdings": holdings})
    return tables


def extract_simulated_capital_tables(row: dict, lines: list[str], rules: list[dict]) -> list[dict]:
    starts = [i for i, ln in enumerate(lines) if "模拟初始资金" in ln]
    tables = []
    for bi, start in enumerate(starts):
        end = starts[bi + 1] if bi + 1 < len(starts) else len(lines)
        block = lines[start:end]
        try:
            total_idx = next(i for i, ln in enumerate(block) if clean_asset_name(ln) == "总和")
        except StopIteration:
            continue
        asset_lines = []
        for ln in block[1:total_idx]:
            asset = clean_asset_name(ln)
            if not looks_like_asset(asset):
                continue
            if asset == "比例":
                continue
            if asset.endswith("：") or asset.endswith(":") or asset in {"美国科技头寸", "日韩", "美国/香港红利", "滞涨风险对冲", "黄金"}:
                continue
            asset_lines.append(asset)
        pct_start = 0
        ratio_positions = [i for i, ln in enumerate(block) if "比例" in ln]
        explain_positions = [i for i, ln in enumerate(block) if "说明" in ln]
        if ratio_positions:
            pct_start = ratio_positions[-1] + 1
        elif explain_positions:
            pct_start = explain_positions[0] + 1
        pcts = []
        for ln in block[pct_start:]:
            val = pct_value(ln)
            if val is not None:
                pcts.append((ln, val))
        if len(asset_lines) < 4 or len(pcts) < 4:
            continue
        n = min(len(asset_lines), len(pcts))
        assets = asset_lines[-n:]
        weights = choose_weight_window(pcts, n)
        total = sum(v for _, v in weights)
        if not (0.85 <= total <= 1.15):
            continue
        group_id = f"{row['id']}:simcap:{start}"
        portfolio_id = infer_portfolio_id(row["title"], "\n".join(block[:80]))
        holdings = []
        for asset, (raw_pct, weight) in zip(assets, weights):
            norm = normalize_asset(asset, rules)
            holdings.append(
                {
                    "date": row["date"],
                    "portfolio_id": portfolio_id,
                    "asset": asset,
                    **norm,
                    "weight": round(weight, 6),
                    "weight_text": raw_pct.replace("%6", "%"),
                    "source_title": row["title"],
                    "source_url": row["url"],
                    "source_id": row["id"],
                    "group_id": group_id,
                    "evidence": "ocr_simulated_capital_table",
                    "confidence": "medium" if 0.95 <= total <= 1.05 else "low",
                    "table_total": round(total, 6),
                }
            )
        tables.append({"group_id": group_id, "date": row["date"], "portfolio_id": portfolio_id, "total": total, "holdings": holdings})
    return tables


def choose_weight_window(pcts: list[tuple[str, float]], n: int) -> list[tuple[str, float]]:
    if len(pcts) <= n:
        return pcts[:n]
    candidates = []
    for i in range(0, len(pcts) - n + 1):
        window = pcts[i : i + n]
        total = sum(v for _, v in window)
        negatives = sum(1 for _, v in window if v < 0)
        candidates.append((abs(total - 1.0) + negatives * 0.25, i, window))
    candidates.sort(key=lambda x: x[0])
    return candidates[0][2]


def extract_domestic_module_table(row: dict, lines: list[str], rules: list[dict]) -> list[dict]:
    if "内地版" not in row["title"] and "公募基金版" not in row["title"]:
        return []
    text = "\n".join(lines)
    if "QDII主线组合" not in text or "A股量化" not in text:
        return []
    # Current OCR for the domestic/public-fund version gives module totals rather
    # than one clean row per fund. Keep it as a 100% module table instead of
    # inventing fund-level weights.
    holdings = [
        ("QDII主线组合", 0.75, "台美日韩港混合 QDII 子池，子成分累计到 75%"),
        ("黄金", 0.10, "华夏黄金 ETF，追踪黄金现货"),
        ("国金量化多因子", 0.10, "A股量化，可以用国金量化精选平替"),
        ("大成动态量化配置", 0.05, "A股量化备选模块"),
    ]
    group_id = f"{row['id']}:domestic_modules"
    rows = []
    for asset, weight, note in holdings:
        norm = normalize_asset(asset, rules)
        rows.append(
            {
                "date": row["date"],
                "portfolio_id": "叫兽指数内地版/公募基金版",
                "asset": asset,
                **norm,
                "weight": round(weight, 6),
                "weight_text": f"{weight:.2%}",
                "source_title": row["title"],
                "source_url": row["url"],
                "source_id": row["id"],
                "group_id": group_id,
                "evidence": "ocr_module_table",
                "confidence": "medium",
                "table_total": 1.0,
                "note": note,
            }
        )
    return [{"group_id": group_id, "date": row["date"], "portfolio_id": "叫兽指数内地版/公募基金版", "total": 1.0, "holdings": rows}]


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[\n。；;]+", text or "") if p.strip()]


def extract_text_events(row: dict) -> list[dict]:
    if not any(k in row["title"] + row["text"][:3000] + row["ocr"][:1500] for k in PORTFOLIO_MARKERS):
        return []
    sentences = split_sentences(row["text"] + "\n" + row["ocr"])
    events = []
    action_re = re.compile(rf"(?P<action>{ACTION_WORDS})(?P<body>[^。；;\n]{{0,90}})")
    pct_change_re = re.compile(r"(?P<asset>[\u4e00-\u9fa5A-Za-z0-9/（）() +.-]{2,36}?)[，, ]*(?P<from>\d{1,2}(?:\.\d+)?)%\s*(?:->|→|到|至|降至|加到|升至)\s*(?P<to>\d{1,2}(?:\.\d+)?)%")
    netvalue_re = re.compile(r"净值(?:从)?(?P<from>\d(?:\.\d+)?)\s*(?:->|→|到|至|回落到|反弹到)\s*(?P<to>\d(?:\.\d+)?)")
    for idx, sentence in enumerate(sentences):
        has_action = re.search(ACTION_WORDS, sentence) is not None
        has_portfolio_context = any(k in sentence for k in ["叫兽指数", "仓位", "持仓", "调仓", "组合", "净值"])
        if not (has_action or has_portfolio_context):
            continue
        for m in pct_change_re.finditer(sentence):
            if not (has_action or any(k in sentence for k in ["仓位", "持仓", "叫兽指数", "组合"])):
                continue
            asset = clean_asset_name(m.group("asset"))
            if not asset or asset in {"期限溢价", "名义10年期收益率", "实际利率", "通胀预期"}:
                continue
            if len(asset) > 28:
                asset = asset[-28:]
            events.append(
                {
                    "date": row["date"],
                    "portfolio_id": infer_portfolio_id(row["title"], sentence),
                    "event_type": "weight_change",
                    "action": "调仓",
                    "asset": asset,
                    "from_weight": float(m.group("from")) / 100.0,
                    "to_weight": float(m.group("to")) / 100.0,
                    "reason": nearby_reason(sentences, idx),
                    "sentence": sentence[:500],
                    "source_title": row["title"],
                    "source_url": row["url"],
                    "source_id": row["id"],
                    "confidence": "high",
                }
            )
        for m in action_re.finditer(sentence):
            body = clean_action_body(m.group("body"))
            if not body:
                continue
            from_w, to_w = weights_from_sentence(sentence)
            events.append(
                {
                    "date": row["date"],
                    "portfolio_id": infer_portfolio_id(row["title"], sentence),
                    "event_type": "action",
                    "action": m.group("action"),
                    "asset": body,
                    "from_weight": from_w,
                    "to_weight": to_w,
                    "reason": nearby_reason(sentences, idx),
                    "sentence": sentence[:500],
                    "source_title": row["title"],
                    "source_url": row["url"],
                    "source_id": row["id"],
                    "confidence": "medium",
                }
            )
        nm = netvalue_re.search(sentence)
        if nm:
            events.append(
                {
                    "date": row["date"],
                    "portfolio_id": infer_portfolio_id(row["title"], sentence),
                    "event_type": "net_value",
                    "action": "净值变化",
                    "asset": "组合净值",
                    "from_weight": nm.group("from"),
                    "to_weight": nm.group("to"),
                    "reason": "",
                    "sentence": sentence[:500],
                    "source_title": row["title"],
                    "source_url": row["url"],
                    "source_id": row["id"],
                    "confidence": "high",
                }
            )
    return dedupe_dicts(events, ["date", "event_type", "action", "asset", "from_weight", "to_weight", "source_url"])


def clean_action_body(text: str) -> str:
    s = re.sub(r"(?:，|,|。|；|;).*$", "", text or "")
    s = re.sub(r"(?:理由|原因|因为|由于|来|去|后|直到|等).*", "", s)
    s = s.strip(" ：:，,。.；;了 的")
    if len(s) < 2 or len(s) > 36:
        return ""
    if any(k in s for k in ["日期", "如下", "之前", "之后", "报告", "新闻", "季度", "指数如下"]):
        return ""
    return s


def weights_from_sentence(sentence: str) -> tuple[str, str]:
    m = re.search(r"(?:从|由)?(?P<from>\d{1,2}(?:\.\d+)?)%?\s*(?:->|→|到|至|降至|升至|加到)\s*(?P<to>\d{1,2}(?:\.\d+)?)%", sentence)
    if not m:
        return "", ""
    return str(float(m.group("from")) / 100.0), str(float(m.group("to")) / 100.0)


def nearby_reason(sentences: list[str], idx: int) -> str:
    window = sentences[idx : min(len(sentences), idx + 4)]
    for s in window:
        if any(k in s for k in ["理由", "原因", "因为", "由于", "源于", "利好", "利空", "风险", "逻辑"]):
            return s[:260]
    return ""


def dedupe_dicts(rows: list[dict], keys: list[str]) -> list[dict]:
    out, seen = [], set()
    for row in rows:
        key = tuple(row.get(k, "") for k in keys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, holdings: list[dict], events: list[dict], candidates: list[dict]) -> None:
    complete_groups = defaultdict(list)
    for h in holdings:
        complete_groups[h["group_id"]].append(h)
    lines = [
        "# Deepvan 组合时间线抽取报告",
        "",
        "口径：只使用已确认 Deep Van 本人公开原文；删除、私密、资源不存在内容不进入本报告。",
        "",
        "## 摘要",
        "",
        f"- 完整 OCR 持仓表：{len(complete_groups)} 组",
        f"- 持仓行：{len(holdings)} 条",
        f"- 文本调仓/净值事件：{len(events)} 条",
        f"- 候选原文：{len(candidates)} 篇/条",
        "",
        "## 完整持仓表",
        "",
    ]
    for group_id, rows in sorted(complete_groups.items(), key=lambda kv: (kv[1][0]["date"], kv[0])):
        first = rows[0]
        lines += [
            f"### {first['date']} · {first['portfolio_id']} · 合计 {first['table_total']:.2%}",
            f"来源：[{first['source_title']}]({first['source_url']})",
            "",
            "| 标的 | 权重 | 置信度 |",
            "|---|---:|---|",
        ]
        for h in rows:
            lines.append(f"| {h['asset']} | {h['weight']:.2%} | {h['confidence']} |")
        lines.append("")
    lines += ["## 调仓/净值事件 Top 80", "", "| 日期 | 组合 | 动作 | 标的 | 变化 | 理由/证据 | 来源 |", "|---|---|---|---|---|---|---|"]
    for e in sorted(events, key=lambda r: (r["date"], r["source_url"]))[:80]:
        change = ""
        if e.get("from_weight") != "" or e.get("to_weight") != "":
            change = f"{e.get('from_weight')} -> {e.get('to_weight')}"
        reason = e.get("reason") or e.get("sentence", "")
        lines.append(f"| {e['date']} | {e['portfolio_id']} | {e['action']} | {e['asset']} | {change} | {reason[:100]} | [link]({e['source_url']}) |")
    lines += ["", "## 需要复核的点", "", "- OCR 表格已经能还原为权重表，但部分标的名称存在识别误差，例如 `南方东英东西精选`、`剩余现金/平仓利润调整` 等，需要建立别名表。", "- 文本调仓事件只作为候选事实；真正回测时优先使用完整 OCR 持仓表。", "- 国内版/国际版已经拆开，但老文章里未显式写版本的表，当前默认归入全球版，需要继续人工抽样复核。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-prefix", default=str(DATA_DIR / "portfolio_timeline"))
    args = parser.parse_args()
    articles = iter_articles()
    rules = load_alias_rules()
    candidates = []
    holdings = []
    events = []
    for row in articles:
        score_text = row["title"] + "\n" + row["text"][:4000] + "\n" + row["ocr"][:2000]
        if any(k in score_text for k in PORTFOLIO_MARKERS):
            candidates.append({"date": row["date"], "title": row["title"], "url": row["url"], "id": row["id"]})
        for table in extract_ocr_tables(row, rules):
            holdings.extend(table["holdings"])
        events.extend(extract_text_events(row))
    holdings = dedupe_dicts(holdings, ["date", "portfolio_id", "asset", "weight", "source_url", "group_id"])
    events = dedupe_dicts(events, ["date", "portfolio_id", "event_type", "action", "asset", "from_weight", "to_weight", "source_url"])
    prefix = Path(args.out_prefix)
    write_csv(prefix.with_suffix(".holdings.csv"), holdings, ["date", "portfolio_id", "asset", "canonical_asset", "symbol", "asset_class", "proxy", "data_status", "weight", "weight_text", "source_title", "source_url", "source_id", "group_id", "evidence", "confidence", "table_total"])
    write_csv(prefix.with_suffix(".events.csv"), events, ["date", "portfolio_id", "event_type", "action", "asset", "from_weight", "to_weight", "reason", "sentence", "source_title", "source_url", "source_id", "confidence"])
    write_csv(prefix.with_suffix(".candidates.csv"), candidates, ["date", "title", "url", "id"])
    report = REPORT_DIR / f"portfolio_timeline_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    write_report(report, holdings, events, candidates)
    print(json.dumps({"holdings": len(holdings), "events": len(events), "candidates": len(candidates), "report": str(report)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
