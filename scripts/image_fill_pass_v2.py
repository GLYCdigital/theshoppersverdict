#!/usr/bin/env python3
"""
image_fill_pass_v2.py — Fast parallel backfill for 23K+ missing product images.

Strategy:
  1. Scan all content/ files for empty amazon_image
  2. Extract ASIN from amazon_url
  3. Parallel fetch Amazon product pages (curl, minimal headers, fast)
  4. Extract og:image meta tag OR landing image
  5. Write image URL back to frontmatter
  6. Commit & push in batches

15 workers, 8s timeout, batched commits every 1000.
"""

import os, re, subprocess, time, json, random
from concurrent.futures import ThreadPoolExecutor, as_completed

CONTENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
]

def find_empty_image_reviews():
    """Walk content/ and find files with empty amazon_image + ASIN."""
    results = []
    for root, dirs, files in os.walk(CONTENT):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if not f.endswith(".md") or f == "_index.md":
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    text = fh.read(2000)
            except:
                continue
            
            if 'amazon_image: ""' not in text and "amazon_image: ''" not in text:
                continue
            
            m = re.search(r'/dp/([A-Z0-9]{10})', text)
            if m:
                results.append((path, m.group(1)))
    
    return results


def fetch_image_for_asin(asin, timeout=8):
    """Fetch Amazon product page and extract og:image URL."""
    ua = random.choice(USER_AGENTS)
    
    try:
        result = subprocess.run([
            "curl", "-sL", "--compressed", "--max-time", str(timeout),
            "-H", f"User-Agent: {ua}",
            "-H", "Accept-Language: en-US,en;q=0.9",
            "-H", "Accept: text/html,application/xhtml+xml",
            f"https://www.amazon.com/dp/{asin}"
        ], capture_output=True, text=True, timeout=timeout+2)
        
        if result.returncode != 0 or not result.stdout:
            return None
        
        html = result.stdout
        
        # Try og:image first (fastest)
        m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.I)
        if m:
            url = m.group(1)
            # Clean up Amazon image URLs
            url = re.sub(r'\._AC_S[XY]\d+_', '._AC_SL1500_', url)
            url = re.sub(r'\._AC_US\d+_', '._AC_SL1500_', url)
            url = re.sub(r'\._SY\d+_', '._SY500_', url)
            return url
        
        # Try landingImage
        m = re.search(r'<img[^>]*id="landingImage"[^>]*src="([^"]+)"', html, re.I)
        if m:
            return m.group(1)
        
        # Try any Amazon image URL in the page
        imgs = re.findall(r'(https://m\.media-amazon\.com/images/I/[^"\' ]+\.(?:_AC_SL1500_|_AC_US230_|_SY355_|_SX355_|_[A-Z0-9_]+)?\.(?:jpg|png|webp))', html)
        if imgs:
            # Return the largest-looking one
            for img in imgs:
                if '_SL1500_' in img or '_SL1200_' in img:
                    return img
            return imgs[0]
        
        return None
        
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"    Error {asin}: {str(e)[:50]}")
        return None


def update_file_image(path, image_url):
    """Replace empty amazon_image in markdown frontmatter."""
    with open(path) as f:
        text = f.read()
    
    if 'amazon_image: ""' in text:
        text = text.replace('amazon_image: ""', f'amazon_image: "{image_url}"', 1)
    elif "amazon_image: ''" in text:
        text = text.replace("amazon_image: ''", f"amazon_image: '{image_url}'", 1)
    else:
        return False
    
    with open(path, 'w') as f:
        f.write(text)
    return True


def git_commit_and_push(fixed_count):
    """Stage, commit, and push changes."""
    result = subprocess.run(["git", "add", "content/"], capture_output=True, cwd=WORKSPACE)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=WORKSPACE)
    if r.returncode != 0:
        subprocess.run(["git", "commit", "--no-verify", "-m", f"Image fill pass: {fixed_count} images added"],
                      capture_output=True, cwd=WORKSPACE)
        push = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=WORKSPACE)
        if push.returncode != 0:
            print(f"  ⚠️ Push issue: {push.stderr.strip()[-100:]}")
        return True
    return False


def main():
    print("=" * 60)
    print("IMAGE FILL PASS V2 — Filling 23K+ missing product images")
    print("Fast parallel: 15 workers, Amazon og:image extraction")
    print("=" * 60)
    
    print("\nScanning for reviews with missing images...", flush=True)
    to_fix = find_empty_image_reviews()
    print(f"  Found {len(to_fix)} reviews with empty images\n", flush=True)
    
    if len(to_fix) == 0:
        print("  Nothing to fix! ✅")
        return
    
    # shuffle for fairness across categories
    random.shuffle(to_fix)
    
    WORKERS = 15
    BATCH_COMMIT = 1000
    
    fixed = 0
    failed = 0
    skipped = 0
    start = time.time()
    total = len(to_fix)
    
    print(f"Starting with {WORKERS} parallel workers...\n")
    
    # Process in batches for periodic commits
    for batch_start in range(0, total, BATCH_COMMIT):
        batch = to_fix[batch_start:batch_start + BATCH_COMMIT]
        
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {}
            for path, asin in batch:
                futs[ex.submit(fetch_image_for_asin, asin, 8)] = (path, asin)
            
            for fut in as_completed(futs):
                path, asin = futs[fut]
                try:
                    image_url = fut.result()
                except:
                    image_url = None
                
                if image_url:
                    if update_file_image(path, image_url):
                        fixed += 1
                    else:
                        skipped += 1
                else:
                    failed += 1
        
        elapsed = time.time() - start
        pct = 100 * (batch_start + len(batch)) / total
        rate = (batch_start + len(batch)) / elapsed * 3600 if elapsed > 0 else 0
        print(f"  [{batch_start+len(batch)}/{total}] Fixed: {fixed} | Failed: {failed} | {pct:.0f}% | {rate:.0f}/hr", flush=True)
        
        # Git commit every batch
        if fixed > 0:
            print(f"  → Committing ({fixed} fixes so far)...", flush=True)
            git_commit_and_push(fixed)
    
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"RESULT: {fixed} images filled, {failed} failed, {skipped} skipped")
    print(f"  Time: {elapsed:.0f}s ({total/elapsed:.1f}/s avg)")
    print(f"{'='*60}")
    
    # Final commit
    if fixed > 0:
        print(f"\n  → Final commit...", flush=True)
        git_commit_and_push(fixed)
        print(f"  ✅ Done. {fixed} product images backfilled.", flush=True)
    else:
        print(f"  ⚠️ No images were fixed.")
    
    return fixed


if __name__ == "__main__":
    main()
