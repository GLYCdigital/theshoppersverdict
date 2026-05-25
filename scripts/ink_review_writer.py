#!/usr/bin/env python3
"""
ink_review_writer.py — Generates full Hugo review content from scraped JSON data.
Reads briefing JSON files, writes markdown review files with complete frontmatter.

Usage: python3 scripts/ink_review_writer.py briefings/*_data.json
"""
import sys, os, json, re, glob
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict")
CONTENT = os.path.join(WORKSPACE, "content")
QUEUE = os.path.join(WORKSPACE, "data", "asin_queue.json")
VERDICT_THRESHOLDS = {
    (4.5, 5.0): 4.6,
    (4.0, 4.4): 4.2,
    (3.5, 3.9): 3.7,
    (0, 3.4): 3.3,
}

def get_verdict(amazon_rating):
    for (lo, hi), score in VERDICT_THRESHOLDS.items():
        if lo <= amazon_rating <= hi:
            return score
    return round(amazon_rating, 1)

def make_slug(title):
    """Generate a URL slug from product title."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    # Trim to a reasonable length
    words = slug.split('-')
    if len(words) > 12:
        words = words[:12]
    slug = '-'.join(words) + '-review'
    return slug

def extract_keywords(title, category, product_type):
    """Generate SEO keywords."""
    keywords = []
    # Product name as keyword
    parts = re.sub(r'[^a-zA-Z0-9 ]', '', title).split()
    if len(parts) >= 2:
        keywords.append(' '.join(parts[:3]).lower() + ' review')
    # Category keywords
    cat_keywords = {
        'coffee': ['coffee maker review', 'espresso machine', 'best coffee gear'],
        'kitchen': ['kitchen appliance review', 'best kitchen gadget'],
        'home-office': ['home office review', 'office chair', 'desk accessory'],
    }
    keywords.extend(cat_keywords.get(category, []))
    return keywords[:5]

def make_faq(title, pros, cons):
    """Generate 3 FAQ questions based on pros/cons."""
    faqs = []
    if pros:
        faqs.append({
            'question': f'What do users like most about the {title.split("Review")[0].strip()}?',
            'answer': f'Users consistently praise the {pros[0].lower()}. Many reviews highlight this as the standout feature.'
        })
    if cons:
        faqs.append({
            'question': f'What are the common complaints about this product?',
            'answer': f'The most frequent criticism is the {cons[0].lower()}. Some users also mention {cons[1].lower() if len(cons) > 1 else "it could be better in other areas"}.'
        })
    faqs.append({
        'question': f'Is this product worth buying?',
        'answer': 'Based on thousands of Amazon reviews, this product delivers solid value for its price point. It has strong ratings and satisfied customers, though it\'s not perfect for everyone.'
    })
    return faqs

def write_review(data, category, asin):
    """Write a full review markdown file."""
    title = data.get('title', 'Unknown Product').strip()
    price = data.get('price')
    rating = data.get('rating', '')
    review_count = data.get('review_count', '')
    image_url = data.get('image', '')
    reviews = data.get('reviews', [])
    
    # Parse price
    price_str = ''
    if isinstance(price, dict):
        price_str = str(price.get('value', ''))
    elif isinstance(price, (int, float)):
        price_str = f'{price:.2f}' if price % 1 else str(int(price))
    elif price:
        price_str = str(price).replace('$', '').strip()
    
    # Parse rating
    try:
        amazon_rating = float(rating) if rating else 4.0
    except:
        amazon_rating = 4.0
    
    # Parse review count
    try:
        rc = int(review_count) if review_count else 0
    except:
        rc = 0
    
    # Generate content
    verdict = get_verdict(amazon_rating)
    slug = make_slug(title)
    seo_title = title.replace('Review', '').strip()[:50] + ' Review: Verdict | TSV'
    meta_desc = f'Our full {title.lower()}. Read real Amazon customer insights, pros, cons, and our verdict. {rc:,}+ reviews analyzed.'
    meta_desc = meta_desc[:157] + '...' if len(meta_desc) > 160 else meta_desc
    
    # Clean product name for alt text
    alt_text = title.replace('"', '').replace("'", '').strip()[:120]
    
    # Generate SEO description for keywords
    keywords = extract_keywords(title, category, '')
    
    # Generate pros/cons from review analysis
    praise_keywords = {
        'quality': ['quality', 'well made', 'durable', 'sturdy', 'solid', 'premium', 'built'],
        'value': ['value', 'worth', 'price', 'affordable', 'reasonable', 'bargain'],
        'ease': ['easy', 'simple', 'intuitive', 'convenient', 'user-friendly', 'setup'],
        'performance': ['fast', 'quick', 'powerful', 'efficient', 'effective', 'great', 'works'],
        'design': ['beautiful', 'sleek', 'modern', 'stylish', 'looks', 'compact', 'sleek'],
    }
    complaint_keywords = {
        'quality': ['cheap', 'flimsy', 'broke', 'defective', 'poor', 'stopped', 'cheaply'],
        'difficult': ['complicated', 'confusing', 'difficult', 'frustrating', 'hard'],
        'performance': ['slow', 'weak', 'ineffective', 'disappointing', 'noisy'],
        'design': ['bulky', 'heavy', 'awkward', 'large', 'uncomfortable'],
    }
    
    praise_counts = {k: 0 for k in praise_keywords}
    complaint_counts = {k: 0 for k in complaint_keywords}
    
    for review_text in reviews:
        rl = review_text.lower()
        for k, words in praise_keywords.items():
            if any(w in rl for w in words):
                praise_counts[k] += 1
        for k, words in complaint_keywords.items():
            if any(w in rl for w in words):
                complaint_counts[k] += 1
    
    # Generate pros/cons list
    pros = {
        'quality': 'Solid build quality that holds up to regular use',
        'value': 'Excellent value for the price point',
        'ease': 'Easy to set up and use right out of the box',
        'performance': 'Strong performance that meets expectations',
        'design': 'Attractive design that looks good in any setting',
    }
    cons = {
        'quality': 'Some users report durability concerns over time',
        'difficult': 'Setup can be confusing for some users',
        'performance': 'Performance may not satisfy power users',
        'design': 'Larger footprint than expected',
    }
    
    pro_list = []
    con_list = []
    for k, v in sorted(praise_counts.items(), key=lambda x: -x[1]):
        if v > 0 and len(pro_list) < 3:
            pro_list.append(pros.get(k, k.replace('_', ' ').title()))
    if not pro_list:
        pro_list = ['Good overall value', 'Does what it\'s supposed to do']
    
    for k, v in sorted(complaint_counts.items(), key=lambda x: -x[1]):
        if v > 0 and len(con_list) < 2:
            con_list.append(cons.get(k, k.replace('_', ' ').title()))
    if not con_list:
        con_list = ['May not suit everyone\'s needs']
    
    # Generate FAQ
    faqs = make_faq(title, pro_list, con_list)
    
    # Generate review body
    body_parts = []
    
    body_parts.append(f"If you're shopping for a {slug.replace('-review', '').replace('-', ' ')}, the {title.split('Review')[0].strip()} has likely crossed your radar. Based on an analysis of thousands of Amazon customer reviews, here's what you need to know before buying.")
    
    body_parts.append(f"## The Good")
    if pro_list:
        body_parts.append(f"The most common praise for this product centers on {pro_list[0].lower()}. Users consistently mention this as a highlight, with many noting it exceeds expectations for the price. {pro_list[1].lower() if len(pro_list) > 1 else 'Build quality'} is another frequently mentioned positive.")
    
    body_parts.append(f"## The Not-So-Good")
    if con_list:
        body_parts.append(f"No product is perfect, and the main complaints involve {con_list[0].lower()}. {con_list[1].lower() if len(con_list) > 1 else 'Some users also mentioned minor issues'} that are worth considering before purchase.")
    
    body_parts.append(f"## Who Should Buy It")
    body_parts.append(f"This product is ideal for anyone looking for a reliable option in this category without overspending. If the key features align with your needs, you'll likely be satisfied.")
    
    body_parts.append(f"## Who Should Skip It")
    body_parts.append(f"If the drawbacks mentioned above are dealbreakers for you, or if you need features beyond what this product offers, consider looking at higher-end alternatives.")
    
    body_parts.append(f"## Bottom Line")
    body_parts.append(f"With a {amazon_rating}/5 rating from over {rc:,} Amazon reviews, the {title.split('Review')[0].strip()} is a solid choice for most buyers. It delivers on its core promises and represents good value. Just be aware of the limitations before clicking buy.")
    
    body = '\n\n'.join(body_parts)
    
    # Build frontmatter
    lines = ['---']
    lines.append(f'title: "{title}"')
    lines.append(f'seo_title: "{seo_title[:57]}"')
    lines.append(f'meta_description: "{meta_desc[:157]}"')
    lines.append(f'slug: "{slug}"')
    lines.append(f'image_alt: "{alt_text}"')
    lines.append('keywords:')
    for kw in keywords[:5]:
        lines.append(f'  - "{kw}"')
    lines.append(f'verdict_score: {verdict}')
    lines.append('faq:')
    for faq in faqs:
        lines.append(f'  - question: "{faq["question"]}"')
        # Escape any double quotes in the answer
        answer = faq['answer'].replace('"', "'")
        lines.append(f'    answer: "{answer}"')
    lines.append(f'date: {datetime.now().strftime("%Y-%m-%d")}')
    lines.append(f'price: {price_str}' if price_str else 'price: null')
    lines.append(f'review_count: {rc}')
    lines.append(f'amazon_rating: {amazon_rating}')
    lines.append(f'amazon_url: "https://www.amazon.com/dp/{asin}/?tag=tsvglyc-20"')
    lines.append(f'amazon_image: "{image_url}"')
    lines.append('pros:')
    for p in pro_list:
        p_safe = p.replace('"', "'")
        lines.append(f'  - "{p_safe}"')
    lines.append('cons:')
    for c in con_list:
        c_safe = c.replace('"', "'")
        lines.append(f'  - "{c_safe}"')
    lines.append('---')
    lines.append('')
    lines.append(body)
    
    # Ensure content directory exists
    cat_dir = os.path.join(CONTENT, category)
    os.makedirs(cat_dir, exist_ok=True)
    
    # Write file
    filepath = os.path.join(cat_dir, f'{slug}.md')
    
    # Check for existing file
    if os.path.exists(filepath):
        print(f'  ⚠️  EXISTS: {filepath} — not overwriting')
        return None
    
    with open(filepath, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    
    print(f'  ✅ Written: {filepath}')
    return filepath

def mark_used(asin):
    """Mark ASIN as used in the queue."""
    if os.path.exists(QUEUE):
        with open(QUEUE) as f:
            q = json.load(f)
        used = set(q.get('used', []))
        used.add(asin)
        q['used'] = sorted(used)
        with open(QUEUE, 'w') as f:
            json.dump(q, f, indent=2)

def main():
    data_files = [f for f in sys.argv[1:] if f.endswith('_data.json')]
    if not data_files:
        print('Usage: python3 ink_review_writer.py briefings/*_data.json')
        sys.exit(1)
    
    written = 0
    for filepath in data_files:
        basename = os.path.basename(filepath)
        # Parse category and ASIN from filename: coffee_B07YQLF481_data.json
        parts = basename.split('_')
        if len(parts) < 2:
            print(f'  ⛔ Invalid filename: {basename}')
            continue
        category = parts[0]
        asin = parts[1]
        
        if not os.path.exists(filepath):
            print(f'  ⛔ Not found: {filepath}')
            continue
        
        with open(filepath) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f'  ⛔ Invalid JSON: {basename} — {e}')
                continue
        
        result = write_review(data, category, asin)
        if result:
            mark_used(asin)
            written += 1
            # Move data file to processed
            processed_dir = os.path.join(WORKSPACE, 'briefings', 'processed')
            os.makedirs(processed_dir, exist_ok=True)
            os.rename(filepath, os.path.join(processed_dir, basename))
    
    print(f'\n✅ {written} reviews written')
    return written

if __name__ == '__main__':
    main()
