#!/opt/homebrew/bin/python3
"""
ink_llm_writer.py — LLM-powered review writer for the daily pipeline.

Reads a single scraped Amazon briefing JSON, generates a DeepSeek-chat review,
and writes it to the correct content/<category>/<slug>-review.md.

Design: single-review, called once per briefing by the pipeline runner.
Same architecture as Til's generate_review.py — stdin JSON or --file path.

Usage:
    python3 scripts/ink_llm_writer.py <briefing_json_path>
    cat briefing.json | python3 scripts/ink_llm_writer.py
    python3 scripts/ink_llm_writer.py --dry-run <briefing_json_path>  # preview only

Output: path to written review file (stdout), stats (stderr).
"""

import os, sys, json, re, time
from datetime import date, datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

WORKSPACE = Path(__file__).resolve().parent.parent
CONTENT_DIR = WORKSPACE / "content"

AFFILIATE_TAG = "tsvglyc-20"
MAX_RETRIES = 2
API_TIMEOUT = 90
MAX_TOKENS = 2500
MIN_DATA_QUALITY = 0  # minimum review snippets needed to generate (0 = product data only)

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

CATEGORY_SHORT = {
    'coffee': 'Coffee & Drinks',
    'kitchen': 'Kitchen & Cooking',
    'home-office': 'Home Office',
    'home-improvement': 'Home Improvement',
    'luxury-beauty': 'Luxury Beauty',
    'pet-supplies': 'Pet Supplies',
    'furniture': 'Furniture',
    'sports-fitness': 'Sports & Fitness',
    'toys-games': 'Toys & Games',
    'patio-lawn-garden': 'Patio & Garden',
}

CAT_KEYWORDS = {
    'coffee': ['coffee maker review', 'espresso machine', 'best coffee gear'],
    'kitchen': ['kitchen appliance review', 'best kitchen gadget', 'cookware review'],
    'home-office': ['home office review', 'best office chair', 'desk accessory review'],
    'home-improvement': ['tool review', 'hardware review', 'home improvement product'],
    'luxury-beauty': ['luxury beauty review', 'best skincare', 'premium beauty product'],
    'pet-supplies': ['pet supply review', 'best pet product', 'dog essentials review'],
    'furniture': ['furniture review', 'home furnishing', 'best furniture'],
    'sports-fitness': ['sports equipment review', 'fitness gear review', 'workout equipment'],
    'toys-games': ['toy review', 'game review', 'best kids toy'],
    'patio-lawn-garden': ['patio review', 'garden tool review', 'outdoor product review'],
}


# ── Helpers ───────────────────────────────────────────────────────

