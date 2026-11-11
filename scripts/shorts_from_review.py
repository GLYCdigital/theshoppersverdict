#!/usr/bin/env python3
"""
shorts_from_review.py — Turn a published review/blog post into a ready-to-render
YouTube Shorts job file for Flash.

Output: flash_queue/YYYY-MM-DD-<slug>.json

Each job contains:
  - 3 hook variants (0-3s)
  - 5-beat 45-60s VO script with on-screen text per beat
  - CTA with affiliate link pre-injected
  - 3 thumbnail text options
  - product image path/URL pulled from frontmatter

No LLM calls. Deterministic templates -> near-zero marginal cost.

Usage:
  python3 scripts/shorts_from_review.py content/blog/2026-11-04-....md
  python3 scripts/shorts_from_review.py --recent 5          # newest blog posts
  python3 scripts/shorts_from_review.py --top 100           # backfill top reviews
  python3 scripts/shorts_from_review.py --top 100 --dry-run
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import date, datetime

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
QUEUE = os.path.join(ROOT, "flash_queue")

SKIP_DIRS = {"reviews", "verdicts", "best-of"}
GENERIC_TITLE = re.compile(r"^(review|ã€|\[|\s*$)", re.I)
AMZ_DP = re.compile(r"https?://(?:www\.)?amazon\.[a-z.]+/dp/([A-Z0-9]{10})[^\"'\s>]*", re.I)
VERDICT_RE = re.compile(r"verdict\W{0,4}(\d(?:\.\d)?)\s*/\s*5", re.I)
COUNT_RE = re.compile(r"([\d,]{3,})\s+(?:Amazon\s+)?(?:reviews|ratings)", re.I)
RATING_RE = re.compile(r"\(?(\d\.\d)\s*/\s*5\)?\s*(?:stars?)?\s*(?:on|from|average|across)", re.I)
PRICE_RE = re.compile(r"\$([\d,]{2,6}(?:\.\d{2})?)")
JUNK_RE = re.compile(
    r"gift[- ]?card|e-?gift|digital (?:code|download)|subscription|prime membership|"
    r"kindle unlimited|audible|reload|balance",
    re.I,
)


def short_name(name, limit=34):
    """Trim marketplace-style titles down to something a VO artist can say."""
    n = re.sub(r"\s*\([^)]*\)\s*", " ", name or "").strip()
    n = re.sub(r"\s+", " ", n)
    if len(n) <= limit:
        return n
    for sep in (",", " - ", " – ", " for ", " with ", " featuring ", " and "):
        head = n.split(sep)[0].strip()
        if 8 <= len(head) <= limit:
            return head
    cut = n[:limit].rsplit(" ", 1)[0]
    return cut.strip(" ,-–")


def clip(text, limit=44):
    """Word-safe truncation for on-screen text."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(" ,.-–")


def mine_body(body, fm):
    """Fill gaps left by blog frontmatter, which omits pros/cons/score."""
    out = {}
    if not isinstance(fm.get("verdict_score"), (int, float)):
        m = VERDICT_RE.search(body or "")
        if m:
            out["verdict_score"] = float(m.group(1))
    if not isinstance(fm.get("review_count"), (int, float)):
        m = COUNT_RE.search(body or "")
        if m:
            out["review_count"] = int(m.group(1).replace(",", ""))
    if not isinstance(fm.get("amazon_rating"), (int, float)):
        m = RATING_RE.search(body or "")
        if m:
            out["amazon_rating"] = float(m.group(1))
    pros = [str(p) for p in (fm.get("pros") or []) if p]
    cons = [str(c) for c in (fm.get("cons") or []) if c]
    if not pros or not cons:
        cur = None
        for line in (body or "").splitlines():
            low = line.lower().strip("# *:")
            if re.fullmatch(r"(pros?|what we like|the good|what works)\W*", low):
                cur = "pros"
                continue
            if re.fullmatch(r"(cons?|what we don'?t like|the bad|the catch|downsides?)\W*", low):
                cur = "cons"
                continue
            if line.startswith(("- ", "* ")) and cur:
                txt = re.sub(r"^[-*]\s+", "", line).strip()
                target = pros if cur == "pros" else cons
                if 12 < len(txt) < 140 and txt not in target:
                    target.append(txt)
    out["pros"] = pros[:3]
    out["cons"] = cons[:3]
    return out


