#!/usr/bin/env python3
"""Scrape ASINs from picked list, verify images, save as JSON data files."""
import sys, os, json, re, time, subprocess
from datetime import datetime
from apify_client import ApifyClient

WORKSPACE = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict")
CONFIG = os.path.join(WORKSPACE, "scripts/.apify_config.json")
BRIEFINGS_DIR = os.path.join(WORKSPACE, "briefings")

TOKEN = json.load(open(CONFIG))["apify_token"]
client = ApifyClient(TOKEN)

def verify_image(image_url):
    """Verify image URL returns 200 and isn't a placeholder."""
    if not image_url:
        print(f'    ❌ No image URL found')
        return False
    if 'placeholder' in image_url.lower():
        print(f'    ❌ Placeholder image: {image_url[:80]}')
        return False
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', image_url],
            capture_output=True, text=True, timeout=15
        )
        http_code = result.stdout.strip()
        if http_code == '200':
            print(f'    ✅ Image verified (HTTP 200)')
            return True
        else:
            print(f'    ❌ Image HTTP {http_code}: {image_url[:80]}')
            return False
    except Exception as e:
        print(f'    ❌ Image check failed: {e}')
        return False

def scrape_asin(asin, category):
    """Scrape a single ASIN via Apify."""
    url = f'https://www.amazon.com/dp/{asin}'
    print(f'\n🔍 [{category}] {asin}...', flush=True)
    
    # Dedup check
    r = subprocess.run(['python3', 'scripts/dedup_check.py', asin],
                       capture_output=True, text=True, cwd=WORKSPACE)
    if r.returncode == 1:
        print(f'  ⛔ SKIP — already reviewed (dedup exit 1)')
        print(f'     {r.stdout.strip()}')
        return None
    
    # Scrape via Apify
    print(f'  📡 Fetching from Apify...', end=' ', flush=True)
    try:
        run = client.actor('R8WeJwLuzLZ6g4Bkk').call(run_input={
            'productUrls': [{'url': url}],
            'maxReviews': 8,
            'sort': 'helpful',
            'scrapeProductDetails': True,
        }, timeout_secs=120)
    except Exception as e:
        print(f'❌ Apify error: {e}')
        return None
    
    dataset_id = run['defaultDatasetId']
    items = list(client.dataset(dataset_id).iterate_items())
    
    if not items:
        print('❌ No data returned')
        return None
    
    p = items[0].get('product', {})
    title = p.get('title', 'Unknown Product')
    print(f'✅ {title[:50]}')
    
    # Price
    price_val = p.get('price')
    if isinstance(price_val, dict):
        price = price_val.get('value')
    elif isinstance(price_val, (int, float)):
        price = float(price_val)
    else:
        price = None
    
    # Rating
    stars_raw = p.get('stars', '')
    rating = float(str(stars_raw).split()[0]) if stars_raw else None
    
    # Review count
    review_count = p.get('reviewsCount', None)
    
    # Image URL — try high res first
    hi_res = p.get('highResolutionImages', [])
    image_url = hi_res[0] if hi_res else None
    if not image_url:
        image_url = p.get('thumbnailImage', '')
    
    # Verify image
    print(f'  🖼️  Verifying image...', end=' ', flush=True)
    if not verify_image(image_url):
        print(f'  ⛔ SKIP {asin} — invalid image')
        return None
    
    # Extract review text
    reviews = []
    for item in items:
        r_text = item.get('reviewDescription', '') or ''
        r_title_text = item.get('reviewTitle', '') or ''
        r_rating = item.get('ratingScore', '')
        r_date = item.get('date', '')
        reviews.append({
            'reviewDescription': r_text,
            'reviewTitle': r_title_text,
            'ratingScore': r_rating,
            'date': r_date
        })
    
    # Build data JSON
    data = {
        'title': title,
        'price': price,
        'rating': rating,
        'review_count': review_count,
        'image': image_url,
        'reviews': [r['reviewDescription'] for r in reviews],
        'raw_reviews': reviews
    }
    
    # Save JSON
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    fpath = os.path.join(BRIEFINGS_DIR, f'{category}_{asin}_data.json')
    with open(fpath, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f'  💾 Saved: {category}_{asin}_data.json')
    return data


def main():
    picked_file = os.path.join(WORKSPACE, 'data', 'picked_asins.json')
    if not os.path.exists(picked_file):
        print(f'❌ No picked_asins.json found. Run pick step first.')
        sys.exit(1)
    
    with open(picked_file) as f:
        picked = json.load(f)
    
    successful = []
    failed = []
    
    for category, asins in picked.items():
        for asin in asins:
            result = scrape_asin(asin, category)
            if result:
                successful.append((category, asin))
            else:
                failed.append((category, asin))
            time.sleep(2)  # rate limit
    
    print(f'\n{"="*50}')
    print(f'✅ {len(successful)} scraped successfully')
    print(f'❌ {len(failed)} failed/skipped')
    for cat, a in successful:
        print(f'  ✅ {cat}/{a}')
    for cat, a in failed:
        print(f'  ⛔ {cat}/{a}')
    
    print(f'\nFiles in briefings/:')
    os.system(f'ls -la {BRIEFINGS_DIR}/ | grep _data.json')

if __name__ == '__main__':
    main()
