#!/usr/bin/env python3
"""build_search_index.py — Replaces Pagefind with a single-file JSON search index.

Pagefind generates one fragment file per page (~18K files), which blew past
Cloudflare Pages' 20,000-file cap and broke deploys. This script walks the
Hugo content tree and emits ONE file (public/search-index.json) with all
review metadata needed for client-side search.

Usage:
    python3 scripts/build_search_index.py [content_dir] [output_path]

Defaults:
    content_dir = content/
    output_path = public/search-index.json

Exit 0 on success, 1 on failure.
"""

import json
import os
import re
import sys

REVIEW_SECTIONS = [
    "kitchen", "coffee", "home-office", "home-improvement", "luxury-beauty",
    "pet-supplies", "furniture", "patio-lawn-garden", "sports-fitness",
    "toys-games",
]

def parse_frontmatter(text):
    """Extract YAML frontmatter fields we care about. Returns dict."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    raw = m.group(1)
    fields = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith(" ") or line.startswith("\t"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        value = value.strip("\"'")
        if value.startswith("[") or value.startswith("-") or value == "":
            # skip list/empty fields (pros/cons/tags/categories handled separately)
            fields[key] = None if value == "" else value
            continue
        fields[key] = value
    return fields


def slug_to_url(section, slug):
    """Map a slug to its permalink (mirrors hugo.toml permalinks)."""
    if not slug:
        return None
    slug = slug.strip("/")
    return f"/{section}/{slug}/"


def main():
    content_dir = sys.argv[1] if len(sys.argv) > 1 else "content"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "public/search-index.json"

    if not os.path.isdir(content_dir):
        print(f"❌ content dir not found: {content_dir}", file=sys.stderr)
        return 1

    entries = []
    seen = set()
    errors = 0

    for section in REVIEW_SECTIONS:
        sec_dir = os.path.join(content_dir, section)
        if not os.path.isdir(sec_dir):
            continue
        for fname in sorted(os.listdir(sec_dir)):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            path = os.path.join(sec_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                print(f"⚠️  read failed: {path}: {e}", file=sys.stderr)
                errors += 1
                continue

            fm = parse_frontmatter(text)
            slug = fm.get("slug")
            url = slug_to_url(section, slug)
            if not url:
                print(f"⚠️  no slug in {path}, skipping", file=sys.stderr)
                errors += 1
                continue
            if url in seen:
                continue
            seen.add(url)

            title = fm.get("title") or os.path.splitext(fname)[0]
            # Build a short summary from the body (first non-heading paragraph)
            body = text.split("---", 2)[-1] if text.count("---") >= 2 else ""
            summary = ""
            for para in body.split("\n\n"):
                para = para.strip()
                if not para or para.startswith("#") or para.startswith("!["):
                    continue
                summary = re.sub(r"\s+", " ", para).strip()
                break
            if len(summary) > 160:
                summary = summary[:157].rstrip() + "…"

            entry = {
                "title": title,
                "url": url,
                "amazon_rating": fm.get("amazon_rating"),
                "review_count": fm.get("review_count"),
                "amazon_image": fm.get("amazon_image"),
                "summary": summary,
            }
            entries.append(entry)

    entries.sort(key=lambda e: e["title"].lower())

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"total": len(entries), "entries": entries}, f, ensure_ascii=False)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"✅ search index: {len(entries)} reviews → {output_path} ({size_kb:.0f} KB)")
    if errors:
        print(f"⚠️  {errors} item(s) skipped with issues", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
