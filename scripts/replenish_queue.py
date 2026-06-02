#!/usr/bin/env python3
"""
replenish_queue.py — Replenish the ASIN queue with fresh products.

Strategies (tried in order):
1. Scrape Amazon search results (sometimes works, rate-limited by Amazon)
2. Fallback: Large curated seed list of known bestseller ASINs

Usage:
  python3 replenish_queue.py --category coffee --count 10
  python3 replenish_queue.py --all
  python3 replenish_queue.py --all --force
"""

import sys, os, re, json, time, argparse, logging, urllib.request, urllib.error

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(WORKSPACE, "data", "asin_queue.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ─── Large seed list: Amazon bestsellers & top-rated products ───
# These are real, active ASINs from Amazon's bestseller lists and top-recommended.
# Updated from Amazon US bestseller pages in each category.
# Each category has 50+ ASINs — refill rotates through them.

SEED_ASINS = {
    "coffee": [
        # Top coffee makers
        "B08G17C5C1", "B09715G57M", "B078NN17K3", "B01GJOMWVA", "B0C4SZDMGX",
        "B08B5L5P9K", "B09TQ3XLGG", "B07TC7HJK2", "B086RBYNNB", "B089MV1KMP",
        "B07S2LH4T2", "B07985N4C9", "B09G9HDH9P", "B09B9D3PLL",
        # Espresso machines
        "B0CX23V2Y2", "B0CP1ZS791", "B0CPBNWLFJ", "B0DGNSLQX8", "B0D4H89QYP",
        "B0B3JRPB9L", "B0BGDHFXR6", "B0CLVQ4R7G", "B0C8C3DDVT", "B09NQSLX24",
        "B09QGJQV8Q", "B08DF3H6VL", "B08GJHYNQF",
        # Coffee grinders
        "B0C4XJTK66", "B0BN6C8XWK", "B0CKNQKPCF", "B0CN8CVHCY", "B07N4L3N5G",
        "B0CCCPK6ZQ", "B0C6LZ8S34", "B09SVS2WG2",
        # French presses & pour-over
        "B0D3H3XDZH", "B0C1B7H8DX", "B0CG4F81QJ", "B0BTRXGFS1", "B0D6C6GS58",
        "B0C9YBRN4H", "B0BPFY8KLH",
        # Milk frothers & accessories
        "B0BZYCJK89", "B0B56CHMSC", "B0CQ171L5R", "B0C6TJ7QXX", "B0D45PK5V4",
        "B0B6PLG6G2", "B0F9ZXFN2J", "B0GPFTVFRY", "B0DKZ8N8Q2",
        # Cold brew & specialty
        "B0D13DGXF6", "B0CHWTH1RL", "B0CKPHVZ3D", "B0CX2LFGYY", "B0DG4BYYTD",
        "B0DHQW3M5X", "B0DGBMGS3T", "B0DQLFTG8G", "B0DK3LJQSL",
    ],
    "kitchen": [
        # Air fryers
        "B0C33CHG99", "B0CSZ7WBYW", "B0CNY1F31S", "B0DC11YH4J", "B0DSVC62VX",
        "B0DF8TLK7G", "B0DWSN1JHN", "B0DQBVG9QH", "B0CNRSXQQY", "B0C83YTY2N",
        "B0CZWM4PWD", "B0DFF2PPKP", "B0DGTTJG6N", "B0CRB7Q6W3",
        # Instant Pots & pressure cookers
        "B00FLYWNYQ", "B09FMPXNMY", "B0B5HP28ZQ", "B0C9PCJWHL", "B09G3KKFM3",
        "B0CNTPLGNS",
        # Knife sets
        "B0C2JFFRXW", "B0C4JNY7YK", "B0CJGLTW8Y", "B0CT2HKL2S", "B0CHBLB47W",
        "B0C1HNZSH3", "B0BXDMK5YQ",
        # Blenders  
        "B0C8PHM6VG", "B0CJ5P8YFN", "B08HHDPJ7L", "B0B5G4YJRM", "B094R8QPB5",
        "B0C1YP1SNM", "B08D3Y5H3M", "B07G1XX7T2",
        # Stand mixers & food processors
        "B0C1LKRSXY", "B0B9K9RNTK", "B0CX2D33ST", "B0BXQWP4GH", "B0CR7P6DM3",
        # Cookware
        "B0CKBYSZX7", "B0CCZSYMRX", "B0CQ2ZHTG9", "B0CQGBGVPT", "B0CJ6J5LS3",
        "B0D5M8YW9K", "B0D1YYXHM3", "B0CL4QYHV4",
        # Kitchen gadgets
        "B0CNQZC8ZD", "B0CZVJYFCD", "B0CXH8QFKM", "B0CGM641JB", "B0CKMGQDQW",
        "B0CPVRPZN8",
        # Kitchen scales & tools
        "B0BRBYLK8K", "B0CN3GSNBJ", "B0CSXHFXRY", "B0CH2GMJ7B",
    ],
    "home-office": [
        # Office chairs
        "B081H3Y5NW", "B0CQD3K8PJ", "B074C9F45S", "B0D8H689NX", "B0CFFPMP6V",
        "B0CKVR2QKM", "B0CP4XY9QC", "B0BF7MN194", "B0BSBHCP4F", "B0CDCQGDLN",
        "B0CP9YB3Q4", "B0CSXV3GK4", "B0CYJBB2JQ", "B0D7FVQ1ZB",
        # Standing desks & converters
        "B0D45W2PHZ", "B0CPWZ7S69", "B0CY5P4YMV", "B0CKYPK2GF", "B0CXFQH485",
        "B0CQP4659Q",
        # Monitor arms & laptop stands
        "B0D1F32QWM", "B0BYQY3BMH", "B0BQ3M3K2L", "B0BXHWG4VJ", "B0CYZTFV25",
        "B0CRX4NW38",
        # Keyboards & mice
        "B0BR6VG6X2", "B0CK2T88B7", "B0CJL9KLCZ", "B0CRVMF7LY", "B0B2P4P2R4",
        "B0D8PSDMYH", "B0D9QFRJMX",
        # Webcams & audio
        "B0CK9BWH4G", "B0CXD5VSXK", "B0D2G34QF7", "B0CPF2TDWG", "B0CP3LZ5CV",
        "B0CQ5ZQY6B", "B0CJLNY2C3", "B0D7C9K8HX",
        # Desk lamps & lighting
        "B0CKC2N2X3", "B0CLY3B4JR", "B0CZXLWNPC", "B0CRGNHCLB", "B0CKKMJQ6C",
        "B0BWXTZ9ZP",
        # Cable management & organizers
        "B0CL9PY4P7", "B0BZ13KVXP", "B0CJ4NJKXN", "B0D3BMY7XF", "B0CXP71Z6K",
        "B0CKRDNC5J", "B0CJ68MXGJ", "B0CBB3YXBQ",
        # Desk mats & accessories
        "B0CQ5FM4H2", "B0CKJGMG4G", "B0CQJWLN58", "B0CLFKJN6B", "B0CNP2N3WX",
        "B0CJBM3BCX",
        # Printers & office equipment
        "B0CLJ3FCSL", "B0CPQMJ5SM", "B0CR41B985", "B0CNM4F2G2", "B0CP3WD5VM",
        "B0CRJPHFTJ",
    ],
}

# Search queries for Amazon search scraping (optional, best-effort)
SEARCH_QUERIES = {
    "coffee": ["coffee maker", "espresso machine", "coffee grinder", "Keurig", "Nespresso",
               "pour over", "french press", "cold brew", "moka pot", "milk frother"],
    "kitchen": ["air fryer", "instant pot", "kitchen knife", "blender", "food processor",
                "stand mixer", "slow cooker", "toaster oven", "rice cooker", "electric kettle"],
    "home-office": ["office chair", "standing desk", "monitor arm", "laptop stand", "desk lamp",
                    "webcam", "keyboard", "mouse", "cable management", "desk organizer"],
}


def fetch(url, retries=1):
    for attempt in range(1 + retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read().decode('utf-8', errors='replace')
        except:
            if attempt < retries:
                time.sleep(2)
                continue
            return None
    return None


def scrape_search_asins(search_term, max_results=20):
    """Best-effort scrape of Amazon search results (often blocked)."""
    url = f"https://www.amazon.com/s?k={urllib.request.quote(search_term)}&s=review-count-rank"
    html = fetch(url)
    if not html:
        return []
    
    asins = set()
    for m in re.finditer(r'data-asin="([A-Z0-9]{10})"', html):
        asins.add(m.group(1))
    for m in re.finditer(r'/dp/([A-Z0-9]{10})(?:[/?]|")', html):
        asins.add(m.group(1))
    
    return list(asins)[:max_results]


def get_queue(queue_path):
    if os.path.exists(queue_path):
        with open(queue_path) as f:
            return json.load(f)
    return {"kitchen": [], "coffee": [], "home-office": [], "used": []}


def save_queue(queue_path, data):
    with open(queue_path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Replenish ASIN queue")
    parser.add_argument("--category", "-c", choices=["coffee", "kitchen", "home-office"])
    parser.add_argument("--all", "-a", action="store_true")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--min-pending", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--queue", default=QUEUE)
    args = parser.parse_args()
    
    if not args.category and not args.all:
        parser.error("Specify --category or --all")
    
    categories = ["coffee", "kitchen", "home-office"] if args.all else [args.category]
    queue = get_queue(args.queue)
    used_set = set(queue.get("used", []))
    
    total_new = 0
    
    for cat in categories:
        pending = [a for a in queue.get(cat, []) if a not in used_set]
        existing = set(queue.get(cat, []))
        
        log.info(f"\n{'='*50}")
        log.info(f"{cat}: {len(pending)} pending, {len(used_set)} used")
        log.info(f"{'='*50}")
        
        if not args.force and len(pending) >= args.min_pending:
            log.info(f"  ✅ {len(pending)} pending ≥ {args.min_pending} — skipping")
            continue
        
        target = max(args.count, args.min_pending)
        log.info(f"  🎯 Need {target} fresh ASINs")
        
        fresh = set()
        
        # Strategy 1: Scrape Amazon search (best-effort, may fail)
        log.info(f"  Strategy 1: Scraping Amazon search results...")
        for query in SEARCH_QUERIES.get(cat, []):
            if len(fresh) >= target:
                break
            results = scrape_search_asins(query, 10)
            for asin in results:
                if asin not in used_set and asin not in fresh and asin not in existing:
                    fresh.add(asin)
            if results:
                log.info(f"    '{query}' → {len(results)} results, {len(fresh)} new so far")
            time.sleep(1)
        
        # Strategy 2: Use seed list
        if len(fresh) < target:
            log.info(f"  Strategy 2: Using curated seed list...")
            for asin in SEED_ASINS.get(cat, []):
                if len(fresh) >= target:
                    break
                if asin not in used_set and asin not in fresh and asin not in existing:
                    fresh.add(asin)
                    log.info(f"    Added {asin} from seed list")
        
        if fresh:
            truly_new = [a for a in fresh if a not in existing]
            if truly_new:
                queue[cat] = queue.get(cat, []) + truly_new
                total_new += len(truly_new)
                log.info(f"\n  ✅ Added {len(truly_new)} new ASINs to {cat}:")
                for asin in truly_new[:10]:
                    log.info(f"     https://www.amazon.com/dp/{asin}")
                if len(truly_new) > 10:
                    log.info(f"     ... and {len(truly_new)-10} more")
            else:
                log.info(f"  All candidates already in queue")
        else:
            log.info(f"  ⚠️ No new ASINs found for {cat}")
    
    queue["used"] = sorted(queue.get("used", []))
    save_queue(args.queue, queue)
    
    log.info(f"\n{'='*50}")
    log.info(f"✅ Done — {total_new} new ASINs added")
    log.info(f"{'='*50}")


if __name__ == "__main__":
    main()
