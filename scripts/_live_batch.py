#!/usr/bin/env python3
"""Scrape 10 fresh live ASINs from Amazon for Ink's 09:00 pipeline."""
import sys, os, json, subprocess, time, re
from apify_client import ApifyClient

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TOKEN = json.load(open(os.path.join(WORKSPACE, "scripts/.apify_config.json")))["apify_token"]
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

# Fresh ASINs from Amazon live search/bestseller pages
BATCH = [
    ("coffee", "B000FFRZ26"),
    ("coffee", "B002YI2IG0"),
    ("coffee", "B00DWKEHU4"),
    ("coffee", "B014W1C2VM"),
    ("kitchen", "B0CBM682SQ"),
    ("kitchen", "B08QXJ31WR"),
    ("kitchen", "B08CZDYNF7"),
    ("home-office", "B0B9CDZ9BL"),
    ("home-office", "B0BMTPC44X"),
    ("home-office", "B079ZV4V3C"),
]

def verify_image(url):
    if not url: return False, "no URL"
    if 'placeholder' in url.lower(): return False, "placeholder"
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                          capture_output=True, text=True, timeout=15)
        return (r.stdout.strip() == "200"), f"HTTP {r.stdout.strip()}"
    except Exception as e: return False, str(e)

# Quick pre-check all ASINs
print("=== Pre-checking ASINs ===")
valid_asins = []
for cat, asin in BATCH:
    code = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", 
         f"https://www.amazon.com/dp/{asin}",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
         "--max-time", "10"],
        capture_output=True, text=True, timeout=12
    ).stdout.strip()
    status = "✅" if code == "200" else f"⛔ ({code})"
    print(f"  {status} {cat}/{asin}")
    if code == "200":
        valid_asins.append((cat, asin))

if not valid_asins:
    print("❌ No valid ASINs found!")
    sys.exit(1)

print(f"\nProceeding with {len(valid_asins)} live ASINs\n")

product_urls = [{"url": f"https://www.amazon.com/dp/{asin}"} for _, asin in valid_asins]
asin_map = {asin: cat for cat, asin in valid_asins}

print(f"[APIFY] Scraping {len(product_urls)} products...")
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
print(f"[APIFY] {len(items)} items returned")

# Group by ASIN
from collections import defaultdict
grouped = defaultdict(list)
for item in items:
    item_url = item.get("url", "") or item.get("product", {}).get("url", "")
    m = re.search(r'(B[A-Z0-9]{9})', item_url)
    if m:
        grouped[m.group(1)].append(item)
    else:
        p = item.get("product", {})
        pasin = p.get("asin", "")
        if pasin:
            grouped[pasin].append(item)

print(f"[GROUPED] ASINs found: {list(grouped.keys())}")

success = 0
failed = 0

for cat, asin in valid_asins:
    items_for_asin = grouped.get(asin, [])
    if not items_for_asin:
        print(f"\n⛔ [{cat}] {asin}: No items — FAILED")
        failed += 1
        continue

    p = items_for_asin[0].get("product", {})
    title = p.get("title", "Unknown Product")
    
    hi_res = p.get("highResolutionImages", [])
    image_url = hi_res[0] if hi_res else p.get("thumbnailImage", "")

    print(f"\n[{cat.upper()}] {asin}: {title[:80]}")
    print(f"  Image: {image_url}")

    ok, detail = verify_image(image_url)
    if not ok:
        print(f"  ⛔ IMAGE: {detail} — FAILED")
        failed += 1
        continue

    print(f"  ✅ Image: {detail}")

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
    for item in items_for_asin:
        review = item.get("review", {})
        rt = review.get("title", "") or item.get("reviewTitle", "")
        rd = review.get("text", "") or item.get("reviewDescription", "")
        if rt or rd:
            reviews_data.append({
                "reviewTitle": rt, "reviewDescription": rd,
                "ratingScore": review.get("rating", "") or item.get("ratingScore", ""),
                "date": review.get("date", "") or item.get("date", ""),
                "author": (review.get("user", {}) or {}).get("name", "") if isinstance(review.get("user"), dict) else item.get("userId", ""),
                "verifiedPurchase": review.get("verified", False) or item.get("isVerified", False),
            })

    data = {
        "asin": asin, "url": f"https://www.amazon.com/dp/{asin}", "category": cat,
        "product": {
            "title": title, "price": price, "rating": rating,
            "reviewsCount": review_count, "imageUrl": image_url,
            "highResolutionImages": hi_res, "thumbnailImage": p.get("thumbnailImage", ""),
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

print(f"\n{'='*50}")
print(f"RESULT: {success} scraped, {failed} failed")
