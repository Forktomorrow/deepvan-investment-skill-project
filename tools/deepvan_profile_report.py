#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from pathlib import Path

import deepvan_monitor as monitor


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(text: str) -> dt.date | None:
    if not text:
        return None
    m = re.search(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})", text)
    if not m:
        return None
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def clean_title(title: str) -> str:
    return re.sub(r"^\([^)]*\)\s*", "", title or "").replace(" - 知乎", "").strip()


def is_deepvan_original(data: dict, article: Path) -> bool:
    title = clean_title(data.get("title", ""))
    text = data.get("text", "")
    meta = data.get("meta", {})
    if meta and "Deep Van" in (data.get("authorHint", "") + text[:300]):
        return True
    if title.startswith("2026.7月周总结") or "NEVEN" in text[:80]:
        return False
    if "Deep Van" in text[:1200] or "Deep Van" in data.get("authorHint", ""):
        return True
    # Browser-fetched archive ids from the old search API are explicitly stored
    # under original_pages; keep them unless they are known third-party summaries.
    return article.parent.name != "2057187497612939295"


def iter_original_pages(paths: list[Path]) -> list[dict]:
    rows = []
    for base in paths:
        if not base.exists():
            continue
        for article in sorted(base.glob("*/article.json")):
            data = load_json(article)
            if not is_deepvan_original(data, article):
                continue
            meta = data.get("meta", {})
            text = data.get("text", "")
            ocr_text_path = article.parent / "ocr_relevant.txt"
            if ocr_text_path.exists():
                ocr_text = ocr_text_path.read_text(encoding="utf-8", errors="ignore").strip()
                if ocr_text:
                    text = text + "\n\n[OCR_IMAGE_TEXT]\n" + ocr_text
            date = parse_date(data.get("published", "")) or parse_date(meta.get("timeText", "")) or parse_date(data.get("title", "")) or parse_date(text[:1600])
            rows.append(
                {
                    "id": article.parent.name,
                    "date": date,
                    "date_text": str(date) if date else (data.get("published") or meta.get("timeText") or ""),
                    "title": clean_title(data.get("title", "")),
                    "url": data.get("url", ""),
                    "text": text,
                    "text_length": data.get("textLength") or len(text),
                    "image_count": len(data.get("images", [])),
                    "source_dir": str(article.parent),
                }
            )
    unique = {}
    for row in rows:
        key = row["url"].split("?")[0] or row["id"]
        old = unique.get(key)
        if not old or row["text_length"] > old["text_length"]:
            unique[key] = row
    return sorted(unique.values(), key=lambda r: r["date"] or dt.date.min, reverse=True)


def recency_weight(date: dt.date | None, today: dt.date, half_life_days: int = 60) -> float:
    if not date:
        return 0.25
    age = max(0, (today - date).days)
    return round(0.25 + 0.75 * math.exp(-math.log(2) * age / half_life_days), 4)


TOPIC_RULES = [
    ("AI / 半导体", ["半导体", "AI", "HBM", "长鑫", "拓荆", "安集", "华海", "通富", "先进封装", "C2W", "W2W", "国产替代"]),
    ("全球配置 / 叫兽指数", ["叫兽指数", "美股", "日韩", "日经", "韩国", "标普", "纳指", "QDII", "SHV", "TLT"]),
    ("黄金 / 大宗", ["黄金", "白银", "有色", "大宗", "美元", "美债", "实际利率", "央行"]),
    ("A股量化 / 内地版", ["量化", "国金量化", "招商量化", "纯A", "内地版", "A股"]),
    ("创新药 / XBI", ["XBI", "创新药", "生物", "FDA", "并购", "药企"]),
    ("红利 / 价值", ["红利", "股息", "南方东西精选", "港股通", "股东回报", "公司治理"]),
]


SKILL_RULES = [
    ("证据优先：把每笔操作留痕，拒绝嘴盘", ["每期的操作我都用表格做了记录", "每笔操作都可以复查", "嘴盘"]),
    ("变量触发调仓：发现核心变量变坏就先降风险", ["资本开支", "Capex", "Meta", "长鑫IPO", "抽取资金", "风险"]),
    ("组合而非单点：用指数/ETF/篮子表达主题", ["叫兽指数", "ETF", "QDII", "指数", "组合"]),
    ("中观映射：海外产业链变量映射到国内可买资产", ["对应国内版", "日韩", "台积电", "东京电子", "BESI", "国产替代"]),
    ("股东回报框架：公司治理改善可重估市场", ["股东回报", "公司治理", "Value-Up", "分红", "回购", "PB"]),
    ("期权/对冲框架：高波动时区分方向和波动率", ["期权", "隐含波动率", "delta", "对冲", "看跌期权"]),
    ("宏观风向标：黄金/美元/美债/汇率用于判断流动性", ["黄金", "美元", "美债", "汇率", "实际利率"]),
]


