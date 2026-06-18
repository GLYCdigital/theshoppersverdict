#!/usr/bin/env python3
"""Test if our IP is blocked or specific ASINs are dead."""
import subprocess, re, time

# ASINs we KNOW exist (from recent successful reviews)
known_good = ['B0FDRZTG7C', 'B0GQ9R5J9T', 'B0DG2X7CKQ', 'B0GQZ6H3LQ']
# ASINs from products that definitely exist right now
popular_asins = ['B07984N4C9', 'B09G9HDH9P', 'B08J6F3DML', 'B086RBYNNB']

for asin in known_good + popular_asins:
    result = subprocess.run([
        'curl', '-sL', '--compressed', '--max-time', '10',
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        '-H', 'Accept: text/html,application/xhtml+xml',
        f'https://www.amazon.com/dp/{asin}'
    ], capture_output=True, text=True, timeout=12)
    
    html = result.stdout
    has_product = 'productTitle' in html
    hires = re.findall(r'data-old-hires="([^"]+)"', html)
    blocked = len(html) < 5000 or 'api-services-support' in html or 'Page Not Found' in html
    
    if has_product and hires:
        print(f'✅ {asin}: image={hires[0]}')
    elif has_product and not hires:
        print(f'⚠️ {asin}: page loaded but no hires image (len={len(html)})')
    elif blocked:
        print(f'❌ {asin}: BLOCKED (len={len(html)})')
    else:
        print(f'❌ {asin}: OTHER (len={len(html)})')

print('\n--- Now trying with Playwright/headed approach ---')

# Check if scrape_headed handles this differently
# Just check the script briefly
with open('scripts/scrape_headed.py') as f:
    head = f.read(500)
    print(f'scrape_headed.py uses: {"playwright" if "playwright" in head else "requests" if "requests" in head else "selenium" if "selenium" in head else "UNKNOWN"}')
    # Check for image extraction
    if 'data-old-hires' in head or '_SL1500_' in head or 'og:image' in head:
        print('Has image extraction code')
