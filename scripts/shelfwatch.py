#!/usr/bin/env python3
"""shelfwatch.py — Amazon Category Intelligence snapshot store + movement reporter.

Foundation for the ShelfWatch product (idea 2026-08-03): sell DTC brands a
monthly category-intelligence report (competitor price/rating movement, sentiment
shifts, ranking movers) mined from our existing scrape + freshness pipeline.

The core gap this fills: reviews carry point-in-time price/rating snapshots, but
nothing records HISTORY. "Movement" reports need a time series. This script:

  1. --seed        → one-time: write t0 baseline for every published review
                    (price/rating/review_count from frontmatter) into
                    data/history/<asin>.jsonl
  2. --snapshot    → append a new timestamped record for one or more briefings
                    (fresh scrape data). Call this every time the pipeline
                    re-scrapes a product.
  3. --watch       → category watcher: given a category (or ASIN list), list
                    products with the biggest price/rating/review-count movement
                    between two dates (weekly/monthly deltas).
  4. --report      → render a markdown category report (what a client would
                    receive monthly): movers, price shifts, sentiment changes.

Data model (data/history/<asin>.jsonl): one JSON object per line, append-only.
  {"ts": "2026-08-03T11:00:00+08:00", "price": 25.99, "rating": 4.6,
   "review_count": 229, "title": "...", "section": "coffee",
   "sentiment": {"positive": 12, "negative": 3, "top_complaints": ["leaks", "loud"]}}

Usage:
  python3 scripts/shelfwatch.py --seed
  python3 scripts/shelfwatch.py --snapshot briefings/coffee_B00AF7WUO2_data.json
  python3 scripts/shelfwatch.py --snapshot briefings/  # all briefings
  python3 scripts/shelfwatch.py --watch coffee --since 30 --delta price
  python3 scripts/shelfwatch.py --report coffee --since 30 [--out report.md]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(WORKSPACE, "content")
HISTORY_DIR = os.path.join(WORKSPACE, "data", "history")
SECTIONS = [
    "kitchen", "coffee", "home-office", "home-improvement", "luxury-beauty",
    "pet-supplies", "furniture", "patio-lawn-garden", "sports-fitness",
    "toys-games",
]

POSITIVE_WORDS = {"love", "great", "perfect", "excellent", "amazing", "best",
                  "easy", "solid", "quiet", "fast", "good", "works", "recommend",
                  "durable", "sturdy", "quality", "happy", "nice", "clean"}
NEGATIVE_WORDS = {"leak", "loud", "broke", "broken", "cheap", "flimsy", "return",
                  "defective", "waste", "poor", "bad", "awful", "crack", "stop",
                  "dead", "noise", "disappoint", "wobble", "rust", "smell", "melt"}


def to_float(v):
    try:
        if v is None or v == "null":
            return None
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def parse_frontmatter(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip("\"'")
    return fields


def extract_sentiment(reviews):
    """Crude sentiment + complaint extraction from review text."""
    pos = neg = 0
    complaints = defaultdict(int)
    for r in reviews or []:
        body = ((r.get("body") or "") + " " + (r.get("title") or "")).lower()
        if any(w in body for w in NEGATIVE_WORDS):
            neg += 1
            for w in NEGATIVE_WORDS:
                if w in body:
                    complaints[w] += 1
        if any(w in body for w in POSITIVE_WORDS):
            pos += 1
    top = [w for w, c in sorted(complaints.items(), key=lambda x: -x[1])[:5]]
    return {"positive": pos, "negative": neg, "top_complaints": top}


def history_path(asin):
    return os.path.join(HISTORY_DIR, f"{asin}.jsonl")


def read_history(asin):
    path = history_path(asin)
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_record(asin, record):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(history_path(asin), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── seed: t0 from published reviews ──────────────────────────────────────────

def seed():
    n = 0
    skipped = 0
    for section in SECTIONS:
        sec_dir = os.path.join(CONTENT_DIR, section)
        if not os.path.isdir(sec_dir):
            continue
        for fname in sorted(os.listdir(sec_dir)):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            fm = parse_frontmatter(os.path.join(sec_dir, fname))
            asin = re.search(r"/dp/([A-Z0-9]{10,14})", fm.get("amazon_url", ""))
            if not asin:
                skipped += 1
                continue
            asin = asin.group(1)
            price = to_float(fm.get("price"))
            rating = to_float(fm.get("amazon_rating"))
            count = to_float(fm.get("review_count"))
            # Don't overwrite existing history — seed only missing ASINs
            if os.path.exists(history_path(asin)) and read_history(asin):
                skipped += 1
                continue
            record = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "price": price,
                "rating": rating,
                "review_count": count,
                "title": fm.get("title", fname),
                "section": section,
                "source": "seed-frontmatter",
            }
            append_record(asin, record)
            n += 1
    print(f"✅ seeded t0 baseline for {n} ASINs ({skipped} skipped/dupes)")


# ── snapshot: append fresh scrape data ───────────────────────────────────────

def snapshot(paths):
    n = 0
    for p in paths:
        if os.path.isdir(p):
            inner = [os.path.join(p, f) for f in os.listdir(p)
                     if f.endswith("_data.json")]
            n += snapshot(inner)
            continue
        if not p.endswith("_data.json"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        asin = d.get("asin")
        if not asin:
            continue
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "price": to_float(d.get("price")),
            "rating": to_float(d.get("rating")),
            "review_count": to_float(d.get("review_count")),
            "title": d.get("title", asin),
            "section": d.get("section", ""),
            "source": "scrape",
            "sentiment": extract_sentiment(d.get("reviews")),
        }
        append_record(asin, record)
        n += 1
    return n


# ── watch/report: movement between two snapshots ─────────────────────────────

def movement(asin, rows, since_days):
    if not rows:
        return None
    cutoff = datetime.now().astimezone() - timedelta(days=since_days)
    recent = [r for r in rows if datetime.fromisoformat(r["ts"]).astimezone() >= cutoff]
    if not recent:
        return None
    first = recent[0]
    last = recent[-1]
    if first is last and len(recent) < 2:
        return None  # no movement possible with a single point in window
    def delta(a, b):
        if a is None or b is None:
            return None
        return round(b - a, 2)
    return {
        "asin": asin,
        "title": last.get("title", asin),
        "section": last.get("section", ""),
        "points": len(recent),
        "price_delta": delta(first.get("price"), last.get("price")),
        "rating_delta": delta(first.get("rating"), last.get("rating")),
        "count_delta": int(delta(first.get("review_count"), last.get("review_count")))
                      if first.get("review_count") is not None
                      and last.get("review_count") is not None else None,
        "first_ts": first.get("ts"),
        "last_ts": last.get("ts"),
        "first_price": first.get("price"),
        "last_price": last.get("price"),
        "first_rating": first.get("rating"),
        "last_rating": last.get("rating"),
        "sentiment": last.get("sentiment"),
    }


def watch(section=None, asins=None, since_days=30, delta_field="price", limit=20):
    results = []
    if asins:
        candidates = [(a, history_path(a)) for a in asins]
    else:
        candidates = []
        if not os.path.isdir(HISTORY_DIR):
            print("❌ no data/history yet — run --seed first", file=sys.stderr)
            return
        for fname in os.listdir(HISTORY_DIR):
            if fname.endswith(".jsonl"):
                candidates.append((fname[:-6], os.path.join(HISTORY_DIR, fname)))
    for asin, path in candidates:
        rows = read_history(asin)
        if not rows:
            continue
        m = movement(asin, rows, since_days)
        if not m:
            continue
        if section and m["section"] != section:
            continue
        val = m.get(f"{delta_field}_delta")
        if val is None:
            continue
        m["_sort"] = abs(val)
        results.append(m)
    results.sort(key=lambda x: -x["_sort"])
    return results[:limit]


def render_report(section, since_days, delta_field, limit):
    results = watch(section=section, since_days=since_days,
                    delta_field=delta_field, limit=limit)
    lines = [
        f"# ShelfWatch — {section.title()} Category Report",
        "",
        f"_Movement over the last {since_days} days · generated "
        f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}_",
        "",
        f"**{len(results)} products with tracked movement** "
        f"(sorted by |{delta_field} delta|).",
        "",
        "| Product | Price Δ | Rating Δ | Reviews Δ | Sentiment |",
        "|---|---|---|---|---|",
    ]
    for m in results:
        pd = f"{m['price_delta']:+.2f}" if m["price_delta"] is not None else "—"
        rd = f"{m['rating_delta']:+.2f}" if m["rating_delta"] is not None else "—"
        cd = f"{m['count_delta']:+d}" if m["count_delta"] is not None else "—"
        sent = ""
        if m.get("sentiment"):
            s = m["sentiment"]
            sent = f"{s['positive']}✓/{s['negative']}✗"
            if s.get("top_complaints"):
                sent += " (" + ", ".join(s["top_complaints"][:3]) + ")"
        title = (m["title"] or m["asin"])[:48].replace("|", "/")
        lines.append(f"| [{title}](/{m['section']}/{m['asin']}/) | {pd} | {rd} | {cd} | {sent} |")
    if len(results) == 0:
        lines.append("_No tracked movement yet — history is still accumulating._")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="ShelfWatch snapshot + movement")
    ap.add_argument("--seed", action="store_true", help="seed t0 baseline from reviews")
    ap.add_argument("--snapshot", nargs="*", help="append scrape snapshot(s)")
    ap.add_argument("--watch", help="section or ASIN list to watch")
    ap.add_argument("--asins", nargs="*", help="explicit ASINs (with --watch)")
    ap.add_argument("--since", type=int, default=30, help="window days")
    ap.add_argument("--delta", default="price", choices=["price", "rating", "review_count"])
    ap.add_argument("--report", help="render markdown report for a section")
    ap.add_argument("--out", help="write report to file")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if args.seed:
        seed()
    if args.snapshot:
        n = snapshot(args.snapshot)
        print(f"✅ appended {n} snapshot(s)")
    if args.report:
        text = render_report(args.report, args.since, args.delta, args.limit)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✅ report → {args.out} ({len(text)} bytes)")
        else:
            print(text)
    if args.watch and not args.report:
        results = watch(section=args.watch, asins=args.asins,
                        since_days=args.since, delta_field=args.delta,
                        limit=args.limit)
        for m in results:
            print(f"  {m['title'][:50]:52} price Δ={m['price_delta']}  "
                  f"rating Δ={m['rating_delta']}  reviews Δ={m['count_delta']}")
        if not results:
            print("No movement found in window (history still accumulating).")
    if not (args.seed or args.snapshot or args.report or args.watch):
        ap.print_help()


if __name__ == "__main__":
    main()
