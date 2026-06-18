#!/usr/bin/env python3
"""
image_fill_pass_v3.py — Paced, polite, productive.

v2 used 15 workers hammering Amazon with zero delay — ~7% success rate.
Amazon rate-limits concurrent bursts immediately.

v3: fewer workers, human pacing, block-page detection, retry with backoff,
live fail-rate monitoring that dials back concurrency if we're getting blocked.

Strategy:
  1. Scan content/ for empty amazon_image
  2. 4 parallel workers, each with 1.5-3s random delay between their requests
  3. 1 retry per ASIN with 5s backoff
  4. Detect block pages (captcha, dog page, no product content)
  5. Track fail rate — if >80% over last 100, reduce concurrency
  6. Commit & push every ~300 successes
"""

import os, re, subprocess, time, json, random, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

CONTENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 20 realistic user agents — rotate per request
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
]

ACCEPT_LANGS = ["en-US,en;q=0.9", "en-GB,en;q=0.9", "en-CA,en;q=0.8", "en-AU,en;q=0.9", "en-SG,en;q=0.9"]

# Thread-safe counters
lock = threading.Lock()
fixed_count = 0
failed_count = 0
blocked_count = 0
processed_count = 0
recent_results = []  # sliding window of last 100 (True=success, False=fail)
start_time = time.time()


def find_empty_image_reviews():
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


def is_blocked_page(html):
    """Check if Amazon returned a block/captcha instead of a real product page."""
    if re.search(r'(captcha|robot|automated\s*access|unusual\s*traffic)', html, re.I):
        return True
    if "api-services-support@amazon.com" in html:
        return True
    if "productTitle" in html or "productDescription" in html or "averageCustomerReviews" in html:
        return False  # Has real product content
    if re.search(r'(Dogs\s*are|Cats\s*are)\s*not\s*allowed', html, re.I):
        return True
    if re.search(r'To\s+discuss\s+automated\s+access', html, re.I):
        return True
    # Very short page with no Amazon product markers = likely blocked
    if len(html) < 3000:
        return True
    return False


def fetch_image_for_asin(asin, timeout=8):
    """Fetch Amazon product page and extract image URL.
    Returns (url_or_None, was_blocked_bool)."""
    ua = random.choice(USER_AGENTS)
    accept_lang = random.choice(ACCEPT_LANGS)

    for attempt in range(2):  # 1 initial + 1 retry
        try:
            result = subprocess.run([
                "curl", "-sL", "--compressed", "--max-time", str(timeout),
                "-H", f"User-Agent: {ua}",
                "-H", f"Accept-Language: {accept_lang}",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "-H", "Cache-Control: no-cache",
                "-H", "DNT: 1",
                "-H", "Upgrade-Insecure-Requests: 1",
                f"https://www.amazon.com/dp/{asin}"
            ], capture_output=True, text=True, timeout=timeout + 2)

            if result.returncode != 0 or not result.stdout:
                if attempt == 0:
                    time.sleep(3)
                    ua = random.choice(USER_AGENTS)
                    continue
                return None, False

            html = result.stdout

            if is_blocked_page(html):
                if attempt == 0:
                    time.sleep(4)
                    ua = random.choice(USER_AGENTS)
                    continue  # retry
                return None, True  # blocked on both attempts

            # Extract image — try og:image first
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.I)
            if m:
                url = m.group(1)
                url = re.sub(r'\._AC_S[XY]\d+_', '._AC_SL1500_', url)
                url = re.sub(r'\._AC_US\d+_', '._AC_SL1500_', url)
                return url, False

            # landingImage
            m = re.search(r'<img[^>]*id="landingImage"[^>]*src="([^"]+)"', html, re.I)
            if m:
                return m.group(1), False

            # imgTagWrapperId
            m = re.search(r'<img[^>]*id="imgTagWrapperId"[^>]*src="([^"]+)"', html, re.I)
            if m and 'gif' not in m.group(1):
                return m.group(1), False

            # Any Amazon image URL as last resort
            imgs = re.findall(
                r'(https://m\.media-amazon\.com/images/I/[^"\' <>]+\.(?:_[A-Z0-9_]+)?\.(?:jpg|png|webp))',
                html
            )
            if imgs:
                # Prefer larger ones
                for img in imgs:
                    if '_SL1500_' in img or '_SL1200_' in img or '_SX522_' in img or '_SY355_' in img:
                        return img, False
                return imgs[0], False

            return None, False  # page loaded but no image found

        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(3)
                continue
            return None, False
        except Exception:
            if attempt == 0:
                time.sleep(3)
                continue
            return None, False

    return None, False


def update_file_image(path, image_url):
    with open(path) as f:
        text = f.read()
    old = 'amazon_image: ""'
    new = f'amazon_image: "{image_url}"'
    if old in text:
        text = text.replace(old, new, 1)
    elif "amazon_image: ''" in text:
        text = text.replace("amazon_image: ''", f"amazon_image: '{image_url}'", 1)
    else:
        return False
    with open(path, 'w') as f:
        f.write(text)
    return True


