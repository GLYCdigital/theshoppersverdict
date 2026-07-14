#!/usr/bin/env python3
"""
fetch_bestsellers.py — Browse Amazon bestseller pages and extract live ASINs.

Usage:
  python3 scripts/fetch_bestsellers.py                          # all categories
  python3 scripts/fetch_bestsellers.py --category coffee        # single category
  python3 scripts/fetch_bestsellers.py --enqueue               # add to queue
"""

import sys, os, json, time, random, re
from playwright.sync_api import sync_playwright

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_PATH = os.path.join(WORKSPACE, "data", "asin_queue.json")

# Amazon Best Sellers URL paths (navigable from /Best-Sellers/zgbs/)
# Format: https://www.amazon.com/Best-Sellers-{NAME}/zgbs/{CODE}/
AMAZON_BESTSELLER_URLS = {
    "coffee":        "https://www.amazon.com/Best-Sellers-Coffee/zgbs/coffee-makers-substitutions/",
    "kitchen":       "https://www.amazon.com/Best-Sellers-Kitchen-Dining/zgbs/kitchen/",
    "home-office":   "https://www.amazon.com/Best-Sellers-Office-Products/zgbs/office-products/",
    "home-improvement": "https://www.amazon.com/Best-Sellers-Tools-Home-Improvement/zgbs/hi/",
    "luxury-beauty": "https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty/",
    "pet-supplies":  "https://www.amazon.com/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/",
    "furniture":     "https://www.amazon.com/Best-Sellers-Home-Kitchen/zgbs/home-garden/",
    "patio-lawn-garden": "https://www.amazon.com/Best-Sellers-Patio-Lawn-Garden/zgbs/lawn-garden/",
    "sports-fitness":"https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/",
    "toys-games":    "https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games/",
}


def extract_asins(page):
    """Extract ASINs from the current bestseller page."""
    asins = page.evaluate("""() => {
        const results = new Set();
        // data-asin attribute on product cards
        document.querySelectorAll('[data-asin]').forEach(el => {
            const a = el.getAttribute('data-asin');
            if (a && a.length === 10 && a[0] === 'B') results.add(a);
        });
        // Any /dp/ link (bestseller cards often don't have data-asin)
        document.querySelectorAll('a[href*="/dp/"]').forEach(el => {
            const m = el.href.match(/\\/dp\\/(B[A-Z0-9]{9})/);
            if (m) results.add(m[1]);
        });
        // P13n cards
        document.querySelectorAll('.p13n-sc-uncoverable-faceout, .zg-grid-general-faceout, .a-section.a-spacing-small').forEach(el => {
            const links = el.querySelectorAll('a[href*="/dp/"]');
            for (const link of links) {
                const m = link.href.match(/\\/dp\\/(B[A-Z0-9]{9})/);
                if (m) results.add(m[1]);
            }
        });
        return [...results];
    }""")
    return asins


def fetch_category(category, page, max_asins=50):
    """Fetch bestseller ASINs for one category."""
    url = AMAZON_BESTSELLER_URLS.get(category)
    if not url:
        print(f"  ❌ Unknown category: {category}")
        return []
    print(f"  → {category}: {url}")
    
    page.goto(url, timeout=60000, wait_until="load")
    time.sleep(3 + random.uniform(1, 3))
    
    asins = extract_asins(page)
    print(f"  → Found {len(asins)} ASINs")
    
    # Try clicking "next page" a couple times for more
    for page_num in range(2, 4):
        if len(asins) >= max_asins:
            break
        next_btn = page.evaluate("""() => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                if (a.textContent.toLowerCase().includes('next page') ||
                    a.getAttribute('aria-label')?.toLowerCase().includes('next')) {
                    return a.href;
                }
            }
            return null;
        }""")
        if next_btn:
            page.goto(next_btn, timeout=60000, wait_until="load")
            time.sleep(3 + random.uniform(1, 2))
            more = extract_asins(page)
            asins = list(set(asins + more))
            print(f"  → Page {page_num}: {len(more)} more ASINs (total {len(asins)})")
        else:
            break
    
    return asins[:max_asins]


def load_queue():
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return {cat: [] for cat in AMAZON_BESTSELLER_URLS} | {"used": []}


def save_queue(data):
    with open(QUEUE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch Amazon bestseller ASINs")
    parser.add_argument("--category", "-c", help="Single category only")
    parser.add_argument("--enqueue", "-e", action="store_true", help="Add to queue")
    parser.add_argument("--prepend", "-p", action="store_true", help="Prepend to front of queue instead of append")
    parser.add_argument("--count", type=int, default=50, help="Max ASINs per category")
    args = parser.parse_args()
    
    categories = [args.category] if args.category else list(AMAZON_BESTSELLER_URLS.keys())
    
    print("=" * 60)
    print("AMAZON BESTSELLER SCRAPER")
    print(f"  Categories: {', '.join(categories)}")
    print("=" * 60)
    
    all_results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        time.sleep(1 + random.uniform(0.5, 2))
        
        for cat in categories:
            asins = fetch_category(cat, page, args.count)
            all_results[cat] = asins
            print()
        
        browser.close()
    
    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    total = 0
    for cat, asins in all_results.items():
        print(f"  {cat}: {len(asins)} ASINs")
        for a in asins[:5]:
            print(f"    https://www.amazon.com/dp/{a}")
        if len(asins) > 5:
            print(f"    ... and {len(asins)-5} more")
        total += len(asins)
    print(f"\n  Total: {total} ASINs")
    
    # Enqueue
    if args.enqueue:
        queue = load_queue()
        used = set(queue.get("used", []))
        added_total = 0
        for cat, asins in all_results.items():
            existing = set(queue.get(cat, []))
            new_asins = [a for a in asins if a not in existing and a not in used]
            if new_asins:
                if args.prepend:
                    queue[cat] = new_asins + queue.get(cat, [])
                    mode = "prepended"
                else:
                    queue[cat] = queue.get(cat, []) + new_asins
                    mode = "appended"
                added_total += len(new_asins)
                print(f"  📥 {mode} {len(new_asins)} new {cat} ASINs")
        save_queue(queue)
        print(f"\n✅ {added_total} new ASINs queued")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
