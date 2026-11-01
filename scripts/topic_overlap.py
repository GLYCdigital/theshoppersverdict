#!/opt/homebrew/bin/python3
"""topic_overlap.py — pre-publish cannibalization gate.

The site has 26k+ review pages plus a daily blog. Nothing checked whether a new
post targets the same search intent as something already published, so
near-duplicates ("breville oracle jet review" vs "breville oracle jet espresso
machine review") split rankings and internal link equity.

This module indexes every existing URL's title (category reviews + blog) and
scores a candidate post's title/slug by token overlap against it.

Scoring is dependency-free (no sklearn): Jaccard plus a containment ratio, so a
short candidate that is a strict subset of a long existing title still scores
high.

Usage:
  python3 scripts/topic_overlap.py --slug S --title T   # gate one candidate
  python3 scripts/topic_overlap.py --report 25          # top overlapping clusters
  python3 scripts/topic_overlap.py --rebuild            # force index rebuild
"""
import json
import os
import re
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CONTENT = WORKSPACE / "content"
CACHE = WORKSPACE / "data" / "topic_index.json"
BLOG_DIR = CONTENT / "blog"
CACHE_TTL = 24 * 3600

STOP = {
    "the", "and", "for", "with", "your", "you", "our", "from", "that", "this",
    "best", "top", "review", "reviews", "guide", "picks", "pick", "buying",
    "worth", "worthit", "vs", "versus", "compare", "comparison", "should",
    "what", "which", "how", "why", "when", "does", "into", "than", "more",
    "most", "new", "set", "pack", "amazon", "price", "cheap", "cheapest",
    "budget", "premium", "ultimate", "complete", "things", "product",
    "products", "machines", "machine", "edition", "inch", "size", "color",
}

# Directories that hold review pages (mirrors build_search_index.py).
REVIEW_SECTIONS = [
    "coffee", "furniture", "home-improvement", "home-office", "kitchen",
    "luxury-beauty", "patio-lawn-garden", "pet-supplies", "sports-fitness",
    "toys-games",
]

BLOCK = 0.85   # near-duplicate intent — refuse to publish, re-angle
WARN = 0.60    # adjacent intent — publish, but flag it

# Seasonal guides repeat by design (one gift guide per category is the target
# state, not a duplicate), so they are flagged but never blocked.
SEASONAL_HINTS = ("gift-guide", "gift guide", "holiday", "black friday",
                  "prime day", "cyber monday")


def _seasonal(slug, title):
    blob = f"{slug} {title}".lower()
    return any(h in blob for h in SEASONAL_HINTS)


def tokens(text):
    """Content-bearing alpha tokens for overlap scoring."""
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", (text or "").lower()):
        if w in STOP or w.isdigit():
            continue
        out.add(w)
    return out


def parse_frontmatter(text):
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("\n---", 3)
    if end == -1:
        return fm
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v:
            fm[k] = v
    return fm


def _doc(url, title):
    toks = tokens(title)
    if len(toks) < 2:
        return None
    return {"u": url, "t": title[:110], "k": sorted(toks)}


def build_index(force=False):
    """Scan content once, cache to data/topic_index.json for 24h."""
    if not force and CACHE.exists():
        age = time.time() - CACHE.stat().st_mtime
        newest = max(
            (p.stat().st_mtime for p in CONTENT.rglob("*.md")), default=0
        ) if age < CACHE_TTL else 0
        if age < CACHE_TTL and newest <= CACHE.stat().st_mtime:
            try:
                return json.loads(CACHE.read_text())
            except (OSError, ValueError):
                pass

    docs = []
    for section in REVIEW_SECTIONS:
        d = CONTENT / section
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            if f.name.startswith("_"):
                continue
            try:
                fm = parse_frontmatter(f.read_text(errors="ignore"))
            except OSError:
                continue
            title = fm.get("title") or f.stem.replace("-", " ")
            doc = _doc(f"/{section}/{f.stem}/", title)
            if doc:
                docs.append(doc)
    for f in BLOG_DIR.glob("*.md"):
        if f.name.startswith("_"):
            continue
        try:
            fm = parse_frontmatter(f.read_text(errors="ignore"))
        except OSError:
            continue
        title = fm.get("title") or f.stem.replace("-", " ")
        doc = _doc(f"/blog/{f.stem}/", title)
        if doc:
            docs.append(doc)

    idx = {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "count": len(docs), "docs": docs}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(idx, ensure_ascii=False))
    return idx


