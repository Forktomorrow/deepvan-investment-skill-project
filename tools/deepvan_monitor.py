#!/usr/bin/env python3
"""
Deep Van Zhihu search backfill and portfolio-change monitor.

Token handling:
  export ZH_TOKEN='...'

Common commands:
  python deepvan_monitor.py backfill --config config.json
  python deepvan_monitor.py monitor --config config.json
  python deepvan_monitor.py report --config config.json

Optional notification:
  export DEEPVAN_NOTIFY_WEBHOOK='https://...'
For Feishu custom bots, the sender posts msg_type=text.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


API_URL = "https://developer.zhihu.com/api/v1/content/zhihu_search"
ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
DEFAULT_CONFIG = ROOT / "config.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def stable_key(item: dict) -> str:
    raw = item.get("Url") or item.get("ContentID") or json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def query_api(token: str, query: str, count: int) -> dict:
    cmd = [
        "curl",
        "-sS",
        "-G",
        API_URL,
        "--data-urlencode",
        f"Query={query}",
        "-d",
        f"Count={max(1, min(count, 10))}",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        f"X-Request-Timestamp: {int(time.time())}",
        "-H",
        "Content-Type: application/json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35, check=False)
    raw = proc.stdout or proc.stderr
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"Code": -1, "Message": raw[:500], "Data": None}


def month_tokens(days: int) -> list[str]:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    y, m = start.year, start.month
    out = []
    while (y, m) <= (today.year, today.month):
        out.append(f"{y}.{m:02d}")
        out.append(f"{y}年{m}月")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def build_backfill_queries(config: dict) -> list[str]:
    names = config["actor_names"]
    portfolio = config["portfolio_keywords"]
    topics = config["topic_keywords"]
    months = month_tokens(config.get("lookback_days", 730))
    queries = []

    for name in names:
        queries.append(name)
        for kw in portfolio + topics:
            queries.append(f"{name} {kw}")
        for month in months:
            queries.append(f"{name} {month}")
        for month in months:
            for kw in portfolio[:8]:
                queries.append(f"{name} {month} {kw}")
        for month in months[-8:]:
            for kw in topics:
                queries.append(f"{name} {month} {kw}")

    deduped = []
    seen = set()
    for q in queries:
        if q not in seen:
            deduped.append(q)
            seen.add(q)
    return deduped[: int(config.get("daily_budget", 1000))]


def build_monitor_queries(config: dict) -> list[str]:
    today = dt.date.today()
    recent = [
        today.strftime("%Y.%m.%d"),
        today.strftime("%Y年%-m月%-d日") if sys.platform != "win32" else f"{today.year}年{today.month}月{today.day}日",
        today.strftime("%Y.%m"),
        f"{today.year}年{today.month}月",
    ]
    queries = []
    for name in config["actor_names"]:
        for kw in config["portfolio_keywords"]:
            queries.append(f"{name} {kw}")
        for token in recent:
            queries.append(f"{name} {token}")
            for kw in config["portfolio_keywords"][:8]:
                queries.append(f"{name} {token} {kw}")
    limit = int(config.get("monitor_query_limit", min(80, int(config.get("daily_budget", 1000)))))
    return list(dict.fromkeys(queries))[:limit]


HOLDING_PATTERNS = [
    re.compile(r"(?P<asset>[\u4e00-\u9fa5A-Za-z0-9._ /+-]{1,24}?)(?:仓位|占比|持仓)?(?:为|:|：)?(?P<pct>\d{1,2}(?:\.\d+)?)%"),
    re.compile(r"(?P<action>加仓|减仓|清仓|止盈|止损|买入|卖出|重仓|低位抄底|保留|新增)(?P<asset>[\u4e00-\u9fa5A-Za-z0-9._ /+-]{1,28})"),
]


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


def deepvan_section_text(item: dict) -> str:
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


def is_portfolio_relevant(item: dict, config: dict) -> bool:
    text = item_text(item)
    if item.get("VoteUpCount", 0) < config.get("alert", {}).get("min_vote_up", 0):
        return False
    return any(k in text for k in config["portfolio_keywords"])


def is_primary_source(item: dict, config: dict) -> bool:
    policy = config.get("source_policy", {})
    authors = set(policy.get("primary_author_names", ["Deep Van"]))
    return item.get("AuthorName") in authors or item.get("_source_kind") == "deepvan_original_page"


def extract_events(item: dict, config: dict) -> list[dict]:
    text = deepvan_section_text(item)
    if not is_portfolio_relevant(item, config):
        return []
    events = []
    for pattern in HOLDING_PATTERNS:
        for match in pattern.finditer(text):
            data = match.groupdict()
            asset = (data.get("asset") or "").strip(" ：:，,。.；;\n\t")
            if not asset or len(asset) < 2:
                continue
            events.append(
                {
                    "asset": asset,
                    "pct": data.get("pct"),
                    "action": data.get("action"),
                    "source_title": item.get("Title", ""),
                    "source_url": item.get("Url", ""),
                    "edit_time": item.get("EditTime"),
                    "vote_up": item.get("VoteUpCount", 0),
                    "author": item.get("AuthorName", ""),
                    "content_id": item.get("ContentID", ""),
                    "snippet": text[:600],
                }
            )
    return events


def evidence_tier(item: dict) -> str:
    if item.get("AuthorName") == "Deep Van":
        return "A"
    text = deepvan_section_text(item)
    if text.startswith("Deep Van") or re.search(r"Deep Van\s*\n?\d+\.\[", text):
        return "B"
    return "C"


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"(?<=\])\s*", " ", text)
    parts = re.split(r"[\n。；;]+", normalized)
    return [p.strip(" \t，,") for p in parts if p.strip(" \t，,")]


def asset_meta(raw_asset: str, config: dict) -> dict:
    raw = raw_asset.strip(" ：:，,。.；;（）()[]【】 \n\t")
    assets = config.get("portfolio_assets", {})
    if raw in assets:
        return {"raw": raw, "known": True, **assets[raw]}
    for name, meta in sorted(assets.items(), key=lambda kv: len(kv[0]), reverse=True):
        if name and name in raw:
            return {"raw": raw, "known": True, **meta}
    if re.fullmatch(r"[A-Z]{2,5}", raw):
        market = "国际"
        return {"raw": raw, "known": True, "canonical": raw, "market": market, "symbol": raw}
    market = "国际" if any(k in raw for k in ["标普", "XBI", "IBB", "QQQ", "纳指", "美股", "日经", "印度", "黄金"]) else "国内"
    return {"raw": raw, "known": False, "canonical": raw, "market": market, "symbol": ""}


def portfolio_asset_meta(raw_asset: str, config: dict) -> dict:
    meta = asset_meta(raw_asset, config)
    if meta.get("known"):
        return meta
    raw = raw_asset.strip(" ：:，,。.；;（）()[]【】 \n\t")
    generic = {
        "科技": {"canonical": "科技", "market": "国内", "symbol": ""},
        "A股科技": {"canonical": "科技", "market": "国内", "symbol": ""},
        "黄金/大宗商品": {"canonical": "黄金/大宗商品", "market": "国内", "symbol": ""},
        "大宗商品": {"canonical": "黄金/大宗商品", "market": "国内", "symbol": ""},
        "A股量化": {"canonical": "A股量化", "market": "国内", "symbol": ""},
        "现金": {"canonical": "现金", "market": "国内", "symbol": ""},
        "标普生物/标普500": {"canonical": "标普生物/标普500", "market": "国际", "symbol": ""},
    }
    for name, value in generic.items():
        if name in raw:
            return {"raw": raw, "known": True, **value}
    return meta


def infer_portfolio_id(item: dict, text: str = "") -> str:
    title = item.get("Title", "") or ""
    sample = title + "\n" + text[:1200]
    if any(k in sample for k in ["内地版", "纯A", "公募基金版", "国内版"]):
        return "叫兽指数内地版/纯A版"
    if "叫兽指数" in sample or any(k in sample for k in ["SHV", "纳斯达克100", "摩根日本", "印度基金LOF", "摩根欧洲动力"]):
        return "叫兽指数国际版/全球配置版"
    if any(k in sample for k in ["当前持仓", "经过这两天调仓", "半导体占比"]):
        return "Deepvan当前跟踪组合"
    return "未命名组合"


def ocr_table_asset_meta(raw_asset: str, config: dict, portfolio_id: str) -> dict:
    meta = portfolio_asset_meta(raw_asset, config)
    if meta.get("known"):
        return meta
    raw = raw_asset.strip(" ：:，,。.；;了 \n\t")
    market = "国内可买全球资产" if "国际版" in portfolio_id or "全球配置" in portfolio_id else "国内"
    symbol = ""
    symbol_map = {
        "SHV": "SHV",
        "纳斯达克100": "QQQ",
        "标普500": "SPY",
        "黄金": "XAU/GLD",
    }
    for key, value in symbol_map.items():
        if key in raw:
            symbol = value
            break
    return {"raw": raw, "known": True, "canonical": raw, "market": market, "symbol": symbol}


def extract_ocr_portfolio_table_records(item: dict, config: dict) -> list[dict]:
    text = item.get("ContentText", "") or deepvan_section_text(item)
    if "[OCR_IMAGE_TEXT]" not in text:
        return []
    records = []
    for block in text.split("[OCR_IMAGE_TEXT]")[1:]:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if "比例" not in lines or "总和" not in lines:
            continue
        total_idx = lines.index("总和")
        ratio_idx = lines.index("比例")
        if ratio_idx <= total_idx:
            continue
        asset_names = [x for x in lines[:total_idx] if x not in {"平仓利润调整"}]
        pct_lines = []
        for ln in lines[ratio_idx + 1 :]:
            if any(k in ln for k in ["加权成本价", "现值", "涨幅", "加权", "说明"]):
                break
            if re.fullmatch(r"\d{1,3}(?:\.\d+)?%", ln):
                pct_lines.append(ln)
        if len(asset_names) < 3 or len(pct_lines) < 3:
            continue
        pairs = []
        for raw_asset, pct_text in zip(asset_names, pct_lines):
            weight = float(pct_text.rstrip("%")) / 100.0
            meta = ocr_table_asset_meta(raw_asset, config, infer_portfolio_id(item, block))
            pairs.append((raw_asset, meta, weight))
        total = sum(w for _, _, w in pairs)
        if not (0.95 <= total <= 1.05):
            continue
        portfolio_id = infer_portfolio_id(item, block)
        group_base = hashlib.sha256((item.get("Url", "") + portfolio_id + "".join(asset_names)).encode("utf-8")).hexdigest()[:16]
        for raw_asset, meta, weight in pairs:
            records.append(
                {
                    "date": str(date_from_item(item)),
                    "action": "组合表持仓",
                    "asset": meta["canonical"],
                    "raw_asset": meta["raw"],
                    "market": meta["market"],
                    "symbol": meta.get("symbol", ""),
                    "weight": weight,
                    "reason": f"OCR识别组合表：{portfolio_id}，该表比例列合计 {format_weight(total)}",
                    "source_title": item.get("Title", ""),
                    "source_url": item.get("Url", ""),
                    "source_author": item.get("AuthorName", ""),
                    "evidence_tier": evidence_tier(item),
                    "snippet": "\n".join(lines[: min(len(lines), 40)])[:500],
                    "portfolio_complete": True,
                    "portfolio_total": round(total, 6),
                    "portfolio_scope": portfolio_id,
                    "portfolio_id": portfolio_id,
                    "portfolio_group_id": f"{group_base}:{portfolio_id}",
                }
            )
    return records


def clean_asset_fragment(fragment: str) -> list[str]:
    fragment = re.sub(r"（[^）]*）|\([^)]*\)", "", fragment)
    fragment = re.sub(r"(?:原因|理由|因为|由于|认为|判断|当前|今日|昨日|计划|建议|操作上).*", "", fragment)
    pieces = re.split(r"[、/和及与，,]", fragment)
    cleaned = []
    stop = {"", "部分", "前期", "方向", "品种", "仓位", "股票", "资产", "风险", "科技", "价值股"}
    for p in pieces:
        p = p.strip(" ：:，,。.；;了 \n\t")
        p = re.sub(r"^(?:轻仓|小幅|大幅|继续|进一步|直接|全部|部分)", "", p).strip()
        if len(p) >= 2 and p not in stop and not re.fullmatch(r"\d+(?:\.\d+)?", p):
            cleaned.append(p)
    return cleaned[:6]


def known_asset_names(config: dict) -> list[str]:
    return sorted(config.get("portfolio_assets", {}).keys(), key=len, reverse=True)


def pct_near_asset(sentence: str, asset: str) -> float | None:
    for match in re.finditer(re.escape(asset), sentence):
        start, end = match.span()
        near = sentence[max(0, start - 16) : min(len(sentence), end + 20)]
        patterns = [
            rf"{re.escape(asset)}(?:仓位|占比|持仓)?(?:为|至|降至|降到|降低到|降低到了|升至|升到|:|：)?\s*(?P<pct>\d{{1,2}}(?:\.\d+)?)%",
            rf"(?P<pct>\d{{1,2}}(?:\.\d+)?)%\s*(?:的)?{re.escape(asset)}",
            r"(?:仓位|占比|持仓)(?:为|至|降至|降到|降低到|降低到了|升至|升到|:|：)?\s*(?P<pct>\d{1,2}(?:\.\d+)?)%",
        ]
        for pattern in patterns:
            m = re.search(pattern, near)
            if m:
                return float(m.group("pct")) / 100.0
    return None


def extract_pct_pairs(sentence: str, config: dict) -> list[dict]:
    pairs: list[dict] = []
    seen = set()
    assets = known_asset_names(config) + ["黄金/大宗商品", "大宗商品", "A股量化", "A股科技", "科技", "现金", "标普生物/标普500"]
    for raw_asset in sorted(set(assets), key=len, reverse=True):
        if raw_asset not in sentence:
            continue
        pct = pct_near_asset(sentence, raw_asset)
        if pct is None:
            continue
        meta = portfolio_asset_meta(raw_asset, config)
        if not meta.get("known"):
            continue
        key = (meta["canonical"], pct)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"asset": meta["canonical"], "raw_asset": meta["raw"], "market": meta["market"], "symbol": meta.get("symbol", ""), "weight": pct})
    return pairs


def mark_portfolio_completeness(records: list[dict], pairs: list[dict], item: dict, sentence: str) -> None:
    by_market: dict[str, float] = {}
    for p in pairs:
        by_market[p["market"]] = by_market.get(p["market"], 0.0) + p["weight"]
    complete_markets = {m: total for m, total in by_market.items() if 0.95 <= total <= 1.05 and len([p for p in pairs if p["market"] == m]) >= 2}
    overall_total = sum(p["weight"] for p in pairs)
    overall_complete = 0.95 <= overall_total <= 1.05 and len(pairs) >= 3
    if not complete_markets and not overall_complete:
        return
    group_base = hashlib.sha256((item.get("Url", "") + sentence).encode("utf-8")).hexdigest()[:16]
    portfolio_id = infer_portfolio_id(item, sentence)
    for r in records:
        market = r.get("market")
        if (overall_complete or market in complete_markets) and any(p["asset"] == r.get("asset") and abs(p["weight"] - (r.get("weight") or -1)) < 0.0001 for p in pairs):
            r["portfolio_complete"] = True
            r["portfolio_total"] = round(overall_total if overall_complete else complete_markets[market], 6)
            r["portfolio_scope"] = portfolio_id if overall_complete else market
            r["portfolio_id"] = portfolio_id if overall_complete else f"{portfolio_id}/{market}"
            r["portfolio_group_id"] = f"{group_base}:{r['portfolio_scope']}"


def reason_for_sentence(sentence: str, next_sentence: str = "") -> str:
    text = sentence
    if any(k in next_sentence for k in ["原因", "理由", "因为", "源于", "认为", "判断", "核心", "风险", "利好", "利空"]):
        text += "；" + next_sentence
    reason_markers = ["原因是", "理由是", "因为", "由于", "源于", "因", "认为", "判断", "核心"]
    for marker in reason_markers:
        if marker in text:
            return text[text.find(marker) :].strip()[:260]
    return text.strip()[:220]


def reason_for_record(action: str, asset: str, sentence: str, sentences: list[str], idx: int) -> str:
    asset_text = asset
    if any(k in asset_text for k in ["XBI", "标普生物", "生科", "创新药", "IBB"]):
        keys = ["XBI", "标普生物", "创新药", "利率", "FDA", "并购", "IPO", "临床"]
    elif any(k in asset_text for k in ["半导体", "雅克", "赛腾", "至纯", "通富", "安集", "华海", "拓荆", "澜起", "京东方"]):
        keys = ["半导体", "AI", "资本开支", "Capex", "CapEx", "Meta", "三星", "收入", "存储", "HBM", "CXL"]
    elif any(k in asset_text for k in ["紫金", "有色", "钨", "厦门钨业"]):
        keys = ["有色", "利率", "钨", "出口", "供应", "资源"]
    elif any(k in asset_text for k in ["美的", "招商", "量化"]):
        keys = ["对冲", "分散", "价值", "量化", "美的", "招商", "内需", "风险"]
    else:
        keys = []

    window = sentences[max(0, idx - 1) : min(len(sentences), idx + 5)]
    scored = []
    for s in window:
        hit = sum(1 for k in keys if k in s)
        reasonish = any(k in s for k in ["原因", "理由", "因为", "由于", "源于", "认为", "判断", "核心", "风险", "利好", "利空", "取决于"])
        if hit or reasonish:
            scored.append((hit + (1 if reasonish else 0), s))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return reason_for_sentence(scored[0][1], "")
    next_sentence = sentences[idx + 1] if idx + 1 < len(sentences) else ""
    return reason_for_sentence(sentence, next_sentence)


def extract_rebalance_records(item: dict, config: dict) -> list[dict]:
    policy = config.get("source_policy", {})
    if policy.get("portfolio_fact_sources") == "primary_only" and not is_primary_source(item, config):
        return []
    text = deepvan_section_text(item)
    ocr_records = extract_ocr_portfolio_table_records(item, config)
    if not any(k in text for k in config.get("portfolio_keywords", [])):
        return ocr_records
    sentences = split_sentences(text)
    records = []
    tier = evidence_tier(item)
    action_pattern = re.compile(r"(?P<action>大幅调仓|重仓加回|低位抄底|加仓|减仓|清仓|平出|止盈|止损|买入|卖出|新增|保留|换仓|换入|转入|加入|加到|去掉|合并|配置|补仓)(?P<asset>[\u4e00-\u9fa5A-Za-z0-9._ /+（）()、和及与-]{1,48})")
    assets = known_asset_names(config)

    for idx, sentence in enumerate(sentences):
        next_sentence = sentences[idx + 1] if idx + 1 < len(sentences) else ""
        if not any(k in sentence for k in config.get("portfolio_keywords", [])):
            continue

        sentence_records_start = len(records)
        pct_pairs = extract_pct_pairs(sentence, config)
        for raw_asset in assets:
            if raw_asset not in sentence:
                continue
            pct = pct_near_asset(sentence, raw_asset)
            if pct is None:
                continue
            meta = asset_meta(raw_asset, config)
            records.append(
                {
                    "date": str(date_from_item(item)),
                    "action": "持仓",
                    "asset": meta["canonical"],
                    "raw_asset": meta["raw"],
                    "market": meta["market"],
                    "symbol": meta.get("symbol", ""),
                    "weight": pct,
                    "reason": reason_for_record("持仓", raw_asset, sentence, sentences, idx),
                    "source_title": item.get("Title", ""),
                    "source_url": item.get("Url", ""),
                    "source_author": item.get("AuthorName", ""),
                    "evidence_tier": tier,
                        "snippet": sentence[:500],
                    }
                )

        for pair in pct_pairs:
            if any(r.get("asset") == pair["asset"] and r.get("weight") == pair["weight"] and r.get("snippet") == sentence[:500] for r in records[sentence_records_start:]):
                continue
            records.append(
                {
                    "date": str(date_from_item(item)),
                    "action": "持仓",
                    "asset": pair["asset"],
                    "raw_asset": pair["raw_asset"],
                    "market": pair["market"],
                    "symbol": pair.get("symbol", ""),
                    "weight": pair["weight"],
                    "reason": reason_for_record("持仓", pair["raw_asset"], sentence, sentences, idx),
                    "source_title": item.get("Title", ""),
                    "source_url": item.get("Url", ""),
                    "source_author": item.get("AuthorName", ""),
                    "evidence_tier": tier,
                    "snippet": sentence[:500],
                }
            )
        mark_portfolio_completeness(records[sentence_records_start:], pct_pairs, item, sentence)

        for match in action_pattern.finditer(sentence):
            action = match.group("action")
            for raw_asset in clean_asset_fragment(match.group("asset")):
                meta = asset_meta(raw_asset, config)
                if not meta.get("known"):
                    continue
                records.append(
                    {
                        "date": str(date_from_item(item)),
                        "action": action,
                        "asset": meta["canonical"],
                        "raw_asset": meta["raw"],
                        "market": meta["market"],
                        "symbol": meta.get("symbol", ""),
                        "weight": None,
                        "reason": reason_for_record(action, raw_asset, sentence, sentences, idx),
                        "source_title": item.get("Title", ""),
                        "source_url": item.get("Url", ""),
                        "source_author": item.get("AuthorName", ""),
                        "evidence_tier": tier,
                        "snippet": sentence[:500],
                    }
                )

    records.extend(ocr_records)
    deduped = []
    seen = set()
    for r in records:
        key = json.dumps({k: r.get(k) for k in ["date", "action", "asset", "weight", "source_url"]}, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            deduped.append(r)
            seen.add(key)
    return deduped


def date_from_item(item: dict) -> dt.date | str:
    ts = item.get("EditTime")
    if not ts:
        return ""
    return dt.datetime.fromtimestamp(int(ts)).date()


def load_portfolio_snapshot() -> dict:
    return load_json(STATE_DIR / "portfolio_snapshot.json", {"国内": {}, "国际": {}, "updated_at": ""})


def apply_rebalance_records(records: list[dict], reset: bool = False) -> tuple[dict, list[dict]]:
    snapshot = {"portfolios": {}, "国内": {}, "国际": {}, "未分类": {}, "updated_at": ""} if reset else load_portfolio_snapshot()
    snapshot.setdefault("portfolios", {})
    changes = []
    applied_complete_groups = set()
    applied_portfolio_groups = set()
    for r in sorted(records, key=lambda x: (x.get("date") or "", x.get("source_url") or "")):
        market = r.get("market") or "未分类"
        snapshot.setdefault(market, {})
        group_id = r.get("portfolio_group_id")
        reset_key = (group_id, market)
        if r.get("portfolio_complete") and group_id and reset_key not in applied_complete_groups:
            snapshot[market] = {}
            applied_complete_groups.add(reset_key)
        asset = r["asset"]
        old = snapshot[market].get(asset, {})
        new = dict(old)
        new.update(
            {
                "symbol": r.get("symbol", ""),
                "last_action": r.get("action"),
                "last_seen": r.get("date"),
                "source_url": r.get("source_url"),
                "portfolio_complete": bool(r.get("portfolio_complete")),
                "portfolio_group_id": group_id or old.get("portfolio_group_id", ""),
                "portfolio_scope": r.get("portfolio_scope") or old.get("portfolio_scope", ""),
            }
        )
        if r.get("weight") is not None:
            new["weight"] = r["weight"]
        if r.get("action") in {"清仓", "去掉", "平出"} and r.get("weight") is None:
            new["weight"] = 0.0
        snapshot[market][asset] = new
        portfolio_id = r.get("portfolio_id") or r.get("portfolio_scope")
        if portfolio_id and r.get("portfolio_complete"):
            portfolio = snapshot["portfolios"].setdefault(portfolio_id, {})
            portfolio_reset_key = (group_id, portfolio_id)
            if group_id and portfolio_reset_key not in applied_portfolio_groups:
                portfolio.clear()
                applied_portfolio_groups.add(portfolio_reset_key)
            p_old = portfolio.get(asset, {})
            p_new = dict(p_old)
            p_new.update(
                {
                    "symbol": r.get("symbol", ""),
                    "market": market,
                    "last_action": r.get("action"),
                    "last_seen": r.get("date"),
                    "source_url": r.get("source_url"),
                    "portfolio_group_id": group_id or p_old.get("portfolio_group_id", ""),
                }
            )
            if r.get("weight") is not None:
                p_new["weight"] = r["weight"]
            portfolio[asset] = p_new
        changes.append({**r, "old_weight": old.get("weight"), "new_weight": new.get("weight")})
    snapshot["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    write_json(STATE_DIR / "portfolio_snapshot.json", snapshot)
    return snapshot, changes


def format_weight(w: float | None) -> str:
    if w is None:
        return "未知"
    return f"{w * 100:.1f}%"


def format_snapshot(snapshot: dict) -> list[str]:
    lines = []
    portfolios = snapshot.get("portfolios") or {}
    for portfolio_id, assets in sorted(portfolios.items()):
        weighted = [(a, v) for a, v in assets.items() if v.get("weight") is not None and v.get("weight") > 0]
        if not weighted:
            continue
        total = sum(v.get("weight", 0) for _, v in weighted)
        lines.append(f"{portfolio_id}：完整度={'完整' if 0.95 <= total <= 1.05 else '部分'}，已识别合计={format_weight(total)}")
        for asset, info in sorted(weighted, key=lambda kv: kv[1].get("weight", 0), reverse=True)[:20]:
            symbol = f"({info.get('symbol')})" if info.get("symbol") else ""
            lines.append(f"- {asset}{symbol}: {format_weight(info.get('weight'))}")
        if total < 0.995:
            lines.append(f"- 未识别/现金/其他: {format_weight(max(0.0, 1.0 - total))}")
        elif total > 1.005:
            lines.append("- 注意：该组合已识别权重超过 100%，需检查是否混入行业桶和个股明细。")
    if lines:
        return lines
    all_weighted = []
    for market in ["国内", "国际", "未分类"]:
        for asset, info in snapshot.get(market, {}).items():
            if info.get("weight") is not None and info.get("weight") > 0:
                all_weighted.append((market, asset, info))
    overall_total = sum(info.get("weight", 0) for _, _, info in all_weighted)
    overall_groups = {info.get("portfolio_group_id") for _, _, info in all_weighted if info.get("portfolio_complete") and info.get("portfolio_scope") == "全组合"}
    overall_complete = bool(overall_groups) and 0.95 <= overall_total <= 1.05
    if overall_groups:
        lines.append(f"全组合：完整度={'完整' if overall_complete else '部分/后续有增量覆盖'}，已识别合计={format_weight(overall_total)}")
    for market in ["国内", "国际", "未分类"]:
        assets = snapshot.get(market, {})
        if not assets:
            continue
        weighted = [(a, v) for a, v in assets.items() if v.get("weight") is not None and v.get("weight") > 0]
        if not weighted:
            continue
        total = sum(v.get("weight", 0) for _, v in weighted)
        complete_groups = {v.get("portfolio_group_id") for _, v in weighted if v.get("portfolio_complete") and v.get("portfolio_group_id")}
        is_complete = bool(complete_groups) and 0.95 <= total <= 1.05
        if overall_complete:
            lines.append(f"{market}桶：全组合内占比={format_weight(total)}")
        else:
            lines.append(f"{market}组合：完整度={'完整' if is_complete else '部分'}，已识别合计={format_weight(total)}")
        for asset, info in sorted(weighted, key=lambda kv: kv[1].get("weight", 0), reverse=True)[:15]:
            symbol = f"({info.get('symbol')})" if info.get("symbol") else ""
            lines.append(f"- {asset}{symbol}: {format_weight(info.get('weight'))}")
        if not overall_complete and total < 0.995:
            lines.append(f"- 未识别/现金/其他: {format_weight(max(0.0, 1.0 - total))}")
        elif total > 1.005:
            lines.append(f"- 注意：当前已识别权重超过 100%，可能混入了行业桶和个股明细的重复口径。")
    return lines


def format_rebalance_alert(changes: list[dict], snapshot: dict) -> str:
    title = f"Deep Van 调仓监控：发现 {len(changes)} 条新组合信号"
    lines = [title, ""]
    ordered = sorted(changes, key=lambda x: (x.get("date") or "", x.get("source_url") or ""), reverse=True)
    for i, c in enumerate(ordered[:18], 1):
        symbol = f" {c['symbol']}" if c.get("symbol") else ""
        old_w = format_weight(c.get("old_weight"))
        new_w = format_weight(c.get("new_weight"))
        lines.append(f"{i}. [{c.get('market')}] {c.get('action')} {c.get('asset')}{symbol}")
        if c.get("weight") is not None or c.get("new_weight") == 0.0:
            lines.append(f"   仓位：{old_w} -> {new_w}")
        lines.append(f"   原因摘要：{c.get('reason') or '未抽取到明确原因'}")
        lines.append(f"   证据：Tier {c.get('evidence_tier')}，来源：{c.get('source_title')}")
        lines.append(f"   链接：{c.get('source_url')}")
    snap_lines = format_snapshot(snapshot)
    if snap_lines:
        lines += ["", "当前已维护组合快照：", *snap_lines]
    return "\n".join(lines)


def search_many(config: dict, queries: list[str], mode: str) -> list[dict]:
    token = os.environ.get("ZH_TOKEN")
    if not token:
        raise SystemExit("Missing ZH_TOKEN. Run: export ZH_TOKEN='...'")

    sleep_s = float(config.get("request_sleep_seconds", 1.25))
    count = int(config.get("count_per_query", 10))
    raw_dir = DATA_DIR / f"raw_{mode}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    all_items: dict[str, dict] = {}

    for idx, query in enumerate(queries, 1):
        data = query_api(token, query, count)
        write_json(raw_dir / f"{idx:04d}.json", {"query": query, "response": data})
        print(f"[{idx}/{len(queries)}] {query} -> {data.get('Code')} {data.get('Message')}")
        if data.get("Code") == 0 and data.get("Data"):
            for item in data["Data"].get("Items", []):
                item["_query"] = query
                key = stable_key(item)
                old = all_items.get(key)
                if not old or item.get("RankingScore", 0) > old.get("RankingScore", 0):
                    all_items[key] = item
        elif data.get("Code") == 30001:
            time.sleep(max(3.0, sleep_s * 3))
        time.sleep(sleep_s)

    rows = sorted(all_items.values(), key=lambda x: (x.get("EditTime", 0), x.get("RankingScore", 0)), reverse=True)
    append_jsonl(DATA_DIR / "items.jsonl", rows)
    return rows


def dedupe_store() -> list[dict]:
    rows = read_jsonl(DATA_DIR / "items.jsonl")
    best: dict[str, dict] = {}
    for row in rows:
        key = stable_key(row)
        old = best.get(key)
        if not old or row.get("RankingScore", 0) > old.get("RankingScore", 0):
            best[key] = row
    out = sorted(best.values(), key=lambda x: (x.get("EditTime", 0), x.get("RankingScore", 0)), reverse=True)
    path = DATA_DIR / "items_deduped.jsonl"
    path.write_text("", encoding="utf-8")
    append_jsonl(path, out)
    return out


def send_webhook(text: str, config: dict) -> None:
    env_name = config.get("alert", {}).get("webhook_url_env", "DEEPVAN_NOTIFY_WEBHOOK")
    url = os.environ.get(env_name)
    if not url:
        return
    provider = (config.get("alert", {}).get("provider", "") or "").lower()
    if provider == "feishu" or "open.feishu.cn/open-apis/bot" in url:
        payload = {"msg_type": "text", "content": {"text": text}}
    elif provider in {"qq", "qqbot"}:
        payload = {"msg_type": "text", "content": {"text": text}}
    elif provider == "generic_json":
        payload = {"text": text, "source": "deepvan_monitor"}
    else:
        payload = {"text": text}
    subprocess.run(
        ["curl", "-sS", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", json.dumps(payload, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def monitor(config: dict, limit: int | None = None) -> None:
    seen_path = STATE_DIR / "seen_items.json"
    prev_events_path = STATE_DIR / "portfolio_events.json"
    seen = set(load_json(seen_path, []))
    prev_events = load_json(prev_events_path, [])
    prev_event_keys = {json.dumps({k: e.get(k) for k in ["asset", "pct", "action", "source_url"]}, ensure_ascii=False, sort_keys=True) for e in prev_events}

    queries = build_monitor_queries(config)
    if limit:
        queries = queries[:limit]
    rows = search_many(config, queries, "monitor")
    new_rows = [r for r in rows if stable_key(r) not in seen]
    events = []
    rebalance_records = []
    for row in new_rows:
        events.extend(extract_events(row, config))
        rebalance_records.extend(extract_rebalance_records(row, config))

    new_events = []
    for event in events:
        event_key = json.dumps({k: event.get(k) for k in ["asset", "pct", "action", "source_url"]}, ensure_ascii=False, sort_keys=True)
        if event_key not in prev_event_keys:
            new_events.append(event)

    for row in new_rows:
        seen.add(stable_key(row))
    write_json(seen_path, sorted(seen))
    write_json(prev_events_path, prev_events + new_events)
    dedupe_store()

    rebalance_seen_path = STATE_DIR / "rebalance_keys.json"
    rebalance_seen = set(load_json(rebalance_seen_path, []))
    fresh_rebalance = []
    for r in rebalance_records:
        key = json.dumps({k: r.get(k) for k in ["date", "action", "asset", "weight", "source_url"]}, ensure_ascii=False, sort_keys=True)
        if key not in rebalance_seen:
            fresh_rebalance.append(r)
            rebalance_seen.add(key)
    write_json(rebalance_seen_path, sorted(rebalance_seen))

    if fresh_rebalance:
        snapshot, changes = apply_rebalance_records(fresh_rebalance)
        text = format_rebalance_alert(changes, snapshot)
    elif new_events:
        lines = [f"Deep Van portfolio monitor: {len(new_events)} new portfolio-related signals"]
        for e in new_events[:20]:
            label = e["asset"]
            if e.get("pct"):
                label += f" {e['pct']}%"
            if e.get("action"):
                label = f"{e['action']} {label}"
            lines.append(f"- {label} | {e['source_title']} | {e['source_url']}")
        text = "\n".join(lines)
    else:
        text = f"Deep Van portfolio monitor: no new portfolio-change signal. New items scanned: {len(new_rows)}"

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    alert_path = REPORT_DIR / f"alert_{stamp}.md"
    alert_path.write_text(text + "\n", encoding="utf-8")
    send_webhook(text, config)
    print(text)


def portfolio_report(config: dict, items_path: Path | None = None) -> None:
    rows = read_jsonl(items_path) if items_path else dedupe_store()
    records = []
    for row in rows:
        records.extend(extract_rebalance_records(row, config))
    snapshot, changes = apply_rebalance_records(records, reset=True)
    text = format_rebalance_alert(changes[:40], snapshot) if changes else "No portfolio records extracted."
    path = REPORT_DIR / f"portfolio_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text(text + "\n", encoding="utf-8")
    print(path)


def webhook_test(config: dict) -> None:
    text = (
        "Deep Van 调仓监控测试\n"
        "飞书机器人已连通。后续如检测到国内/国际组合调仓，会发送：动作、资产、仓位变化、原因摘要、来源链接和证据等级。"
    )
    send_webhook(text, config)
    print("webhook test sent")


def report(config: dict, items_path: Path | None = None) -> None:
    rows = read_jsonl(items_path) if items_path else dedupe_store()
    events = []
    for row in rows:
        events.extend(extract_events(row, config))
    by_asset: dict[str, list[dict]] = {}
    for e in events:
        by_asset.setdefault(e["asset"], []).append(e)
    lines = [
        "# Deep Van Monitor Report",
        "",
        f"- Items: {len(rows)}",
        f"- Portfolio-related extracted events: {len(events)}",
        "",
        "## Top Extracted Assets/Actions",
        "",
    ]
    for asset, evs in sorted(by_asset.items(), key=lambda kv: len(kv[1]), reverse=True)[:40]:
        lines.append(f"- {asset}: {len(evs)}")
    lines += ["", "## Recent Events", ""]
    for e in sorted(events, key=lambda x: x.get("edit_time") or 0, reverse=True)[:80]:
        label = e["asset"]
        if e.get("pct"):
            label += f" {e['pct']}%"
        if e.get("action"):
            label = f"{e['action']} {label}"
        lines.append(f"- {label} | {e['source_title']} | {e['source_url']}")
    path = REPORT_DIR / f"report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backfill", "monitor", "report", "portfolio-report", "webhook-test", "queries"])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--items", help="optional JSONL item corpus; useful for browser-fetched original pages")
    parser.add_argument("--limit", type=int, help="limit query count for smoke tests")
    args = parser.parse_args()
    config = load_json(Path(args.config), {})

    if args.command == "queries":
        queries = build_backfill_queries(config)
        if args.limit:
            queries = queries[: args.limit]
        for query in queries:
            print(query)
    elif args.command == "backfill":
        queries = build_backfill_queries(config)
        if args.limit:
            queries = queries[: args.limit]
        rows = search_many(config, queries, "backfill")
        deduped = dedupe_store()
        print(f"Fetched {len(rows)} rows this run; store now has {len(deduped)} deduped rows.")
    elif args.command == "monitor":
        monitor(config, args.limit)
    elif args.command == "report":
        report(config, Path(args.items) if args.items else None)
    elif args.command == "portfolio-report":
        portfolio_report(config, Path(args.items) if args.items else None)
    elif args.command == "webhook-test":
        webhook_test(config)


if __name__ == "__main__":
    main()
