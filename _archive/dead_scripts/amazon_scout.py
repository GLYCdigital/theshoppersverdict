#!/usr/bin/env python3
"""Amazon Scout - extracts product data from Amazon for review briefings."""

import sys, re, json, os, urllib.request, urllib.error
from datetime import datetime

HEADERS_LIST = [
    {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Accept-Language': 'en-US,en;q=0.9'},
    {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Accept-Language': 'en-US,en;q=0.9'},
    {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Accept-Language': 'en-US,en;q=0.9'},
    {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1', 'Accept-Language': 'en-US,en;q=0.9'},
]


def extract_asin(text):
    m = re.search(r'/(?:dp|product)/([A-Z0-9]{10})', text)
    if m: return m.group(1)
    m = re.search(r'(B[A-Z0-9]{9})\b', text)
    if m: return m.group(1)
    return None

def fetch(url):
    import time
    for headers in HEADERS_LIST:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode('utf-8', errors='replace')
                # Check we got real content (not a captcha stub)
                if len(html) > 5000 and ('productTitle' in html or 'buybox' in html or 'Amazon' in html):
                    return html
                # If first attempt got captcha-style content, try next agent
                continue
        except: continue
    return None

def g(html, pattern, group=1):
    m = re.search(pattern, html, re.DOTALL)
    return m.group(group).strip() if m else None

def extract_title(html):
    t = g(html, r'<span id="productTitle"[^>]*>(.*?)</span>')
    if t: return t
    t = g(html, r'<title>(.*?)</title>')
    if t: return re.sub(r'\s*[:|-]\s*Amazon\..*', '', t).strip()
    return 'Unknown'

def extract_image(html):
    m = re.search(r"data-a-dynamic-image='\{&quot;([^&]+\.jpg)", html)
    if m: return m.group(1)
    m = re.search(r'data-a-dynamic-image=\'{"([^"]+\.(?:jpg|png))', html)
    if m: return m.group(1)
    m = re.search(r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9._%+-]+\._AC_SL1500_\.jpg', html)
    if m: return m.group(0)
    m = re.search(r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9._%+-]+\.jpg', html)
    if m: return m.group(0)
    return None

def extract_rating(html):
    m = re.search(r'<span class="a-icon-alt"[^>]*>([\d.]+) out of 5', html)
    if m: return float(m.group(1))
    return None

def extract_review_count(html):
    m = re.search(r'<span id="acrCustomerReviewText"[^>]*>([\d,]+)', html)
    if m: return int(m.group(1).replace(',',''))
    m = re.search(r'(\d[\d,]*)\s*customer\s*(?:ratings|reviews)', html, re.I)
    if m: return int(m.group(1).replace(',',''))
    return None

def extract_price(html):
    m = re.search(r'<span class="a-price-whole"[^>]*>(\d[\d,]*)<', html)
    f = re.search(r'<span class="a-price-fraction"[^>]*>(\d+)<', html)
    if m:
        p = m.group(1)
        if f: p += '.' + f.group(1)
        return p
    return None

def extract_reviews(html, max_n=15):
    reviews = []
    blocks = re.findall(r'<div[^>]*data-hook="review"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
    for block in blocks[:max_n]:
        m = re.search(r'<span[^>]*data-hook="review-body"[^>]*>(.*?)</span>', block, re.DOTALL)
        if m:
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            text = text.replace('\n', ' ').replace('\r', '')
            if len(text) > 50:
                reviews.append(text)
    return reviews

def analyze(reviews):
    praise = {'Quality': ['quality','well made','durable','sturdy','solid','premium'],
              'Value': ['value','worth','price','affordable','reasonable'],
              'Ease of Use': ['easy','simple','intuitive','convenient','user-friendly'],
              'Performance': ['fast','quick','powerful','efficient','effective','great'],
              'Design': ['beautiful','sleek','modern','stylish','looks','design','compact','sleek']}
    complaints = {'Quality Issues': ['cheap','flimsy','broke','defective','poor quality','stopped'],
                 'Difficult to Use': ['complicated','confusing','difficult','frustrating'],
                 'Poor Performance': ['slow','weak','ineffective','disappointing'],
                 'Design Flaws': ['noisy','bulky','heavy','awkward'],
                 'Support/Warranty': ['support','warranty','return','refund']}
    pc = {k:0 for k in praise}
    cc = {k:0 for k in complaints}
    for r in reviews:
        rl = r.lower()
        for k,v in praise.items():
            for w in v:
                if w in rl: pc[k] += 1; break
        for k,v in complaints.items():
            for w in v:
                if w in rl: cc[k] += 1; break
    return pc, cc

def make_briefing(asin, data):
    lines = []
    lines.append('# Product Briefing: ' + data['title'])
    lines.append('')
    lines.append('**ASIN:** ' + asin)
    lines.append('**Date:** ' + datetime.now().strftime('%Y-%m-%d'))
    if data.get('image_url'): lines.extend(['', '**Image URL:** ' + data['image_url']])
    lines.extend(['', '## Quick Stats', '',
        '| Field | Value |', '|-------|-------|'])
    if data.get('rating'): lines.append('| Amazon Rating | ' + str(data['rating']) + '/5 ⭐ |')
    rc = data.get('review_count')
    if rc: lines.append('| Review Count | ' + f'{rc:,} |')
    if data.get('price'): lines.append('| Price | $' + data['price'] + ' |')
    lines.append('')

    if data.get('praise'):
        lines.append('## Top Praise Themes')
        sorted_p = sorted(data['praise'].items(), key=lambda x: x[1], reverse=True)
        for k,v in sorted_p:
            if v > 0:
                bars = '█' * min(v, 15)
                lines.append('- **' + k + ':** ' + bars + ' (' + str(v) + '/' + str(len(data.get('reviews',[]))) + ')')
        lines.append('')

    if data.get('complaints'):
        lines.append('## Top Complaint Themes')
        sorted_c = sorted(data['complaints'].items(), key=lambda x: x[1], reverse=True)
        for k,v in sorted_c:
            if v > 0:
                bars = '█' * min(v, 15)
                lines.append('- **' + k + ':** ' + bars + ' (' + str(v) + '/' + str(len(data.get('reviews',[]))) + ')')
        lines.append('')

    if data.get('reviews'):
        lines.append('## Review Samples')
        for i, r in enumerate(data['reviews'][:5], 1):
            lines.append(str(i) + '. ' + r[:200] + ('...' if len(r)>200 else ''))
        lines.append('')

    lines.append('---')
    lines.append('_Generated by Amazon Scout on ' + datetime.now().strftime('%Y-%m-%d %H:%M') + '_')
    return '\n'.join(lines)

def main():
    if len(sys.argv) < 2:
        print('Usage: python3 amazon_scout.py <ASIN_or_URL>'); sys.exit(1)
    asin = extract_asin(sys.argv[1])
    if not asin:
        print('ERROR: No ASIN found in:', sys.argv[1]); sys.exit(1)

    url = 'https://www.amazon.com/dp/' + asin
    print('[SCOUT] Fetching', url, '...')
    html = fetch(url)
    if not html:
        print('ERROR: Amazon blocked the request. Try a different ASIN.')
        sys.exit(1)

    print('[SCOUT] Extracting data...')
    data = {
        'title': extract_title(html),
        'image_url': extract_image(html),
        'rating': extract_rating(html),
        'review_count': extract_review_count(html),
        'price': extract_price(html),
    }

    print('[SCOUT] Extracting reviews...')
    data['reviews'] = extract_reviews(html)
    if data['reviews']:
        pc, cc = analyze(data['reviews'])
        data['praise'] = pc
        data['complaints'] = cc
    else:
        data['praise'] = {}
        data['complaints'] = {}

    print()
    print('='*60)
    print(data['title'])
    print('='*60)
    print('  ASIN:      ' + asin)
    print('  Rating:    ' + (str(data['rating']) + '/5 ⭐' if data['rating'] else 'N/A'))
    print('  Reviews:   ' + (f'{data["review_count"]:,}' if data['review_count'] else 'N/A'))
    rc2 = data['price']; print('  Price:     ' + ('$' + rc2 if rc2 else 'N/A'))
    print('  Image:     ' + (data['image_url'] or 'N/A'))
    print('  Parsed:    ' + str(len(data['reviews'])) + ' reviews')
    if data.get('praise'):
        print()
        print('  Top Praise:')
        for k,v in sorted(data['praise'].items(), key=lambda x:x[1], reverse=True):
            if v > 0: print('    - ' + k + ': ' + str(v) + '/' + str(len(data['reviews'])))
    print('='*60)
    print()

    briefing_dir = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict/briefings")
    os.makedirs(briefing_dir, exist_ok=True)
    fpath = os.path.join(briefing_dir, asin + '_briefing.md')
    with open(fpath, 'w') as f:
        f.write(make_briefing(asin, data))
    print('[SCOUT] Briefing saved:', fpath)

if __name__ == '__main__':
    main()
