#!/usr/bin/env python3
"""Build data/product_ledger.json from the scraped briefings.

Design notes (see CONVERSATION_LOG 2026-10-27 improvement-idea review):
  - This is an INDEXING job, not a scraping job. briefings/ is the source.
  - ASIN is not a stable identity key (recycled listings; parent/child variants),
    so every record also carries a heuristic `family_key`.
  - "The price" is a fiction: we store price_observed + marketplace + observed_at.
    Consumers must render it as observed-with-date, never as durable fact.
  - The file is GENERATED, never served. No API.
  - Completeness is measured against the publish queue only, and a partial run is
    flagged so gates can fail closed.
  - Briefings that cannot be keyed are listed in `ungated` explicitly, so a gate
    can never silently believe it covered something it did not.

Usage:
    python3 scripts/build_product_ledger.py            # write ledger
    python3 scripts/build_product_ledger.py --dry-run  # report only
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFINGS = os.path.join(ROOT, "briefings")
QUEUE = os.path.join(ROOT, "data", "asin_queue.json")
# Also outside data/: Hugo would parse it into .Site.Data on every build.
OUT = os.path.join(ROOT, "state", "product_ledger.json")
# NOT under data/: Hugo auto-loads everything in data/ and aborts the whole
# build on an unsupported format (.jsonl). This is pipeline state, not site data.
HISTORY = os.path.join(ROOT, "state", "price_history.jsonl")

# Tokens that describe a *variant*, not a product family.
VARIANT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:fl\.?\s*oz|oz|ml|l|g|kg|lb|lbs|ct|count|pack|pcs|pc|piece|"
    r"inch|in\.?|cm|mm|ft|w|watt|wattage|qt|gal)\b",
    re.I,
)
PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
NOISE_RE = re.compile(
    r"\b(?:pack of \d+|set of \d+|\d+\s*-?\s*pack|bundle|refill|replacement|"
    r"new|updated|improved|upgraded|latest|version|model)\b",
    re.I,
)
COLOR_RE = re.compile(
    r"\b(?:black|white|silver|grey|gray|red|blue|green|pink|beige|navy|cream|"
    r"stainless steel|chrome|matte|gloss|clear|multicolou?r)\b",
    re.I,
)
SLUG_RE = re.compile(r"[^a-z0-9]+")


def marketplace_of(url: str) -> tuple[str, str]:
    """Return (marketplace, currency) from an Amazon URL/domain."""
    u = (url or "").lower()
    m = re.search(r"amazon\.([a-z.]{2,6})", u)
    if not m:
        return ("unknown", "unknown")
    host = m.group(1).rstrip("/")
    table = {
        "com": ("US", "USD"),
        "sg": ("SG", "SGD"),
        "co.uk": ("UK", "GBP"),
        "co.jp": ("JP", "JPY"),
        "ca": ("CA", "CAD"),
        "com.au": ("AU", "AUD"),
        "de": ("DE", "EUR"),
    }
    return (table.get(host, ("unknown", "unknown")))


def family_key(brand: str | None, title: str | None) -> str | None:
    """Heuristic product-family key: brand + title with variant noise stripped.

    ASIN alone merges variants and splits recycled listings; this groups the
    things a human would call "the same product in a different size/colour".
    It is deliberately conservative: when in doubt it keeps tokens, producing a
    narrower family rather than a wrong merge.
    """
    if not title:
        return None
    t = PAREN_RE.sub(" ", title)
    t = VARIANT_RE.sub(" ", t)
    t = NOISE_RE.sub(" ", t)
    t = COLOR_RE.sub(" ", t)
    t = t.lower()
    t = SLUG_RE.sub("-", t).strip("-")
    if not t:
        return None
    b = SLUG_RE.sub("-", (brand or "").lower()).strip("-")
    if b and not t.startswith(b):
        t = f"{b}-{t}"
    return t[:120]


def observed_at_of(data: dict, path: str) -> tuple[str, str]:
    """When was this record actually observed?

    Preference order matters: mtime is NOT trustworthy. Five briefings carry a
    scrapeTimestamp, and on those the file mtime runs up to 36 days LATER than
    the scrape (files were copied/restored, which resets mtime). So use the
    scraped timestamp when the scraper recorded one, and label mtime as a weak
    fallback so consumers can weight it accordingly.
    """
    ts = data.get("scrapeTimestamp") or data.get("scraped_at")
    if isinstance(ts, str) and ts.strip():
        try:
            dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (dt.astimezone(timezone.utc).isoformat(timespec="seconds"), "scrape_timestamp")
        except Exception:
            pass
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        try:
            secs = ts / 1000 if ts > 1e11 else ts
            return (datetime.fromtimestamp(secs, tz=timezone.utc).isoformat(timespec="seconds"), "scrape_timestamp")
        except Exception:
            pass
    return (iso(os.path.getmtime(path)), "file_mtime")


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def is_asin(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[A-Z0-9]{10}", v.strip()) is not None


def load_queue() -> dict[str, list[str]]:
    try:
        with open(QUEUE) as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for cat, items in raw.items():
        if isinstance(items, list):
            out[cat] = [i for i in items if isinstance(i, str)]
    return out


def build(dry_run: bool = False) -> dict:
    files = sorted(glob.glob(os.path.join(BRIEFINGS, "*.json")))
    run_manifest = []
    products: dict[str, dict] = {}
    ungated: list[dict] = []
    collisions: list[dict] = []
    fam_index: dict[str, list[str]] = {}
    list_rooted = 0
    unreadable = 0
    # Append-only observation log. Last-write-wins throws away the one sentence
    # we most want to be able to write: "it was $349 in October, now $399".
    # Dedupe key keeps re-runs idempotent.
    seen_obs: set[tuple[str, str]] = set()
    new_obs: list[dict] = []
    try:
        with open(HISTORY) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    seen_obs.add((o.get("asin", ""), o.get("observed_at", "")))
                except Exception:
                    continue
    except FileNotFoundError:
        pass

    for path in files:
        name = os.path.basename(path)
        try:
            with open(path) as fh:
                data = json.load(fh)
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
        except Exception:
            unreadable += 1
            ungated.append({"file": name, "reason": "unreadable"})
            continue

        run_manifest.append(f"{name}:{int(mtime)}:{size}")

        if isinstance(data, list):
            list_rooted += 1
            data = data[0] if data else {}
        if not isinstance(data, dict):
            ungated.append({"file": name, "reason": "not an object"})
            continue

        asin = (data.get("asin") or "").strip().upper() if data.get("asin") else ""
        if not is_asin(asin):
            ungated.append(
                {"file": name, "reason": "no valid ASIN (cannot be gated)", "title": data.get("title")}
            )
            continue

        url = data.get("actual_url") or data.get("url") or ""
        market, currency = marketplace_of(url)
        price = data.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            price = None
        elif price <= 0:
            price = None

        observed_at, observed_src = observed_at_of(data, path)

        rec = {
            "asin": asin,
            "family_key": family_key(data.get("brand"), data.get("title")),
            "title": data.get("title"),
            "brand": data.get("brand"),
            "price_observed": price,
            "currency": currency,
            "marketplace": market,
            "observed_at": observed_at,
            "observed_at_source": observed_src,
            "image": data.get("image"),
            "source_url": url or None,
            "rating": data.get("rating"),
            "review_count": data.get("review_count"),
            "briefing_file": name,
        }

        prev = products.get(asin)
        if prev is None or rec["observed_at"] >= prev["observed_at"]:
            if prev is not None:
                # keep the history pointer so drift is auditable later
                rec["superseded_observed_at"] = prev.get("observed_at")
                rec["superseded_price_observed"] = prev.get("price_observed")
            products[asin] = rec

        key = (asin, rec["observed_at"])
        if rec["price_observed"] is not None and key not in seen_obs:
            seen_obs.add(key)
            new_obs.append(
                {
                    "asin": asin,
                    "observed_at": rec["observed_at"],
                    "observed_at_source": rec["observed_at_source"],
                    "price": rec["price_observed"],
                    "currency": currency,
                    "marketplace": market,
                    "briefing_file": name,
                }
            )

        if rec["family_key"]:
            fam_index.setdefault(rec["family_key"], []).append(asin)

    for fam, asins in fam_index.items():
        uniq = sorted(set(asins))
        if len(uniq) > 1:
            collisions.append({"family_key": fam, "asins": uniq, "variant_count": len(uniq)})

    # Completeness is measured against the publish queue ONLY: a run that skips
    # briefings we never publish is fine; one that skips a queued product is not.
    queue = load_queue()
    queued = sorted({a.strip().upper() for items in queue.values() for a in items if is_asin(a.strip().upper())})
    missing = [a for a in queued if a not in products]
    no_price = sorted(a for a in products if products[a]["price_observed"] is None)

    run_hash = hashlib.sha256("\n".join(run_manifest).encode()).hexdigest()[:16]

    # Annotate + persist the append-only observations now that the run id exists.
    for o in new_obs:
        o["scrape_run_id"] = run_hash
    if new_obs and not dry_run:
        with open(HISTORY, "a") as fh:
            for o in new_obs:
                fh.write(json.dumps(o, sort_keys=True) + "\n")

    # Per-ASIN observation stats: how many distinct observations we hold, and
    # whether a *range* claim would be honest (>=2 observations on different days).
    obs_by_asin: dict[str, list[dict]] = {}
    try:
        with open(HISTORY) as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("asin"):
                    obs_by_asin.setdefault(o["asin"], []).append(o)
    except FileNotFoundError:
        pass
    for asin, rec in products.items():
        obs = sorted(obs_by_asin.get(asin, []), key=lambda o: o.get("observed_at", ""))
        rec["observation_count"] = len(obs)
        rec["first_observed_at"] = obs[0]["observed_at"] if obs else None
        if obs:
            rec["price_first"] = obs[0].get("price")
            rec["price_latest"] = obs[-1].get("price")
        distinct_days = {o["observed_at"][:10] for o in obs if o.get("observed_at")}
        # Contract (agreed with ink:main): a public range requires >=2 observations
        # on >=2 distinct days AND every contributing observation to be
        # scrape_timestamp-era. Approximate sources (file mtime, post frontmatter
        # dates) stay internal-only, no matter how many of them we accumulate.
        sources = {o.get("observed_at_source") for o in obs}
        rec["observation_sources"] = sorted(s for s in sources if s)
        rec["range_eligible"] = (
            len(obs) >= 2
            and len(distinct_days) >= 2
            and sources == {"scrape_timestamp"}
        )

    # Freshness: the whole point of the gate is to stop stale facts from
    # shipping. Surface it here so a consumer can fail closed without parsing
    # every record, and so a dead scrape is visible rather than silent.
    stamps = sorted(r["observed_at"] for r in products.values() and [r for r in products.values() if r["observed_at"]] or [])
    now = datetime.now(timezone.utc)
    newest = stamps[-1] if stamps else None
    oldest = stamps[0] if stamps else None
    if newest:
        age_days = (now - datetime.fromisoformat(newest)).days
    else:
        age_days = None
    stale_14d = sum(
        1
        for r in products.values()
        if r.get("observed_at")
        and (now - datetime.fromisoformat(r["observed_at"])).days > 14
    )

    ledger = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scrape_run_id": run_hash,
        "source_dir": "briefings/",
        "record_count": len(products),
        "completeness": {
            "queue_total": len(queued),
            "queue_covered": len(queued) - len(missing),
            "queue_missing": missing,
            "partial_run": bool(missing),
            "briefing_files": len(files),
            "unreadable": unreadable,
            "list_rooted": list_rooted,
            "records_without_price": len(no_price),
            "records_without_price_sample": no_price[:20],
            # Fail-closed contract: a consumer gate MUST block when
            # partial_run is true, rather than serving a half-refreshed world.
        },
        "freshness": {
            "newest_observed_at": newest,
            "oldest_observed_at": oldest,
            "newest_age_days": age_days,
            "records_older_than_14d": stale_14d,
            "source_stalled": (age_days or 0) > 14,
            # If source_stalled is true, do NOT build gates on this file: the
            # scrape is dead, not the products.
        },
        "ungated": ungated,
        "family_collisions": collisions,
        "products": products,
    }

    if not dry_run:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        tmp = OUT + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(ledger, fh, indent=1, sort_keys=True)
        os.replace(tmp, OUT)

    return ledger


def main() -> int:
    dry = "--dry-run" in sys.argv
    led = build(dry_run=dry)
    c = led["completeness"]
    print(f"{'DRY RUN — ' if dry else ''}ledger records: {led['record_count']}")
    print(f"run id: {led['scrape_run_id']}  briefings: {c['briefing_files']}")
    print(f"queue coverage: {c['queue_covered']}/{c['queue_total']}  partial_run: {c['partial_run']}")
    if c["queue_missing"]:
        print(f"  missing from queue: {c['queue_missing'][:10]}")
    fr = led["freshness"]
    print(
        f"freshness: newest {fr['newest_observed_at']} ({fr['newest_age_days']}d old) "
        f"stalled={fr['source_stalled']} stale>14d={fr['records_older_than_14d']}"
    )
    print(f"without price: {c['records_without_price']}  ungated: {len(led['ungated'])}")
    print(f"family collisions (>1 ASIN same family): {len(led['family_collisions'])}")
    for col in led["family_collisions"][:5]:
        print(f"  {col['family_key'][:60]} -> {col['asins']}")
    if not dry:
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