def make_slug(title, asin):
    """Generate clean review slug — title-based with ASIN suffix."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    words = slug.split('-')
    if len(words) > 10:
        words = words[:10]
    return '-'.join(words) + '-' + asin.lower() + '-review'


def yq(s):
    """YAML-safe quoted string."""
    return str(s).replace('"', '\\"')


def load_briefing(path):
    """Load and validate briefing JSON. Returns dict or None."""
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        # Minimum viable data
        title = data.get('title', '') or data.get('name', '')
        reviews = data.get('reviews', [])
        if not title:
            return None
        return data
    except Exception:
        return None


def extract_reviews(briefing):
    """Extract top positive + critical review text from briefing."""
    reviews = briefing.get('reviews', [])
    if not reviews:
        return [], []

    sorted_revs = sorted(reviews, key=lambda r: float(r.get('rating', 0)), reverse=True)
    top_pos = [r for r in sorted_revs if float(r.get('rating', 0)) >= 4][:3]
    critical = [r for r in sorted_revs if float(r.get('rating', 0)) <= 3][:2]
    return top_pos, critical


def gather_product_data(briefing):
    """Extract all product metadata from briefing into a clean dict."""
    title = briefing.get('title', '') or briefing.get('name', '')
    asin = briefing.get('asin', '')
    price = briefing.get('price', '') or briefing.get('list_price', '')
    if isinstance(price, (int, float)):
        price = f"${price:.2f}"
    rating = briefing.get('rating', 0) or briefing.get('amazon_rating', 0)
    review_count = briefing.get('review_count', 0) or briefing.get('reviews_count', 0)
    image = briefing.get('image', '') or briefing.get('main_image', '')
    category = briefing.get('category', 'kitchen')
    brand = briefing.get('brand', '')

    # Normalize
    try:
        rating = round(float(rating), 1)
    except (ValueError, TypeError):
        rating = 4.0
    try:
        review_count = int(review_count)
    except (ValueError, TypeError):
        review_count = 0

    verdict = round(rating * 0.95, 1) if rating > 3 else round(rating, 1)
    verdict = min(5.0, max(1.0, verdict))

    return {
        'title': title.strip(),
        'asin': asin,
        'price': price,
        'rating': rating,
        'review_count': review_count,
        'image': image,
        'category': category,
        'cat_label': CATEGORY_LABEL.get(category, 'product'),
        'cat_short': CATEGORY_SHORT.get(category, 'Kitchen'),
        'brand': brand,
        'verdict': verdict,
        'slug': make_slug(title, asin),
    }


# ── Prompt builder ─────────────────────────────────────────────────

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


def build_prompt(data, briefing):
    """Build the review prompt with all product data and customer quotes."""
    name = data['title']
    asin = data['asin']
    cat_label = data['cat_label']
    rating = data['rating']
    verdict = data['verdict']
    review_count = data['review_count']
    price = data['price'] or 'Check price on Amazon'
    image = data['image']
    slug = data['slug']
    stars = '⭐' * round(rating)
    today = date.today().isoformat()
    cat_keywords = CAT_KEYWORDS.get(data['category'], [])
    cat_short = data['cat_short']

    # Customer review quotes
    top_pos, critical = extract_reviews(briefing)
    quotes_text = ""
    if top_pos or critical:
        quotes_text = "\n## REAL CUSTOMER REVIEWS (quote these naturally in your review)\n"
        for r in top_pos:
            text = (r.get('text', '') or r.get('review', '') or '')[:250].strip()
            name_r = r.get('name', '') or r.get('reviewer', '') or 'Verified Buyer'
            ra = r.get('rating', '')
            if text:
                quotes_text += f'\n"{text}" — {name_r} ({ra}★)\n'
        for r in critical:
            text = (r.get('text', '') or r.get('review', '') or '')[:250].strip()
            name_r = r.get('name', '') or r.get('reviewer', '') or 'Verified Buyer'
            ra = r.get('rating', '')
            if text:
                quotes_text += f'\n"{text}" — {name_r} ({ra}★)\n'

    return f"""Write a professional product review for: {name} ({cat_short})

PRODUCT DATA:
- Category: {cat_label}
- Amazon rating: {rating}/5 ({stars}) with {review_count:,} ratings
- Price: {price}
- ASIN: {asin}
- Verdict score: {verdict}/5
{quotes_text}

FRONTMATTER (fill all fields precisely):
---
title: "{name}"
seo_title: "[55-65 char SEO title — keyword-rich, include 'Review']"
meta_description: "[140-155 char meta description — compelling, keyword-optimized]"
slug: "{slug}"
image_alt: "[Descriptive alt text for the {cat_label} product image]"
verdict_score: {verdict}
date: {today}
price: {price}
review_count: {review_count}
amazon_rating: {rating}
amazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"
amazon_image: "{image}"
categories:
  - {cat_short}
keywords:
  - "{cat_keywords[0]}"
  - "{cat_keywords[1]}"
pros:
  - "[Specific, concrete pro — not generic]"
  - "[Specific pro 2]"
  - "[Specific pro 3]"
cons:
  - "[Specific, honest con — not dismissive]"
  - "[Specific con 2]"
---

Write the full review body now. This is a {cat_label} with {review_count:,}+ Amazon ratings at {rating}/5 average. Give shoppers the real story.

IMPORTANT: No ![image](...) markdown tags. Vary structure naturally."""


# ── API caller ─────────────────────────────────────────────────────

def call_deepseek(system_prompt, user_prompt):
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=API_TIMEOUT)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=MAX_TOKENS,
            )
            text = resp.choices[0].message.content
            tokens = resp.usage.total_tokens if resp.usage else 0
            return text, tokens
        except Exception as e:
            err = str(e)
            if attempt < MAX_RETRIES:
                wait = (attempt + 1) * 3
                print(f"  ⚠️ API attempt {attempt+1} failed — retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                raise RuntimeError(f"DeepSeek API failed after {MAX_RETRIES+1} attempts: {err[:200]}")

    return None, 0


# ── Response parser ───────────────────────────────────────────────

def clean_output(text, data):
    """Parse LLM output, fix frontmatter, strip inline images, inject affiliate CTA."""
    slug = data['slug']
    name = data['title']
    asin = data['asin']

    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if not fm_match:
        # LLM didn't follow format — inject frontmatter
        today = date.today().isoformat()
        fm = f"""---
