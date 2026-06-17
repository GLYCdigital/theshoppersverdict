#!/usr/bin/env python3
"""
image_fill_pass.py — Second pass to fill missing images for 24K+ reviews.
 
Uses 3 parallel curl workers (gentle), longer delays, to get Amazon product page images.
Only processes reviews that have empty `amazon_image` field.
"""
import os, re, subprocess, time, json
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

CONTENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")
ASINS_TO_CHECK = []

def find_image_empty_reviews():
    """Walk content/ and find files with empty amazon_image."""
    results = []
    for root, dirs, files in os.walk(CONTENT):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if not f.endswith(".md") or f == "_index.md":
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    text = fh.read(1000)
            except:
                continue
            
            # Check for empty image + extract ASIN
            if 'amazon_image: ""' in text or "amazon_image: ''" in text:
                m = re.search(r'/dp/([A-Z0-9]{10})', text)
                if m:
                    results.append((path, m.group(1)))
    
    return results

def curl_product_page_gentle(asin, timeout=10):
    """Gentle product page fetch."""
    try:
        result = subprocess.run([
            "curl", "-sL", "--compressed", "--max-time", str(timeout),
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "-H", "Accept-Language: en-US,en;q=0.9",
            f"https://www.amazon.com/dp/{asin}"
        ], capture_output=True, text=True, timeout=timeout+2)
        if result.returncode == 0 and "productTitle" in result.stdout:
            return result.stdout
    except:
        pass
    return None

def extract_image(html, asin):
    """Extract image URL from HTML."""
    m = re.search(r'<img[^>]*[Ll]anding[Ii]mage[^>]*src="([^"]+)"', html)
    if m:
        return m.group(1)
    imgs = re.findall(r'https://m\.media-amazon\.com/images/I/[^"\' ]+\._AC_SY300_SX300_[^"\']+\.jpg', html)
    if imgs:
        return imgs[0]
    return None

def update_file_image(path, image_url):
    """Replace empty amazon_image in markdown frontmatter."""
    with open(path) as f:
        text = f.read()
    
    old = 'amazon_image: ""'
    new = f'amazon_image: "{image_url}"'
    if old in text:
        text = text.replace(old, new, 1)
    else:
        old2 = "amazon_image: ''"
        new2 = f"amazon_image: '{image_url}'"
        if old2 in text:
            text = text.replace(old2, new2, 1)
        else:
            return False
    
    with open(path, 'w') as f:
        f.write(text)
    return True

def main():
    print("=" * 60)
    print("IMAGE FILL PASS — Filling 24K+ missing product images")
    print("=" * 60)
    print("\nScanning for reviews with missing images...", flush=True)
    
    to_fix = find_image_empty_reviews()
    print(f"  Found {len(to_fix)} reviews with empty images\n", flush=True)
    
    fixed = 0
    failed = 0
    skipped = 0
    start = time.time()
    
    BATCH_SIZE = 100
    
    for b_start in range(0, len(to_fix), BATCH_SIZE):
        batch = to_fix[b_start:b_start + BATCH_SIZE]
        
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(curl_product_page_gentle, asin, 10): (path, asin) for path, asin in batch}
            for fut in as_completed(futs):
                path, asin = futs[fut]
                try:
                    html = fut.result()
                except:
                    html = None
                
                if html:
                    img = extract_image(html, asin)
                    if img:
                        if update_file_image(path, img):
                            fixed += 1
                        else:
                            skipped += 1
                    else:
                        failed += 1
                else:
                    failed += 1
        
        elapsed = time.time() - start
        rate = (b_start + len(batch)) / elapsed * 3600 if elapsed > 0 else 0
        pct = 100 * fixed / max(b_start + len(batch), 1)
        print(f"  [{b_start+len(batch)}/{len(to_fix)}] Fixed: {fixed} ({pct:.0f}%) | Rate: {rate:.0f}/hr", flush=True)
        
        # Commit every 5000 fixes
        if fixed > 0 and fixed % 5000 == 0:
            print(f"\n  → Committing {fixed} image fixes...", flush=True)
            subprocess.run(["git", "add", "content/"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if r.returncode != 0:
                subprocess.run(["git", "commit", "--no-verify", "-m", f"Image fill: {fixed} images added"],
                             capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                subprocess.run(["git", "push"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                print(f"  ✅ Pushed", flush=True)
    
    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"DONE: {fixed} images filled, {failed} failed, {skipped} skipped")
    print(f"  Time: {elapsed:.0f}s ({len(to_fix)/elapsed:.1f}/s)")
    print(f"{'='*60}")
    
    # Final commit
    if fixed > 0:
        print(f"\n  → Final commit...", flush=True)
        subprocess.run(["git", "add", "content/"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if r.returncode != 0:
            subprocess.run(["git", "commit", "--no-verify", "-m", f"Image fill pass complete: {fixed} images"],
                         capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            subprocess.run(["git", "push"], capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            print(f"  ✅ Pushed final", flush=True)
    
    return fixed

if __name__ == "__main__":
    main()
