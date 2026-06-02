#!/usr/bin/env python3
"""Scrape all 10 products from Amazon via Apify and save image URLs."""
from apify_client import ApifyClient
import json, os

# CREDENTIALS REDACTED — use .apify_config.json instead
client = ApifyClient('APIFY_API_TOKEN_REDACTED')

PRODUCTS = [
    ('Aeropress Go', 'B07YVL8SF3', 'coffee'),
    ('Keurig K-Mini Plus', 'B07DR89BR6', 'coffee'),
    ('Nespresso Vertuo Next', 'B0CFFSNQNT', 'coffee'),
    ('Ninja Specialty Coffee Maker', 'B07PFLM2LK', 'coffee'),
    ('Autonomous ErgoChair 2', 'B0FL2F3W34', 'home-office'),
    ('FlexiSpot Standing Desk Converter', 'B0B2W8VBQX', 'home-office'),
    ('FlexiSpot Standing Desk', 'B07H2WGFQN', 'home-office'),
    ('Instant Pot Duo 7-in-1', 'B08WCLJ7JG', 'kitchen'),
    ('Ninja Professional Plus Blender', 'B0BMGSZMW9', 'kitchen'),
    ('Vitamix E310 Explorian', 'B0758JHZM3', 'kitchen'),
]

results = {}
for name, asin, cat in PRODUCTS:
    print(f'{name} ({asin})...', end=' ', flush=True)
    run = client.actor('R8WeJwLuzLZ6g4Bkk').call(run_input={
        'productUrls': [{'url': f'https://www.amazon.com/dp/{asin}'}],
        'maxReviews': 3,
        'scrapeProductDetails': True,
    }, timeout_secs=60)
    dataset_id = run['defaultDatasetId']
    items = list(client.dataset(dataset_id).iterate_items())
    if items and items[0].get('product'):
        p = items[0]['product']
        title = p.get('title', '?')
        hi_res = p.get('highResolutionImages', [])
        img = hi_res[0] if hi_res else p.get('thumbnailImage', '')
        price_val = p.get('price', {})
        price = price_val.get('value', '') if isinstance(price_val, dict) else str(price_val)
        rating = str(p.get('stars', '')).split()[0] if p.get('stars') else ''
        reviews = p.get('reviewsCount', 0)
        print(f'✅ img found' if img else '❌ no image')
        results[name] = {'asin': asin, 'category': cat, 'title': title, 'image': img, 
                        'price': price, 'rating': rating, 'review_count': reviews}
    else:
        print('❌ no data')
        results[name] = {'asin': asin, 'category': cat, 'title': '', 'image': '', 
                        'price': '', 'rating': '', 'review_count': 0}

out = os.path.expanduser('~/.openclaw/workspace/ink/product_data.json')
with open(out, 'w') as f:
    json.dump(results, f, indent=2)
print(f'\n💾 Saved to {out}')

for name, d in results.items():
    img_status = '✅' if d.get('image') else '❌'
    print(f'{name:35s} | {d["asin"]} | img={img_status} | price={d.get("price","?")} | {d.get("image","")[:70]}')
