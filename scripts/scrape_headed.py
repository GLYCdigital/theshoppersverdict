#!/usr/bin/env python3
"""
Headed Chrome Amazon scraper — product data + reviews.
Uses system Chrome (channel='chrome') — NEVER headless, NEVER Playwright Chromium.

Usage: python3 scrape_headed.py <ASIN> <category> [--reviews N]
Saves: briefings/<category>_<ASIN>_data.json
"""

import sys, os, json, re, subprocess
from playwright.sync_api import sync_playwright

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

DEFAULT_MAX_REVIEWS = 8


def verify_image(url):
    if not url: return False, "no URL"
    if 'placeholder' in url.lower(): return False, "placeholder"
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                          capture_output=True, text=True, timeout=15)
        code = r.stdout.strip()
        return code == "200", f"HTTP {code}"
    except Exception as e:
        return False, str(e)


def parse_price(s):
    if not s: return None
    try: return float(re.sub(r'[^0-9.]', '', s))
    except: return None


def parse_rating(s):
    if not s: return None
    m = re.search(r'([\d.]+)', s)
    return float(m.group(1)) if m else None


def parse_review_count(s):
    if not s: return 0
    cleaned = re.sub(r'[^0-9]', '', s)
    return int(cleaned) if cleaned else 0


def scrape_all(asin, category, max_reviews=DEFAULT_MAX_REVIEWS):
    """Scrape product data and reviews from the product page."""
    url = f"https://www.amazon.com/dp/{asin}"
    
    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"  → Retry attempt {attempt}/{MAX_RETRIES}...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, channel='chrome')
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            
            # ── 1. Load product page ──
            print(f"  → Loading product page...")
            page.goto(url, timeout=30000, wait_until='load')
            page.wait_for_timeout(4000)
            
            # ── 1b. Handle Amazon bot check interstitial ──
            bot_check = page.evaluate('''() => {
                const body = document.body?.textContent || '';
                if (body.includes('Click the button below to continue') ||
                    body.includes('Enter the characters you see below') ||
                    document.querySelector('#captchacharacters')) {
                    return 'captcha';
                }
                if (body.includes('continue shopping') &&
                    (document.querySelector('input[type="submit"]') ||
                     document.querySelector('.a-button button, .a-button input'))) {
                    return 'bot_check';
                }
                return null;
            }''')
            if bot_check:
                print(f"  ⚠️  Bot check page detected ({bot_check}), clicking through...")
                clicked = page.evaluate('''() => {
                    const btns = [
                        document.querySelector('#captchacharacters + div input[type="submit"]'),
                        document.querySelector('input[type="submit"]'),
                        document.querySelector('.a-button button'),
                        document.querySelector('.a-button input'),
                        document.querySelector('form button[type="submit"]'),
                        [...document.querySelectorAll('a, button, input')].find(el =>
                            el.textContent?.toLowerCase().includes('continue') ||
                            el.textContent?.toLowerCase().includes('shopping') ||
                            el.value?.toLowerCase().includes('continue') ||
                            el.title?.toLowerCase().includes('continue'))
                    ];
                    for (const btn of btns) {
                        if (btn) { btn.click(); return true; }
                    }
                    return false;
                }''')
                if clicked:
                    print(f"  → Clicked continue button, waiting for navigation...")
                    page.wait_for_timeout(5000)
                    try:
                        page.wait_for_function('() => document.querySelector("#productTitle") !== null || document.body.textContent.includes("Click the button") === false', timeout=15000)
                    except:
                        pass
                    page.wait_for_timeout(2000)
                else:
                    print(f"  → No button found to click, trying page reload...")
                    page.goto(url, timeout=30000, wait_until='load')
                    page.wait_for_timeout(5000)
            
            # ── 2. Extract product data ──
            product = page.evaluate('''() => {
                const d = {};
                d.title = document.querySelector('#productTitle')?.textContent?.trim() || '';
                d.price = document.querySelector('.a-price .a-offscreen')?.textContent?.trim() || '';
                d.rating = document.querySelector('#acrPopover .a-icon-alt')?.textContent?.trim() ||
                            document.querySelector('.a-icon-alt')?.textContent?.trim() || '';
                d.review_count = document.querySelector('#acrCustomerReviewText')?.textContent?.trim() || '';
                const img = document.querySelector('#landingImage') || document.querySelector('#imgTagWrapperId img');
                d.image = img?.src || '';
                d.high_res = img?.dataset?.oldHires || '';
                d.features = [];
                document.querySelectorAll('#feature-bullets li span.a-list-item').forEach(el => {
                    const t = el.textContent.trim();
                    if (t && t.length > 5 && !t.startsWith('\u203a')) d.features.push(t);
                });
                d.brand = document.querySelector('#bylineInfo')?.textContent?.trim()?.replace('Brand: ','') || '';
                return d;
            }''')
            
            if not product.get('title'):
                print(f"  ❌ No product data — bot check? (attempt {attempt}/{MAX_RETRIES})")
                browser.close()
                continue
            
            product['url'] = page.url
            product['asin'] = asin
            
            # ── 3. Scroll to load reviews ──
            print(f"  → Scrolling to reviews...")
            for pct in [30, 50, 70, 85, 95]:
                page.evaluate(f'window.scrollTo(0, document.body.scrollHeight * {pct / 100})')
                page.wait_for_timeout(1200)
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(1500)
            
            if page.evaluate('document.querySelectorAll(\'[data-hook="review"]\').length') == 0:
                see_all = page.evaluate('''() => {
                    const links = document.querySelectorAll("a");
                    for (const a of links) {
                        if (a.textContent.toLowerCase().includes("review") &&
                            a.href.includes("product-reviews")) {
                            return a.href;
                        }
                    }
                    return null;
                }''')
                if see_all:
                    print(f"  → Following review link...")
                    page.goto(see_all, timeout=30000, wait_until='load')
                    page.wait_for_timeout(3000)
            
            # ── 4. Expand truncated reviews ──
            expand_count = page.evaluate('''() => {
                let count = 0;
                document.querySelectorAll('[data-hook="review"]').forEach(card => {
                    const btn = card.querySelector('[data-hook="reviewExpandButtonContainer"] button, .review-read-more-button');
                    if (btn) { btn.click(); count++; }
                });
                return count;
            }''')
            if expand_count:
                print(f"  → Expanded {expand_count} truncated reviews")
                page.wait_for_timeout(1000)
            
            # ── 5. Extract reviews ──
            reviews = page.evaluate('''() => {
                const reviews = [];
                document.querySelectorAll('[data-hook="review"]').forEach(card => {
                    const r = {};
                    r.title = card.querySelector('[data-hook="reviewTitle"]')?.textContent?.trim() || '';
                    r.body = card.querySelector('[data-hook="reviewText"]')?.textContent?.trim() || '';
                    r.body = r.body.replace(/Read moreRead less/g, '').replace(/Brief content visible, double tap to read full content\\.?/g, '').replace(/Full content visible, double tap to read brief content\\.?/g, '').trim();
                    r.rating = card.querySelector('[data-hook="review-star-rating"]')?.textContent?.trim() || '';
                    r.date = card.querySelector('[data-hook="review-date"]')?.textContent?.trim() || '';
                    r.author = card.querySelector('.a-profile-name')?.textContent?.trim() || '';
                    if (r.body || r.title) reviews.push(r);
                });
                return reviews;
            }''')
            
            print(f"  → Extracted {len(reviews)} reviews")
            reviews = reviews[:max_reviews]
            
            browser.close()
        
        return product, reviews
    
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts")
    return None


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scrape_headed.py <ASIN> <category> [--reviews N]")
        sys.exit(1)
    
    asin = sys.argv[1]
    category = sys.argv[2]
    max_reviews = DEFAULT_MAX_REVIEWS
    
    for i, arg in enumerate(sys.argv):
        if arg == '--reviews' and i + 1 < len(sys.argv):
            max_reviews = int(sys.argv[i + 1])
    
    print(f"[SCRAPE] {asin} ({category}) — up to {max_reviews} reviews")
    
    result = scrape_all(asin, category, max_reviews)
    if not result:
        print("  ❌ FAILED")
        sys.exit(1)
    
    product, reviews = result
    
    # Parse
    price_val = parse_price(product.get('price', ''))
    rating_val = parse_rating(product.get('rating', ''))
    review_count_val = parse_review_count(product.get('review_count', ''))
    image_url = product.get('high_res') or product.get('image', '')
    
    print(f"\n[PRODUCT] {product['title'][:100]}")
    print(f"  Price:     ${price_val}" if price_val else "  Price:     N/A")
    print(f"  Rating:    {rating_val}/5 ({review_count_val:,} total)" if rating_val else "  Rating:    N/A")
    print(f"  Image:     {'✅' if image_url else '❌'} {image_url[:80]}")
    print(f"  Features:  {len(product.get('features', []))} bullets")
    print(f"  Reviews:   {len(reviews)} scraped")
    
    # Verify image
    if image_url:
        ok, detail = verify_image(image_url)
        print(f"  Verify:    {'✅' if ok else '⛔'} {detail}")
        if not ok:
            print("  ⛔ SKIPPED — image invalid")
            sys.exit(1)
    else:
        print("  ❌ SKIPPED — no image")
        sys.exit(1)
    
    # Save
    data = {
        "title": product['title'],
        "price": price_val,
        "rating": rating_val,
        "review_count": review_count_val,
        "image": image_url,
        "reviews": reviews,
        "features": product.get('features', []),
        "brand": product.get('brand', ''),
        "asin": asin,
        "actual_url": product.get('url', ''),
    }
    
    out_path = os.path.join(BRIEFINGS_DIR, f"{category}_{asin}_data.json")
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\n[DONE] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
