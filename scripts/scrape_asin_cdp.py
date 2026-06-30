#!/usr/bin/env python3
"""
CDP-based Amazon product scraper using TradingView's headed browser.
Falls back when headed Chrome scraper is blocked.

Usage: python3 scripts/scrape_asin_cdp.py <ASIN> <category> [maxReviews]

Extracts: title, price, rating, review_count, image, features, description
Saves to: briefings/<category>_<ASIN>_data.json
"""

import sys, os, json, re, asyncio, time, random, subprocess
import websockets

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

CDP_PORT = 9222
MAX_RETRIES = 2

def get_navigable_ws_url():
    """Create a fresh browser tab via CDP and return its WebSocket URL.
    Using a fresh tab avoids Electron security restrictions on app-internal pages."""
    result = subprocess.run(
        ['curl', '-s', f'http://localhost:{CDP_PORT}/json'],
        capture_output=True, text=True, timeout=10
    )
    targets = json.loads(result.stdout)
    
    # Find the browser-level endpoint to create a new target
    browser_ws = None
    for t in targets:
        if t.get('type') == 'browser' and 'webSocketDebuggerUrl' in t:
            browser_ws = t['webSocketDebuggerUrl']
            break
    
    if browser_ws:
        # Create a fresh blank page target via the browser endpoint
        try:
            result = subprocess.run(
                ['curl', '-s', '-X', 'PUT', 
                 f'http://localhost:{CDP_PORT}/json/new?about:blank'],
                capture_output=True, text=True, timeout=10
            )
            new_target = json.loads(result.stdout)
            if 'webSocketDebuggerUrl' in new_target:
                return new_target['webSocketDebuggerUrl']
        except Exception as e:
            print(f"  ⚠️ Could not create new target: {e}")
    
    # Fallback: look for a page that's NOT a TradingView app page (file:///)
    for t in targets:
        url = t.get('url', '')
        if t.get('type') == 'page' and not url.startswith('file://'):
            return t['webSocketDebuggerUrl']
    
    # Last resort: any page
    for t in targets:
        if t.get('type') == 'page' and 'webSocketDebuggerUrl' in t:
            return t['webSocketDebuggerUrl']
    
    return None


