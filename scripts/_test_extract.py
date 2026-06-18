#!/usr/bin/env python3
"""Test Amazon image extraction across multiple products."""
import subprocess, re

test_asins = [
    'B0FDRZTG7C', 'B07PNNLVK2', 'B08FMNXX7J', 'B0CPPS6SC4',
    'B09M2XT6BZ', 'B0F5BC6L4Z', 'B0DK8W9KJY', 'B0BFR36RPM',
    'B09G9HDH9P', 'B08J6F3DML', 'B0DG2X7CKQ', 'B0GQ9R5J9T'
]

for asin in test_asins:
    try:
        result = subprocess.run([
            'curl', '-sL', '--compressed', '--max-time', '8',
            '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            f'https://www.amazon.com/dp/{asin}'
        ], capture_output=True, text=True, timeout=10)

        html = result.stdout
        has_product = 'productTitle' in html
        hires = re.findall(r'data-old-hires="([^"]+)"', html)
        first = hires[0] if hires else None
        is_blocked = 'captcha' in html.lower() or 'api-services-support@amazon.com' in html or len(html) < 3000

        print(f'{asin}: ok={has_product} blocked={is_blocked} hires={len(hires)} img={"YES" if first else "NO"} len={len(html)}')
        if first:
            print(f'  -> {first}')
        else:
            # Try _SL1500_ as fallback
            sl1500 = re.findall(r'https://m\.media-amazon\.com/images/I/[^"\']+\._SL1500_[^"\']*\.jpg', html)
            if sl1500:
                print(f'  -> (SL1500) {sl1500[0]}')
            else:
                print(f'  -> NO IMAGE FOUND')
    except Exception as e:
        print(f'{asin}: ERROR {e}')
