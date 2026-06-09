#!/usr/bin/env python3
"""
scrape_competitor_asins.py — Scrape ASINs from competitor review sites.
Uses Chrome-matching User-Agent to bypass bot detection.

Usage:
  python3 scripts/scrape_competitor_asins.py                # full run
  python3 scripts/scrape_competitor_asins.py --dry-run       # extract only
  python3 scripts/scrape_competitor_asins.py --list          # list sources
"""

import sys, os, json, re, subprocess, time
from pathlib import Path

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_PATH = os.path.join(WORKSPACE, "data", "asin_queue.json")

CURL_HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Cache-Control: no-cache",
]

SOURCES = [
    # ── Kitchen ──
    ("https://www.goodhousekeeping.com/cooking-tools/a62581556/best-kitchen-gear-coffee-tea-awards-2024/", "kitchen", "GoodHousekeeping Kitchen"),
    ("https://www.goodhousekeeping.com/home-products/g4284154/best-amazon-kitchen-gadgets/", "kitchen", "GoodHousekeeping Kitchen Gadgets"),
    ("https://www.eatingwell.com/best-kitchen-gadgets-on-amazon-2025-8776448", "kitchen", "EatingWell Kitchen Gadgets"),
    # ── Coffee ──
    ("https://www.goodhousekeeping.com/appliances/coffee-maker-reviews/g29070518/best-coffee-makers/", "coffee", "GoodHousekeeping Coffee"),
    ("https://www.epicurious.com/expert-advice/best-coffee-makers-2025", "coffee", "Epicurious Coffee Makers"),
    # ── Home Office ──
    ("https://www.goodhousekeeping.com/home-products/g32616824/best-home-office-supplies-amazon/", "home-office", "GoodHousekeeping Home Office"),
    ("https://www.techradar.com/news/best-home-office-tech", "home-office", "TechRadar Home Office"),
    # ── Home Improvement ──
    ("https://www.bobvila.com/articles/best-tools/", "home-improvement", "BobVila Tools"),
    ("https://www.popularmechanics.com/home/tools/g45826557/best-tools/", "home-improvement", "PopularMechanics Tools"),
    # ── Luxury Beauty ──
    ("https://www.goodhousekeeping.com/beauty/anti-aging/g5169/best-anti-aging-products/", "luxury-beauty", "GoodHousekeeping Beauty"),
    ("https://www.allure.com/shop/best-skin-care-products", "luxury-beauty", "Allure Skincare"),
    # ── Pet Supplies ──
    ("https://www.goodhousekeeping.com/life/pets/g62340002/best-pet-products-amazon/", "pet-supplies", "GoodHousekeeping Pets"),
    ("https://www.prevention.com/life/pets/g46841170/best-pet-products-on-amazon/", "pet-supplies", "Prevention Pet Products"),
]

ASIN_RE = re.compile(r'/dp/(B[A-Z0-9]{9})')
ASIN_ALT_RE = re.compile(r'/product/(B[A-Z0-9]{9})')
TAG_ASIN_RE = re.compile(r'/[dg]p/(B[A-Z0-9]{9})[?/"]')  # broader match


def fetch_page(url):
    """Fetch raw HTML via curl with Chrome headers."""
    try:
        cmd = ["curl", "-sL", "--max-time", "30", "--compressed"] + CURL_HEADERS + [url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        return result.stdout
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return ""


def extract_asins(html):
    """Extract unique ASINs from HTML."""
    asins = set()
    for match in TAG_ASIN_RE.finditer(html):
        asins.add(match.group(1))
    for match in ASIN_ALT_RE.finditer(html):
        asins.add(match.group(1))
    # Also try to find amazon.com/dp/ URLs without closing quote
    for m in re.finditer(r'amazon\.com/dp/(B[A-Z0-9]{9})', html):
        asins.add(m.group(1))
    return asins


def load_queue():
    with open(QUEUE_PATH) as f:
        return json.load(f)


def save_queue(q):
    with open(QUEUE_PATH, 'w') as f:
        json.dump(q, f, indent=2)


def add_asins_to_queue(asins, category, dry_run=False):
    """Add new ASINs to the queue category."""
    q = load_queue()
    if category not in q:
        q[category] = []
    
    existing = set(q[category]) | set(q.get('used', []))
    new = [a for a in asins if a not in existing]
    
    if dry_run:
        return new
    
    if new:
        q[category].extend(new)
        save_queue(q)
    
    return new


def main():
    dry_run = '--dry-run' in sys.argv
    
    if '--list' in sys.argv:
        print("Sources:")
        for url, cat, label in SOURCES:
            print(f"  [{cat}] {label}: {url}")
        return 0
    
    total_new = 0
    results = {}
    
    print("=" * 60)
    print("COMPETITOR ASIN SCRAPER")
    if dry_run:
        print("  MODE: DRY RUN (no queue changes)")
    print("=" * 60)
    
    for url, category, label in SOURCES:
        print(f"\n📡 {label} → {category}")
        
        html = fetch_page(url)
        if not html:
            print(f"   ❌ Empty response")
            continue
        
        asins = extract_asins(html)
        print(f"   Page: {len(html)} bytes → {len(asins)} ASINs")
        
        new = add_asins_to_queue(asins, category, dry_run)
        results[label] = {'found': len(asins), 'new': len(new), 'category': category}
        total_new += len(new)
        
        if new:
            print(f"   ✅ {len(new)} new: {', '.join(sorted(new)[:8])}")
            if len(new) > 8:
                print(f"      ... and {len(new)-8} more")
        else:
            print(f"   ⚠️ No new ASINs ({len(asins)} in page, all already queued)")
        
        if not dry_run:
            time.sleep(2)  # polite
    
    print("\n" + "=" * 60)
    print(f"TOTAL: {total_new} new ASINs added across {len(SOURCES)} sources")
    for label, r in results.items():
        status = "✅" if r['new'] > 0 else "—"
        print(f"  {status} {label}: {r['new']}/{r['found']} new → {r['category']}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
