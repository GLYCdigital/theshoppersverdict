#!/usr/bin/env python3
"""Convert scraped briefing data to JSON for ink_review_writer.py."""
import sys, os, json, re
from apify_client import ApifyClient

WORKSPACE = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict")
CONFIG = os.path.join(WORKSPACE, "scripts/.apify_config.json")
BRIEFINGS = os.path.join(WORKSPACE, "briefings")
TOKEN = json.load(open(CONFIG))["apify_token"]
client = ApifyClient(TOKEN)

asins = [
    ("coffee", "B0GYJCYF4D"),
    ("coffee", "B08133HX34"),
    ("coffee", "B086H458MP"),
    ("coffee", "B0DP5PRC35"),
    ("kitchen", "B0DPNK52B8"),
    ("kitchen", "B0CVNK5DQR"),
    ("kitchen", "B0CZPJ1833"),
    ("home-office", "B0F4KRS3Y6"),
    ("home-office", "B0BRCJL4MM"),
    ("home-office", "B00P8582AC"),
]

for cat, asin in asins:
    print(f"[{cat}] {asin}...", end=' ', flush=True)
    
    url = f'https://www.amazon.com/dp/{asin}'
    run = client.actor('R8WeJwLuzLZ6g4Bkk').call(run_input={
        'productUrls': [{'url': url}],
        'maxReviews': 8,
        'sort': 'helpful',
        'scrapeProductDetails': True,
    }, timeout_secs=90)
    
    dataset_id = run['defaultDatasetId']
    items = list(client.dataset(dataset_id).iterate_items())
    
    if not items:
        print('❌ empty - skipping')
        continue
    
    p = items[0].get('product', {})
    title = p.get('title', 'Unknown Product')
    price_val = p.get('price')
    if isinstance(price_val, dict):
        price = price_val.get('value')
    elif isinstance(price_val, (int, float)):
        price = float(price_val)
    else:
        price = None
    stars_raw = p.get('stars', '')
    rating = float(str(stars_raw).split()[0]) if stars_raw else None
    review_count = p.get('reviewsCount', None)
    hi_res = p.get('highResolutionImages', [])
    image_url = hi_res[0] if hi_res else p.get('thumbnailImage', '')
    
    # Extract review texts
    all_reviews = items[0].get('reviews', []) if 'reviews' in items[0] else []
    # Also check for reviews in the main items list
    review_texts = []
    for item in items:
        if 'reviewDescription' in item:
            review_texts.append(item.get('reviewDescription', ''))
        for r in item.get('reviews', []):
            if isinstance(r, dict) and 'reviewDescription' in r:
                review_texts.append(r.get('reviewDescription', ''))

    data = {
        'asin': asin,
        'title': title,
        'price': price,
        'rating': rating,
        'review_count': review_count,
        'image': image_url,
        'reviews': review_texts
    }
    
    # Image verification - HTTP 200 check
    status = None
    if image_url:
        import subprocess
        try:
            r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', image_url], 
                             capture_output=True, text=True, timeout=10)
            status = r.stdout.strip()
        except:
            status = '000'
    
    if status != '200' or 'placeholder' in str(image_url).lower():
        print(f'⛔ Image fail (HTTP {status}) — SKIPPING')
        outpath = os.path.join(BRIEFINGS, f'{cat}_{asin}_data_failed.json')
    else:
        print(f'✅ Image OK (HTTP {status}) — {title[:40]}')
        outpath = os.path.join(BRIEFINGS, f'{cat}_{asin}_data.json')
    
    with open(outpath, 'w') as f:
        json.dump(data, f, indent=2)

    # Also update the briefing markdown with verified image URL
    briefing_md = os.path.join(BRIEFINGS, f'{cat}_{asin}_briefing.md')
    if os.path.exists(briefing_md):
        with open(briefing_md) as f:
            md = f.read()
        # Update image line if exists
        if '| Image |' in md and image_url:
            md_new = re.sub(r'\| Image \|.*\|', f'| Image | {image_url} |', md)
            with open(briefing_md, 'w') as f:
                f.write(md_new)

print('\nDone!')
