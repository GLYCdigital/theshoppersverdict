#!/usr/bin/env python3
"""
Scrape a single ASIN via Apify actor R8WeJwLuzLZ6g4Bkk.
Usage: python3 scrape_asin.py <ASIN> [maxReviews]

Saves raw data to briefings/<category>_<ASIN>_data.json
Verifies image URL and reports result.
"""

import sys, os, json, re, subprocess, time
from apify_client import ApifyClient

WORKSPACE = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict")
config_path = os.path.join(WORKSPACE, "scripts/.apify_config.json")
API_TOKEN = json.load(open(config_path))["apify_token"]
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

def extract_asin(text):
    m = re.search(r'(B[A-Z0-9]{9})\b', text)
    return m.group(1) if m else None

def verify_image(url):
    """Check image URL is reachable and not a placeholder."""
    if not url:
        return False, "no URL provided"
    if 'placeholder' in url.lower():
        return False, "placeholder URL"
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=15
        )
        code = result.stdout.strip()
        if code == "200":
            return True, code
        return False, f"HTTP {code}"
    except Exception as e:
        return False, str(e)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_asin.py <ASIN> [maxReviews]")
        sys.exit(1)
    
    asin = extract_asin(sys.argv[1])
    if not asin:
        asin = sys.argv[1].strip()
        # validate format
        if not re.match(r'^B[A-Z0-9]{9}$', asin):
            print(f"ERROR: Invalid ASIN format: {asin}")
            sys.exit(1)
    
    max_reviews = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"[SCRAPE] Fetching {url} (maxReviews={max_reviews})...")
    
    client = ApifyClient(API_TOKEN)
    run = client.actor("R8WeJwLuzLZ6g4Bkk").call(run_input={
        "productUrls": [{"url": url}],
        "maxReviews": max_reviews,
        "sort": "helpful",
        "scrapeProductDetails": True,
    })
    
    dataset_id = run["defaultDatasetId"]
    items = list(client.dataset(dataset_id).iterate_items())
    
    if not items:
        print("ERROR: No data returned from Apify")
        sys.exit(1)
    
    # Extract product info
    p = items[0].get("product", {})
    title = p.get("title", "Unknown Product")
    
    # Image URL extraction
    hi_res = p.get("highResolutionImages", [])
    image_url = hi_res[0] if hi_res else None
    if not image_url:
        image_url = p.get("thumbnailImage", "")
    
    # Price
    price_val = p.get("price")
    if isinstance(price_val, dict):
        price = price_val.get("value")
    elif isinstance(price_val, (int, float)):
        price = float(price_val)
    else:
        price = None
    
    # Rating
    stars_raw = p.get("stars", "")
    if stars_raw is None: stars_raw = ""
    rating = float(str(stars_raw).split()[0]) if stars_raw else None
    
    review_count = p.get("reviewsCount", None)
    
    # Build output data
    reviews_data = []
    for item in items:
        review = item.get("review", {})
        if review:
            reviews_data.append({
                "reviewTitle": review.get("title", ""),
                "reviewDescription": review.get("text", ""),
                "ratingScore": review.get("rating", ""),
                "date": review.get("date", ""),
                "author": review.get("user", {}).get("name", "") if isinstance(review.get("user"), dict) else "",
                "verifiedPurchase": review.get("verified", False),
            })
    
    data = {
        "asin": asin,
        "url": url,
        "product": {
            "title": title,
            "price": price,
            "rating": rating,
            "reviewsCount": review_count,
            "imageUrl": image_url,
            "highResolutionImages": hi_res,
            "thumbnailImage": p.get("thumbnailImage", ""),
        },
        "reviews": reviews_data,
        "totalReviewsFetched": len(reviews_data),
        "scrapeTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    # Save data
    out_path = os.path.join(BRIEFINGS_DIR, f"coffee_{asin}_data.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\n[DATA] Saved: {out_path}")
    print(f"[PRODUCT] {title}")
    print(f"  Price:     ${price}" if price else "  Price:     N/A")
    print(f"  Rating:    {rating}/5" if rating else "  Rating:    N/A")
    print(f"  Reviews:   {review_count} total, {len(reviews_data)} sampled")
    print(f"  Image URL: {image_url}" if image_url else "  Image URL: None")
    
    # Verify image URL
    print(f"\n[IMAGE] Verifying: {image_url}")
    ok, detail = verify_image(image_url)
    if ok:
        print(f"  ✅ HTTP {detail} — image valid, saved")
    else:
        print(f"  ⛔ {detail} — SKIPPED (placeholder or unreachable)")
    
    print(f"\n[DONE] Scrape complete for {asin}")
    return data

if __name__ == "__main__":
    main()
