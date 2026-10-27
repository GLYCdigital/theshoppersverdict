#!/usr/bin/env python3
"""Drop numeric prices from posts whose price observation is stale.

Rule (agreed 2026-10-27): no numeric price renders without an observed_at
inside 14 days. Until the scraper is revived, every entry in
data/product_ledger.json is stale, so numeric prices are removed and the
post links out to the live listing instead. Provenance is preserved in
data/price_history.jsonl, so prices can be restored once observations are
fresh again.

Usage:
    python3 scripts/drop_stale_prices.py            # dry run (default)
    python3 scripts/drop_stale_prices.py --apply    # write changes
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
LEDGER = ROOT / "state" / "product_ledger.json"
FRESH_DAYS = 14

NUMERIC = re.compile(r'^price:\s*(?:\$\s*"?([0-9][0-9.]*)"?|"?([0-9][0-9.]*)"?)\s*$', re.M)
ASIN = re.compile(r'/(?:dp|gp/product)/([A-Z0-9]{10})')


def load_ledger():
    if not LEDGER.exists():
        return None
    with LEDGER.open() as fh:
        data = json.load(fh)
    raw = data.get("products") or data.get("records") or []
    records = raw.values() if isinstance(raw, dict) else raw
    by_asin = {}
    for rec in records:
        asin = (rec.get("asin") or "").upper()
        if asin:
            by_asin[asin] = rec
    return {"by_asin": by_asin, "freshness": data.get("freshness", {})}


def is_fresh(rec, cutoff):
    if not rec:
        return False
    ts = rec.get("observed_at") or rec.get("verified_at")
    if not ts:
        return False
    try:
        observed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed >= cutoff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=FRESH_DAYS)
    args = ap.parse_args()

    ledger = load_ledger()
    if ledger is None:
        print("ERROR: state/product_ledger.json missing — refusing to guess freshness", file=sys.stderr)
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    stale, fresh, unverifiable = [], [], []

    for path in CONTENT.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        head = text[3:].split("\n---", 1)[0]
        m = NUMERIC.search(head)
        if not m:
            continue
        am = ASIN.search(head)
        asin = am.group(1) if am else None
        rec = ledger["by_asin"].get(asin) if asin else None
        if not asin:
            unverifiable.append(path)
        elif is_fresh(rec, cutoff):
            fresh.append(path)
        else:
            stale.append((path, m.group(1) or m.group(2)))

    print(f"numeric-priced posts : {len(stale) + len(fresh) + len(unverifiable)}")
    print(f"stale (drop)         : {len(stale)}")
    print(f"fresh (keep)         : {len(fresh)}")
    print(f"no ASIN (ungated)    : {len(unverifiable)}")
    print(f"source_stalled       : {ledger['freshness'].get('source_stalled')}")

    if not args.apply:
        print("\ndry run — pass --apply to write")
        for path, price in stale[:5]:
            print(f"  would drop {price} :: {path.relative_to(ROOT)}")
        return 0

    for path, price in stale:
        text = path.read_text(encoding="utf-8")
        text = NUMERIC.sub("price: null", text, count=1)
        path.write_text(text, encoding="utf-8")
    print(f"\napplied: {len(stale)} prices dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
