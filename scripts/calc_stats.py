#!/usr/bin/env python3
"""Pre-calculate site stats for Hugo data file.
Avoids expensive 26k-page scratch loops in Hugo templates."""

import os, re, json

total_verdicts = 0
total_reviews = 0
content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")

for root, dirs, files in os.walk(content_dir):
    for f in files:
        if not f.endswith(".md"):
            continue
        path = os.path.join(root, f)
        with open(path, "r") as fh:
            content = fh.read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        # Only count review-type pages (skip about, contact, best-of, etc.)
        if "layout:" in fm and any(x in fm for x in ["today", "verdicts", "bestof", "about", "contact", "search"]):
            continue
        # Count as a verdict if it has an ASIN (product review)
        if re.search(r'^asin:\s', fm, re.MULTILINE):
            total_verdicts += 1
        m = re.search(r'^review_count:\s*(\d+)', fm, re.MULTILINE)
        if m:
            total_reviews += int(m.group(1))

data = {
    "total_verdicts": total_verdicts,
    "total_reviews_analyzed": total_reviews,
}

data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(data_dir, exist_ok=True)
with open(os.path.join(data_dir, "stats.json"), "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ {total_verdicts:,} verdicts, {total_reviews:,} reviews analysed ({total_reviews/1_000_000:.1f}M)")