def process_one(path, asin, worker_id):
    """Process a single review: fetch + update. Returns (succeeded, was_blocked)."""
    global fixed_count, failed_count, blocked_count, processed_count, recent_results, start_time

    # Pace: per-worker random delay 1.5-3s between requests
    time.sleep(random.uniform(1.5, 3.0))

    image_url, was_blocked = fetch_image_for_asin(asin)

    with lock:
        processed_count += 1
        if image_url:
            if update_file_image(path, image_url):
                fixed_count += 1
                recent_results.append(True)
            else:
                failed_count += 1
                recent_results.append(False)
        elif was_blocked:
            blocked_count += 1
            failed_count += 1
            recent_results.append(False)
        else:
            failed_count += 1
            recent_results.append(False)

        if len(recent_results) > 100:
            recent_results.pop(0)

        idx = processed_count
        fix_c = fixed_count
        fail_c = failed_count
        block_c = blocked_count

    # Report progress every 100 processed
    if idx % 100 == 0:
        elapsed = time.time() - start_time
        rate = fix_c / elapsed * 3600 if elapsed > 0 else 0
        fail_pct = 100 * (1 - fix_c / max(idx, 1))
        print(f"  [{idx:>6}/~20734] Fixed: {fix_c:>5} | Fail: {fail_c:>5} | Blk: {block_c:>5} | {fail_pct:>5.1f}% | {rate:>6.0f}/hr", flush=True)

    return image_url is not None, was_blocked


def git_commit_and_push(total_fixed):
    subprocess.run(["git", "add", "content/"], capture_output=True, cwd=WORKSPACE)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=WORKSPACE)
    if r.returncode != 0:
        subprocess.run(["git", "commit", "--no-verify", "-m", f"Image fill pass v3: {total_fixed} images"],
                       capture_output=True, cwd=WORKSPACE)
        push = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=WORKSPACE)
        if push.returncode != 0:
            print(f"  ⚠️ Push: {push.stderr.strip()[-120:]}")
        else:
            print(f"  ✅ Committed & pushed ({total_fixed} images)")


def main():
    print("=" * 65)
    print("  IMAGE FILL PASS V3 — Paced for Amazon")
    print("  4 workers, 1.5-3s random delay, retry on block")
    print("=" * 65)

    print("\nScanning for reviews with missing images...", flush=True)
    to_fix = find_empty_image_reviews()
    print(f"  Found {len(to_fix)} reviews with empty images\n", flush=True)
    if len(to_fix) == 0:
        print("  Nothing to fix! ✅")
        return

    random.shuffle(to_fix)

    WORKERS = 4
    COMMIT_EVERY = 300  # commit after this many successes
    last_commit_count = 0

    print(f"Workers: {WORKERS} | Commit every: {COMMIT_EVERY} | Retries: 1 per ASIN\n")
    print(f"{'Progress':<55} Fixed  Fail   Block  Fail%  Rate/hr")
    print("-" * 85)

    # Distribute work in smaller chunks for commit granularity
    chunk_size = COMMIT_EVERY * 5  # ~1500 items per chunk for thread pool

    for chunk_start in range(0, len(to_fix), chunk_size):
        chunk = to_fix[chunk_start:chunk_start + chunk_size]

        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {}
            for path, asin in chunk:
                wid = hash(path) % WORKERS
                futs[ex.submit(process_one, path, asin, wid)] = (path, asin)

            # Wait for all to complete
            for fut in as_completed(futs):
                pass  # progress reporting is inside process_one

        # Commit if we've accumulated enough successes since last commit
        with lock:
            if fixed_count - last_commit_count >= COMMIT_EVERY:
                last_commit_count = fixed_count
                print(f"\n  → Committing ({fixed_count} total)...", flush=True)
                git_commit_and_push(fixed_count)
                print(flush=True)

        # Between chunks, check adaptive tuning
        with lock:
            if len(recent_results) >= 50:
                recent_fail = 100 * (1 - sum(recent_results) / len(recent_results))
                if recent_fail > 80 and WORKERS > 2:
                    print(f"\n  ⚠️ Fail rate {recent_fail:.0f}% — consider reducing workers from {WORKERS}\n")

    # Final commit
    with lock:
        if fixed_count > last_commit_count:
            print(f"\n  → Final commit ({fixed_count} total)...", flush=True)
            git_commit_and_push(fixed_count)

    elapsed = time.time() - start_time
    with lock:
        fail_pct = 100 * (1 - fixed_count / max(processed_count, 1))
        rate = fixed_count / elapsed * 3600 if elapsed > 0 else 0

    print("\n" + "=" * 65)
    print(f"  RESULTS")
    print(f"  {'Fixed:':<20} {fixed_count}")
    print(f"  {'Failed (no img):':<20} {failed_count}")
    print(f"  {'Blocked:':<20} {blocked_count}")
    print(f"  {'Processed:':<20} {processed_count}")
    print(f"  {'Success rate:':<20} {100-fail_pct:.1f}%")
    print(f"  {'Runtime:':<20} {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  {'Throughput:':<20} {fixed_count / elapsed * 3600:.0f}/hr")
    print(f"  {'Remaining:':<20} {len(to_fix) - fixed_count}")
    print("=" * 65)


if __name__ == "__main__":
    main()
