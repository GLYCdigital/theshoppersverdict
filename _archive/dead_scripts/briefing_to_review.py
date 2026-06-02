#!/usr/bin/env python3
"""
Converts an Apify briefing markdown into a Hugo review file.
Usage: python3 briefing_to_review.py <briefing_file> [category]
"""

import sys, os, re, json
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
CONTENT = os.path.join(WORKSPACE, "theshoppersverdict/content")
BRIEFINGS = os.path.join(WORKSPACE, "theshoppersverdict/briefings")
PROCESSED = os.path.join(BRIEFINGS, "processed")
QUEUE = os.path.join(WORKSPACE, "theshoppersverdict/data/asin_queue.json")

def extract_asin(filename):
    m = re.search(r'([A-Z0-9]{10})_briefing', os.path.basename(filename))
    return m.group(1) if m else None

def lookup_category(asin):
    if not os.path.exists(QUEUE): 
        return "kitchen"
    with open(QUEUE) as f:
        q = json.load(f)
    for cat, items in q.items():
        if cat != "used" and asin in items:
            return cat
    return "kitchen"

def parse_briefing(filepath):
    with open(filepath) as f:
        text = f.read()
    
    title_m = re.search(r"# Product Briefing: (.+)", text)
    title = title_m.group(1).strip() if title_m else "Unknown Product"
    
    price = ""
    price_m = re.search(r'\|\s*Price.*?\$?([\d.]+)', text)
    if price_m: price = price_m.group(1)
    
    review_count = "0"
    rc_m = re.search(r'\|\s*Reviews.*?(\d[\d,]*)', text)
    if rc_m: review_count = rc_m.group(1)
    
    rating = "4.5"
    rating_m = re.search(r'\|\s*Rating.*?([\d.]+)', text)
    if rating_m: rating = rating_m.group(1)
    
    pros = []
    section = re.search(r'## Top Praise Themes(.*?)(?:##|$)', text, re.DOTALL)
    if section:
        for line in section.group(1).split('\n'):
            m = re.search(r'-\s+\*\*([^*]+)\*\*', line)
            if m: pros.append(m.group(1).strip().rstrip(':'))
    
    cons = []
    section = re.search(r'## Top Complaint Themes(.*?)(?:##|$)', text, re.DOTALL)
    if section:
        for line in section.group(1).split('\n'):
            m = re.search(r'-\s+\*\*([^*]+)\*\*', line)
            if m: cons.append(m.group(1).strip().rstrip(':'))
    
    excerpt = ""
    excerpt_m = re.search(r'\*\*\d+\.\s*\[.*?\].*?\*\*.*?\n> (.+?)(?:\n\n|\Z)', text, re.DOTALL)
    if excerpt_m:
        excerpt = excerpt_m.group(1).strip()[:200]
    
    return {
        "title": title,
        "price": price,
        "review_count": review_count.replace(",", ""),
        "rating": rating,
        "pros": pros[:5],
        "cons": cons[:5],
        "excerpt": excerpt,
    }

def generate_hugo(data, category, asin):
    slug = re.sub(r'[^a-z0-9]+', '-', data["title"].lower()).strip('-')
    parts = slug.split('-')
    slug = '-'.join(parts[:8])
    
    lines = []
    lines.append('---')
    lines.append(f'title: "{data["title"]}"')
    lines.append(f'date: {datetime.now().strftime("%Y-%m-%d")}')
    lines.append(f'verdict_score: 9.0')
    lines.append(f'review_count: {data["review_count"]}')
    lines.append(f'amazon_rating: {data["rating"]}')
    lines.append(f'amazon_url: "https://www.amazon.com/dp/{asin}/?tag=tsvglyc-20"')
    lines.append(f'amazon_image: ""')
    
    if data["pros"]:
        lines.append('pros:')
        for p in data["pros"]:
            lines.append(f'  - "{p}"')
    
    if data["cons"]:
        lines.append('cons:')
        for c in data["cons"]:
            lines.append(f'  - "{c}"')
    
    lines.append('---')
    lines.append('')
    lines.append(f'Based on analysis of {int(data["review_count"]):,} Amazon customer reviews, here is our verdict.')
    lines.append('')
    
    if data["excerpt"]:
        lines.append(data["excerpt"])
        lines.append('')
    
    lines.append('---')
    lines.append(f'*Auto-generated from Scout briefing. Full review pending Ink\'s edit.*')
    
    return '\n'.join(lines), slug

def main():
    if len(sys.argv) < 2:
        print('Usage: briefing_to_review.py <briefing_file>', file=sys.stderr)
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f'File not found: {filepath}', file=sys.stderr)
        sys.exit(1)
    
    asin = extract_asin(filepath)
    if not asin:
        print(f'Could not extract ASIN from: {filepath}', file=sys.stderr)
        sys.exit(1)
    
    category = sys.argv[2] if len(sys.argv) > 2 else lookup_category(asin)
    
    data = parse_briefing(filepath)
    content, slug = generate_hugo(data, category, asin)
    
    out_dir = os.path.join(CONTENT, category)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'{slug}.md')
    
    with open(out_file, 'w') as f:
        f.write(content)
    
    os.makedirs(PROCESSED, exist_ok=True)
    os.rename(filepath, os.path.join(PROCESSED, os.path.basename(filepath)))
    
    print(f'✅ {category}/{slug}.md — {data["title"][:50]}...')
    return 0

if __name__ == '__main__':
    sys.exit(main())
