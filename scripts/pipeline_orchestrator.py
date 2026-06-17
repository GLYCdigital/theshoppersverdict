#!/usr/bin/env python3
"""
Pipeline Orchestrator — tiered scraping with graceful degradation.

Tiers per ASIN:
  1. Headed Chrome scrape (scrape_headed.py)
  2. Backlog briefings (briefings/_backlog/)
  3. Skip — mark ASIN for future retry

Partial yield is published — 6/10 is better than 0/10.
Yield monitor alerts ops group when coverage < 80%.

Usage:
  python3 scripts/pipeline_orchestrator.py                    # full 10-review batch
  python3 scripts/pipeline_orchestrator.py --dry-run          # simulate, don't scrape
  python3 scripts/pipeline_orchestrator.py --category coffee --count 4  # single cat
"""

import sys, os, json, re, random, subprocess, time, shutil, glob
from pathlib import Path

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
BACKLOG_DIR = os.path.join(BRIEFINGS_DIR, "_backlog")
PROCESSED_DIR = os.path.join(BRIEFINGS_DIR, "processed")
QUEUE_PATH = os.path.join(WORKSPACE, "data", "asin_queue.json")
PROCESSED_ASINS_PATH = os.path.join(WORKSPACE, "data", "processed_asins.json")

SCRAPE_COOLDOWN_S = 45  # anti-bot: seconds between headed Chrome scrapes

DEFAULT_DISTRIBUTION = {
    "coffee": 2,
    "kitchen": 2,
    "home-office": 2,
    "home-improvement": 2,
    "luxury-beauty": 1,
    "pet-supplies": 1,
}
YIELD_ALERT_THRESHOLD = 0.80  # alert ops group if < 80% of target

os.makedirs(BRIEFINGS_DIR, exist_ok=True)
os.makedirs(BACKLOG_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)


# ─── helpers ───────────────────────────────────────────

def load_queue():
    with open(QUEUE_PATH) as f:
        return json.load(f)


def load_processed():
    """Load set of already-processed ASINs (cross-run dedup)."""
    processed = set()
    if os.path.exists(PROCESSED_ASINS_PATH):
        with open(PROCESSED_ASINS_PATH) as f:
            processed = set(json.load(f))
    # Also check used list in queue
    q = load_queue()
    processed.update(q.get('used', []))
    # Also check briefings/processed/ directory
    for f in glob.glob(os.path.join(PROCESSED_DIR, '*_data.json')):
        asin = Path(f).stem.split('_')[-1] if '_' in Path(f).stem else None
        if asin and asin.startswith('B'):
            processed.add(asin)
    return processed


def dedup_check(asin):
    """Quick dedup — returns True if ASIN is new."""
    result = subprocess.run(
        ["python3", os.path.join(WORKSPACE, "scripts", "dedup_check.py"), asin],
        capture_output=True, text=True, timeout=15
    )
    return result.returncode == 0


def pick_asins(category, count, processed):
    """Pick `count` fresh ASINs from queue."""
    queue = load_queue()
    pending = [a for a in queue.get(category, []) if a not in processed]
    return pending[:count]


# ─── tier scrapers ─────────────────────────────────────

