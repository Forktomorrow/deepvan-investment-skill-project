#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


CUT_MARKERS = ["推荐阅读", "关于作者", "大家都在搜", "理性发言", "点击查看全部评论", "所属专栏"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date_text(text: str) -> str:
    for pat in [r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", r"(20\d{2})(\d{2})(\d{2})"]:
        m = re.search(pat, text or "")
        if not m:
            continue
        try:
            return str(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    return ""


def article_date(data: dict) -> str:
    meta = data.get("meta") or {}
    return parse_date_text(data.get("published", "")) or parse_date_text(meta.get("timeText", "")) or parse_date_text(data.get("title", ""))


def body_text(data: dict) -> str:
    text = data.get("text", "") or ""
    for marker in CUT_MARKERS:
        idx = text.find(marker)
        if idx > 200:
            text = text[:idx]
    return text


def clean_title(title: str) -> str:
    return re.sub(r"^\([^)]*\)\s*", "", title or "").replace(" - 知乎", "").strip()


def nav_date_from_context(context: str, fallback: str) -> str:
    # If the context explicitly says 年初/年末, preserve that as a point estimate.
    value_pos = max(context.rfind("净值"), context.rfind("新高"), context.rfind("回撤"))
    local = context[max(0, value_pos - 80) :] if value_pos >= 0 else context
    if "年末" in local:
        y = re.search(r"(20\d{2})年终总结", context)
        if y:
            return f"{y.group(1)}-12-31"
    m = re.search(r"年初[（(](20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})[）)]", local)
    if m:
        return parse_date_text(".".join(m.groups()))
    # Do not use ranges such as 20240611-20250514 as the nav date. Those describe
    # the chart window, while the net value belongs to the article/update date.
    explicit = parse_date_text(local)
    if explicit and not re.search(r"20\d{6}\s*[-~—至到]\s*20\d{6}", local):
        return explicit
    return fallback


def extract_nav_points() -> list[dict]:
    rows = []
    for base_name in ["original_pages_recent", "original_pages"]:
        base = DATA_DIR / base_name
        if not base.exists():
            continue
        for article in sorted(base.glob("*/article.json")):
            data = load_json(article)
            title = clean_title(data.get("title", ""))
            text = body_text(data)
            if "叫兽指数" not in title and "叫兽指数" not in text[:1200]:
                continue
            fallback_date = article_date(data)
            if not fallback_date:
                continue
            if not ("净值" in title or "净值" in text[:1800] or "叫兽指数" in title):
                continue
            candidates = []
            patterns = [
                r"净值(?:为|到了|到|从|突破|接近|回落到|上升到|上升到了)?\s*(?P<a>[01]\.\d{2,4})(?:\s*(?:->|→|到|至|上涨到|回落到|降低到)\s*(?P<b>[01]\.\d{2,4}))?",
                r"目前净值\s*(?P<a>[01]\.\d{2,4})(?:（上期(?P<b>[01]\.\d{2,4})[^）]*）)?",
                r"(?P<label>年初|年末)[^。；\n]{0,20}净值(?:为)?\s*(?P<a>[01]\.\d{2,4})",
            ]
            sample = title + "\n" + text[:2400]
            for pat in patterns:
                for m in re.finditer(pat, sample):
                    context = sample[max(0, m.start() - 120) : m.end() + 160].replace("\n", " ")
                    values = []
                    if m.groupdict().get("a"):
                        values.append(float(m.group("a")))
                    if m.groupdict().get("b"):
                        values.append(float(m.group("b")))
                    for value_i, value in enumerate(values):
                        if not (0.9 <= value <= 1.6):
                            continue
                        # Drop obvious generic explanations, not index points.
                        if "从1.000开始" in context or "单位净值" in context or "实时参考净值" in context:
                            continue
                        date = nav_date_from_context(context, fallback_date)
                        if value_i == 0 and "目前净值" in context:
                            date = fallback_date
                        if value_i == 1 and "上期" in context:
                            explicit = parse_date_text(context)
                            if explicit:
                                date = explicit
                        # For ordinary "from A -> B" updates, B is the current
                        # official NAV. A is kept only when the context names it
                        # as 年初/年末/上期 with a date; otherwise it is reference
                        # text, not a standalone point.
                        if len(values) > 1 and value_i == 0 and not any(k in context for k in ["年初", "年末", "上期", "上一期"]):
                            continue
                        candidates.append(
                            {
                                "date": date,
                                "nav": value,
                                "source_date": fallback_date,
                                "source_title": title,
                                "source_url": (data.get("url") or "").split("?")[0],
                                "source_id": article.parent.name,
                                "context": context[:500],
                            }
                        )
            for row in candidates:
                rows.append(row)
    # Dedupe and keep the most direct source per date/nav.
    for row in rows:
        if row["source_id"] == "1913642337441129084" and abs(row["nav"] - 1.1385) < 0.0001:
            row["date"] = row["source_date"]
        if row["source_id"] == "1988327505925513278" and abs(row["nav"] - 1.067) < 0.0001:
            row["date"] = "2025-01-08"
        if row["source_id"] == "1988327505925513278" and abs(row["nav"] - 1.291) < 0.0001:
            row["date"] = "2025-12-31"
    out, seen = [], set()
    for row in sorted(rows, key=lambda r: (r["date"], r["source_date"], r["nav"])):
        key = (row["date"], round(row["nav"], 4), row["source_url"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_outputs() -> None:
    rows = extract_nav_points()
    DATA_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / "official_nav_points.csv"
    fields = ["date", "nav", "source_date", "source_title", "source_url", "source_id", "context"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = REPORT_DIR / f"official_nav_points_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = [
        "# Deepvan 官方净值点审计",
        "",
        "口径：只从 Deep Van 本人公开原文正文前段抽取 `叫兽指数` 净值表述；排除评论、推荐阅读和行情软件里的单只基金单位净值。",
        "",
        "| 日期 | 净值 | 来源发布日期 | 来源 | 摘要 |",
        "|---|---:|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['date']} | {float(r['nav']):.4f} | {r['source_date']} | [{r['source_title']}]({r['source_url']}) | {r['context'][:120]} |")
    lines += [
        "",
        "## 审计结论",
        "",
        "- 叫兽指数并非 2025-04-24 才推出；原文多次写明起点为 2024-06-11。",
        "- 2025-04-24 是当前持仓重建器最早稳定解析到完整 OCR 持仓表的日期，不是组合成立日。",
        "- 后续面板应同时展示官方净值点和持仓重建净值；两者偏差超过阈值时，需要优先复核 OCR 表和分红复权。",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"csv": str(csv_path), "report": str(report), "rows": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    write_outputs()
