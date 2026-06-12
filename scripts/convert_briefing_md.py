#!/usr/bin/env python3
"""Convert a briefing .md file to _data.json format that ink_review_writer expects."""
import sys, os, json, re

def parse_briefing_md(filepath):
    with open(filepath) as f:
        text = f.read()
    
    # ASIN from filename
    basename = os.path.basename(filepath)
    asin_match = re.search(r'_(B[A-Z0-9]{9})_', basename)
    asin = asin_match.group(1) if asin_match else ""
    
    # Title
    title_match = re.search(r'^# Product Briefing:\s*(.+)$', text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Unknown Product"
    
    # Price
    price_match = re.search(r'\|\s*Price\s*\|\s*\$?([\d,.]+)', text)
    price = float(price_match.group(1).replace(',', '')) if price_match else None
    
    # Rating
    rating_match = re.search(r'\|\s*Rating\s*\|\s*([\d.]+)/5', text)
    rating = float(rating_match.group(1)) if rating_match else None
    
    # Review count
    rc_match = re.search(r'Reviews Analyzed\s*\|\s*([\d,]+)\s+total', text)
    review_count = int(rc_match.group(1).replace(',', '')) if rc_match else 0
    
    # Image
    img_match = re.search(r'\|\s*Image\s*\|\s*(https?://[^\s|]+)', text)
    image_url = img_match.group(1) if img_match else ""
    
    # Extract review samples
    reviews = []
    review_pattern = re.compile(r'\*\*(\d+\.\s*\[([\d.]+)/5\]\s*[\d-]+)\s*[—–-]+\s*(.+?)\*\*\n>(.+?)(?=\n\*\*\d+|\Z)', re.DOTALL)
    
    # Alternative simpler pattern
    for block in re.split(r'\*\*\d+\.\s*\[(\d+\.?\d*)/5\]', text):
        pass
    
    # Just grab all review blocks
    review_blocks = re.finditer(
        r'\*\*\d+\.\s*\[([\d.]+)/5\]\s+([\d-]+)\s*[—–-]+\s*(.+?)\*\*\n>(.+?)(?=\n\*\*\d+|\Z)',
        text, re.DOTALL
    )
    
    for i, match in enumerate(review_blocks):
        if i >= 8:
            break
        rating_val = float(match.group(1))
        date = match.group(2)
        review_title = match.group(3).strip()
        body = match.group(4).strip()
        reviews.append({
            "title": review_title,
            "body": body,
            "rating": rating_val,
            "date": date
        })
    
    # If no reviews found with pattern, try simpler extraction
    if not reviews:
        # Extract between numbered list items
        lines = text.split('\n')
        in_reviews = False
        current_review = {}
        for line in lines:
            if line.startswith('## Review Samples'):
                in_reviews = True
                continue
            if in_reviews:
                rmatch = re.match(r'\*\*(\d+)\.\s+\[([\d.]+)/5\]\s+([\d-]+)\s*[—–-]+\s*(.+)\*\*', line)
                if rmatch:
                    if current_review.get('body'):
                        reviews.append(current_review)
                    current_review = {
                        "title": rmatch.group(4).strip(),
                        "rating": float(rmatch.group(2)),
                        "date": rmatch.group(3),
                        "body": ""
                    }
                elif line.startswith('>') and current_review:
                    current_review["body"] += line[1:].strip() + " "
                elif line.startswith('---') and current_review:
                    if current_review.get('body'):
                        reviews.append(current_review)
                    current_review = {}
        if current_review.get('body'):
            reviews.append(current_review)
    
    # Clean up review bodies
    for r in reviews:
        r['body'] = r.get('body', '').strip()
    
    # Also extract category from filepath
    cat_match = re.match(r'([a-z-]+)_', basename)
    category = cat_match.group(1) if cat_match else "general"
    
    return {
        "title": title,
        "asin": asin,
        "price": price,
        "rating": rating,
        "review_count": review_count,
        "image": image_url,
        "reviews": reviews,
        "_source": "converted_md"
    }

def main():
    for filepath in sys.argv[1:]:
        if not filepath.endswith('_briefing.md'):
            print(f"  ⛔ Skip (not briefing): {filepath}")
            continue
        
        data = parse_briefing_md(filepath)
        if not data or not data.get('title'):
            print(f"  ⛔ Failed to parse: {filepath}")
            continue
        
        basename = os.path.basename(filepath)
        parts = basename.split('_')
        category = parts[0]
        asin = parts[1]
        
        outpath = os.path.join(os.path.dirname(filepath), f"{category}_{asin}_data.json")
        with open(outpath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"  ✅ Converted: {basename} → {os.path.basename(outpath)}")
        print(f"     Title: {data['title'][:60]}...")
        print(f"     Price: {data['price']} | Rating: {data['rating']} | Reviews: {len(data['reviews'])}")

if __name__ == '__main__':
    main()
