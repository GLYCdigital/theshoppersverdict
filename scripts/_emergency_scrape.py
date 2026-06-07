#!/usr/bin/env python3
"""Emergency scrape — 10 fresh ASINs for Ink's 09:00 pipeline."""
import sys, os, json, subprocess, time
from apify_client import ApifyClient

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TOKEN = json.load(open(os.path.join(WORKSPACE, "scripts/.apify_config.json")))["apify_token"]
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

# Fresh ASINs not yet scraped (avoid the ones that returned empty)
BATCH = [
    ("coffee", "B0C4XJTK66"),
    ("coffee", "B0CN8CVHCY"),
    ("coffee", "B0C4SZDMGX"),
    ("coffee", "B0CX23V2Y2"),
    ("kitchen", "B0DSVC62VX"),
    ("kitchen", "B09G3KKFM3"),
    ("kitchen", "B08D3Y5H3M"),
    ("home-office", "B0CYZTFV25"),
    ("home-office", "B0CRX4NW38"),
    ("home-office", "B0CPWZ7S69"),
]

def verify_image(url):
    if not url:
        return False, "no URL"
    if 'placeholder' in url.lower():
        return False, "placeholder"
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=15
        )
        code = r.stdout.strip()
        return (code == "200"), f"HTTP {code}"
    except Exception as e:
        return False, str(e)

# Build all URLs
asin_map = {asin: cat for cat, asin in BATCH}
product_urls = [{"url": f"https://www.amazon.com/dp/{asin}"} for _, asin in BATCH]

print(f"[EMERGENCY] Scraping {len(product_urls)} products via Apify...")
client = ApifyClient(API_TOKEN)

try:
    run = client.actor("R8WeJwLuzLZ6g4Bkk").call(run_input={
        "productUrls": product_urls,
        "maxReviews": 8,
        "sort": "helpful",
        "scrapeProductDetails": True,
    }, timeout_secs=180)
except Exception as e:
    print(f"⛔ Apify call failed: {e}")
    sys.exit(1)

dataset_id = run["defaultDatasetId"]
items = list(client.dataset(dataset_id).iterate_items())
print(f"[APIFY] {len(items)} items returned from dataset")

# Group items by ASIN
import re
from collections import defaultdict

grouped = defaultdict(list)
for item in items:
    item_url = item.get("url", "") or item.get("product", {}).get("url", "")
    asin_match = re.search(r'(B[A-Z0-9]{9})', item_url)
    if asin_match:
        grouped[asin_match.group(1)].append(item)

# Fallback
if not grouped:
    for item in items:
        p = item.get("product", {})
        pasin = p.get("asin", "") or ""
        if pasin:
            grouped[pasin].append(item)
        else:
            link = p.get("link", "") or p.get("url", "")
            am = re.search(r'(B[A-Z0-9]{9})', link)
            if am:
                grouped[am.group(1)].append(item)

print(f"[GROUPED] ASINs found: {list(grouped.keys())}")

success = 0
skipped = 0

for cat, asin in BATCH:
    items_for_asin = grouped.get(asin, [])
    if not items_for_asin:
        print(f"\n⛔ [{cat}] {asin}: No items — SKIPPING")
        skipped += 1
        continue

    p = items_for_asin[0].get("product", {})
    title = p.get("title", "Unknown Product")

    hi_res = p.get("highResolutionImages", [])
    image_url = hi_res[0] if hi_res else None
    if not image_url:
        image_url = p.get("thumbnailImage", "")

    print(f"\n[{cat.upper()}] {asin}: {title[:80]}")
    print(f"  Image: {image_url}")

    ok, detail = verify_image(image_url)
    if not ok:
        print(f"  ⛔ IMAGE FAIL: {detail} — SKIPPING")
        skipped += 1
        continue
    print(f"  ✅ Image valid: {detail}")

    price_val = p.get("price")
    if isinstance(price_val, dict):
        price = price_val.get("value")
    elif isinstance(price_val, (int, float)):
        price = float(price_val)
    else:
        price = None

    stars_raw = p.get("stars", "")
    if stars_raw is None: stars_raw = ""
    rating = float(str(stars_raw).split()[0]) if stars_raw else None
    review_count = p.get("reviewsCount", None)

    reviews_data = []
    for item in items_for_asin:
        review = item.get("review", {})
        rt = review.get("title", "") or item.get("reviewTitle", "")
        rd = review.get("text", "") or item.get("reviewDescription", "")
        rs = review.get("rating", "") or item.get("ratingScore", "")
        if rt or rd:
            reviews_data.append({
                "reviewTitle": rt,
                "reviewDescription": rd,
                "ratingScore": rs,
                "date": review.get("date", "") or item.get("date", ""),
                "author": (review.get("user", {}) or {}).get("name", "") if isinstance(review.get("user"), dict) else item.get("userId", ""),
                "verifiedPurchase": review.get("verified", False) or item.get("isVerified", False),
            })

    data = {
        "asin": asin,
        "url": f"https://www.amazon.com/dp/{asin}",
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
    success += 1

print(f"\n{'='*60}")
print(f"EMERGENCY SCRAPE: {success} scraped, {skipped} skipped")
