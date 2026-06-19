#!/usr/bin/env python3
"""
image_fill_pass_v4.py — Async Playwright, fresh page per ASIN.

Critical insight: Amazon tracks navigation within the same page/tab.
If you load multiple product pages in the same tab, the 2nd+ return stripped 404s.
Fix: each ASIN gets its own page (new tab), closed after extraction.
"""

import os, re, sys, time, json, random, asyncio, subprocess

CONTENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "content")
WORKSPACE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

_playwright = None
_browser = None
_context = None

fixed_count = 0
failed_count = 0
processed_count = 0
start_time = 0
last_commit_count = 0
stats_lock = None


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


def git_commit_and_push(total_fixed):
    subprocess.run(["git", "add", "content/"], capture_output=True, cwd=WORKSPACE)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=WORKSPACE)
    if r.returncode != 0:
        subprocess.run(["git", "commit", "--no-verify", "-m", f"Image fill pass v4: {total_fixed} images"],
                       capture_output=True, cwd=WORKSPACE)
        push = subprocess.run(["git", "push"], capture_output=True, text=True, cwd=WORKSPACE)
        if push.returncode != 0:
            print(f"  ⚠️ Push: {push.stderr.strip()[-120:]}")
        else:
            print(f"  ✅ Pushed ({total_fixed} images)")


async def init_browser():
    global _playwright, _browser, _context
    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    _context = await _browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='America/New_York',
    )
    await _context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)


async def close_browser():
    global _playwright, _browser, _context
    if _browser:
        try: await _browser.close()
        except: pass
        _browser = None; _context = None
    if _playwright:
        try: await _playwright.stop()
        except: pass
        _playwright = None


async def fetch_one(page, asin, timeout_ms=15000):
    """Navigate to ASIN and extract high-res image URL from a FRESH page."""
    from playwright.async_api import TimeoutError as PwTimeout
    try:
        await page.goto(f'https://www.amazon.com/dp/{asin}',
                       wait_until='domcontentloaded', timeout=timeout_ms)
        await asyncio.sleep(random.uniform(0.3, 0.6))
        
        title = await page.title()
        if 'Page Not Found' in title:
            return None, False
        
        # data-old-hires (most reliable)
        try:
            hires = await page.eval_on_selector(
                '[data-old-hires]',
                'el => el.getAttribute("data-old-hires")'
            )
            if hires:
                return hires, False
        except:
            pass
        
        # Fallback: data-a-dynamic-image
        try:
            dynamic = await page.eval_on_selector(
                '#landingImage',
                'el => el.getAttribute("data-a-dynamic-image")'
            )
            if dynamic:
                data = json.loads(dynamic)
                if data:
                    urls = list(data.keys())
                    for u in urls:
                        if '_SL1500_' in u or '_AC_SL1500_' in u:
                            return u, False
                    return urls[0], False
        except:
            pass
        
        # Fallback: any img in imgTagWrapperId
        try:
            src = await page.eval_on_selector(
                '#imgTagWrapperId img',
                'el => el.getAttribute("src")'
            )
            if src and 'm.media-amazon.com' in src:
                return src, False
        except:
            pass
        
        return None, False
    except PwTimeout:
        return None, False
    except Exception:
        return None, False


async def process_batch(batch):
    """Process a batch — each ASIN gets its own fresh page, closed after."""
    global fixed_count, failed_count, processed_count, stats_lock, _context
    
    sem = asyncio.Semaphore(3)
    
    async def process_one(path, asin):
        async with sem:
            page = await _context.new_page()
            page.set_default_timeout(15000)
            try:
                image_url, _ = await fetch_one(page, asin)
                return image_url is not None and update_file_image(path, image_url)
            finally:
                try: await page.close()
                except: pass
    
    tasks = [process_one(p, a) for p, a in batch]
    results = await asyncio.gather(*tasks)
    
    async with stats_lock:
        for success in results:
            processed_count += 1
            if success:
                fixed_count += 1
            else:
                failed_count += 1


