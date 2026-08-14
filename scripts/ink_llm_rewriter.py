#!/opt/homebrew/bin/python3
"""
ink_llm_rewriter.py — Batch-rewrite all TSV reviews with DeepSeek LLM.

Replaces template-generated slop with individually written, SEO-optimized reviews.
Modeled after Til's rewrite_all_reviews.py: direct DeepSeek API, concurrent workers,
size-based skip detection, checkpoint resume.

Usage:
    python3 scripts/ink_llm_rewriter.py              # Process ALL reviews
    python3 scripts/ink_llm_rewriter.py --dry-run    # Show stats, no writes
    python3 scripts/ink_llm_rewriter.py --resume     # Resume from checkpoint
    python3 scripts/ink_llm_rewriter.py --sample 20  # Test with first 20
    python3 scripts/ink_llm_rewriter.py --category coffee  # One category only
    python3 scripts/ink_llm_rewriter.py --asin B0CD84J6KY   # Single ASIN

Time estimate: ~3h for 27k reviews at 4 concurrent.
Cost estimate: ~$18-22 total for all 27k.
"""

import os, sys, json, re, time, hashlib
from datetime import date, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ── Config ────────────────────────────────────────────────────────
N_CONCURRENT = 12
CHECKPOINT_EVERY = 50
MIN_BYTES = 100000  # rewrite ALL reviews (none should be 100KB+)

DEEPSEEK_API_KEY = "sk-b1c9d5fbebf7451095abd1878cb9414e"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

WORKSPACE = Path(__file__).resolve().parent.parent
CONTENT_DIR = WORKSPACE / "content"
BRIEFINGS_DIR = WORKSPACE / "briefings"
CHECKPOINT_FILE = WORKSPACE / "state" / "rewrite_checkpoint.txt"

AFFILIATE_TAG = "tsvglyc-20"
PACE_DELAY = 0.3   # between submissions to avoid rate bursts
API_TIMEOUT = 90
MAX_RETRIES = 3
MAX_TOKENS = 2500

CATEGORY_LABEL = {
    'coffee': 'coffee maker or coffee gear',
    'kitchen': 'kitchen appliance, cookware, or kitchen gadget',
    'home-office': 'office product or workspace gear',
    'home-improvement': 'tool, hardware, or home improvement product',
    'luxury-beauty': 'luxury beauty or skincare product',
    'pet-supplies': 'pet supply or pet care product',
    'furniture': 'furniture or home furnishing',
    'sports-fitness': 'sports equipment or fitness gear',
    'toys-games': 'toy or game',
    'patio-lawn-garden': 'patio, lawn, or garden product',
}

# ── Stats ────────────────────────────────────────────────────────
stats_lock = threading.Lock()
stats = {"done": 0, "skipped": 0, "errors": 0, "tokens": 0, "started": None}


# ── Checkpoint helpers ───────────────────────────────────────────

def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return set(CHECKPOINT_FILE.read_text().strip().split('\n'))
    return set()


def save_checkpoint(slugs_done):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text('\n'.join(sorted(slugs_done)))


# ── Frontmatter + data loader ────────────────────────────────────

