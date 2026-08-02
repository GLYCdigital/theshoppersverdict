#!/usr/bin/env python3
"""
stale_reviews.py — Review freshness pass for The Shopper's Verdict.

Why: Reviews publish with a price/rating snapshot at write time. Amazon prices and
ratings drift weekly, so 26K+ live reviews show stale prices and outdated verdict
scores. This tool finds stale reviews, diffs fresh scraped data against frontmatter,
and produces a patch list for review (or applies it when told to).

Workflow (per improvement idea 2026-08-02):
  1. --scan           → list reviews that need a freshness check (stale or never verified)
  2. re-scrape top priority ones (external; scrape_headed.py)
  3. --diff <fresh>   → compare fresh data vs frontmatter, emit patch list JSON
  4. review patch list (human or CI), then --apply <patches.json> to write YAML
  5. every patch stamps `last_verified:` so dedup/pipeline can skip fresh ASINs

Thresholds (drift that triggers a patch): price ±10% OR rating ±0.3 (configurable).
verdict_score is recomputed with the same VERDICT_THRESHOLDS as ink_review_writer.py.

Usage:
  python3 scripts/stale_reviews.py --scan [--days 90] [--out patches.json]
  python3 scripts/stale_reviews.py --scan --priority traffic.json   # weight by traffic
  python3 scripts/stale_reviews.py --diff <fresh_data.json> [--out patches.json] [--dry-run]
  python3 scripts/stale_reviews.py --apply <patches.json> [--dry-run]
  python3 scripts/stale_reviews.py --stats
  python3 scripts/stale_reviews.py --verify <file.md> [--price 25.99 --rating 4.6 --count 300]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, date

import yaml

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(WORKSPACE, "content")
DEFAULT_PATCH_OUT = os.path.join(WORKSPACE, "data", "freshness_patches.json")

# Same thresholds as ink_review_writer.py — verdict score stays consistent site-wide.
VERDICT_THRESHOLDS = {
    (4.5, 5.0): 4.6, (4.0, 4.4): 4.2, (3.5, 3.9): 3.7, (0, 3.4): 3.3,
}

DEFAULT_STALE_DAYS = 90       # re-check reviews older than this
DEFAULT_PRICE_PCT = 0.10      # price drift trigger: ±10%
DEFAULT_RATING_DELTA = 0.3    # rating drift trigger: ±0.3


def get_verdict(amazon_rating):
    for (lo, hi), score in VERDICT_THRESHOLDS.items():
        if lo <= amazon_rating <= hi:
            return score
    return round(amazon_rating, 1)


# ── frontmatter ──────────────────────────────────────────────────────────────

def parse_frontmatter(path):
    """Parse a review file's YAML frontmatter. Returns (frontmatter_dict, raw_frontmatter_str, body_str) or (None, None, None)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return None, None, None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return None, None, None
    raw_fm, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        return None, None, None
    return fm, raw_fm, body


def extract_asin(fm, raw_fm=""):
    url = fm.get("amazon_url", "")
    m = re.search(r"/dp/([A-Z0-9]{10,14})", str(url))
    if m:
        return m.group(1)
    m = re.search(r"/dp/([A-Z0-9]{10,14})", raw_fm)
    return m.group(1) if m else None


