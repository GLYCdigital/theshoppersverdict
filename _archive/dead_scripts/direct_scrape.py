#!/usr/bin/env python3
"""Direct Amazon scrape from local machine (bypasses Apify proxy issues).
Fetches product pages directly and generates briefings with review data."""
import os, json, re, time, sys
from datetime import datetime
import requests
from bs4 import BeautifulSoup

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
BRIEFINGS_DIR = os.path.join(WORKSPACE, "theshoppersverdict/briefings")
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def fetch_product(asin):
    url = f'https://www.amazon.com/dp/{asin}'
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Title
    title_el = soup.select_one('#productTitle')
    title = title_el.get_text(strip=True) if title_el else 'Unknown'
    
    # Price
    price_el = soup.select_one('.a-price .a-offscreen')
    price = None
    if price_el:
        ptext = price_el.get_text(strip=True).replace('$','').replace(',','')
        try: price = float(ptext)
        except: pass
    
    # Rating
    rating_el = soup.select_one('.a-icon-alt')
    rating = None
    if rating_el:
        rtext = rating_el.get_text(strip=True).split()[0]
        try: rating = float(rtext)
        except: pass
    
    # Image
    img_el = soup.select_one('#landingImage')
    image_url = ''
    if img_el and img_el.get('src'):
        image_url = img_el['src']
    
    # Review count
    rev_el = soup.select_one('#acrCustomerReviewText')
    review_count = None
    if rev_el:
        rtext = rev_el.get_text(strip=True).replace(',','').split()[0]
        try: review_count = int(rtext)
        except: pass
    
    # Fetch review page too
    review_url = f'https://www.amazon.com/product-reviews/{asin}/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews&sortBy=helpful'
    try:
        rr = requests.get(review_url, headers=HEADERS, timeout=30)
        rsoup = BeautifulSoup(rr.text, 'html.parser')
        reviews = []
        for rev in rsoup.select('[data-hook="review"]')[:8]:
            rtitle_el = rev.select_one('[data-hook="review-title"]')
            rtitle = rtitle_el.get_text(strip=True) if rtitle_el else ''
            rbody_el = rev.select_one('[data-hook="review-body"]')
            rbody = rbody_el.get_text(strip=True) if rbody_el else ''
            rrating_el = rev.select_one('[data-hook="review-star-rating"]')
            rrating = rrating_el.get_text(strip=True).split()[0] if rrating_el else '?'
            rdate_el = rev.select_one('[data-hook="review-date"]')
            rdate = rdate_el.get_text(strip=True) if rdate_el else ''
            if rbody:
                reviews.append({
                    'title': rtitle,
                    'body': rbody,
                    'rating': rrating,
                    'date': rdate,
                })
    except Exception as e:
        print(f'  ⚠ Review page failed: {e}')
        reviews = []
    
    return {
        'asin': asin,
        'title': title,
        'price': price,
        'rating': rating,
        'review_count': review_count,
        'image_url': image_url,
        'reviews': reviews,
    }

# Pick 10 fresh ASINs
QUEUE = os.path.join(WORKSPACE, "theshoppersverdict/data/asin_queue.json")
with open(QUEUE) as f:
    q = json.load(f)

content_asins = set()
content_dir = os.path.join(WORKSPACE, "theshoppersverdict/content")
for cat in ['coffee', 'kitchen', 'home-office']:
    cat_dir = os.path.join(content_dir, cat)
    if not os.path.isdir(cat_dir): continue
    for fname in os.listdir(cat_dir):
        if not fname.endswith('.md'): continue
        with open(os.path.join(cat_dir, fname)) as f:
            text = f.read()
            m = re.search(r'/dp/([A-Z0-9]{10})', text)
            if m: content_asins.add(m.group(1))

PICK = {
    'coffee':   [a for a in q['coffee'] if a not in content_asins][:4],
    'kitchen':   [a for a in q['kitchen'] if a not in content_asins][:3],
    'home-office': [a for a in q['home-office'] if a not in content_asins][:3],
}

print(f'🎯 Picking from queue:')
for cat, asins in PICK.items():
    print(f'  {cat}: {asins}')

for cat, asin_list in PICK.items():
    for asin in asin_list:
        print(f'\n📦 Fetching {cat}/{asin}...', flush=True)
        try:
            p = fetch_product(asin)
        except Exception as e:
            print(f'  ❌ Failed: {e}')
            continue
        
        title = p['title']
        price = p.get('price')
        rating = p.get('rating')
        review_count = p.get('review_count')
        image_url = p.get('image_url', '')
        reviews = p.get('reviews', [])
        
        print(f'  ✅ {title[:60]}')
        print(f'  💰 ${price}' if price else '  💰 N/A')
        print(f'  ⭐ {rating}' if rating else '  ⭐ N/A')
        print(f'  📊 {review_count} reviews' if review_count else '  📊 N/A')
        print(f'  📝 {len(reviews)} reviews scraped')
        
        # Generate briefing
        lines = []
        lines.append(f'# Product Briefing: {title}')
        lines.append('')
        lines.append(f'**ASIN:** {asin}  |  **Date:** {datetime.now().strftime("%Y-%m-%d")}')
        lines.append('')
        lines.append('## Quick Stats')
        lines.append('')
        lines.append('| Field | Value |')
        lines.append('|-------|-------|')
        lines.append(f'| Price | ${price}' if price else '| Price | N/A |')
        if rating: lines.append(f'| Rating | {rating}/5 ⭐ |')
        if review_count: lines.append(f'| Reviews Analyzed | {review_count:,} total, {len(reviews)} sampled |')
        if image_url: lines.append(f'| Image | {image_url} |')
        lines.append('')
        
        if reviews:
            lines.append('## Review Samples')
            lines.append('')
            for i, r in enumerate(reviews[:5], 1):
                text = r.get('body', '')
                rtitle = r.get('title', '')
                rtg = r.get('rating', '?')
                dt = r.get('date', '')
                lines.append(f'**{i}. [{rtg}/5] {dt}** — {rtitle}')
                lines.append(f'> {text[:400]}{"..." if len(text) > 400 else ""}')
                lines.append('')
        
        lines.append('---')
        lines.append(f'*Briefing generated by Ink direct scrape on {datetime.now().strftime("%Y-%m-%d %H:%M")}*')
        
        fpath = os.path.join(BRIEFINGS_DIR, f'{cat}_{asin}_briefing.md')
        with open(fpath, 'w') as f:
            f.write('\n'.join(lines))
        print(f'  💾 Saved: {fpath}')
        
        time.sleep(3)  # Rate limit

print(f'\n{"="*50}')
print(f'✅ Briefings generated')
