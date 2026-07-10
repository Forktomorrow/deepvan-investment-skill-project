#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


DATE_PATTERNS = [
    re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})"),
    re.compile(r"(20\d{2})/(\d{1,2})/(\d{1,2})"),
    re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})"),
]

TITLE_DATE_PATTERNS = [
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
    re.compile(r"(20\d{2})[/.-](\d{1,2})[/.-](\d{1,2})"),
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def first_date(text: str) -> dt.date | None:
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None


def title_date(title: str) -> dt.date | None:
    if not title:
        return None
    for pattern in TITLE_DATE_PATTERNS:
        m = pattern.search(title)
        if not m:
            continue
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None


def canonical_url(url: str) -> str:
    return (url or "").split("?")[0]


def extract_article_date(data: dict) -> tuple[dt.date | None, str]:
    meta = data.get("meta", {}) or {}
    title = data.get("title", "") or ""
    candidates = [
        ("published", first_date(data.get("published", "") or "")),
        ("meta.timeText", first_date(meta.get("timeText", "") or "")),
        ("title", title_date(title)),
    ]
    for source, value in candidates:
        if value:
            return value, source
    return None, ""


def is_high_confidence_original(data: dict) -> bool:
    title = data.get("title", "") or ""
    text = data.get("text", "") or ""
    author_hint = data.get("authorHint", "") or ""
    if "NEVEN" in text[:200]:
        return False
    if "Deep Van" in author_hint:
        return True
    if "Deep Van" in text[:1500]:
        return True
    if title.startswith("Deep Van 的想法"):
        return True
    return False


def canonical_profile_date(row: dict) -> str | None:
    title = row.get("title", "") or ""
    text = row.get("text", "") or ""
    published = row.get("published", "") or ""
    meta_time = ((row.get("meta") or {}).get("timeText", "")) or ""
    for candidate in [published, meta_time, title]:
        d = first_date(candidate) or title_date(candidate)
        if d:
            return str(d)
    corpus_start = first_date(text[:400])
    return str(corpus_start) if corpus_start else None


def load_profile_list_items() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    profile_dir = DATA_DIR / "profile_lists"
    for name in ["activity.json", "answers.json", "posts.json", "pins_deep_scroll.json"]:
        path = profile_dir / name
        if path.exists():
            out[name] = load_json(path).get("items", [])
    return out


def profile_list_span(items: list[dict]) -> tuple[str | None, str | None]:
    dates: list[dt.date] = []
    for item in items:
        text = "\n".join([item.get("timeText", ""), item.get("title", ""), item.get("text", "")])
        d = first_date(text) or title_date(item.get("title", ""))
        if d:
            dates.append(d)
    if not dates:
        return None, None
    return str(min(dates)), str(max(dates))


def is_original_profile_item(item: dict) -> bool:
    text = item.get("text", "") or ""
    kind = item.get("kind", "") or ""
    if "赞同了回答" in text or "赞同了文章" in text or "收藏了" in text:
        return False
    if kind in {"/answers", "/posts", "/pins_deep_scroll"}:
        return True
    return any(marker in text for marker in ["回答了问题", "发布了想法", "发布了文章"])


def primary_item_url(item: dict) -> str | None:
    urls = item.get("urls") or []
    if not urls:
        return None
    return canonical_url(urls[0])


def iter_articles() -> list[dict]:
    rows = []
    for base_name in ["original_pages_recent", "original_pages"]:
        base = DATA_DIR / base_name
        if not base.exists():
            continue
        for article in sorted(base.glob("*/article.json")):
            data = load_json(article)
            url = canonical_url(data.get("url", ""))
            ocr_path = article.parent / "ocr_relevant.txt"
            ocr_text = ocr_path.read_text(encoding="utf-8", errors="ignore").strip() if ocr_path.exists() else ""
            date_value, date_source = extract_article_date(data)
            rows.append(
                {
                    "id": article.parent.name,
                    "url": url,
                    "title": data.get("title", ""),
                    "date": str(date_value) if date_value else None,
                    "date_source": date_source,
                    "text_len": len(data.get("text", "") or ""),
                    "image_count": len(data.get("images", []) or []),
                    "ocr_len": len(ocr_text),
                    "author_hint": data.get("authorHint", "") or "",
                    "high_confidence_original": is_high_confidence_original(data),
                    "source_dir": base_name,
                    "path": str(article),
                }
            )
    best: dict[str, dict] = {}
    for row in rows:
        key = row["url"] or row["id"]
        old = best.get(key)
        if not old or row["text_len"] > old["text_len"]:
            best[key] = row
    return sorted(best.values(), key=lambda r: (r["date"] or "", r["url"]))


def build_inventory(rows: list[dict], profile_lists: dict[str, list[dict]]) -> dict:
    high_conf_rows = [r for r in rows if r["high_confidence_original"]]
    dated_rows = [r for r in high_conf_rows if r["date"]]
    by_year = Counter()
    for row in dated_rows:
        by_year[row["date"][:4]] += 1

    source_hits: dict[str, int] = defaultdict(int)
    profile_urls: dict[str, set[str]] = {}
    all_profile_urls: set[str] = set()
    for name, items in profile_lists.items():
        urls = set()
        for item in items:
            if not is_original_profile_item(item):
                continue
            cleaned = primary_item_url(item)
            if cleaned:
                urls.add(cleaned)
                all_profile_urls.add(cleaned)
        profile_urls[name] = urls

    row_by_url = {r["url"]: r for r in rows if r["url"]}
    high_conf_by_url = {r["url"]: r for r in high_conf_rows if r["url"]}
    cached_profile_urls = set(u for u in all_profile_urls if u in row_by_url)
    high_conf_profile_urls = set(u for u in all_profile_urls if u in high_conf_by_url)
    missing_profile_urls = sorted(u for u in all_profile_urls if u not in high_conf_by_url)
    low_conf_profile_urls = sorted(u for u in all_profile_urls if u in row_by_url and u not in high_conf_by_url)
    for name, urls in profile_urls.items():
        source_hits[name] = sum(1 for u in urls if u in high_conf_by_url)

    early_mentions = []
    for row in high_conf_rows:
        profile_date = canonical_profile_date(load_json(Path(row["path"])))
        if profile_date and profile_date < (row["date"] or profile_date):
            early_mentions.append(
                {
                    "url": row["url"],
                    "title": row["title"],
                    "published_date": row["date"],
                    "earliest_body_date": profile_date,
                }
            )

    return {
        "inventory": {
            "profile_items": len(all_profile_urls),
            "all_cached_high_conf_originals": len(high_conf_rows),
            "profile_cached_originals": len(high_conf_profile_urls),
            "profile_cached_any_quality": len(cached_profile_urls),
            "missing_or_unverified_originals": len(missing_profile_urls),
            "low_conf_profile_originals": len(low_conf_profile_urls),
            "full_text_coverage": round(len(high_conf_profile_urls) / len(all_profile_urls), 4) if all_profile_urls else None,
            "date_min": min((r["date"] for r in dated_rows), default=None),
            "date_max": max((r["date"] for r in dated_rows), default=None),
            "cached_chars": sum(r["text_len"] for r in high_conf_rows),
            "image_urls": sum(r["image_count"] for r in high_conf_rows),
            "ocr_items": sum(1 for r in high_conf_rows if r["ocr_len"] > 0),
            "ocr_chars": sum(r["ocr_len"] for r in high_conf_rows),
            "by_year": dict(sorted(by_year.items())),
            "by_source_list": dict(source_hits),
            "profile_spans": {
                name: {
                    "item_count": len(items),
                    "original_item_count": sum(1 for item in items if is_original_profile_item(item)),
                    "date_min": profile_list_span(items)[0],
                    "date_max": profile_list_span(items)[1],
                }
                for name, items in profile_lists.items()
            },
            "earliest_body_dates": early_mentions[:20],
        },
        "cached": high_conf_rows,
        "missing": missing_profile_urls,
        "low_conf_profile_urls": low_conf_profile_urls,
    }


def write_report(inventory: dict) -> Path:
    inv = inventory["inventory"]
    profile_spans = inv.get("profile_spans", {})
    path = REPORT_DIR / "corpus_inventory_report.md"
    lines = [
        "# Deepvan 原文库存报告",
        "",
        "## 总览",
        "",
        f"- 当前 profile 列表中的唯一 URL：{inv['profile_items']}",
        f"- 当前 profile 列表已缓存高置信原文：{inv['profile_cached_originals']}",
        f"- 缓存里全部高置信原文：{inv['all_cached_high_conf_originals']}",
        f"- 当前 profile 列表仍缺或未验证原文：{inv['missing_or_unverified_originals']}",
        f"- 当前 profile 列表低置信缓存：{inv['low_conf_profile_originals']}",
        f"- 已发现 URL 的高置信全文覆盖率：{inv['full_text_coverage']}",
        f"- 高置信原文日期范围：{inv['date_min']} ~ {inv['date_max']}",
        f"- 正文字数：{inv['cached_chars']}",
        f"- 图片数：{inv['image_urls']}",
        f"- 带 OCR 的原文数：{inv['ocr_items']}",
        f"- OCR 字数：{inv['ocr_chars']}",
        "",
        "## Profile 列表时间覆盖",
        "",
        "| List | Items | Original Items | Min Date | Max Date |",
        "|---|---:|---:|---|---|",
    ]
    for name, meta in profile_spans.items():
        lines.append(
            f"| {name} | {meta['item_count']} | {meta['original_item_count']} | {meta['date_min'] or ''} | {meta['date_max'] or ''} |"
        )

    lines += ["", "## 按年份分布", "", "| Year | Count |", "|---|---:|"]
    for year, count in inv.get("by_year", {}).items():
        lines.append(f"| {year} | {count} |")

    lines += [
        "",
        "## 口径说明",
        "",
        "- 日期优先取 `published`、`meta.timeText`、标题中的显式日期，不再从正文深处抓日期，避免被历史回顾和推荐阅读污染。",
        "- Profile 原文 URL 只取每条主页列表项的主 URL，不把文内“上期回答”等链接重复算入缺口。",
        "- Activity 中的“赞同了回答/文章”不计入 Deep Van 本人原文覆盖率。",
        "- 高置信原文只统计 Deep Van 本人原文，不把第三方内容混进去。",
        "- 这份报告回答的是“当前已发现 URL 抓全了没有”；不等于“2024-01 至今全量主页内容已证明发现完毕”。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default=str(DATA_DIR / "corpus_inventory.json"))
    args = parser.parse_args()
    rows = iter_articles()
    profile_lists = load_profile_list_items()
    inventory = build_inventory(rows, profile_lists)
    out_json = Path(args.out_json)
    out_json.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    report = write_report(inventory)
    print(
        "cached_originals={cached} profile_items={profile} missing={missing} date_min={date_min} date_max={date_max} report={report}".format(
            cached=inventory["inventory"]["profile_cached_originals"],
            profile=inventory["inventory"]["profile_items"],
            missing=inventory["inventory"]["missing_or_unverified_originals"],
            date_min=inventory["inventory"]["date_min"],
            date_max=inventory["inventory"]["date_max"],
            report=report,
        )
    )


if __name__ == "__main__":
    main()