def to_float(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return to_float(v.get("value"))
    if isinstance(v, str):
        v = v.replace("$", "").replace(",", "").strip()
        if not v or v.lower() == "null":
            return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ── scan ─────────────────────────────────────────────────────────────────────

def iter_review_files():
    for root, dirs, files in os.walk(CONTENT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            yield os.path.join(root, f)


def review_age_days(fm):
    """Age of the review's `date` (or last_verified) in days. None if undated."""
    for key in ("last_verified", "date"):
        d = fm.get(key)
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.date()
        elif isinstance(d, date):
            pass
        else:
            try:
                d = date.fromisoformat(str(d)[:10])
            except ValueError:
                continue
        return (date.today() - d).days
    return None


def load_priority(path):
    """Load a priority map {asin: score} from JSON (dict, list of {asin,traffic}, or {asins:[...]})."""
    if not path or not os.path.exists(path):
        return {}
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        # {"B0XXXX": 123, ...} or {"asins": [{"asin":..., "traffic":...}]}
        if "asins" in data and isinstance(data["asins"], list):
            return {str(x.get("asin", "")).upper(): float(x.get("traffic", 0)) for x in data["asins"] if x.get("asin")}
        return {str(k).upper(): float(v) for k, v in data.items()}
    if isinstance(data, list):
        return {str(x.get("asin", "")).upper(): float(x.get("traffic", x.get("score", 0))) for x in data if isinstance(x, dict) and x.get("asin")}
    return {}


def cmd_scan(args):
    stale_days = args.days or DEFAULT_STALE_DAYS
    priority = load_priority(args.priority)
    cutoff = date.today()

    stale, fresh, undated = [], [], 0
    for path in iter_review_files():
        fm, raw, body = parse_frontmatter(path)
        if fm is None:
            continue
        if "amazon_url" not in fm and "amazon_rating" not in fm:
            continue  # not a product review
        asin = extract_asin(fm, raw or "")
        age = review_age_days(fm)
        verified = fm.get("last_verified") is not None
        is_stale = (not verified) or (age is not None and age >= stale_days)

        rec = {
            "path": os.path.relpath(path, WORKSPACE),
            "asin": asin,
            "title": (fm.get("title") or "")[:80],
            "price": to_float(fm.get("price")),
            "rating": to_float(fm.get("amazon_rating")),
            "review_count": fm.get("review_count"),
            "verdict_score": fm.get("verdict_score"),
            "date": str(fm.get("date", ""))[:10],
            "last_verified": str(fm.get("last_verified", ""))[:10],
            "age_days": age,
            "priority": priority.get(asin, 0),
        }
        if is_stale:
            stale.append(rec)
        elif verified:
            fresh.append(rec)
        if age is None:
            undated += 1

    # Sort: highest priority first, then oldest, then never-verified.
    stale.sort(key=lambda r: (-r["priority"], -(r["age_days"] if r["age_days"] is not None else 99999)))

    print(f"📊 Freshness scan (stale if unverified or ≥{stale_days}d old):")
    print(f"   Total review files : {len(stale) + len(fresh)}")
    print(f"   🟡 Stale/needs check: {len(stale)}")
    print(f"   🟢 Fresh (verified) : {len(fresh)}")
    print(f"   ⚠️  Undated files    : {undated}")
    if stale:
        print(f"\n   Top 10 to re-scrape first:")
        for r in stale[:10]:
            flag = "never-verified" if not r["last_verified"] else f"{r['age_days']}d old"
            prio = f" (traffic {r['priority']:.0f})" if r["priority"] else ""
            print(f"     {r['asin']}  {r['title'][:44]:44s} {flag}{prio}")

    if args.out:
        out = os.path.join(WORKSPACE, args.out)
        with open(out, "w") as fh:
            json.dump({"generated": str(date.today()), "stale_days": stale_days,
                       "reviews": stale}, fh, indent=2)
        print(f"\n   💾 Full stale list → {os.path.relpath(out, WORKSPACE)}")
    return 0


# ── diff ─────────────────────────────────────────────────────────────────────

def normalize_fresh(fresh):
    """Accept a briefing JSON or list → dict keyed by ASIN."""
    if isinstance(fresh, list):
        fresh = fresh[0] if fresh and isinstance(fresh[0], dict) else {}
    if not isinstance(fresh, dict) or fresh.get("error"):
        return {}
    asin = str(fresh.get("asin", "")).upper()
    if not asin or len(asin) < 10:
        # try to find asin in a url field
        m = re.search(r"/dp/([A-Z0-9]{10,14})", str(fresh.get("actual_url", "")))
        asin = m.group(1) if m else None
    if not asin:
        return {}
    return {asin: fresh}


def patch_for(fm, fresh, price_pct, rating_delta, asin, path):
    """Compute proposed field updates for one review. Returns (patch, changes, drift_summary)."""
    patch = {"asin": asin, "path": path}
    changes = []
    drift = {}

    cur_price = to_float(fm.get("price"))
    new_price = to_float(fresh.get("price"))
    if cur_price is not None and new_price is not None and cur_price > 0:
        pct = (new_price - cur_price) / cur_price
        drift["price_pct"] = round(pct * 100, 1)
        if abs(pct) >= price_pct:
            patch["price"] = round(new_price, 2)
            changes.append(f"price ${cur_price:.2f} → ${new_price:.2f} ({pct*100:+.1f}%)")
    elif cur_price is None and new_price is not None:
        patch["price"] = round(new_price, 2)
        changes.append(f"price (was null) → ${new_price:.2f}")

    cur_rating = to_float(fm.get("amazon_rating"))
    new_rating = to_float(fresh.get("rating"))
    if cur_rating is not None and new_rating is not None:
        d = new_rating - cur_rating
        drift["rating_delta"] = round(d, 2)
        if abs(d) >= rating_delta:
            patch["amazon_rating"] = round(new_rating, 1)
            changes.append(f"rating {cur_rating} → {new_rating} ({d:+.1f})")
    elif cur_rating is None and new_rating is not None:
        patch["amazon_rating"] = round(new_rating, 1)
        changes.append(f"rating (was null) → {new_rating}")

    new_count = fresh.get("review_count")
    cur_count = fm.get("review_count")
    if new_count is not None:
        try:
            new_count = int(new_count)
            cur_count = int(cur_count) if cur_count is not None else None
        except (ValueError, TypeError):
            new_count = None
    if new_count is not None and (cur_count is None or new_count != cur_count):
        if cur_count is not None and cur_count > 0:
            drift["review_count_pct"] = round((new_count - cur_count) / cur_count * 100, 1)
        patch["review_count"] = new_count
        changes.append(f"review_count {cur_count or 'null'} → {new_count}")

    # verdict_score follows rating
    if "amazon_rating" in patch:
        patch["verdict_score"] = get_verdict(patch["amazon_rating"])

    patch["last_verified"] = str(date.today())
    return patch, changes, drift


def cmd_diff(args):
    with open(args.diff) as fh:
        fresh_map = normalize_fresh(json.load(fh))
    if not fresh_map:
        print("❌ No usable ASIN found in diff file.")
        return 2

    patches, skipped = [], []
    price_pct = args.price_pct or DEFAULT_PRICE_PCT
    rating_delta = args.rating_delta or DEFAULT_RATING_DELTA

    for asin, fresh in fresh_map.items():
        target = None
        for path in iter_review_files():
            fm, raw, body = parse_frontmatter(path)
            if fm is None:
                continue
            if extract_asin(fm, raw or "") == asin:
                target = (path, fm)
                break
        if not target:
            skipped.append({"asin": asin, "reason": "no matching review on site"})
            continue
        path, fm = target
        rel = os.path.relpath(path, WORKSPACE)
        patch, changes, drift = patch_for(fm, fresh, price_pct, rating_delta, asin, rel)
        if changes:
            patch["changes"] = changes
            patch["drift"] = drift
            patches.append(patch)
        else:
            # still stamp last_verified so dedup skips it next time
            patches.append({"asin": asin, "path": rel, "last_verified": str(date.today()),
                            "changes": ["no drift — stamping last_verified"], "drift": drift, "noop": True})

    print(f"🔍 Diffed {len(fresh_map)} ASIN(s) against live frontmatter:")
    print(f"   📝 Patches proposed : {len(patches)}")
    for p in patches:
        tag = " (noop)" if p.get("noop") else ""
        print(f"     {p['asin']}  {p['path']}{tag}")
        for c in p.get("changes", []):
            print(f"        • {c}")
    if skipped:
        print(f"   ⏭  Skipped: {[s['asin'] for s in skipped]}")

    out = os.path.join(WORKSPACE, args.out or DEFAULT_PATCH_OUT)
    with open(out, "w") as fh:
        json.dump({"generated": str(date.today()), "price_pct": price_pct,
                   "rating_delta": rating_delta, "patches": patches, "skipped": skipped}, fh, indent=2)
    print(f"\n   💾 Patch list → {os.path.relpath(out, WORKSPACE)}")
    return 0


# ── apply ────────────────────────────────────────────────────────────────────

def apply_patch(path_abs, patch):
    """Rewrite frontmatter fields in place. Preserves everything else byte-for-byte."""
    with open(path_abs, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n?)(.*)$", text, re.S)
    if not m:
        return False, "no frontmatter"
    open_delim, raw_fm, close_delim, body = m.group(1), m.group(2), m.group(3), m.group(4)
    lines = raw_fm.split("\n")

    def set_field(name, value):
        """Replace `name:` line, or insert before date/amazon_url if absent. Returns count."""
        line = f"{name}: {value}"
        for i, ln in enumerate(lines):
            if re.match(rf"^{re.escape(name)}:", ln):
                lines[i] = line
                return 1
        # insert after 'date:' if present, else append
        for i, ln in enumerate(lines):
            if ln.startswith("date:"):
                lines.insert(i + 1, line)
                return 1
        lines.append(line)
        return 1

    changed = 0
    for field in ("price", "amazon_rating", "review_count", "verdict_score", "last_verified"):
        if field in patch:
            v = patch[field]
            if field in ("amazon_rating", "verdict_score"):
                v = f"{v:.1f}" if isinstance(v, float) else v
            elif field == "price" and isinstance(v, float):
                v = f"{v:g}" if v % 1 == 0 else f"{v:.2f}"
            set_field(field, v)
            changed += 1

    new_text = open_delim + "\n".join(lines) + close_delim + body
    with open(path_abs, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    return True, f"{changed} field(s) patched"


def cmd_apply(args):
    with open(args.apply) as fh:
        data = json.load(fh)
    patches = data.get("patches", data if isinstance(data, list) else [])
    applied, skipped = [], []

    for p in patches:
        path_abs = os.path.join(WORKSPACE, p["path"]) if not os.path.isabs(p["path"]) else p["path"]
        if not os.path.exists(path_abs):
            skipped.append({"asin": p.get("asin"), "path": p["path"], "reason": "file missing"})
            continue
        if p.get("noop"):
            # stamp last_verified only
            ok, msg = apply_patch(path_abs, {"last_verified": p["last_verified"]})
        else:
            ok, msg = apply_patch(path_abs, {k: v for k, v in p.items() if k in
                                             ("price", "amazon_rating", "review_count", "verdict_score", "last_verified")})
        if ok:
            applied.append({"asin": p.get("asin"), "path": p["path"], "msg": msg})
        else:
            skipped.append({"asin": p.get("asin"), "path": p["path"], "reason": msg})

    print(f"✅ Applied {len(applied)} patch(es):")
    for a in applied:
        print(f"     {a['asin']}  {a['path']} — {a['msg']}")
    if skipped:
        print(f"   ⏭  Skipped {len(skipped)}: {[s['reason'] for s in skipped]}")
    return 0


# ── stats & verify ───────────────────────────────────────────────────────────

def cmd_stats(args):
    total = price = rating = count = verified = 0
    for path in iter_review_files():
        fm, raw, body = parse_frontmatter(path)
        if fm is None or "amazon_url" not in fm and "amazon_rating" not in fm:
            continue
        total += 1
        if to_float(fm.get("price")) is not None:
            price += 1
        if to_float(fm.get("amazon_rating")) is not None:
            rating += 1
        if fm.get("review_count") is not None:
            count += 1
        if fm.get("last_verified"):
            verified += 1
    print(f"📈 Freshness stats:")
    print(f"   Reviews total      : {total}")
    print(f"   With price         : {price} ({price*100//max(total,1)}%)")
    print(f"   With rating        : {rating} ({rating*100//max(total,1)}%)")
    print(f"   With review_count  : {count} ({count*100//max(total,1)}%)")
    print(f"   With last_verified : {verified} ({verified*100//max(total,1)}%)")
    print(f"   Freshness coverage : {verified*100//max(total,1)}% — target 100%")
    return 0


def cmd_verify(args):
    """Check one review file against fresh values, print what would change."""
    for path in iter_review_files():
        if os.path.basename(path) == args.verify or path.endswith(args.verify):
            fm, raw, body = parse_frontmatter(path)
            if fm is None:
                print("❌ No frontmatter")
                return 2
            fresh = {}
            if args.price is not None:
                fresh["price"] = args.price
            if args.rating is not None:
                fresh["rating"] = args.rating
            if args.count is not None:
                fresh["review_count"] = args.count
            asin = extract_asin(fm, raw or "")
            patch, changes, drift = patch_for(fm, fresh, DEFAULT_PRICE_PCT, DEFAULT_RATING_DELTA, asin, args.verify)
            print(f"🔎 {asin}  {args.verify}")
            print(f"   now  : price={fm.get('price')} rating={fm.get('amazon_rating')} count={fm.get('review_count')} verdict={fm.get('verdict_score')}")
            print(f"   drift: {drift or 'none'}")
            for c in changes:
                print(f"   • {c}")
            return 0
    print(f"❌ File not found: {args.verify}")
    return 2


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Review freshness pass for The Shopper's Verdict")
    sub = ap.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="list stale reviews")
    p_scan.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS)
    p_scan.add_argument("--priority", help="JSON file mapping ASIN→traffic score")
    p_scan.add_argument("--out", help="output JSON path (default: none)")

    p_diff = sub.add_parser("diff", help="diff fresh scraped data vs frontmatter")
    p_diff.add_argument("diff", help="fresh data JSON (briefing format)")
    p_diff.add_argument("--price-pct", type=float, default=DEFAULT_PRICE_PCT)
    p_diff.add_argument("--rating-delta", type=float, default=DEFAULT_RATING_DELTA)
    p_diff.add_argument("--out")

    p_apply = sub.add_parser("apply", help="apply a reviewed patch list")
    p_apply.add_argument("apply", help="patch list JSON")

    p_stats = sub.add_parser("stats", help="freshness coverage stats")
    p_verify = sub.add_parser("verify", help="check one file against fresh values")
    p_verify.add_argument("verify", help="review .md filename or path")
    p_verify.add_argument("--price", type=float)
    p_verify.add_argument("--rating", type=float)
    p_verify.add_argument("--count", type=int)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 2
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "stats":
        return cmd_stats(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