async def scrape_asin(asin, max_retries=MAX_RETRIES):
    """Scrape a single ASIN via CDP."""
    ws_url = get_navigable_ws_url()
    if not ws_url:
        raise RuntimeError("No navigable page found — is TradingView running with CDP?")
    
    url = f"https://www.amazon.com/dp/{asin}"
    product_data = None
    
    for attempt in range(max_retries):
        try:
            async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
                # Random initial delay before navigation — human doesn't type at machine speed
                await asyncio.sleep(1 + random.uniform(0.5, 2.5))
                # Navigate to Amazon
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Page.navigate",
                    "params": {"url": url}
                }))
                
                # Wait for page to settle — randomized for human-like timing
                await asyncio.sleep(4 + random.uniform(1, 4))
                
                # Extract product data
                await ws.send(json.dumps({
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": """
                        (function() {
                            const data = {};
                            
                            // Title
                            const titleEl = document.querySelector('#productTitle');
                            data.title = titleEl ? titleEl.textContent.trim() : '';
                            
                            // Price - Amazon.sg or .com format
                            const priceEl = document.querySelector('.a-price .a-offscreen') ||
                                           document.querySelector('#priceblock_ourprice') ||
                                           document.querySelector('.a-price-whole');
                            data.price = priceEl ? priceEl.textContent.trim().replace(/[^0-9.,]/g, '') : '';
                            
                            // Rating
                            const ratingEl = document.querySelector('#acrPopover .a-icon-alt') ||
                                            document.querySelector('.a-icon-alt');
                            data.rating = ratingEl ? ratingEl.textContent.trim() : '';
                            
                            // Review count
                            const reviewEl = document.querySelector('#acrCustomerReviewText');
                            data.review_count = reviewEl ? reviewEl.textContent.trim() : '';
                            
                            // Image URL
                            const imgEl = document.querySelector('#landingImage') ||
                                         document.querySelector('#imgTagWrapperId img');
                            data.image = imgEl ? (imgEl.src || '') : '';
                            // Try to get hi-res version
                            if (imgEl && imgEl.dataset.oldHires) {
                                data.high_res_image = imgEl.dataset.oldHires;
                            }
                            
                            // Features / bullet points
                            const features = [];
                            document.querySelectorAll('#feature-bullets li span.a-list-item').forEach(el => {
                                const text = el.textContent.trim();
                                if (text && !text.startsWith('›')) features.push(text);
                            });
                            data.features = features;
                            
                            // Product description
                            const descEl = document.querySelector('#productDescription p') ||
                                          document.querySelector('#productDescription span');
                            data.description = descEl ? descEl.textContent.trim().slice(0, 1000) : '';
                            
                            // Brand
                            const brandEl = document.querySelector('#bylineInfo');
                            data.brand = brandEl ? brandEl.textContent.trim().replace('Brand: ', '') : '';
                            
                            // Actual URL after redirect
                            data.actual_url = window.location.href;
                            
                            // Availability
                            const availEl = document.querySelector('#availability span');
                            data.availability = availEl ? availEl.textContent.trim() : '';
                            
                            // Bestseller rank
                            const bsrEl = document.querySelector('#productDetails_detailBullets_sections1');
                            data.details_section = bsrEl ? bsrEl.textContent.trim().slice(0, 2000) : '';
                            
                            return JSON.stringify(data);
                        })()
                        """,
                        "returnByValue": True
                    }
                }))
                
                # Read the result
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        if data.get('id') == 2:
                            result_str = data.get('result', {}).get('result', {}).get('value', '{}')
                            product_data = json.loads(result_str)
                            break
                    except asyncio.TimeoutError:
                        break
                
                # Close the temporary tab
                await ws.send(json.dumps({
                    "id": 3,
                    "method": "Target.closeTarget",
                    "params": {}
                }))
                
                if product_data and product_data.get('title'):
                    return product_data
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 + random.uniform(1, 5))
                    
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 + random.uniform(1, 5))
    
    return product_data


def verify_image(url):
    """Check image URL is reachable."""
    if not url:
        return False, "no URL"
    if 'placeholder' in url.lower():
        return False, "placeholder"
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=15
        )
        code = result.stdout.strip()
        return code == "200", f"HTTP {code}"
    except Exception as e:
        return False, str(e)


def parse_price(price_str):
    """Extract numeric price from string like 'S$122.89' or '$49.99'."""
    if not price_str:
        return None
    # Remove currency symbols and commas
    cleaned = re.sub(r'[^0-9.]', '', price_str)
    try:
        return float(cleaned)
    except:
        return None


def parse_rating(rating_str):
    """Extract rating from '4.8 out of 5 stars'."""
    if not rating_str:
        return None
    match = re.search(r'([\d.]+)', rating_str)
    return float(match.group(1)) if match else None


def parse_review_count(rc_str):
    """Extract count from '(20,522)'."""
    if not rc_str:
        return 0
    cleaned = re.sub(r'[^0-9]', '', rc_str)
    return int(cleaned) if cleaned else 0


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scrape_asin_cdp.py <ASIN> <category>")
        sys.exit(1)
    
    asin = sys.argv[1]
    category = sys.argv[2]
    
    print(f"[CDP SCRAPE] {asin} ({category})")
    print(f"  Navigating to Amazon...")
    
    raw = asyncio.run(scrape_asin(asin))
    
    if not raw or not raw.get('title'):
        print("  ❌ FAILED: No product data extracted")
        sys.exit(1)
    
    # Parse extracted data
    price_val = parse_price(raw.get('price', ''))
    rating_val = parse_rating(raw.get('rating', ''))
    review_count_val = parse_review_count(raw.get('review_count', ''))
    image_url = raw.get('high_res_image') or raw.get('image', '')
    
    print(f"\n[PRODUCT] {raw['title'][:100]}")
    print(f"  Price:     ${price_val}" if price_val else "  Price:     N/A")
    print(f"  Rating:    {rating_val}/5 ({review_count_val:,} reviews)" if rating_val else "  Rating:    N/A")
    print(f"  Brand:     {raw.get('brand', 'N/A')}")
    print(f"  Image:     {'✅' if image_url else '❌'} {image_url[:80]}...")
    print(f"  Features:  {len(raw.get('features', []))} bullet points")
    
    # Verify image
    if image_url:
        ok, detail = verify_image(image_url)
        status = "✅" if ok else "⛔"
        print(f"  Image verify: {status} {detail}")
        if not ok:
            print("  ⛔ SKIPPED — image invalid")
            sys.exit(1)
    else:
        print("  ❌ SKIPPED — no image found")
        sys.exit(1)
    
    # Build output data in writer-compatible format
    data = {
        "title": raw['title'],
        "price": price_val,
        "rating": rating_val,
        "review_count": review_count_val,
        "image": image_url,
        "reviews": [],  # CDP scraper doesn't fetch reviews (yet)
        "features": raw.get('features', []),
        "description": raw.get('description', ''),
        "brand": raw.get('brand', ''),
        "asin": asin,
        "actual_url": raw.get('actual_url', ''),
    }
    
    # Save
    out_path = os.path.join(BRIEFINGS_DIR, f"{category}_{asin}_data.json")
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\n[DONE] Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
