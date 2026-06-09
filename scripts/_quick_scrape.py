#!/usr/bin/env python3
"""ASIN quick-extract from URLs — add results to queue."""
import sys, os, json, re, subprocess, time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_PATH = os.path.join(WORKSPACE, "data", "asin_queue.json")

HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "-H", "Accept: text/html,application/xhtml+xml",
    "-H", "Accept-Language: en-US,en;q=0.9",
]

SRC = [
    # sites that use direct /dp/ links (no JS redirect)
    ("https://www.goodhousekeeping.com/cooking-tools/a62581556/best-kitchen-gear-coffee-tea-awards-2024/", "kitchen", "GH Kitchen Awards"),
    ("https://www.popularmechanics.com/home/tools/g45826557/best-tools/", "home-improvement", "PopMech Tools"),
    ("https://www.bobvila.com/articles/best-tools/", "home-improvement", "BobVila Tools"),
    # Wirecutter categories
    ("https://www.nytimes.com/wirecutter/reviews/best-coffee-maker/", "coffee", "Wirecutter Coffee"),
    ("https://www.nytimes.com/wirecutter/reviews/best-standing-desk/", "home-office", "Wirecutter Desks"),
    ("https://www.nytimes.com/wirecutter/reviews/best-office-chair/", "home-office", "Wirecutter Chairs"),
    ("https://www.nytimes.com/wirecutter/reviews/best-pet-supplies/", "pet-supplies", "Wirecutter Pets"),
    ("https://www.nytimes.com/wirecutter/reviews/best-skin-care-products/", "luxury-beauty", "Wirecutter Skincare"),
    # Smaller affiliate sites
    ("https://www.realsimple.com/best-kitchen-gadgets-amazon-8782100", "kitchen", "RealSimple Kitchen"),
    ("https://www.realsimple.com/best-home-office-supplies-amazon-8782111", "home-office", "RealSimple Home Office"),
]

ASIN_RE = re.compile(r'/[dg]p/(B[A-Z0-9]{9})')
PRODUCT_RE = re.compile(r'/product/(B[A-Z0-9]{9})')

def fetch(url):
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", "20"] + HEADERS + [url],
                         capture_output=True, text=True, timeout=25)
        return r.stdout
    except:
        return ""

def extract(html):
    s = set()
    for m in ASIN_RE.finditer(html): s.add(m.group(1))
    for m in PRODUCT_RE.finditer(html): s.add(m.group(1))
    return s

def queue_add(asins, cat):
    with open(QUEUE_PATH) as f:
        q = json.load(f)
    existing = set(q.get(cat, [])) | set(q.get('used', []))
    new = [a for a in asins if a not in existing]
    if new:
        q.setdefault(cat, []).extend(new)
        with open(QUEUE_PATH, 'w') as f:
            json.dump(q, f, indent=2)
    return new

total = 0
for url, cat, label in SRC:
    html = fetch(url)
    if not html:
        print(f"❌ {label}: empty")
        continue
    asins = extract(html)
    new = queue_add(asins, cat)
    total += len(new)
    print(f"{'✅' if new else '—'} {label}: {len(new)} new / {len(asins)} found  [{cat}]")
    if new:
        print(f"   {', '.join(sorted(new)[:8])}")
    time.sleep(1.5)

print(f"\nTotal: {total} new ASINs added")