def read_existing_review(path):
    """Extract frontmatter + body, plus ASIN."""
    text = path.read_text(encoding='utf-8')
    meta = {"slug": path.stem}

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        body = fm_match.group(2)

        # Extract known fields
        for key in ['title', 'seo_title', 'meta_description', 'slug', 'image_alt',
                     'verdict_score', 'price', 'review_count', 'amazon_rating',
                     'amazon_url', 'amazon_image']:
            m = re.search(rf'{key}:\s*["\']?(.*?)["\']?\s*$', fm, re.MULTILINE)
            if m:
                val = m.group(1).strip()
                meta[key] = val

        # Extract list fields (pros, cons)
        for key in ['pros', 'cons']:
            section = re.search(rf'{key}:\s*\n((?:\s*-.*\n?)*)', fm, re.MULTILINE)
            if section:
                items = re.findall(r'-\s*["\']?(.*?)["\']?\s*$', section.group(1), re.MULTILINE)
                meta[f'_{key}_raw'] = items

        # Extract ASIN from amazon_url
        asin_m = re.search(r'/dp/([A-Z0-9]{10})', meta.get('amazon_url', ''))
        meta['asin'] = asin_m.group(1) if asin_m else None

        # Category from path
        parts = path.relative_to(CONTENT_DIR).parts
        meta['category'] = parts[0] if parts else 'kitchen'
        meta['cat_label'] = CATEGORY_LABEL.get(meta['category'], 'product')

        # Verdict score
        try:
            meta['verdict_score'] = float(meta.get('verdict_score', 4.0))
        except (ValueError, TypeError):
            meta['verdict_score'] = 4.0

        # Amazon rating
        try:
            meta['amazon_rating'] = float(meta.get('amazon_rating', meta['verdict_score']))
        except (ValueError, TypeError):
            meta['amazon_rating'] = meta['verdict_score']

        # Review count
        try:
            meta['review_count'] = int(meta.get('review_count', 0))
        except (ValueError, TypeError):
            meta['review_count'] = 0

        # Title cleanup
        title = meta.get('title', path.stem.replace('-', ' ').title())
        meta['title'] = title.strip()
        if not meta.get('name'):
            # Derive clean product name from title
            meta['name'] = re.sub(r'\s*Review.*$', '', title).strip()
    else:
        meta['title'] = path.stem.replace('-', ' ').title()
        meta['name'] = meta['title']
        meta['category'] = 'kitchen'
        meta['cat_label'] = 'product'
        meta['verdict_score'] = 4.0
        meta['amazon_rating'] = 4.0
        meta['review_count'] = 0
        meta['asin'] = None
        body = text

    return meta, body


def find_briefing(asin):
    """Load briefing JSON for real customer quotes."""
    if not asin:
        return None
    pattern = f'*_{asin}_data.json'
    for match in BRIEFINGS_DIR.glob(pattern):
        if 'failed_empty' in str(match):
            continue
        try:
            data = json.loads(match.read_text())
            if not isinstance(data, dict):
                continue
            return data
        except Exception:
            continue
    return None


# ── Prompt builder ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are The Shopper's Verdict — an Amazon product expert who writes honest, detailed, buyer-focused reviews. Your readers are real shoppers about to spend their hard-earned money. Help them decide.

Your voice:
- Direct, authoritative, experienced. No marketing fluff. No AI-sounding filler.
- You've researched this product. Reference specific features, materials, dimensions.
- Give specific, actionable buying advice — not generic observations.
- Honest about downsides. Every product has them. Say what they are plainly.
- Use real customer feedback when provided — quote it, attribute it naturally.

Structure (vary it naturally — never the same order twice):
- Opening hook: What makes this product worth considering (or what makes it skippable)
- What's in the box / what you actually get
- Performance, build quality, real-world use
- What buyers consistently praise (with real quotes if provided)
- Where it falls short (specific, honest — every product has tradeoffs)
- Who should buy this — specific buyer personas
- FAQ: 3 real questions shoppers ask, with direct, helpful answers
- The Verdict: Clear recommendation, "Buy it if / Skip it if" format, star rating

