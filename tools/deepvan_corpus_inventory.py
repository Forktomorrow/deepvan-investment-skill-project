#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_url(url: str) -> str:
    url = (url or "").split("?")[0].strip()
    return url.rstrip("/")


def content_id(url: str) -> str:
    m = re.search(r"/(?:answer|p|pin)/(\d+)", url)
    return m.group(1) if m else ""


def parse_date(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})",
        r"(20\d{2})/(\d{1,2})/(\d{1,2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            y, mo, d = map(int, m.groups())
            return str(dt.date(y, mo, d))
    return ""


def iter_profile_items(profile_dir: Path) -> list[dict]:
    rows = []
    for name in ["activity.json", "answers.json", "posts.json"]:
        path = profile_dir / name
        if not path.exists():
            continue
        data = load_json(path)
        items = data if isinstance(data, list) else data.get("items") or data.get("Items") or []
        for item in items:
            urls = item.get("urls") or []
            url = next((u for u in urls if "zhihu.com" in u), "")
            if not url:
                continue
            rows.append(
                {
                    "source_list": name,
                    "kind": item.get("kind", ""),
                    "title": item.get("title", ""),
                    "text": item.get("text", ""),
                    "timeText": item.get("timeText", ""),
                    "url": canonical_url(url),
                    "content_id": content_id(url),
                    "date": parse_date(item.get("timeText", "") + " " + item.get("title", "") + " " + item.get("text", "")),
                }
            )
    unique = {}
    for row in rows:
        key = row["url"] or row["content_id"]
        if key and key not in unique:
            unique[key] = row
    return list(unique.values())


def iter_cached_originals(dirs: list[Path]) -> list[dict]:
    rows = []
    for base in dirs:
        if not base.exists():
            continue
        for path in base.glob("*/article.json"):
            try:
                data = load_json(path)
            except Exception:
                continue
            ocr_path = path.parent / "ocr_relevant.txt"
            ocr_text = ocr_path.read_text(encoding="utf-8", errors="ignore").strip() if ocr_path.exists() else ""
            url = canonical_url(data.get("url", ""))
            text = data.get("text", "") or ""
            date = parse_date(data.get("published", "") + " " + data.get("title", "") + " " + text[:1000])
            rows.append(
                {
                    "url": url,
                    "content_id": content_id(url) or path.parent.name,
                    "title": data.get("title", ""),
                    "date": date,
                    "text_len": len(text),
                    "images": len(data.get("images", [])),
                    "ocr_len": len(ocr_text),
                    "path": str(path),
                }
            )
    unique = {}
    for row in rows:
        key = row["url"] or row["content_id"]
        old = unique.get(key)
        if not old or row["text_len"] + row["ocr_len"] > old["text_len"] + old["ocr_len"]:
            unique[key] = row
    return list(unique.values())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--profile-dir", default="data/profile_lists")
    parser.add_argument("--original-dirs", nargs="+", default=["data/original_pages_recent", "data/original_pages"])
    parser.add_argument("--out", default="data/corpus_inventory.json")
    parser.add_argument("--missing-out", default="data/backfill_missing_urls.json")
    args = parser.parse_args()

    root = Path(args.root)
    profile_items = iter_profile_items(root / args.profile_dir)
    cached = iter_cached_originals([root / p for p in args.original_dirs])
    cached_keys = {row["url"] for row in cached if row["url"]} | {row["content_id"] for row in cached if row["content_id"]}
    missing = [row for row in profile_items if row["url"] not in cached_keys and row["content_id"] not in cached_keys]

    dates = [row["date"] for row in cached if row["date"]]
    inventory = {
        "profile_items": len(profile_items),
        "cached_originals": len(cached),
        "full_text_coverage": round(len(cached) / len(profile_items), 4) if profile_items else 0,
        "missing_originals": len(missing),
        "date_min": min(dates) if dates else "",
        "date_max": max(dates) if dates else "",
        "cached_chars": sum(row["text_len"] for row in cached),
        "image_urls": sum(row["images"] for row in cached),
        "ocr_items": sum(1 for row in cached if row["ocr_len"] > 0),
        "ocr_chars": sum(row["ocr_len"] for row in cached),
        "by_year": dict(Counter(row["date"][:4] for row in cached if row["date"])),
        "by_source_list": dict(Counter(row["source_list"] for row in profile_items)),
    }
    write_json(root / args.out, {"inventory": inventory, "cached": cached[:], "missing": missing[:]})
    write_json(root / args.missing_out, missing)
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
