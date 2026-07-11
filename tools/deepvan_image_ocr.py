#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OCR_SWIFT = ROOT / "scripts" / "vision_ocr.swift"
OCR_BIN = ROOT / "data" / "bin" / "vision_ocr"


KEYWORDS = [
    "持仓", "仓位", "调仓", "组合", "叫兽指数", "纯A", "内地版", "全球版",
    "美的", "招商", "量化", "标普", "XBI", "半导体", "黄金", "红利",
    "ETF", "QDII", "%", "净值", "减仓", "加仓", "清仓",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def image_ext(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in [".webp", ".png", ".jpg", ".jpeg"]:
        if path.endswith(ext):
            return ext
    return ".img"


def safe_name(url: str, idx: int) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"image_{idx:03d}_{digest}{image_ext(url)}"


def interesting_image(img: dict) -> bool:
    src = img.get("src", "")
    alt_cls = f"{img.get('alt','')} {img.get('className','')}"
    width = int(img.get("width") or 0)
    height = int(img.get("height") or 0)
    if not src or "data:" in src:
        return False
    if any(k in alt_cls for k in ["Avatar", "头像", "UserLink", "AuthorInfo", "sticker"]):
        return False
    if width < 240 or height < 120:
        return False
    return True


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def ensure_ocr_binary() -> Path | None:
    if OCR_BIN.exists():
        return OCR_BIN
    OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = run(["swiftc", str(OCR_SWIFT), "-o", str(OCR_BIN)], timeout=240)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode == 0 and OCR_BIN.exists():
        return OCR_BIN
    return None


def download_image(url: str, out: Path) -> bool:
    if out.exists() and out.stat().st_size > 0:
        return True
    proc = run(["curl", "-L", "-sS", "--max-time", "20", "-A", "Mozilla/5.0", url, "-o", str(out)], timeout=25)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 0


def convert_to_png(path: Path) -> Path | None:
    png = path.with_suffix(".png")
    if png.exists() and png.stat().st_size > 0:
        return png
    proc = run(["sips", "-s", "format", "png", str(path), "--out", str(png)], timeout=25)
    if proc.returncode == 0 and png.exists() and png.stat().st_size > 0:
        return png
    if path.suffix.lower() == ".png":
        return path
    return None


def ocr_image(path: Path, binary: Path | None) -> str:
    if not binary:
        return ""
    cached = path.with_suffix(path.suffix + ".ocr.txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="ignore").strip()
    try:
        proc = run([str(binary), str(path)], timeout=25)
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    text = proc.stdout.strip()
    cached.write_text(text, encoding="utf-8")
    return text


def classify_text(text: str) -> tuple[bool, list[str]]:
    hits = [k for k in KEYWORDS if k.lower() in text.lower()]
    has_pct = bool(re.search(r"\d{1,2}(?:\.\d+)?\s*%", text))
    return bool(hits and (has_pct or len(hits) >= 2)), hits


def process_article(article: Path, max_images: int) -> dict:
    data = load_json(article)
    images = [img for img in data.get("images", []) if interesting_image(img)]
    out_dir = article.parent / "images"
    out_dir.mkdir(exist_ok=True)
    results = []
    binary = ensure_ocr_binary()
    for idx, img in enumerate(images[:max_images], 1):
        src = img["src"]
        raw_path = out_dir / safe_name(src, idx)
        if not download_image(src, raw_path):
            results.append({"src": src, "downloaded": False, "error": "download_failed", **img})
            continue
        png = convert_to_png(raw_path)
        if not png:
            results.append({"src": src, "downloaded": True, "error": "convert_failed", "path": str(raw_path), **img})
            continue
        text = ocr_image(png, binary)
        relevant, hits = classify_text(text)
        results.append(
            {
                "src": src,
                "downloaded": True,
                "path": str(raw_path),
                "png": str(png),
                "ocr_text": text,
                "relevant": relevant,
                "hits": hits,
                **img,
            }
        )
    write_json(article.parent / "ocr_results.json", results)
    relevant_text = "\n\n".join(r["ocr_text"] for r in results if r.get("relevant") and r.get("ocr_text"))
    (article.parent / "ocr_relevant.txt").write_text(relevant_text, encoding="utf-8")
    return {"article": str(article), "images": len(images), "processed": len(results), "relevant": sum(1 for r in results if r.get("relevant"))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dirs", nargs="+", default=[str(DATA_DIR / "original_pages_recent"), str(DATA_DIR / "original_pages")])
    parser.add_argument("--articles", nargs="+", help="Specific article.json files or article directories to process.")
    parser.add_argument("--max-images-per-article", type=int, default=8)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    articles: list[Path] = []
    if args.articles:
        for item in args.articles:
            path = Path(item)
            if path.is_dir():
                path = path / "article.json"
            if path.exists():
                articles.append(path)
    else:
        for d in args.dirs:
            base = Path(d)
            if base.exists():
                articles.extend(sorted(base.glob("*/article.json")))
    summaries = []
    for article in articles[: args.limit]:
        summaries.append(process_article(article, args.max_images_per_article))
    out = DATA_DIR / "ocr_run_summary.json"
    write_json(out, summaries)
    print(f"articles={len(summaries)} relevant={sum(s['relevant'] for s in summaries)} out={out}")


if __name__ == "__main__":
    main()