Rules:
- Do NOT include markdown image tags ![ ](...) — the theme handles images.
- You CAN reference product images in text: "As shown in the product image..."
- Rating must match the verdict_score value provided.
- Output: 600-900 words. No filler, no template feel.
- Meta description: max 155 characters, SEO-optimized with primary keyword.
- SEO title: 55-65 characters, keyword-rich but natural.
- Pros/cons: Specific, not generic. No "Check Amazon for current pricing" cop-outs.
- Vary section order, sentence structure, and opening style naturally."""


def build_prompt(meta, briefing):
    """Build review prompt with product data and customer quotes."""
    name = meta['name']
    asin = meta.get('asin', '')
    cat_label = meta['cat_label']
    rating = meta['amazon_rating']
    verdict = meta['verdict_score']
    review_count = meta['review_count']
    price = meta.get('price', 'Check price on Amazon')
    amazon_image = meta.get('amazon_image', '')
    slug = meta['slug']
    stars = '⭐' * round(rating)
    today = date.today().isoformat()

    # Briefing context
    briefing_text = ""
    if briefing:
        reviews = briefing.get('reviews', [])
        if reviews:
            sorted_revs = sorted(reviews, key=lambda r: r.get('rating', 0), reverse=True)
            top_pos = [r for r in sorted_revs if r.get('rating', 0) >= 4][:3]
            critical = [r for r in sorted_revs if r.get('rating', 0) <= 3][:2]

            if top_pos or critical:
                briefing_text = "\n## REAL CUSTOMER REVIEWS (quote these naturally in your review)\n"
                for r in top_pos:
                    text = r.get('text', r.get('review', ''))[:200].strip()
                    name_r = r.get('name', r.get('reviewer', 'Verified Buyer'))
                    ra = r.get('rating', '')
                    if text:
                        briefing_text += f'\n"{text}" — {name_r} ({ra}★)\n'
                for r in critical:
                    text = r.get('text', r.get('review', ''))[:200].strip()
                    name_r = r.get('name', r.get('reviewer', 'Verified Buyer'))
                    ra = r.get('rating', '')
                    if text:
                        briefing_text += f'\n"{text}" — {name_r} ({ra}★)\n'

    return f"""Write a professional product review for: {name}

PRODUCT DATA:
- Category: {cat_label}
- Amazon rating: {rating}/5 ({stars}) with {review_count:,} ratings
- Price: {price}
- Verdict score: {verdict}/5
{briefing_text}

FRONTMATTER (fill all fields):
---
title: "{name}"
seo_title: "[55-65 char SEO title — keyword-rich, include 'Review']"
meta_description: "[140-155 char meta description — compelling, keyword-optimized]"
slug: "{slug}"
image_alt: "[Descriptive alt text for the product image]"
verdict_score: {verdict}
date: {today}
price: {price}
review_count: {review_count}
amazon_rating: {rating}
amazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"
amazon_image: "{amazon_image}"
pros:
  - "[Specific, concrete pro — not generic]"
  - "[Specific pro 2]"
  - "[Specific pro 3]"
cons:
  - "[Specific, honest con — not dismissive]"
  - "[Specific con 2]"
---

Write the full review body. This is a {cat_label} with {review_count:,}+ Amazon ratings at {rating}/5 average. Give shoppers the real story.

IMPORTANT: No ![image](...) markdown tags. Vary structure naturally."""


# ── Clean & finalize ─────────────────────────────────────────────

def clean_output(text, meta):
    """Parse LLM output, fix frontmatter, strip inline images, inject affiliate CTA."""
    slug = meta['slug']
    name = meta['name']
    asin = meta.get('asin', '')

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if not fm_match:
        return text  # can't parse, return as-is

    fm_block = fm_match.group(1)
    body = fm_match.group(2)

    # Fix verdict_score and amazon_rating to match original
    fm_block = re.sub(r'verdict_score:\s*[\d.]+', f'verdict_score: {meta["verdict_score"]}', fm_block)
    fm_block = re.sub(r'amazon_rating:\s*[\d.]+', f'amazon_rating: {meta["amazon_rating"]}', fm_block)

    # Ensure slug
    if 'slug:' not in fm_block:
        fm_block += f'\nslug: "{slug}"'

    # Ensure amazon_url with affiliate tag
    if 'amazon_url:' not in fm_block and asin:
        fm_block += f'\namazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"'

    # Ensure amazon_image preserved
    if 'amazon_image:' not in fm_block and meta.get('amazon_image'):
        fm_block += f'\namazon_image: "{meta["amazon_image"]}"'

    # Strip ALL inline images from body
    body = re.sub(r'!\[.*?\]\([^)]+\)', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Affiliate CTA
    cta = f"""\n## Where to Buy\n\n👉 **[Check Price on Amazon →](https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG})**\n\n*We earn a small commission at no extra cost to you — this helps fund more honest reviews.*\n"""

    footer = f"""\n---\n*Last updated: {date.today().isoformat()}. Ratings and prices current as of review date. Verify on Amazon before purchasing.*\n"""

    return f"---\n{fm_block.strip()}\n---\n\n{body.strip()}\n{cta}{footer}"


