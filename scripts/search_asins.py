#!/usr/bin/env python3
"""
Search Amazon for top products using Apify Google/Amazon search
Finds real ASINs for kitchen, coffee, home-office categories
"""

import sys, os, json, re, time
from apify_client import ApifyClient

CONFIG_PATH = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict/scripts/.apify_config.json")

with open(CONFIG_PATH) as f:
    config = json.load(f)

TOKEN = config["apify_token"]
client = ApifyClient(TOKEN)

# Search queries — each will return ~20 results
SEARCHES = {
    "kitchen": [
        "air fryer best seller",
        "instant pot pressure cooker",
        "kitchen knife set top rated",
        "blender best seller amazon"
    ],
    "coffee": [
        "coffee maker best seller amazon",
        "espresso machine top rated",
        "coffee grinder best seller"
    ],
    "home-office": [
        "office chair best seller amazon",
        "monitor best seller amazon",
        "standing desk top rated",
        "webcam best seller amazon"
    ]
}

# Appears to — Search Actor (scrapes Google Shopping results)
SEARCH_ACTOR = "shanesizemore/google-shopping-scraper"

# Alternative: just use the Amazon Search Actor directly
AMAZON_SEARCH_ACTOR = "ajoymajumdar/amazon-search"

def search_amazon(query, max_results=10):
    """Search Amazon for products matching query"""
    print(f"  Searching: '{query}'...", end=" ", flush=True)
    try:
        run = client.actor(AMAZON_SEARCH_ACTOR).call(run_input={
            "searchTerm": query,
            "maxResults": max_results,
            "country": "US",
            "currency": "USD",
        }, timeout_secs=60)
        
        dataset_id = run['defaultDatasetId']
        items = list(client.dataset(dataset_id).iterate_items())
        asins = []
        for item in items:
            asin = item.get('asin') or item.get('ASIN', '')
            url = item.get('url', '') or item.get('productUrl', '')
            # Extract ASIN from URL
            if not asin and url:
                m = re.search(r'/dp/([A-Z0-9]{10})', url)
                if m:
                    asin = m.group(1)
            title = item.get('title', '') or item.get('name', '')
            if asin:
                asins.append((asin, title[:80]))
        
        print(f"{len(asins)} results")
        return asins
    except Exception as e:
        print(f"Error: {e}")
        return []

def main():
    results = {}
    
    for category, queries in SEARCHES.items():
        print(f"\n{'='*50}")
        print(f"Category: {category}")
        print(f"{'='*50}")
        category_asins = []
        
        for query in queries:
            items = search_amazon(query)
            category_asins.extend(items)
            time.sleep(2)  # Rate limit between searches
        
        # Deduplicate by ASIN
        seen = set()
        unique = []
        for asin, title in category_asins:
            if asin not in seen:
                seen.add(asin)
                unique.append((asin, title))
        
        results[category] = unique
        print(f"\n  Total unique ASINs for {category}: {len(unique)}")
        for asin, title in unique:
            print(f"    {asin}: {title}")
    
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    
    queue = {}
    for cat, items in results.items():
        asin_list = [a for a, t in items]
        queue[cat] = asin_list
        print(f"  {cat}: {len(asin_list)} ASINs")
    
    queue_path = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict/data/asin_queue.json")
    with open(queue_path, 'w') as f:
        json.dump(queue, f, indent=2)
    print(f"\n✅ Queue saved: {queue_path}")

if __name__ == '__main__':
    main()
