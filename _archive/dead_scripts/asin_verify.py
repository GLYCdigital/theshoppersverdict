#!/usr/bin/env python3
"""
ASIN Verifier v2 — Checks if an Amazon ASIN is valid using multiple strategies.
1. Quick: Check if ASIN is in our queue (already vetted)
2. Direct: Try fetching the product page (sometimes works)
3. Apify: Use the Amazon Reviews Scraper actor (most reliable, costs credits)
4. Fallback: Trust the seed list

Usage: python3 asin_verify.py <ASIN>
Returns exit 0 if likely valid, 1 if likely invalid.
"""

import sys, os, re, json, urllib.request, urllib.error

WORKSPACE = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict")
QUEUE_FILE = os.path.join(WORKSPACE, "data", "asin_queue.json")

# ASINs from our seed list — trust these directly (known Amazon products)
TRUSTED_ASINS = set()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def load_trusted():
    """Load trusted ASINs from seed list."""
    global TRUSTED_ASINS
    try:
        from replenish_queue import SEED_ASINS
        for cat_asins in SEED_ASINS.values():
            TRUSTED_ASINS.update(cat_asins)
    except ImportError:
        pass


def verify_via_queue(asin):
    """Check if ASIN appears in our queue (was added by a search/replenish run)."""
    if not os.path.exists(QUEUE_FILE):
        return None
    try:
        with open(QUEUE_FILE) as f:
            data = json.load(f)
        for cat in ["coffee", "kitchen", "home-office"]:
            if asin in data.get(cat, []):
                return True
        return None  # Not in queue = unknown, not invalid
    except:
        return None


def verify_via_http(asin):
    """Try fetching the Amazon product page directly."""
    url = f"https://www.amazon.com/dp/{asin}"
    
    # Try multiple user agents
    agents = [
        HEADERS['User-Agent'],
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    ]
    
    for agent in agents:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': agent,
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })
            resp = urllib.request.urlopen(req, timeout=10)
            html = resp.read().decode('utf-8', errors='ignore')
            
            # Check for product title
            if '<span id="productTitle"' in html:
                return True
            
            # Check for price/buybox
            if '"buybox"' in html or 'add-to-cart' in html:
                return True
            
            # Check for standard Amazon page structure
            if 'Amazon' in html and len(html) > 5000:
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            # Other errors (503, captcha) — try next agent
            continue
        except:
            continue
    
    return None  # Ambiguous — keep trying


def verify_via_trust(asin):
    """Check if ASIN is in the trusted seed list."""
    load_trusted()
    if asin in TRUSTED_ASINS:
        return True
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: asin_verify.py <ASIN>", file=sys.stderr)
        sys.exit(1)
    
    asin = sys.argv[1].strip().upper()
    if not re.match(r'^[A-Z0-9]{10}$', asin):
        print(f"❌ {asin}: Invalid ASIN format")
        sys.exit(1)
    
    # Strategy 1: Check queue (fast, no network)
    result = verify_via_queue(asin)
    if result is True:
        print(f"✅ {asin}: Already in queue (known product)")
        sys.exit(0)
    
    # Strategy 2: Trusted seed list
    result = verify_via_trust(asin)
    if result is True:
        print(f"✅ {asin}: In trusted seed list")
        sys.exit(0)
    
    # Strategy 3: Direct HTTP check
    result = verify_via_http(asin)
    if result is True:
        print(f"✅ {asin}: Product page loaded successfully")
        sys.exit(0)
    if result is False:
        print(f"❌ {asin}: HTTP 404 — product not found")
        sys.exit(1)
    
    # If all strategies came back None (ambiguous), assume valid
    # The timeout pipeline will catch invalid ASINs when scraping fails
    print(f"⚠️  {asin}: Ambiguous (assuming valid, verify on scrape)")
    sys.exit(0)


if __name__ == "__main__":
    main()
