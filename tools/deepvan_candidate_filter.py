#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

INVESTMENT_KEYWORDS = [
    "A股", "行情", "持仓", "仓位", "调仓", "加仓", "减仓", "清仓", "止盈", "止损",
    "叫兽指数", "纯A", "内地版", "全球版", "组合", "指数", "ETF", "QDII",
    "半导体", "AI", "长鑫", "国产替代", "拓荆", "安集", "华海", "雅克", "通富",
    "美的", "招商", "量化", "国金量化", "黄金", "紫金", "厦钨", "钨", "XBI", "创新药",
    "标普", "纳指", "日韩", "日经", "韩国", "SHV", "TLT", "南方东西精选", "红利",
]

ACTION_MARKERS = ["回答了问题", "发布了文章", "发布了想法"]
IGNORE_MARKERS = ["赞同了回答", "收藏了", "关注了", "赞同了文章"]


def load_profile_lists(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("items", []):
            item = dict(item)
            item["_list_file"] = str(path)
            rows.append(item)
    return rows


def parse_dt(text: str) -> str:
    m = re.search(r"(20\d{2}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?)", text or "")
    if m:
        return m.group(1)
    return text or ""


def score_item(item: dict) -> tuple[int, list[str]]:
    text = f"{item.get('title','')}\n{item.get('text','')}"
    hits = [k for k in INVESTMENT_KEYWORDS if k.lower() in text.lower()]
    score = 0
    if any(m in text for m in ACTION_MARKERS):
        score += 20
    if any(k in text for k in ["持仓", "仓位", "调仓", "叫兽指数", "纯A", "内地版", "组合"]):
        score += 30
    if any(k in text for k in ["A股", "行情", "半导体", "量化", "黄金", "XBI", "标普"]):
        score += 10
    score += min(30, len(hits) * 3)
    return score, hits


def filter_candidates(rows: list[dict], limit: int) -> list[dict]:
    out = []
    seen = set()
    for item in rows:
        text = item.get("text", "")
        if any(m in text for m in IGNORE_MARKERS):
            continue
        urls = item.get("urls") or []
        if not urls:
            continue
        score, hits = score_item(item)
        if score <= 0:
            continue
        url = urls[0].split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "score": score,
                "time": parse_dt(item.get("timeText", "")),
                "title": item.get("title", ""),
                "url": urls[0],
                "hits": hits,
                "preview": text[:500],
                "source": item.get("_list_file", ""),
            }
        )
    out.sort(key=lambda x: (x["score"], x["time"]), reverse=True)
    return out[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", default=str(DATA_DIR / "profile_lists"))
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--out", default=str(DATA_DIR / "profile_candidates.json"))
    args = parser.parse_args()
    profile_dir = Path(args.profile_dir)
    rows = load_profile_lists([profile_dir / "activity.json", profile_dir / "answers.json", profile_dir / "posts.json"])
    candidates = filter_candidates(rows, args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(rows)} candidates={len(candidates)} out={out}")


if __name__ == "__main__":
    main()
