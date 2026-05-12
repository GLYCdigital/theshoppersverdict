#!/usr/bin/env python3
"""
ASIN Verifier — Checks if an Amazon ASIN returns a valid product before Signal spends Apify credits
Usage: python3 asin_verify.py <ASIN>
Returns exit 0 if valid, 1 if invalid (404/blocked)
"""

import sys, os, json, re, urllib.request, urllib.error

def verify(asin):
    """Quick HEAD/GET to Amazon to verify product exists"""
    url = f"https://www.amazon.com/dp/{asin}"
    req = urllib.request.Request(url, method='GET')
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    req.add_header('Accept-Language', 'en-US,en;q=0.9')
    
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode('utf-8', errors='ignore')
        # Check for "title" meta tag which indicates a real product page
        title_match = re.search(r'<span id="productTitle"[^>]*>(.*?)</span>', html, re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            if title and len(title) > 5:
                print(f"✅ {asin}: {title[:80]}")
                return True
        
        # Fallback: check for "price" or "buybox" indicators
        if 'add-to-cart' in html or 'buybox' in html:
            print(f"⚠️  {asin}: Amazon page loaded, no title found")
            return True  # Still might work
        
        print(f"❌ {asin}: No product title found (404 or captcha)")
        return False
    except urllib.error.HTTPError as e:
        print(f"❌ {asin}: HTTP {e.code}")
        return False
    except Exception as e:
        print(f"❌ {asin}: Error - {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: asin_verify.py <ASIN>")
        sys.exit(1)
    
    asin = sys.argv[1].strip()
    if not re.match(r'^[A-Z0-9]{10}$', asin):
        print(f"❌ {asin}: Invalid ASIN format")
        sys.exit(1)
    
    result = verify(asin)
    sys.exit(0 if result else 1)
