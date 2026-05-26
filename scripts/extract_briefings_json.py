#!/usr/bin/env python3
"""Extract data from existing briefing markdown files and create JSON for review writer."""
import os, re, json, subprocess

BRIEFINGS = os.path.expanduser("~/.openclaw/workspace/theshoppersverdict/briefings")

briefing_files = [f for f in os.listdir(BRIEFINGS) if f.endswith('_briefing.md')]

converted = 0
failed = 0

for bf in sorted(briefing_files):
    # Parse: coffee_B0GYJCYF4D_briefing.md
    parts = bf.split('_')
    if len(parts) < 2:
        continue
    cat = parts[0]
    asin = parts[1]
    
    path = os.path.join(BRIEFINGS, bf)
    with open(path) as f:
        content = f.read()
    
    # Extract fields from markdown
    title_match = re.search(r'# Product Briefing:\s*(.+?)(?:\n|$)', content)
    title = title_match.group(1).strip() if title_match else 'Unknown Product'
    
    price_match = re.search(r'\|\s*Price\s*\|\s*\$?([\d.]+)', content)
    price = float(price_match.group(1)) if price_match else None
    
    rating_match = re.search(r'\|\s*Rating\s*\|\s*([\d.]+)/5', content)
    rating = float(rating_match.group(1)) if rating_match else None
    
    review_count_match = re.search(r'\|\s*Reviews Analyzed\s*\|\s*([\d,]+)\s*total', content)
    review_count_str = review_count_match.group(1).replace(',', '') if review_count_match else None
    review_count = int(review_count_str) if review_count_str else None
    
    image_match = re.search(r'\|\s*Image\s*\|\s*(.+?)\s*\|', content)
    image_url = image_match.group(1).strip() if image_match else ''
    
    # Extract review samples
    review_section = content.split('## Review Samples')[-1] if '## Review Samples' in content else ''
    reviews = []
    # Find all quoted review texts
    review_texts = re.findall(r'> (.+)', review_section)
    for t in review_texts:
        t = t.replace('"', "'").strip()
        if t and not t.startswith('*') and len(t) > 20:
            reviews.append(t)
    
    # Image verification
    status = '000'
    if image_url:
        try:
            r = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', image_url],
                             capture_output=True, text=True, timeout=10)
            status = r.stdout.strip()
        except:
            status = 'error'
    
    if status == '200' and 'placeholder' not in str(image_url).lower():
        print(f'✅ {cat}/{asin} — Image OK (HTTP {status}): {title[:40]}')
        
        data = {
            'asin': asin,
            'title': title,
            'price': price,
            'rating': rating,
            'review_count': review_count,
            'image': image_url,
            'reviews': reviews
        }
        
        outpath = os.path.join(BRIEFINGS, f'{cat}_{asin}_data.json')
        with open(outpath, 'w') as f:
            json.dump(data, f, indent=2)
        converted += 1
    else:
        print(f'⛔ {cat}/{asin} — Image FAIL (HTTP {status}): {title[:40]}')
        failed += 1

print(f'\n✅ {converted} JSON files created')
if failed:
    print(f'⛔ {failed} ASINs failed image verification')
