#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_articles(dirs: list[Path]) -> list[dict]:
    rows = []
    seen = set()
    for base in dirs:
        if not base.exists():
            continue
        for article in base.glob("*/article.json"):
            data = load_json(article)
            url = (data.get("url") or "").split("?")[0]
            key = url or article.parent.name
            if key in seen:
                continue
            seen.add(key)
            text = data.get("text", "") or ""
            ocr = article.parent / "ocr_relevant.txt"
            ocr_text = ocr.read_text(encoding="utf-8", errors="ignore") if ocr.exists() else ""
            rows.append(
                {
                    "id": article.parent.name,
                    "url": url,
                    "title": data.get("title", ""),
                    "text_len": len(text),
                    "ocr_len": len(ocr_text.strip()),
                    "image_count": len(data.get("images", [])),
                    "has_deepvan_hint": "Deep Van" in text[:1500] or "Deep Van" in (data.get("authorHint", "") or ""),
                    "path": str(article),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dirs", nargs="+", default=[str(DATA_DIR / "original_pages_recent"), str(DATA_DIR / "original_pages")])
    parser.add_argument("--short-threshold", type=int, default=250)
    args = parser.parse_args()
    rows = iter_articles([Path(x) for x in args.dirs])
    short = [r for r in rows if r["text_len"] < args.short_threshold]
    no_author = [r for r in rows if not r["has_deepvan_hint"]]
    serious = [r for r in no_author if r["text_len"] >= args.short_threshold]
    ocr = [r for r in rows if r["ocr_len"] > 0]
    report = {
        "total_unique_articles": len(rows),
        "short_text_count": len(short),
        "no_author_hint_count": len(no_author),
        "serious_author_mismatch_count": len(serious),
        "ocr_article_count": len(ocr),
        "text_chars": sum(r["text_len"] for r in rows),
        "ocr_chars": sum(r["ocr_len"] for r in rows),
        "short_text": short,
        "serious_author_mismatch": serious,
    }
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_DIR.mkdir(exist_ok=True)
    lines = [
        "# Deepvan 数据质量报告",
        "",
        f"- 唯一原文数：{report['total_unique_articles']}",
        f"- 短文本条目（<{args.short_threshold} 字）：{report['short_text_count']}",
        f"- 无 Deep Van 作者提示：{report['no_author_hint_count']}",
        f"- 严重作者块疑似错抓：{report['serious_author_mismatch_count']}",
        f"- 有 OCR 文本的原文：{report['ocr_article_count']}",
        f"- 正文字数：{report['text_chars']}",
        f"- OCR 字数：{report['ocr_chars']}",
        "",
        "## 严重作者块疑似错抓",
        "",
    ]
    if serious:
        lines += ["| ID | Text | Title | URL |", "|---|---:|---|---|"]
        for r in serious:
            lines.append(f"| {r['id']} | {r['text_len']} | {r['title'][:80]} | {r['url']} |")
    else:
        lines.append("未发现。")
    lines += ["", "## 短文本条目", "", "| ID | Text | Title | URL |", "|---|---:|---|---|"]
    for r in short[:80]:
        lines.append(f"| {r['id']} | {r['text_len']} | {r['title'][:80]} | {r['url']} |")
    out = REPORT_DIR / "data_quality_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"articles={len(rows)} short={len(short)} serious_author_mismatch={len(serious)} report={out}")


if __name__ == "__main__":
    main()
