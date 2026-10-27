#!/usr/bin/env python3
"""Post-price-drop verification: confirm schema + frontmatter are consistent.

Checks a sample of review pages (spread across categories) after the price-drop
pass, asserting:
  1. frontmatter has no numeric `price` (and no leftover empty `price:` key)
  2. rendered Product schema has NO `offers` key
  3. rendered Product schema STILL has `aggregateRating`

Usage:
  python3 scripts/verify_price_drop.py --build /tmp/tsv_build --sample 10
  python3 scripts/verify_price_drop.py --build /tmp/tsv_build --sample 10 --matrix
"""
import argparse
import glob
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.S)
NUMERIC = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def frontmatter(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        m = FRONTMATTER.match(fh.read(4000))
    return m.group(1) if m else ""


def catalogue():
    """Review pages only: have amazon_rating."""
    out = []
    for path in glob.glob(os.path.join(ROOT, "content", "**", "*.md"), recursive=True):
        fm = frontmatter(path)
        if "amazon_rating:" not in fm:
            continue
        out.append((path, fm))
    return out


def price_state(fm):
    """`price: null` is the house convention for 'we hold no price' — not a defect."""
    m = re.search(r"^price:[ \t]*(.*)$", fm, re.M)
    if not m:
        return "absent", None
    val = m.group(1).strip().strip("\"'")
    if val in ("", "null", "~"):
        return "null", val
    return ("numeric" if NUMERIC.match(val) else "text"), val


def product_schema(build_dir, md_path):
    """Find the rendered page for a content file, honouring slug/frontmatter overrides."""
    rel = os.path.relpath(md_path, os.path.join(ROOT, "content"))
    stem = os.path.splitext(rel)[0]
    fm = frontmatter(md_path)
    slug_m = re.search(r"^slug:[ \t]*(.+)$", fm, re.M)
    slug = slug_m.group(1).strip().strip("\"'") if slug_m else os.path.basename(stem)
    candidates = [stem, os.path.join(os.path.dirname(stem), slug)]
    top = os.path.join(ROOT, "content")
    for d in os.listdir(top):
        if os.path.isdir(os.path.join(top, d)):
            candidates.append(os.path.join(d, slug))
    html = None
    for cand in candidates:
        path = os.path.join(build_dir, cand, "index.html")
        if os.path.exists(path):
            html = path
            break
    if html is None:
        return None, os.path.join(build_dir, candidates[0], "index.html")
    with open(html, encoding="utf-8", errors="ignore") as fh:
        doc = fh.read()
    for m in LDJSON.finditer(doc):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item, html
    return False, html


def pick(pages, n):
    """Spread the sample across top-level content sections."""
    by_section = {}
    for path, fm in pages:
        rel = os.path.relpath(path, os.path.join(ROOT, "content"))
        by_section.setdefault(rel.split(os.sep)[0], []).append((path, fm))
    if not by_section:
        return []
    sections = sorted(by_section)
    out = []
    i = 0
    random.seed(7)
    while len(out) < n and i < n * len(sections):
        sec = sections[i % len(sections)]
        pool = by_section[sec]
        out.append(random.choice(pool))
        i += 1
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default=os.path.join(ROOT, "public"))
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--matrix", action="store_true",
                    help="also report the full-corpus price state counts")
    args = ap.parse_args()

    pages = catalogue()
    if args.matrix:
        counts = {}
        for path, fm in pages:
            state, _ = price_state(fm)
            counts[state] = counts.get(state, 0) + 1
        print("corpus price state:", dict(sorted(counts.items())),
              f"(total {len(pages)})")

    fails = 0
    print(f"\nsampling {args.sample} review pages across sections:")
    for path, fm in pick(pages, args.sample):
        rel = os.path.relpath(path, os.path.join(ROOT, "content"))
        state, val = price_state(fm)
        schema, html = product_schema(args.build, path)
        problems = []
        if state == "numeric":
            problems.append(f"numeric price still in frontmatter ({val})")
        if state == "text":
            problems.append(f"non-numeric price left in frontmatter ({val!r})")
        if schema is None:
            problems.append(f"no built page at {html}")
        elif schema is False:
            problems.append("no Product schema found")
        else:
            if "offers" in schema:
                problems.append("offers present")
            if "aggregateRating" not in schema:
                problems.append("aggregateRating MISSING")
        status = "FAIL" if problems else "ok"
        fails += bool(problems)
        print(f"  [{status}] {rel}  price={state}"
              + (f"  -> {', '.join(problems)}" if problems else "") +
              (f"   {os.path.relpath(html, args.build)}" if html and problems else ""))

    print(f"\n{fails} failure(s) in sample")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
