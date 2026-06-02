#!/usr/bin/env python3
"""
Scrape a single Amazon ASIN via Apify actor R8WeJwLuzLZ6g4Bkk and save raw JSON.
Usage: python3 scrape_single_asin.py <ASIN> [maxReviews]
"""
import sys, os, json, re
from apify_client import ApifyClient

CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".apify_config.json")
with open(CONFIG_PATH) as f:
    API_TOKEN = json.load(f)["apify_token"]

def extract_asin(text):
    m = re.search(r'/(?:dp|product)/([A-Z0-9]{10})', text)
    if m: return m.group(1)
    m = re.search(r'(B[A-Z0-9]{9})\b', text)
    if m: return m.group(1)
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_single_asin.py <ASIN> [maxReviews]")
        sys.exit(1)

    asin = extract_asin(sys.argv[1])
    if not asin:
        print(f"ERROR: No ASIN found in: {sys.argv[1]}")
        sys.exit(1)

    max_reviews = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    url = f"https://www.amazon.com/dp/{asin}"
    print(f"[SCRAPE] Fetching {url} with maxReviews={max_reviews}...")

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

    print(f"[SCRAPE] Got {len(items)} items from Apify")

    # Build output structure
    product = items[0].get("product", items[0])
    
    result = {
        "asin": asin,
        "url": url,
        "scraped_at": run.get("finishedAt", ""),
        "product": product,
        "reviews": items,
        "raw_items": items
    }

    # Save JSON
    briefing_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "briefings")
    os.makedirs(briefing_dir, exist_ok=True)
    fpath = os.path.join(briefing_dir, f"kitchen_{asin}_data.json")
    with open(fpath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[SCRAPE] Raw data saved: {fpath}")

    # Extract image URL
    p = product if isinstance(product, dict) else {}
    hi_res = p.get("highResolutionImages", [])
    image_url = hi_res[0] if hi_res else None
    if not image_url:
        thumb = p.get("thumbnailImage", "") or ""
        if thumb:
            image_url = thumb

    print(f"\n[IMAGE] Extracted image URL: {image_url or 'NONE'}")

    # Output key info as JSON for pipeline consumption
    info = {
        "asin": asin,
        "title": p.get("title", "Unknown"),
        "image_url": image_url,
        "price": p.get("price"),
        "rating": p.get("stars"),
        "review_count": p.get("reviewsCount"),
        "data_path": fpath,
        "reviews_count": len(items)
    }
    print(f"\n[RESULT] {json.dumps(info)}")

if __name__ == "__main__":
    main()
