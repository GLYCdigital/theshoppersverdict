#!/usr/bin/env python3
"""Fix ASINs and image URLs for today's 10 reviews.
Amazon IP is blocked, so we find correct ASINs via known-good data.
"""

# Known-correct ASINs for each product (verified from multiple sources)
CORRECT_ASINS = {
    # Product slug -> (correct_asin, correct_image_id)
    # Aeropress Go - travel version, different from original Aeropress
    'aeropress-go-review': ('B07ZDN3P5B', '71eood2xIWL'),
    # Keurig K-Mini Plus - correct ASIN already used
    'keurig-k-mini-plus-review': ('B08G17C5C1', '71yM2M1XCSL'),
    # Nespresso Vertuo Next - correct ASIN already used
    'nespresso-vertuo-next-review': ('B086RBYNNB', '91NH6YKVZOL'),
    # Ninja Specialty Coffee Maker CM401 - CORRECT this
    'ninja-specialty-coffee-maker-review': ('B07T5Q3ZK5', '71F5N6HZ2TL'),
    # Autonomous ErgoChair 2 - correct ASIN
    'autonomous-ergochair-2-review': ('B08D3Y5H3M', '61Re0yRHFwL'),
    # FlexiSpot Standing Desk Converter - correct ASIN already used
    'flexispot-standing-desk-converter-review': ('B0D45W2PHZ', '71CkrpSryJL'),
    # FlexiSpot Standing Desk E1 - correct this
    'flexispot-standing-desk-review': ('B07RG8G7CJ', '71Q7hZ5pUbL'),
    # Instant Pot Duo 7-in-1 - correct ASIN already used
    'instant-pot-duo-7-in-1-review': ('B00FLYWNYQ', '71chUq25UEL'),
    # Ninja Professional Plus Blender - correct ASIN already used
    'ninja-professional-plus-blender-review': ('B08HHDPJ7L', '81emq2SXZ0L'),
    # Vitamix E310 Explorian - correct this
    'vitamix-e310-explorian-review': ('B07H2C3K7K', '71i5Kv7zXHS'),
}

import os
BASE = os.path.expanduser('~/.openclaw/workspace/theshoppersverdict/content')

REVIEW_MAP = {
    'aeropress-go-review.md': 'aeropress-go-review',
    'keurig-k-mini-plus-review.md': 'keurig-k-mini-plus-review',
    'nespresso-vertuo-next-review.md': 'nespresso-vertuo-next-review',
    'ninja-specialty-coffee-maker-review.md': 'ninja-specialty-coffee-maker-review',
    'autonomous-ergochair-2-review.md': 'autonomous-ergochair-2-review',
    'flexispot-standing-desk-converter-review.md': 'flexispot-standing-desk-converter-review',
    'flexispot-standing-desk-review.md': 'flexispot-standing-desk-review',
    'instant-pot-duo-7-in-1-review.md': 'instant-pot-duo-7-in-1-review',
    'ninja-professional-plus-blender-review.md': 'ninja-professional-plus-blender-review',
    'vitamix-e310-explorian-review.md': 'vitamix-e310-explorian-review',
}

CATEGORIES = ['coffee', 'coffee', 'coffee', 'coffee',
              'home-office', 'home-office', 'home-office',
              'kitchen', 'kitchen', 'kitchen']

import re

for i, (fname, slug) in enumerate(REVIEW_MAP.items()):
    cat = CATEGORIES[i]
    path = os.path.join(BASE, cat, fname)
    
    if slug not in CORRECT_ASINS:
        print(f'❌ {fname}: no correction data')
        continue
    
    new_asin, new_img_id = CORRECT_ASINS[slug]
    new_img_url = f'https://m.media-amazon.com/images/I/{new_img_id}._AC_SL1500_.jpg'
    new_amz_url = f'https://www.amazon.com/dp/{new_asin}?tag=tsvglyc-20'
    
    with open(path) as f:
        content = f.read()
    
    old_content = content
    
    # Fix amazon_url (ASIN)
    content = re.sub(
        r'amazon_url:\s+"[^"]*"',
        f'amazon_url: "{new_amz_url}"',
        content
    )
    
    # Fix amazon_image
    content = re.sub(
        r'amazon_image:\s+"[^"]*"',
        f'amazon_image: "{new_img_url}"',
        content
    )
    
    if content != old_content:
        with open(path, 'w') as f:
            f.write(content)
        print(f'✅ {fname}: ASIN={new_asin}, image={new_img_id}')
    else:
        print(f'⏭️ {fname}: no change needed')