title: "{name}"
seo_title: "{name} Review: Is It Worth It? ({data['verdict']}/5 Verdict)"
meta_description: "Honest {name} review. We tested it, read Amazon reviews, and give you the real verdict. {data['verdict']}/5 stars."
slug: "{slug}"
image_alt: "{name} product image"
verdict_score: {data['verdict']}
date: {today}
price: {data['price']}
review_count: {data['review_count']}
amazon_rating: {data['rating']}
amazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"
amazon_image: "{data['image']}"
categories:
  - {data['cat_short']}
pros:
  - ""
cons:
  - ""
keywords:
  - ""
---
"""
        return fm + text

    fm_block = fm_match.group(1)
    body = fm_match.group(2)

    # Fix numeric fields
    fm_block = re.sub(r'verdict_score:\s*[\d.]+', f'verdict_score: {data["verdict"]}', fm_block)
    fm_block = re.sub(r'amazon_rating:\s*[\d.]+', f'amazon_rating: {data["rating"]}', fm_block)
    fm_block = re.sub(r'review_count:\s*\d+', f'review_count: {data["review_count"]}', fm_block)

    # Ensure essential fields
    if 'slug:' not in fm_block:
        fm_block += f'\nslug: "{slug}"'
    if 'amazon_url:' not in fm_block and asin:
        fm_block += f'\namazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"'
    if 'amazon_image:' not in fm_block and data.get('image'):
        fm_block += f'\namazon_image: "{data["image"]}"'

    # Strip inline images, cleanup whitespace
    body = re.sub(r'!\[.*?\]\([^)]+\)', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Affiliate CTA footer
    cta = f"""\n## Where to Buy\n\n👉 **[Check Price on Amazon →](https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG})**\n\n*We earn a small commission at no extra cost to you — this helps fund more honest reviews.*\n"""
    footer = f"""\n---\n*Last updated: {date.today().isoformat()}. Ratings and prices current as of review date. Verify on Amazon before purchasing.*\n"""

    return f"---\n{fm_block.strip()}\n---\n\n{body.strip()}\n{cta}{footer}"


# ── Writer ─────────────────────────────────────────────────────────

def write_review(md_text, data):
    """Write review to content/<category>/<slug>.md"""
    category = data['category']
    slug = data['slug']
    out_dir = CONTENT_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.md"
    path.write_text(md_text, encoding='utf-8')
    return path


# ── Main ───────────────────────────────────────────────────────────

def generate_review(briefing_path):
    """Generate a single LLM review from a briefing JSON. Returns output path."""
    briefing = load_briefing(briefing_path)
    if not briefing:
        raise ValueError(f"Insufficient data in {briefing_path}")

    data = gather_product_data(briefing)

    # Check if already published
    existing, existing_path = asin_already_exists(data['asin'])
    if existing:
        print(f"  ⏭️  {data['title'][:60]} already published at {existing_path}", file=sys.stderr)
        return None

    # Build prompts
    system_prompt = SYSTEM_PROMPT
    user_prompt = build_prompt(data, briefing)

    # Call LLM
    start = time.time()
    raw_text, tokens = call_deepseek(system_prompt, user_prompt)
    elapsed = time.time() - start

    # Parse and clean
    md_text = clean_output(raw_text, data)

    # Write
    path = write_review(md_text, data)

    print(f"  ✅ {data['title'][:60]} in {elapsed:.0f}s ({tokens} tokens)", file=sys.stderr)
    return str(path)


def asin_already_exists(asin):
    """Check if an ASIN is already published anywhere in content/."""
    if not asin:
        return False, None
    for root, dirs, files in os.walk(CONTENT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    text = fh.read()
                if f"/dp/{asin}/" in text or f"/dp/{asin}?" in text:
                    return True, path
            except Exception:
                continue
    return False, None


def main():
    dry_run = '--dry-run' in sys.argv

    # Determine input source
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    briefing_path = args[0] if args else None

    if not briefing_path:
        print("Usage: ink_llm_writer.py <briefing.json> [--dry-run]", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(briefing_path):
        print(f"Error: file not found: {briefing_path}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        briefing = load_briefing(briefing_path)
        if not briefing:
            print("❌ Insufficient data for review", file=sys.stderr)
            sys.exit(1)
        data = gather_product_data(briefing)
        print(json.dumps(data, indent=2))
        return

    try:
        path = generate_review(briefing_path)
        if path:
            print(path)
    except Exception as e:
        print(f"❌ Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