# ── API caller ───────────────────────────────────────────────────

def call_deepseek(prompt):
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=API_TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=MAX_TOKENS,
            )
            text = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0
            return text, tokens
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep((attempt + 1) * 3)
            else:
                raise

    return None, 0


# ── Single review processor ──────────────────────────────────────

def process_one(path, briefing):
    slug = path.stem
    meta, body = read_existing_review(path)

    # Defensive: ensure numeric ratings
    try:
        meta['amazon_rating'] = float(meta.get('amazon_rating', 4.0))
    except (ValueError, TypeError):
        meta['amazon_rating'] = 4.0
    try:
        meta['review_count'] = int(meta.get('review_count', 0))
    except (ValueError, TypeError):
        meta['review_count'] = 0

    prompt = build_prompt(meta, briefing)
    raw, tokens = call_deepseek(prompt)
    if not raw:
        raise RuntimeError(f"Empty response for {slug}")

    cleaned = clean_output(raw, meta)
    path.write_text(cleaned, encoding='utf-8')

    with stats_lock:
        stats["done"] += 1
        stats["tokens"] += tokens

    return slug


# ── Main driver ──────────────────────────────────────────────────

def main():
    dry_run = '--dry-run' in sys.argv
    resume = '--resume' in sys.argv
    sample = None
    if '--sample' in sys.argv:
        idx = sys.argv.index('--sample')
        if idx + 1 < len(sys.argv):
            sample = int(sys.argv[idx + 1])

    category_filter = None
    if '--category' in sys.argv:
        idx = sys.argv.index('--category')
        if idx + 1 < len(sys.argv):
            category_filter = sys.argv[idx + 1]

    asin_filter = None
    if '--asin' in sys.argv:
        idx = sys.argv.index('--asin')
        if idx + 1 < len(sys.argv):
            asin_filter = sys.argv[idx + 1]

    print(f"🖋️  Ink LLM Review Rewriter — {datetime.now().strftime('%H:%M:%S SGT')}")
    print(f"   Model: {DEEPSEEK_MODEL} | Workers: {N_CONCURRENT} | Checkpoint: every {CHECKPOINT_EVERY}")
    if dry_run:
        print("   Mode: DRY RUN — no files will be written")
    print()

    # Find all reviews
    all_reviews = sorted(CONTENT_DIR.glob("**/*.md"))
    all_reviews = [p for p in all_reviews if any(
        parent.name in CATEGORY_LABEL for parent in p.parents
    )]

    print(f"📁 Found {len(all_reviews)} total review files")

    # Filter by size (skip already long-form)
    to_process = []
    skipped_size = 0
    for path in all_reviews:
        size = path.stat().st_size
        if size > MIN_BYTES:
            skipped_size += 1
        else:
            to_process.append(path)

    print(f"   {skipped_size} already long-form (> {MIN_BYTES}B, skipping)")
    print(f"   {len(to_process)} template reviews to rewrite")

    # Category filter
    if category_filter:
        to_process = [p for p in to_process
                      if p.relative_to(CONTENT_DIR).parts[0] == category_filter]
        print(f"   Filtered to category: {category_filter} → {len(to_process)} reviews")

    # ASIN filter
    if asin_filter:
        to_process = [p for p in to_process
                      if read_existing_review(p)[0].get('asin') == asin_filter]
        if to_process:
            print(f"   Found ASIN {asin_filter}")
        else:
            print(f"   ⚠️  ASIN {asin_filter} not found or already rewritten")
            return

    # Sample
    if sample:
        to_process = to_process[:sample]
        print(f"   SAMPLE: {len(to_process)} only")

    if dry_run:
        for p in to_process[:10]:
            meta, _ = read_existing_review(p)
            print(f"   Would rewrite: {meta['name'][:80]} ({p.stem[:50]})")
        if len(to_process) > 10:
            print(f"   ... and {len(to_process) - 10} more")
        # Cost estimate
        est = len(to_process) * 2500 * 1.5
        print(f"\n   Est. tokens: ~{est:,.0f} | Est. cost: ~${est * 0.0000011 + est * 0.7 * 0.00000027:.2f}")
        return

    # Resume from checkpoint
    done_set = load_checkpoint() if resume else set()
    if done_set:
        to_process = [p for p in to_process if p.stem not in done_set]
        print(f"   Resuming: {len(to_process)} remaining after checkpoint")

    if not to_process:
        print("   Nothing to do!")
        return

    stats["started"] = time.time()
    stats["total"] = len(to_process)

    print(f"\n🚀 Processing {len(to_process)} reviews...")
    est_sec = len(to_process) * 30 / N_CONCURRENT
    print(f"   Estimated time: {est_sec/60:.0f} min at {N_CONCURRENT}x concurrent", flush=True)

    # Process with thread pool
    done_slugs = set(done_set)
    batch_done = 0

    with ThreadPoolExecutor(max_workers=N_CONCURRENT) as ex:
        futures = {}

        for path in to_process:
            meta, _ = read_existing_review(path)
            bt = find_briefing(meta.get('asin'))

            fut = ex.submit(process_one, path, bt)
            futures[fut] = path.stem

            # Pace submissions
            if len(futures) >= N_CONCURRENT * 2:
                time.sleep(PACE_DELAY)

                # Check completions
                done_now = []
                for f in list(futures.keys()):
                    if f.done():
                        try:
                            s = f.result()
                            done_slugs.add(s)
                            done_now.append(s)
                        except Exception as e:
                            with stats_lock:
                                stats["errors"] += 1
                                stats["done"] += 1
                            print(f"  ❌ {futures[f]}: {e}")
                        del futures[f]

                if done_now:
                    batch_done += len(done_now)
                    elapsed = time.time() - stats["started"]
                    rate = batch_done / max(elapsed, 1) * 60
                    print(f"  [{batch_done}/{len(to_process)}] "
                          f"Latest: {done_now[-1][:40]} "
                          f"({elapsed/60:.0f}m, {rate:.0f}/min)")

                # Checkpoint
                if len(done_slugs) % CHECKPOINT_EVERY < N_CONCURRENT and len(done_slugs) > 0:
                    save_checkpoint(done_slugs)

        # Wait for remaining
        for f in as_completed(list(futures.keys())):
            try:
                s = f.result()
                done_slugs.add(s)
            except Exception as e:
                with stats_lock:
                    stats["errors"] += 1
                    stats["done"] += 1
                print(f"  ❌ {futures[f]}: {e}")

    # Final checkpoint
    save_checkpoint(done_slugs)

    # Report
    elapsed = time.time() - stats["started"]
    print(f"\n✅ Done in {elapsed/60:.0f}m")
    print(f"   Rewritten: {stats['done']}")
    print(f"   Errors: {stats['errors']}")
    print(f"   Total tokens: {stats['tokens']:,}")
    est_cost = stats['tokens'] * 0.0000011 + stats['tokens'] * 0.7 * 0.00000027
    print(f"   Est cost: ${est_cost:.2f}")


if __name__ == "__main__":
    main()