def classify_topics(text: str) -> list[str]:
    return [name for name, keys in TOPIC_RULES if any(k.lower() in text.lower() for k in keys)]


def skill_hits(rows: list[dict], today: dt.date, half_life_days: int = 60) -> list[dict]:
    out = []
    for name, keys in SKILL_RULES:
        evidence = []
        score = 0.0
        for row in rows:
            text = row["text"]
            hits = [k for k in keys if k.lower() in text.lower()]
            if not hits:
                continue
            w = recency_weight(row["date"], today, half_life_days)
            score += w * min(1.0, len(hits) / 3)
            snippet = next((s for s in monitor.split_sentences(text) if any(k.lower() in s.lower() for k in hits)), "")[:180]
            evidence.append({"date": row["date_text"], "title": row["title"], "weight": w, "hits": hits[:4], "snippet": snippet, "url": row["url"]})
        if evidence:
            out.append({"skill": name, "score": round(score, 3), "evidence": sorted(evidence, key=lambda x: x["weight"], reverse=True)[:5]})
    return sorted(out, key=lambda x: x["score"], reverse=True)


def make_monitor_item(row: dict, config: dict) -> dict:
    ts = int(dt.datetime.combine(row["date"], dt.time()).timestamp()) if row["date"] else 0
    return {
        "Title": row["title"],
        "ContentText": row["text"],
        "Url": row["url"],
        "AuthorName": "Deep Van",
        "EditTime": ts,
        "VoteUpCount": 0,
        "_source_kind": "deepvan_original_page",
    }


def write_report(rows: list[dict], config: dict) -> Path:
    today = dt.date(2026, 7, 10)
    records = []
    for row in rows:
        item = make_monitor_item(row, config)
        records.extend(monitor.extract_rebalance_records(item, config))
    records = sorted(records, key=lambda r: (r.get("date") or "", r.get("source_url") or ""), reverse=True)
    half_life_days = int(config.get("skill_recency_half_life_days", 60))
    skills = skill_hits(rows, today, half_life_days)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"profile_original_research_{stamp}.md"

    lines = [
        "# Deep Van 原文研究档案",
        "",
        "口径：只使用主页/回答/文章中 Deep Van 本人发布内容；第三方总结只作为发现线索，不进入本报告事实表。",
        "",
        "## Corpus",
        "",
        "| Date | Title | Text | Images | Topics | Weight |",
        "|---|---|---:|---:|---|---:|",
    ]
    for row in rows[:80]:
        topics = "、".join(classify_topics(row["text"])[:4])
        lines.append(
            f"| {row['date_text']} | [{row['title']}]({row['url']}) | {row['text_length']} | {row['image_count']} | {topics} | {recency_weight(row['date'], today, half_life_days):.2f} |"
        )

    lines += ["", "## Portfolio / Rebalance Events", ""]
    if records:
        lines += ["| Date | Action | Asset | Weight | Evidence | Source |", "|---|---|---|---:|---|---|"]
        for r in records[:80]:
            lines.append(
                f"| {r.get('date')} | {r.get('action')} | {r.get('asset')} | {monitor.format_weight(r.get('weight'))} | "
                f"{(r.get('reason') or r.get('snippet') or '')[:120]} | [{r.get('source_title')}]({r.get('source_url')}) |"
            )
    else:
        lines.append("未从原文中抽到可结构化持仓事件。")

    lines += ["", "## Recency-Weighted Skills", ""]
    for s in skills:
        lines.append(f"### {s['skill']}  score={s['score']}")
        for e in s["evidence"]:
            lines.append(f"- {e['date']} w={e['weight']:.2f} [{e['title']}]({e['url']}): {e['snippet']}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--recent-dir", default=str(DATA_DIR / "original_pages_recent"))
    parser.add_argument("--archive-dir", default=str(DATA_DIR / "original_pages"))
    args = parser.parse_args()
    config = monitor.load_json(Path(args.config), {})
    rows = iter_original_pages([Path(args.recent_dir), Path(args.archive_dir)])
    path = write_report(rows, config)
    print(f"rows={len(rows)} report={path}")


if __name__ == "__main__":
    main()
