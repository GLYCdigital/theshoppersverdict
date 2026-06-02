#!/usr/bin/env python3
"""Ink emergency scrape: 10 fresh ASINs from queue → briefings"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
from batch_scout import scrape, make_briefing

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
BRIEFINGS_DIR = os.path.join(WORKSPACE, "theshoppersverdict/briefings")
QUEUE = os.path.join(WORKSPACE, "theshoppersverdict/data/asin_queue.json")

with open(QUEUE) as f:
    q = json.load(f)

used = set(q.get('used', []))
# Pick 4 coffee, 3 kitchen, 3 home-office — all confirmed NEW
ASINS = {
    'coffee':   [a for a in q['coffee'] if a not in used][:4],
    'kitchen':   [a for a in q['kitchen'] if a not in used][:3],
    'home-office': [a for a in q['home-office'] if a not in used][:3],
}

os.makedirs(BRIEFINGS_DIR, exist_ok=True)
total = 0
for cat, asin_list in ASINS.items():
    for asin in asin_list:
        result = scrape(asin)
        if not result:
            print(f'  SKIPPED {asin}')
            continue
        briefing = make_briefing(
            result['asin'], result['title'], result['price'],
            result['rating'], result['review_count'],
            result['image_url'], result['items']
        )
        fpath = os.path.join(BRIEFINGS_DIR, f'{cat}_{asin}_briefing.md')
        with open(fpath, 'w') as f:
            f.write(briefing)
        total += 1
        print(f'  💾 {cat}/{asin} saved')
        time.sleep(2)  # rate limit courtesy

print(f'\n✅ {total}/10 briefings generated')