def tier1_scrape(asin, category, dry_run=False):
    """Headed Chrome scrape — returns data dict or None."""
    if dry_run:
        print(f"    [DRY] Would scrape {asin} via headed Chrome")
        return {"_tier": 1, "_dry": True}
    
    try:
        result = subprocess.run(
            ["python3", os.path.join(WORKSPACE, "scripts", "scrape_headed.py"),
             asin, category, "--reviews", "8"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"    ❌ Tier 1 failed: {result.stderr.strip()[-120:]}")
            return None
        
        # Load saved data
        data_path = os.path.join(BRIEFINGS_DIR, f"{category}_{asin}_data.json")
        if os.path.exists(data_path):
            with open(data_path) as f:
                data = json.load(f)
                data['_tier'] = 1
                return data
    except Exception as e:
        print(f"    ❌ Tier 1 exception: {e}")
    return None


def tier2_backlog(category, count_needed):
    """Find pre-scraped briefings from backlog."""
    # Look for JSON data files and briefing markdown files
    candidates = []
    
    for pattern in [f"{category}_*_data.json", f"{category}_*_briefing.md"]:
        for f in glob.glob(os.path.join(BACKLOG_DIR, pattern)):
            asin_match = re.search(r'_(B[A-Z0-9]{9})_', os.path.basename(f))
            if asin_match:
                asin = asin_match.group(1)
                candidates.append((f, asin))
    
    results = []
    for filepath, asin in candidates[:count_needed]:
        if not dedup_check(asin):
            continue
        
        if filepath.endswith('_data.json'):
            # Copy JSON directly
            dst = os.path.join(BRIEFINGS_DIR, os.path.basename(filepath))
            shutil.copy(filepath, dst)
            with open(dst) as f:
                data = json.load(f)
            # Handle list-wrapped JSON output format
            if isinstance(data, list):
                data = data[0] if data and isinstance(data[0], dict) else {}
            if not isinstance(data, dict) or data.get('error'):
                print(f"    ⚠️  Tier 2 skip: {asin} — backlog JSON is error/wrapper")
                continue
            data['_tier'] = 2
            data['_source'] = 'backlog'
            results.append(data)
            print(f"    ✅ Tier 2: {asin} from backlog JSON")
        
        elif filepath.endswith('_briefing.md'):
            # Convert briefing markdown to JSON
            from_briefing = parse_briefing_md(filepath)
            if from_briefing and from_briefing.get('image'):
                dst = os.path.join(BRIEFINGS_DIR, f"{category}_{asin}_data.json")
                from_briefing['_tier'] = 2
                from_briefing['_source'] = 'backlog_md'
                with open(dst, 'w') as f:
                    json.dump(from_briefing, f, indent=2)
                results.append(from_briefing)
                print(f"    ✅ Tier 2: {asin} from backlog briefing")
    
    return results


def parse_briefing_md(filepath):
    """Extract product data from briefing markdown."""
    try:
        with open(filepath) as f:
            text = f.read()
        
        title_match = re.search(r'^# Product Briefing: (.+)$', text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Unknown Product"
        
        price_match = re.search(r'\|\s*Price\s*\|\s*\$?([\d,.]+)', text)
        price = float(price_match.group(1).replace(',', '')) if price_match else None
        
        rating_match = re.search(r'\|\s*Rating\s*\|\s*([\d.]+)', text)
        rating = float(rating_match.group(1)) if rating_match else None
        
        rc_match = re.search(r'Reviews Analyzed\s*\|\s*([\d,]+)\s+total', text)
        review_count = int(rc_match.group(1).replace(',', '')) if rc_match else 0
        
        img_match = re.search(r'\|\s*Image\s*\|\s*(https?://[^\s|]+)', text)
        image_url = img_match.group(1) if img_match else ""
        
        return {
            "title": title,
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "image": image_url,
            "reviews": [],
        }
    except Exception as e:
        print(f"    ⚠️ Failed to parse briefing: {e}")
        return None


# ─── orchestration ─────────────────────────────────────

def process_category(category, count, processed, dry_run=False):
    """Process one category through tiers. Returns list of scraped data dicts."""
    results = []
    needed = count
    
    if dry_run:
        asins = pick_asins(category, count, processed)
        return [{'_tier': 0, '_dry': True, '_asin': a, '_category': category} for a in asins]
    
    # Tier 1: Headed Chrome
    asins = pick_asins(category, needed, processed)
    tier1_used = set()
    
    for i, asin in enumerate(asins):
        if len(results) >= count:
            break
        if i > 0 and SCRAPE_COOLDOWN_S > 0:
            print(f"  ⏳ Cooling down {SCRAPE_COOLDOWN_S}s to avoid bot detection...")
            time.sleep(SCRAPE_COOLDOWN_S)
        print(f"  → {category} ASIN {asin}: Tier 1 (headed Chrome)")
        data = tier1_scrape(asin, category)
        if data and data.get('title'):
            results.append(data)
            processed.add(asin)
            tier1_used.add(asin)
            print(f"    ✅ {data['title'][:70]}")
        else:
            print(f"    ❌ Tier 1 failed for {asin}")
    
    # Tier 2: Backlog fallback
    remaining = count - len(results)
    if remaining > 0:
        print(f"  → {category}: {remaining} slots unfilled, trying backlog...")
        backlog_results = tier2_backlog(category, remaining)
        for data in backlog_results:
            if data.get('title'):
                results.append(data)
                # Extract ASIN from data
                asin = data.get('asin', '')
                if asin:
                    processed.add(asin)
    
    # Tier 3: Accept gap
    shortfall = count - len(results)
    if shortfall > 0:
        print(f"  ⚠️ {category}: {shortfall}/{count} slots unfilled — no more tiers")
    
    return results


def run_pipeline(distribution=None, dry_run=False):
    """Main orchestrator. Returns (results_by_category, yield_pct)."""
    if distribution is None:
        distribution = DEFAULT_DISTRIBUTION
    
    processed = load_processed()
    results = {}
    total_target = sum(distribution.values())
    
    print("=" * 60)
    print(f"PIPELINE ORCHESTRATOR — {total_target} reviews across {len(distribution)} categories")
    if dry_run:
        print("  MODE: DRY RUN")
    print("=" * 60)
    
    # Shuffle category order so different ASINs get first crack each day
    cat_order = list(distribution.items())
    random.shuffle(cat_order)
    
    for category, count in cat_order:
        print(f"\n📦 {category.upper()} — target: {count}")
        cat_results = process_category(category, count, processed, dry_run)
        results[category] = cat_results
        print(f"  → Yield: {len(cat_results)}/{count}")
    
    # ── Summary ──
    total_yield = sum(len(r) for r in results.values())
    yield_pct = total_yield / total_target if total_target > 0 else 0
    
    print("\n" + "=" * 60)
    print(f"PIPELINE COMPLETE")
    print(f"  Target: {total_target} reviews")
    print(f"  Yield:  {total_yield} reviews ({yield_pct:.0%})")
    
    for category, cat_results in results.items():
        tiers = [r.get('_tier', '?') for r in cat_results]
        tier1_count = tiers.count(1)
        tier2_count = tiers.count(2)
        status = "✅" if len(cat_results) >= distribution[category] else "⚠️"
        print(f"  {status} {category}: {len(cat_results)}/{distribution[category]} (T1:{tier1_count} T2:{tier2_count})")
    
    # Yield alert
    if yield_pct < YIELD_ALERT_THRESHOLD and not dry_run:
        print(f"\n⚠️ YIELD ALERT: {yield_pct:.0%} < {YIELD_ALERT_THRESHOLD:.0%} threshold — notify ops group")
    
    print("=" * 60)
    
    return results, yield_pct


# ─── CLI ───────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without scraping")
    parser.add_argument("--category", "-c", help="Process single category only")
    parser.add_argument("--count", type=int, default=0, help="Count for single category")
    args = parser.parse_args()
    
    if args.category and args.count:
        distribution = {args.category: args.count}
        results, yield_pct = run_pipeline(distribution, args.dry_run)
    else:
        results, yield_pct = run_pipeline(dry_run=args.dry_run)
    
    # Save processed ASINs
    all_asins = []
    for cat, rs in results.items():
        for r in rs:
            asin = r.get('_asin') or r.get('asin', '')
            if asin and not asin.startswith('_'):
                all_asins.append(asin)
    
    processed = load_processed()
    processed.update(all_asins)
    with open(PROCESSED_ASINS_PATH, 'w') as f:
        json.dump(sorted(processed), f)
    
    # Exit 0 even for partial yield — caller handles reporting
    return 0


if __name__ == "__main__":
    sys.exit(main())
