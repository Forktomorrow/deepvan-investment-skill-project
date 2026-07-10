#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


PIN_RE = re.compile(r"https://www\.zhihu\.com/pin/(\d+)")
DATE_RE = re.compile(r"发布于(20\d{2}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?)")


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def clean_long_scroll(long_path: Path) -> list[dict]:
    payload = load_json(long_path, {"items": []})
    seen: set[str] = set()
    rows: list[dict] = []
    for raw in payload.get("items", []):
        url = (raw.get("url") or "").split("?")[0]
        m = PIN_RE.search(url)
        if not m or url in seen:
            continue
        seen.add(url)
        text = raw.get("text") or ""
        date_match = DATE_RE.search(text[:1500])
        rows.append(
            {
                "idx": len(rows) + 1,
                "kind": "/pins_deep_scroll",
                "title": "Deep Van 的想法",
                "urls": [url],
                "timeText": date_match.group(1) if date_match else "",
                "text": "",
                "source": "profile_pins_deep_scroll_long.json:url_only",
            }
        )
    return rows


def cached_ids(cache_dir: Path) -> set[str]:
    return {p.parent.name for p in cache_dir.glob("*/article.json")}


def inaccessible_ids(path: Path) -> set[str]:
    rows = load_json(path, [])
    out = set()
    for row in rows:
        url = row.get("url", "")
        m = PIN_RE.search(url)
        if m:
            out.add(m.group(1))
    return out


def article_path(cache_dir: Path, url: str) -> Path | None:
    m = PIN_RE.search(url)
    if not m:
        return None
    path = cache_dir / m.group(1) / "article.json"
    return path if path.exists() else None


def is_deepvan_article(data: dict) -> bool:
    title = data.get("title", "") or ""
    text = data.get("text", "") or ""
    author_hint = data.get("authorHint", "") or ""
    if "Deep Van" in author_hint:
        return True
    if title.startswith("Deep Van 的想法") or "Deep Van 的想法" in title:
        return True
    if "Deep Van" in text[:1500]:
        return True
    return False


def enrich_from_cached_article(row: dict, cache_dir: Path) -> tuple[dict | None, str]:
    path = article_path(cache_dir, row["urls"][0])
    if not path:
        return row, "missing_cache"
    data = load_json(path, {})
    if not is_deepvan_article(data):
        return None, "not_deepvan_original"
    text = data.get("text", "") or ""
    date_match = DATE_RE.search(text)
    enriched = dict(row)
    if date_match:
        enriched["timeText"] = date_match.group(1)
    enriched["text"] = text[:500]
    enriched["cachedPath"] = str(path)
    return enriched, "deepvan_original"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-profile-list", action="store_true")
    parser.add_argument("--long-path", default=str(DATA_DIR / "profile_pins_deep_scroll_long.json"))
    parser.add_argument("--cache-dir", default=str(DATA_DIR / "original_pages_recent"))
    parser.add_argument("--inaccessible-path", default=str(DATA_DIR / "inaccessible_urls.json"))
    args = parser.parse_args()

    rows = clean_long_scroll(Path(args.long_path))
    ids_cached = cached_ids(Path(args.cache_dir))
    ids_inaccessible = inaccessible_ids(Path(args.inaccessible_path))
    missing = []
    cached = 0
    inaccessible = 0
    for row in rows:
        url = row["urls"][0]
        pin_id = PIN_RE.search(url).group(1)
        if pin_id in ids_cached:
            cached += 1
        elif pin_id in ids_inaccessible:
            inaccessible += 1
        else:
            missing.append(url)

    if args.write_profile_list:
        filtered_rows = []
        excluded_rows = []
        inaccessible_set = inaccessible_ids(Path(args.inaccessible_path))
        cache_dir = Path(args.cache_dir)
        for row in rows:
            pin_id = PIN_RE.search(row["urls"][0]).group(1)
            if pin_id in inaccessible_set:
                excluded_rows.append({"url": row["urls"][0], "reason": "inaccessible"})
                continue
            enriched, reason = enrich_from_cached_article(row, cache_dir)
            if enriched is None:
                excluded_rows.append({"url": row["urls"][0], "reason": reason})
                continue
            filtered_rows.append(enriched)
        out_path = DATA_DIR / "profile_lists" / "pins_deep_scroll.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"count": len(filtered_rows), "items": filtered_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        excluded_path = DATA_DIR / "profile_lists" / "pins_deep_scroll_excluded.json"
        excluded_path.write_text(json.dumps({"count": len(excluded_rows), "items": excluded_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    queue_path = DATA_DIR / "pin_missing_fetch_queue.json"
    queue_path.write_text(json.dumps({"count": len(missing), "urls": missing}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "long_scroll_unique_pins": len(rows),
                "cached": cached,
                "inaccessible": inaccessible,
                "missing": len(missing),
                "queue": str(queue_path),
                "profile_list_written": bool(args.write_profile_list),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