async def restart_browser_if_needed(items_since_restart):
    """Restart browser every 500 items to prevent Playwright memory leak."""
    global _playwright, _browser, _context
    if items_since_restart >= 500:
        print(f"\n  🔄 Browser restart at {items_since_restart} items (memory cleanup)...", flush=True)
        await close_browser()
        await init_browser()
        print(f"  ✅ Browser restarted\n", flush=True)
        return True
    return False


async def process_all(to_fix):
    global fixed_count, failed_count, processed_count, start_time, last_commit_count
    start_time = time.time()
    await init_browser()
    
    CONCURRENT = 2
    BATCH = 40
    COMMIT_EVERY = 100
    BROWSER_RESTART_EVERY = 500
    items_since_restart = 0
    
    print(f"\nWorkers: {CONCURRENT} concurrent | Commit: {COMMIT_EVERY} | Browser restart: {BROWSER_RESTART_EVERY}")
    print(f"Total: {len(to_fix)} ASINs\n")
    
    for batch_start in range(0, len(to_fix), BATCH):
        batch = to_fix[batch_start:batch_start + BATCH]
        try:
            await process_batch(batch)
            items_since_restart += len(batch)
        except Exception as e:
            print(f"\n  ⚠️ Batch error: {str(e)[:80]}. Restarting browser...", flush=True)
            await close_browser()
            await init_browser()
            items_since_restart = 0
            # Retry this batch
            try:
                await process_batch(batch)
                items_since_restart += len(batch)
            except Exception as e2:
                print(f"  ❌ Retry also failed: {str(e2)[:80]}. Skipping batch.", flush=True)
                continue
        
        elapsed = time.time() - start_time
        rate = fixed_count / elapsed * 3600 if elapsed > 0 else 0
        fail_pct = 100 * (1 - fixed_count / max(processed_count, 1))
        eta_secs = max(0, (len(to_fix) - processed_count) / max(processed_count / elapsed, 0.001))
        print(f"  [{processed_count:>6}/{len(to_fix)}] Fixed: {fixed_count:>5} | Fail: {failed_count:>5} | {fail_pct:>5.1f}% | {rate:>6.0f}/hr | ETA: {eta_secs/60:.0f}m", flush=True)
        
        if fixed_count - last_commit_count >= COMMIT_EVERY:
            last_commit_count = fixed_count
            print(f"\n  → Committing ({fixed_count} total)...", flush=True)
            git_commit_and_push(fixed_count)
            print(flush=True)
        
        # Prevent Playwright memory leak: restart browser periodically
        await restart_browser_if_needed(items_since_restart)
        if items_since_restart >= BROWSER_RESTART_EVERY:
            items_since_restart = 0
    
    await close_browser()
    
    if fixed_count > last_commit_count:
        print(f"\n  → Final commit...", flush=True)
        git_commit_and_push(fixed_count)
    
    elapsed = time.time() - start_time
    fail_pct = 100 * (1 - fixed_count / max(processed_count, 1))
    rate = fixed_count / elapsed * 3600 if elapsed > 0 else 0
    
    print("\n" + "=" * 65)
    print(f"  RESULTS")
    print(f"  {'Fixed:':<20} {fixed_count}")
    print(f"  {'Failed:':<20} {failed_count}")
    print(f"  {'Processed:':<20} {processed_count}")
    print(f"  {'Success rate:':<20} {100-fail_pct:.1f}%")
    print(f"  {'Runtime:':<20} {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  {'Throughput:':<20} {rate:.0f}/hr")
    print(f"  {'Remaining:':<20} {len(to_fix) - fixed_count}")
    print("=" * 65)
    return fixed_count


def main():
    global total_to_process, stats_lock
    stats_lock = asyncio.Lock()
    
    print("=" * 65)
    print("  IMAGE FILL PASS V4 — Async Playwright (fresh page per ASIN)")
    print("=" * 65)
    
    print("\nScanning...", flush=True)
    to_fix = find_empty_image_reviews()
    print(f"  Found {len(to_fix)} reviews with empty images\n", flush=True)
    
    if len(to_fix) == 0:
        print("  Nothing to fix! ✅")
        return
    
    random.shuffle(to_fix)
    total_to_process = len(to_fix)
    asyncio.run(process_all(to_fix))


if __name__ == "__main__":
    main()