# ---------------------------------------------------------------- parsing
def split_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = {}
    return fm, parts[2]


def clean_product_name(fm, slug, body):
    """Best-effort human product name."""
    for key in ("product_name", "product"):
        if fm.get(key):
            return str(fm[key]).strip()

    title = (fm.get("title") or "").strip()
    # "Is the Breville Barista Express Worth It? An Honest Deep-Dive" -> Breville Barista Express
    m = re.search(r"\bIs the (.+?) Worth It\b", title, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(.+?)\s+(?:Review|Hands-On|Tested)\b", title, re.I)
    if m:
        cand = m.group(1).strip(" :-–—")
        if len(cand) > 3:
            return cand
    if title and not GENERIC_TITLE.match(title) and len(title) < 90:
        return title.split("?")[0].strip()

    # fall back to slug -> Title Case
    base = re.sub(r"-(review|worth-it|\d{4})", "", slug, flags=re.I)
    return " ".join(w.capitalize() for w in base.split("-") if w)[:70].strip()


def affiliate_link(fm, body):
    if fm.get("amazon_url"):
        return str(fm["amazon_url"]).strip()
    m = AMZ_DP.search(body or "")
    if m:
        return f"https://www.amazon.com/dp/{m.group(1)}/?tag=tsvglyc-20"
    return ""


def asin_of(link):
    m = AMZ_DP.search(link or "")
    return m.group(1) if m else ""


def product_image(fm):
    for key in ("amazon_image", "image", "featured_image"):
        if fm.get(key):
            return str(fm[key]).strip()
    return ""


# ---------------------------------------------------------------- copy
def money(fm):
    price = fm.get("price")
    if isinstance(price, (int, float)) and price:
        return f"${price:,.0f}" if price >= 10 else f"${price:.2f}"
    return ""


def hooks(name, score, price, reviews):
    p = f" at {price}" if price else ""
    out = []
    out.append(f"Stop. If you're about to buy the {name}{p}, watch the next 40 seconds.")
    if score:
        out.append(f"{name}: {score} out of 5. Here's what the 4-star reviewers won't tell you.")
    if reviews:
        out.append(f"{reviews} Amazon reviews of the {name} — and one thing nobody mentions.")
    out.append(f"The {name}: worth your money or a $40 mistake?")
    seen, uniq = set(), []
    for h in out:
        if h.lower() not in seen:
            seen.add(h.lower())
            uniq.append(h)
    return uniq[:3]


def lower_first(s):
    s = (s or "").strip().rstrip(".")
    if not s:
        return s
    return s[0].lower() + s[1:]


def head_clause(text, max_words=9):
    """Short, speakable clause for the VO — cut at a natural break."""
    t = (text or "").strip().rstrip(".")
    for sep in (" — ", " – ", "; ", ", ", " with ", " that ", " so "):
        if sep in t:
            head = t.split(sep)[0].strip()
            if 2 <= len(head.split()) <= max_words + 2:
                t = head
                break
    if t.count("(") > t.count(")"):
        t = t.split("(")[0].strip()
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    # never end on a dangling connector
    trailing = {"to", "of", "for", "and", "or", "the", "a", "an", "with", "in", "on",
                "at", "by", "from", "than", "very", "more", "less"}
    words = t.split()
    while words and words[-1].lower().strip(",-–") in trailing:
        words.pop()
    t = " ".join(words).rstrip(",-– ")
    return lower_first(t)


def beats(name, score, price, reviews, rating, pros, cons, track):
    pro = pros[0] if pros else "solid build quality for the money"
    con = cons[0] if cons else "a couple of small tradeoffs worth knowing"
    social = ""
    if reviews and rating:
        social = f"{reviews} Amazon ratings, averaging {rating} stars."
    elif reviews:
        social = f"{reviews} Amazon ratings can't all be wrong."
    elif rating:
        social = f"It averages {rating} stars on Amazon."

    return [
        {
            "beat": 1,
            "t": "0:00-0:08",
            "vo": " ".join(
                x for x in [f"This is the {name}.", social, "So I dug through the reviews so you don't have to."] if x
            ),
            "onscreen": [f"THE {name.upper()}", social.replace('.', '') if social else "REAL REVIEW DATA"],
            "broll": "product hero shot, slow push-in",
            "track": track,
        },
        {
            "beat": 2,
            "t": "0:08-0:20",
            "vo": f"First, the good news: {pro}. That's the part that actually holds up in daily use.",
            "onscreen": ["WHAT ACTUALLY WORKS", clip(pro, 44)],
            "broll": "product in use, hands close-up",
            "track": track,
        },
        {
            "beat": 3,
            "t": "0:20-0:32",
            "vo": f"Now the catch — {con}. Nobody puts that in the listing photos.",
            "onscreen": ["THE CATCH", clip(con, 44)],
            "broll": "detail shot, slight dutch angle",
            "track": track,
        },
        {
            "beat": 4,
            "t": "0:32-0:44",
            "vo": (
                f"The upside: {head_clause(pro)}. "
                f"The tradeoff: {head_clause(con)}. That's your call before checkout."
            ),
            "onscreen": ["THE UPSIDE", clip(head_clause(pro), 44).upper(), "THE TRADEOFF", clip(head_clause(con), 44).upper()],
            "broll": "compare shot / price overlay",
            "track": track,
        },
        {
            "beat": 5,
            "t": "0:44-0:55",
            "vo": (
                (f"My verdict: {score} out of 5. " if score else "My verdict is in the full write-up. ")
                + "Full breakdown with the review data is linked below — check today's price before you commit."
            ),
            "onscreen": [f"VERDICT {score}/5" if score else "FULL VERDICT", "LINK IN DESCRIPTION"],
            "broll": "logo end card + product",
            "track": track,
        },
    ]


def thumbnails(name, score, price):
    opts = []
    if score:
        opts.append(f"{score}/5 — WORTH IT?")
    opts.append(f"{name.upper()} — HONEST REVIEW" if len(name) < 26 else "HONEST REVIEW")
    if price:
        opts.append(f"{price} — BUY OR SKIP?")
    opts.append("THE CATCH NOBODY MENTIONS")
    seen, uniq = set(), []
    for o in opts:
        if o.lower() not in seen:
            seen.add(o.lower())
            uniq.append(o)
    return uniq[:3]


# ---------------------------------------------------------------- build
def build_job(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    fm, body = split_frontmatter(raw)
    slug = (fm.get("slug") or os.path.basename(path).replace(".md", "")).strip()
    full = clean_product_name(fm, slug, body)
    name = short_name(full)
    link = affiliate_link(fm, body)
    if JUNK_RE.search(slug) or JUNK_RE.search(full):
        return None, "not_a_product"
    mined = mine_body(body, fm)
    score = fm.get("verdict_score")
    if not isinstance(score, (int, float)):
        score = mined.get("verdict_score")
    score = float(score) if isinstance(score, (int, float)) else None
    reviews = fm.get("review_count")
    if not isinstance(reviews, (int, float)):
        reviews = mined.get("review_count")
    rating = fm.get("amazon_rating")
    if not isinstance(rating, (int, float)):
        rating = mined.get("amazon_rating")
    pros = mined["pros"]
    cons = mined["cons"]
    if reviews and isinstance(reviews, (int, float)):
        reviews = f"{int(reviews):,}"
    price = money(fm)
    if not price:
        m = PRICE_RE.search(fm.get("meta_description") or "") or PRICE_RE.search(body or "")
        if m:
            price = f"${m.group(1)}"

    if not link:
        return None, "no_affiliate_link"

    site_url = f"https://theshoppersverdict.com/{slug}/"
    summary = (fm.get("meta_description") or fm.get("description") or "").strip()

    job = {
        "schema": "tsv.shorts.v1",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source_file": os.path.relpath(path, ROOT),
        "slug": slug,
        "product": name,
        "product_full": full,
        "asin": asin_of(link),
        "site_url": site_url,
        "affiliate_url": link,
        "product_image": product_image(fm),
        "verdict_score": score,
        "amazon_rating": rating,
        "review_count": reviews,
        "price": price,
        "summary": summary,
        "duration_target_sec": 55,
        "track": "suggest: upbeat lo-fi, 90bpm, ducked under VO",
        "hooks": hooks(name, score, price, reviews),
        "beats": beats(name, score, price, reviews, rating, pros, cons, "suggest: upbeat lo-fi, 90bpm"),
        "cta": {
            "vo": f"Link's in the description — check today's price on the {name} before you buy.",
            "onscreen": "LINK IN DESCRIPTION",
            "url": link,
            "button_text": "Check Price on Amazon",
        },
        "thumbnail_text": thumbnails(name, score, price),
        "youtube": {
            "title": f"{name} Review: Worth It? ({'Verdict ' + str(score) + '/5' if score else 'Honest Look'})",
            "description": (summary + "\n\nFull review: " + site_url + "\n\n" + link).strip(),
            "tags": [
                t
                for t in [
                    name.lower(),
                    f"{name.lower()} review",
                    "amazon finds",
                    "honest review",
                    "worth it",
                ]
            ],
            "hashtags": ["#shorts", "#amazonfinds", "#review"],
        },
        "status": "ready",
    }
    return job, None


def write_job(job, outdir=QUEUE, dry_run=False):
    os.makedirs(outdir, exist_ok=True)
    fname = f"{date.today().isoformat()}-{job['slug']}.json"
    out = os.path.join(outdir, fname)
    if os.path.exists(out):  # slug collision between two source files
        stem = fname[:-5]
        i = 2
        while os.path.exists(os.path.join(outdir, f"{stem}-{i}.json")):
            i += 1
        out = os.path.join(outdir, f"{stem}-{i}.json")
    if not dry_run:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(job, fh, indent=2, ensure_ascii=False)
    return out


# ---------------------------------------------------------------- selection
def all_candidates():
    files = []
    for path in glob.glob(os.path.join(CONTENT, "**", "*.md"), recursive=True):
        rel = os.path.relpath(path, CONTENT)
        top = rel.split(os.sep)[0]
        if top in SKIP_DIRS:
            continue
        files.append(path)
    return files


def recent_blog(n):
    files = [
        f
        for f in sorted(glob.glob(os.path.join(CONTENT, "blog", "*.md")), reverse=True)
        if not os.path.basename(f).startswith("_")
    ]
    return files[:n]


def top_reviews(n):
    """Rank by (review_count, verdict_score) — traffic proxy without analytics."""
    scored = []
    for path in all_candidates():
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                fm, _ = split_frontmatter(fh.read())
        except Exception:
            continue
        link = affiliate_link(fm, "")
        if not link:
            continue
        rc = fm.get("review_count")
        rc = float(rc) if isinstance(rc, (int, float)) else 0
        vs = fm.get("verdict_score")
        vs = float(vs) if isinstance(vs, (int, float)) else 0
        name = clean_product_name(fm, fm.get("slug") or "", "")
        if GENERIC_TITLE.match(name):
            continue
        if JUNK_RE.search(name) or JUNK_RE.search(str(fm.get("slug") or "")):
            continue
        scored.append((rc * (vs or 1), path))
    scored.sort(reverse=True)
    return [p for _, p in scored[:n]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--recent", type=int, default=0)
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--outdir", default=QUEUE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = list(args.files)
    if args.recent:
        targets += recent_blog(args.recent)
    if args.top:
        targets += top_reviews(args.top)
    if not targets:
        ap.error("give file paths, or --recent N / --top N")

    ok, skipped = [], []
    for path in targets:
        job, err = build_job(path)
        if err:
            skipped.append((path, err))
            continue
        ok.append(write_job(job, args.outdir, args.dry_run))

    print(f"queued={len(ok)} skipped={len(skipped)} outdir={args.outdir}"
          + (" (dry-run)" if args.dry_run else ""))
    for p in ok[:5]:
        print("  +", os.path.basename(p))
    if len(ok) > 5:
        print(f"  ... +{len(ok) - 5} more")
    for p, e in skipped[:5]:
        print("  -", os.path.basename(p), e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