def overlap(cand, other):
    """Jaccard blended with containment (subset candidates still score high)."""
    if not cand or not other:
        return 0.0
    inter = len(cand & other)
    if not inter:
        return 0.0
    jac = inter / len(cand | other)
    cont = inter / min(len(cand), len(other))
    return round(0.5 * jac + 0.5 * cont, 3)


def check(slug, title="", idx=None, block=BLOCK, warn=WARN):
    """Return (level, score, match) where level is 'block' | 'warn' | 'ok'."""
    idx = idx or build_index()
    cand = tokens((slug or "").replace("-", " ")) | tokens(title)
    best, hit = 0.0, None
    hit_cont = 0.0
    for d in idx["docs"]:
        other = set(d["k"])
        s = overlap(cand, other)
        if s > best:
            best, hit = s, d
            hit_cont = len(cand & other) / min(len(cand), len(other)) if cand and other else 0.0
    # A candidate whose tokens are fully contained in an existing title is the
    # same subject, whatever the wording ("...worth it" vs ".. review").
    # Comparison posts ("X vs Y") are a distinct intent, so they only block on a
    # near-identical wording, not on subject containment.
    is_vs = "vs" in (slug or "").lower().split("-")
    subject_dup = hit_cont >= 0.95 and len(cand) >= 3 and not is_vs
    if (subject_dup or best >= block) and _seasonal(slug, title):
        level = "warn"
    elif subject_dup or best >= block:
        level = "block"
    else:
        level = "warn" if best >= warn else "ok"
    return level, best, hit


def report(limit=25):
    """Highest-overlap existing pairs — consolidation candidates."""
    idx = build_index()
    docs = idx["docs"]
    pairs = {}
    for d in docs:
        if "/blog/" not in d["u"]:
            continue  # blog posts are the cheap-to-consolidate surface
        cand = set(d["k"])
        best, hit = 0.0, None
        for o in docs:
            if o["u"] == d["u"]:
                continue
            s = overlap(cand, set(o["k"]))
            if s > best:
                best, hit = s, o
        if hit and best >= WARN:
            pairs[d["u"]] = (best, hit["u"], d["t"])
    ranked = sorted(pairs.items(), key=lambda kv: -kv[1][0])[:limit]
    if not ranked:
        print("✅ No blog post overlaps an existing page above the warn threshold")
        return
    print(f"⚠️  {len(pairs)} blog post(s) overlapping existing pages (top {len(ranked)}):")
    for url, (score, twin, title) in ranked:
        print(f"  {score:.2f}  {url}\n        ↳ {twin}   [{title[:60]}]")


def main():
    args = sys.argv[1:]
    if "--rebuild" in args:
        idx = build_index(force=True)
        print(f"✅ index rebuilt: {idx['count']} pages → {CACHE}")
        return 0
    if "--report" in args:
        i = args.index("--report")
        n = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 25
        report(n)
        return 0

    slug = title = ""
    for i, a in enumerate(args):
        if a == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
        if a == "--title" and i + 1 < len(args):
            title = args[i + 1]
    if not slug and not title:
        print(__doc__)
        return 2
    level, score, hit = check(slug, title)
    icon = {"block": "🛑", "warn": "⚠️ ", "ok": "✅"}[level]
    print(f"{icon} {level.upper()} ({score:.2f}) candidate: {slug or title}")
    if hit:
        print(f"    closest: {hit['u']}  [{hit['t']}]")
    return 1 if level == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
