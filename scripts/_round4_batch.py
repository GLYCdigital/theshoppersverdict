#!/usr/bin/env python3
"""Round 4 — home-office ASINs to reach 10 total."""
import sys, os, json, subprocess, time
from apify_client import ApifyClient

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TOKEN = json.load(open(os.path.join(WORKSPACE, "scripts/.apify_config.json")))["apify_token"]
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

# Pick more home-office ASINs from the queue
BATCH = [
    ("home-office", "B0CBN6PL3Z"),
    ("home-office", "B0D45HFQLK"),
    ("home-office", "B0DBLBJ2HG"),
    ("home-office", "B01MDLWVRQ"),
    ("home-office", "B0CYZTFV25"),
    ("home-office", "B0CRX4NW38"),
    ("home-office", "B0CPWZ7S69"),
    ("home-office", "B0CY5P4YMV"),
    ("home-office", "B0CXD5VSXK"),
]

def verify_image(url):
    if not url:
        return False, "no URL"
    if 'placeholder' in url.lower():
        return False, "placeholder"
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                          capture_output=True, text=True, timeout=15)
        code = r.stdout.strip()
        return (code == "200"), f"HTTP {code}"
    except Exception as e:
        return False, str(e)

def scrape_one(cat, asin):
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"\n{'='*60}")
    print(f"[{cat.upper()}] Scraping {asin}...")
    
    client = ApifyClient(API_TOKEN)
    try:
        run = client.actor("R8WeJwLuzLZ6g4Bkk").call(run_input={
            "productUrls": [{"url": url}],
            "maxReviews": 8,
            "sort": "helpful",
            "scrapeProductDetails": True,
        })
    except Exception as e:
        print(f"  ⛔ Apify call failed: {e}")
        return None
    
    dataset_id = run["defaultDatasetId"]
    items = list(client.dataset(dataset_id).iterate_items())
    
    if not items:
        print(f"  ⛔ No data returned")
        return None
    
    p = items[0].get("product", {})
    title = p.get("title", "Unknown")
    
    hi_res = p.get("highResolutionImages", [])
    image_url = hi_res[0] if hi_res else None
    if not image_url:
        image_url = p.get("thumbnailImage", "")
    
    print(f"  Product: {title[:80]}")
    print(f"  Image:   {image_url}")
    
    ok, detail = verify_image(image_url)
    if not ok:
        print(f"  ⛔ IMAGE FAIL: {detail} — SKIPPING")
        return None
    print(f"  ✅ Image valid: {detail}")
    
    price_val = p.get("price")
    if isinstance(price_val, dict):
        price = price_val.get("value")
    elif isinstance(price_val, (int, float)):
        price = float(price_val)
    else:
        price = None
    
    stars_raw = p.get("stars", "")
    rating = float(str(stars_raw).split()[0]) if stars_raw else None
    review_count = p.get("reviewsCount", None)
    
    reviews_data = []
    for item in items:
        rt = item.get("reviewTitle", "")
        rd = item.get("reviewDescription", "")
        if rt or rd:
            reviews_data.append({
                "reviewTitle": rt,
                "reviewDescription": rd,
                "ratingScore": item.get("ratingScore", ""),
                "date": item.get("date", ""),
                "author": item.get("userId", ""),
                "verifiedPurchase": item.get("isVerified", False),
            })
    
    data = {
        "asin": asin,
        "url": url,
        "category": cat,
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
    
    out_path = os.path.join(BRIEFINGS_DIR, f"{cat}_{asin}_data.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"  💾 Saved: {out_path} ({len(reviews_data)} reviews)")
    return out_path

success = 0
skipped = 0
results = []
TARGET = 7  # We need 7 more to reach 10 total

for cat, asin in BATCH:
    if success >= TARGET:
        print(f"\nTarget ({TARGET}) reached — stopping")
        break
    path = scrape_one(cat, asin)
    if path:
        success += 1
        results.append((cat, asin, path))
    else:
        skipped += 1
    time.sleep(1.5)

print(f"\n{'='*60}")
print(f"ROUND 4 COMPLETE: {success} scraped, {skipped} skipped")
for cat, asin, path in results:
    print(f"  ✅ {cat}/{asin} → {path}")
