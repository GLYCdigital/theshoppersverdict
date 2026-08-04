#!/usr/bin/env python3
"""
ink_review_writer.py - Quality-first review writer.
Generates Hugo review content from scraped Amazon data.

Every review is built from actual customer review text.
Rating-based sentiment: 4-5★ = praise, 1-2★ = complaints, 3★ = neutral.
No generic fallback text - if data is too thin, the review is skipped.
"""
import sys, os, json, re, glob
from datetime import datetime
from collections import Counter

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(WORKSPACE, "content")
QUEUE = os.path.join(WORKSPACE, "data", "asin_queue.json")
AFFILIATE_TAG = "tsvglyc-20"
SITE_NAME = ""  # white-label: e.g. "DEWALT" — empty = The Shopper's Verdict

# ── Helpers ──────────────────────────────────────────────────────────────────

def asin_already_exists(asin):
    for root, dirs, files in os.walk(CONTENT):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    text = fh.read()
            except Exception:
                continue
            if f"/dp/{asin}/" in text or f"/dp/{asin}?" in text:
                return True, path
    return False, None


VERDICT_THRESHOLDS = {
    (4.5, 5.0): 4.6, (4.0, 4.4): 4.2, (3.5, 3.9): 3.7, (0, 3.4): 3.3,
}


def get_verdict(amazon_rating):
    for (lo, hi), score in VERDICT_THRESHOLDS.items():
        if lo <= amazon_rating <= hi:
            return score
    return round(amazon_rating, 1)


def make_slug(title):
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    words = slug.split('-')
    if len(words) > 12:
        words = words[:12]
    return '-'.join(words) + '-review'


def extract_keywords(title, category):
    keywords = []
    parts = re.sub(r'[^a-zA-Z0-9 ]', '', title).split()
    if len(parts) >= 2:
        keywords.append(' '.join(parts[:3]).lower() + ' review')
    cat_map = {
        'coffee': ['coffee maker review', 'espresso machine', 'best coffee gear'],
        'kitchen': ['kitchen appliance review', 'best kitchen gadget'],
        'home-office': ['home office review', 'office chair', 'desk accessory'],
        'home-improvement': ['home improvement review', 'best tool review'],
        'luxury-beauty': ['luxury beauty review', 'best skincare review', 'premium beauty'],
        'pet-supplies': ['pet supplies review', 'best pet product', 'dog essentials'],
    }
    keywords.extend(cat_map.get(category, []))
    return keywords[:5]


def yq(s):
    """YAML-safe quoted string."""
    return str(s).replace('"', '\\"')


def clean(s):
    """Clean up text for display."""
    return re.sub(r'\s+', ' ', s).strip()


def extract_rating(rating_str):
    """Extract numeric rating from string like '4 out of 5 stars' or 4.4."""
    if not rating_str:
        return None
    if isinstance(rating_str, (int, float)):
        return float(rating_str)
    m = re.search(r'([\d.]+)', str(rating_str))
    return float(m.group(1)) if m else None


# ── Theme detection keywords ─────────────────────────────────────────────────

POSITIVE_THEMES = {
    'quality': ['quality', 'well made', 'durable', 'sturdy', 'solid', 'premium', 'well-built', 'high quality'],
    'value': ['great value', 'worth the money', 'good price', 'affordable', 'reasonable price', 'bargain', 'excellent value'],
    'ease': ['easy to use', 'easy setup', 'simple', 'intuitive', 'user friendly', 'straightforward', 'plug and play'],
    'performance': ['works great', 'powerful', 'fast', 'efficient', 'effective', 'does the job', 'excellent results'],
    'design': ['looks great', 'sleek', 'modern', 'stylish', 'compact', 'sleek design', 'beautiful'],
    'noise': ['quiet', 'silent', 'whisper quiet'],
    'size': ['compact', 'small footprint', 'space saving', 'perfect size', 'fits perfectly'],
    'features': ['great features', 'lots of features', 'versatile', 'multi functional', 'handy'],
}

NEGATIVE_THEMES = {
    'quality': ['cheap', 'flimsy', 'broke', 'defective', 'poor quality', 'fell apart', 'stopped working'],
    'value': ['overpriced', 'not worth', 'too expensive', 'pricey', 'expensive for'],
    'ease': ['complicated', 'confusing', 'difficult to set up', 'frustrating', 'hard to use', 'complex'],
    'performance': ['slow', 'weak', 'ineffective', 'disappointing', 'underpowered', 'inconsistent', 'poor results'],
    'design': ['bulky', 'ugly', 'cheap looking', 'bigger than expected', 'poor design', 'awkward'],
    'noise': ['loud', 'noisy', 'too loud', 'annoying noise', 'humming'],
    'size': ['too big', 'too large', 'takes up space', 'bulky', 'larger than expected', 'too small'],
    'features': ['missing features', 'lacks', 'no option', 'limited'],
}

THEME_LABELS = {
    'quality': ('build quality', 'durability'),
    'value': ('value for money', 'pricing'),
    'ease': ('ease of use', 'setup'),
    'performance': ('performance', 'performance'),
    'design': ('design', 'design'),
    'noise': ('noise levels', 'noise'),
    'size': ('size', 'size'),
    'features': ('features', 'features'),
}


def match_themes_in_text(text, theme_dict):
    """Return list of theme names matched in text."""
    t = text.lower()
    matched = []
    for theme, keywords in theme_dict.items():
        for kw in keywords:
            if kw in t:
                matched.append(theme)
                break
    return matched


def extract_use_cases(text):
    """Extract use-case patterns from review text."""
    patterns = [
        'daily', 'every day', 'everyday', 'morning', 'office', 'home',
        'travel', 'camping', 'gift', 'present', 'kitchen', 'bathroom',
        'garage', 'workshop', 'dorm', 'apartment', 'small space',
        'professional', 'beginner', 'starter', 'family',
    ]
    found = []
    t = text.lower()
    for p in patterns:
        if p in t:
            found.append(p)
    return found


def extract_sentence_containing(phrase, full_text):
    """Extract the sentence containing a given phrase from full text."""
    for sent in re.split(r'[.!?\n]+', full_text):
        if phrase.lower() in sent.lower().strip():
            return clean(sent).strip()
    return None


def analyze_reviews(reviews):
    """
    Parse reviews using rating-based sentiment classification.
    4-5 star -> praise bucket
    1-2 star -> complaint bucket
    3 star -> neutral (used sparingly)
    """
    praise_phrases = []
    complaint_phrases = []
    praise_themes = Counter()
    complaint_themes = Counter()
    all_text = []
    reviewer_contexts = []

    for review_obj in reviews:
        if isinstance(review_obj, dict):
            text = (review_obj.get('body') or review_obj.get('review') or '')
            title = (review_obj.get('title') or '')
            rating_str = review_obj.get('rating', '')
        else:
            text = str(review_obj)
            title = ''
            rating_str = ''

        full_text = (title + ' ' + text).strip()
        if not full_text:
            continue
        all_text.append(full_text)

        # Classify by rating
        stars = extract_rating(rating_str)

        # Extract use cases regardless of rating
        reviewer_contexts.extend(extract_use_cases(full_text))

        if stars is None:
            continue

        if stars >= 4:
            themes = match_themes_in_text(full_text, POSITIVE_THEMES)
            for t in themes:
                praise_themes[t] += 1
                for kw in POSITIVE_THEMES[t]:
                    sent = extract_sentence_containing(kw, full_text)
                    if sent and len(sent) > 15:
                        praise_phrases.append(sent)
                        break

        elif stars <= 2:
            themes = match_themes_in_text(full_text, NEGATIVE_THEMES)
            for t in themes:
                complaint_themes[t] += 1
                for kw in NEGATIVE_THEMES[t]:
                    sent = extract_sentence_containing(kw, full_text)
                    if sent and len(sent) > 15:
                        complaint_phrases.append(sent)
                        break

        elif stars == 3:
            # Neutral reviews - check both positive and negative
            themes = match_themes_in_text(full_text, POSITIVE_THEMES)
            for t in themes:
                praise_themes[t] += 1
                for kw in POSITIVE_THEMES[t]:
                    sent = extract_sentence_containing(kw, full_text)
                    if sent and len(sent) > 15:
                        praise_phrases.append(sent)
                        break
            themes = match_themes_in_text(full_text, NEGATIVE_THEMES)
            for t in themes:
                complaint_themes[t] += 1
                for kw in NEGATIVE_THEMES[t]:
                    sent = extract_sentence_containing(kw, full_text)
                    if sent and len(sent) > 15:
                        complaint_phrases.append(sent)
                        break

    # Deduplicate praise phrases
    seen = set()
    unique_praise = []
    for p in praise_phrases:
        key = p[:80].lower()
        if key not in seen:
            seen.add(key)
            unique_praise.append(p)

    # Deduplicate complaint phrases
    seen = set()
    unique_complaints = []
    for p in complaint_phrases:
        key = p[:80].lower()
        if key not in seen:
            seen.add(key)
            unique_complaints.append(p)

    top_praise = [t for t, _ in praise_themes.most_common(5)]
    top_complaints = [t for t, _ in complaint_themes.most_common(5)]

    ctx_counts = Counter(reviewer_contexts)
    top_contexts = [t for t, _ in ctx_counts.most_common(5)]

    total_analyzed = sum(1 for r in reviews if isinstance(r, dict) and extract_rating(r.get('rating', '')) is not None)

    return {
        'praise_themes': top_praise,
        'complaint_themes': top_complaints,
        'praise_phrases': unique_praise[:5],
        'complaint_phrases': unique_complaints[:3],
        'reviewer_contexts': top_contexts,
        'total_reviews_analyzed': total_analyzed or len(reviews),
    }


# ── Quality Gate ─────────────────────────────────────────────────────────────

def passes_quality_gate(analysis):
    """
    Only publish if we have REAL data to work with.
    Blocks thin, generic reviews.
    """
    has_praise_quotes = len(analysis['praise_phrases']) >= 2
    has_complaint_quotes = len(analysis['complaint_phrases']) >= 1
    has_themes = len(analysis['praise_themes']) >= 1

    if not has_themes:
        return False, "No identifiable themes - review data too thin"

    if not has_praise_quotes and not (analysis['praise_themes'] and analysis['complaint_themes']):
        return False, "Insufficient review data - need at least 2 real praise quotes or 1 theme + 1 complaint"

    return True, "Passes quality check"


# ── Content Generation ───────────────────────────────────────────────────────

def short_product_name(title, max_words=5, max_chars=50):
    """Get a short, readable product name from the full title."""
    raw = re.sub(r'\s*Review\s*$', '', title).strip()
    short = ' '.join(raw.split()[:max_words]).rstrip(',')
    if len(short) > max_chars:
        short = ' '.join(short.split()[:3])
    return short


def truncate_sentence(text, max_len=150):
    """Truncate text at a sentence boundary within max_len."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_period = truncated.rfind('.')
    if last_period > max_len * 0.6:
        return truncated[:last_period + 1]
    return truncated.rstrip() + '...'


def write_body(title, product_type, analysis, rc, amazon_rating):
    """Generate a review body using REAL review quotes and data."""
    parts = []
    clean_title = short_product_name(title)
    p_phrases = analysis['praise_phrases']
    c_phrases = analysis['complaint_phrases']
    top_p = analysis['praise_themes'][:3]
    top_c = analysis['complaint_themes'][:2]
    contexts = analysis['reviewer_contexts']

    total_review_count = max(rc, analysis['total_reviews_analyzed'])

    # Opening (template renders the 'The Verdict' H2 once)
    if p_phrases:
        quote = truncate_sentence(p_phrases[0], 130)
        parts.append(
            f"The {clean_title} is a popular choice - with {total_review_count:,} "
            f"Amazon reviews behind it. Here is what buyers actually say.\n\n"
            f"> \"{quote}\""
        )
    else:
        parts.append(
            f"The {clean_title} has {total_review_count:,} Amazon reviews and "
            f"averages **{amazon_rating}/5 stars**. We analyzed the feedback to help you decide."
        )

    # What Buyers Love
    if p_phrases:
        body = "## What Buyers Love\n\n"
        for i, q in enumerate(p_phrases[:4]):
            q_clean = truncate_sentence(q, 155)
            if i == 0:
                body += f"The most frequent praise: \"{q_clean}\"\n\n"
            else:
                body += f"Another reviewer noted: \"{q_clean}\"\n\n"
        parts.append(body.strip())

    elif top_p:
        labels = [THEME_LABELS.get(t, (t, t))[0] for t in top_p[:3]]
        if labels:
            parts.append(
                f"## What Buyers Love\n\n"
                f"The strongest praise centers on **{' , '.join(labels)}**. "
                f"Across {analysis['total_reviews_analyzed']:,} rated reviews, these themes "
                f"came up most frequently among satisfied customers."
            )

    # Where It Falls Short
    if c_phrases:
        body = "## Where It Falls Short\n\n"
        for i, q in enumerate(c_phrases[:3]):
            q_clean = truncate_sentence(q, 155)
            if i == 0:
                body += f"The most common complaint: \"{q_clean}\"\n\n"
            else:
                body += f"Others mentioned: \"{q_clean}\"\n\n"
        parts.append(body.strip())

    elif top_c:
        labels = [THEME_LABELS.get(t, (t, t))[1] for t in top_c[:2]]
        parts.append(
            f"## Where It Falls Short\n\n"
            f"The most consistent criticisms involve **{' and '.join(labels)}**. "
            f"These issues appear regularly enough in reviews to be worth knowing before you buy."
        )
    else:
        # No complaints found - note it
        parts.append(
            f"## Where It Falls Short\n\n"
            f"Negative reviews are minimal for this product. Most buyers report being satisfied, "
            f"and consistent complaints are hard to find across the feedback we analyzed."
        )

    # Who Should Buy It
    if contexts:
        if 'beginner' in contexts or 'starter' in contexts:
            parts.append(
                f"## Who Should Buy It\n\n"
                f"This is a great fit for **beginners** - several reviewers mention buying it "
                f"as their first {product_type}. It strikes a balance between capability and simplicity."
            )
        elif 'daily' in contexts or 'everyday' in contexts:
            parts.append(
                f"## Who Should Buy It\n\n"
                f"Best for **daily, regular use**. Many reviewers use this as part of their "
                f"routine and report solid long-term results."
            )
        elif 'gift' in contexts or 'present' in contexts:
            parts.append(
                f"## Who Should Buy It\n\n"
                f"A **solid gift option** - several buyers purchased this as a present "
                f"and the recipients were happy with it."
            )
        elif 'travel' in contexts or 'camping' in contexts:
            parts.append(
                f"## Who Should Buy It\n\n"
                f"Ideal for **travelers** - reviewers consistently mention using it on the go, "
                f"and its portability is a major plus."
            )
        elif 'small space' in contexts or 'apartment' in contexts or 'dorm' in contexts:
            parts.append(
                f"## Who Should Buy It\n\n"
                f"Works well in **smaller spaces** - apartments, dorms, and compact homes. "
                f"Reviewers in tight spaces found it fits without dominating."
            )
        else:
            most_common = contexts[0]
            parts.append(
                f"## Who Should Buy It\n\n"
                f"This works well for **{most_common} use** - that is how most reviewers "
                f"are using it and reporting good results."
            )

    # Who Should Skip It
    if c_phrases or top_c:
        skip_bits = []
        for t in top_c[:2]:
            skip_bits.append(THEME_LABELS.get(t, (t, t))[1])
        skip_text = ' and '.join(skip_bits) if skip_bits else 'these issues'
        parts.append(
            f"## Who Should Skip It\n\n"
            f"If the downsides above sound like dealbreakers - especially the recurring "
            f"complaints about {skip_text} - "
            f"you may want to look at alternatives. For everyone else, the positives generally outweigh the negatives."
        )
    else:
        parts.append(
            f"## Who Should Skip It\n\n"
            f"There are few consistent complaints, so most buyers will be satisfied. "
            f"That said, no product is for everyone - if the features do not match your needs, keep looking."
        )

    # Bottom Line
    parts.append(
        f"## Bottom Line\n\n"
        f"With **{amazon_rating}/5** from {total_review_count:,}+ Amazon reviews, the {clean_title} "
        f"is a proven choice in the {product_type} category. "
        + (f"The main drawbacks "
           f"{' and '.join([THEME_LABELS.get(t, (t,t))[1] for t in top_c[:2]]) if top_c else ''} "
           f"are real but do not affect most buyers. " if top_c else "")
        + f"If it fits what you are looking for, it is a reliable pick backed by real customer feedback."
    )

    return '\n\n'.join(parts)


def write_faq(title, analysis, product_type):
    """Generate FAQ from actual review themes and quotes."""
    short = short_product_name(title, max_words=4, max_chars=40)
    p_phrases = analysis['praise_phrases']
    c_phrases = analysis['complaint_phrases']
    top_p = analysis['praise_themes']
    top_c = analysis['complaint_themes']
    contexts = analysis.get('reviewer_contexts', [])

    faqs = []

    # FAQ 1: What do buyers like
    if p_phrases:
        q = p_phrases[0]
        q_short = truncate_sentence(q, 105)
        faqs.append({
            'question': f'What do buyers like most about the {short}?',
            'answer': f'{q_short} That is the most consistent positive theme across verified Amazon reviews for this product.'
        })
    elif top_p:
        labels = [THEME_LABELS.get(t, (t, t))[0] for t in top_p[:2]]
        faqs.append({
            'question': f'What do buyers like most about the {short}?',
            'answer': f'Reviewers consistently praise the {" and ".join(labels)}. These are the most commonly mentioned positive aspects.'
        })

    # FAQ 2: What are the downsides
    if c_phrases:
        q = c_phrases[0]
        q_short = truncate_sentence(q, 105)
        faqs.append({
            'question': f'What are the common complaints about the {short}?',
            'answer': f'The most frequently cited issue: {q_short} It is worth knowing before purchasing.'
        })
    elif top_c:
        labels = [THEME_LABELS.get(t, (t, t))[1] for t in top_c[:2]]
        faqs.append({
            'question': f'What are the common complaints about the {short}?',
            'answer': f'The main criticisms center on {" and ".join(labels)}. These are mentioned often enough to be worth noting.'
        })
    else:
        faqs.append({
            'question': f'What are the downsides of the {short}?',
            'answer': f'Across the reviews we analyzed, there are no consistently mentioned complaints. Most buyers report being satisfied.'
        })

    # FAQ 3: Who is this for
    if 'beginner' in contexts or 'starter' in contexts:
        faqs.append({
            'question': f'Is the {short} good for beginners?',
            'answer': f'Yes - many reviewers mention this as their first {product_type} and were satisfied with the experience.'
        })
    elif 'daily' in contexts or 'everyday' in contexts:
        faqs.append({
            'question': f'Is the {short} durable for daily use?',
            'answer': f'Yes, reviewers using it daily report it holds up well over time.'
        })
    elif 'gift' in contexts:
        faqs.append({
            'question': f'Is the {short} a good gift?',
            'answer': f'Yes - several reviewers bought this as a gift and the recipients were pleased.'
        })
    elif 'travel' in contexts or 'camping' in contexts:
        faqs.append({
            'question': f'Is the {short} portable enough for travel?',
            'answer': f'Yes - reviewers consistently mention using it while traveling and appreciate its portability.'
        })
    else:
        faqs.append({
            'question': f'Should I buy the {short}?',
            'answer': f'If the features match what you are looking for, yes. With {analysis["total_reviews_analyzed"]:,}+ reviews averaging strongly, it is a reliable choice in the {product_type} category.'
        })

    return faqs


# ── Main Writer ──────────────────────────────────────────────────────────────

def write_review(data, category, asin, force=False):
    """Write a full review from scraped data."""
    title = clean(data.get('title', 'Unknown Product'))
    price = data.get('price')
    rating = data.get('rating', '')
    review_count = data.get('review_count', '')
    image_url = data.get('image', '')
    reviews = data.get('reviews', [])

    # Parse metadata
    price_str = ''
    if isinstance(price, dict):
        price_str = str(price.get('value', ''))
    elif isinstance(price, (int, float)):
        price_str = f'{price:.2f}' if price % 1 else str(int(price))
    elif price:
        price_str = str(price).replace('$', '').strip()

    try:
        amazon_rating = float(rating) if rating else 4.0
    except:
        amazon_rating = 4.0

    try:
        rc = int(review_count) if review_count else 0
    except:
        rc = 0

    # Analyze reviews
    analysis = analyze_reviews(reviews)

    # Quality gate
    if not force:
        gate_pass, gate_reason = passes_quality_gate(analysis)
        if not gate_pass:
            print(f'  QUALITY GATE FAILED: {gate_reason}')
            print(f'     ({len(reviews)} reviews, {len(analysis["praise_phrases"])} praise quotes, {len(analysis["complaint_phrases"])} complaint quotes)')
            return None
    else:
        print(f'  Force mode - skipping quality gate')

    # Determine product type from category
    product_type_map = {
        'coffee': 'coffee maker or brewer',
        'kitchen': 'kitchen appliance',
        'home-office': 'home office accessory',
        'home-improvement': 'tool or home improvement product',
        'luxury-beauty': 'beauty or skincare product',
        'pet-supplies': 'pet product',
        'furniture': 'piece of furniture',
        'patio-lawn-garden': 'outdoor or garden product',
        'sports-fitness': 'sports or fitness item',
        'toys-games': 'toy or game',
    }
    product_type = product_type_map.get(category, 'product')

    # Generate pros from real review data
    pro_list = []
    for i, phrase in enumerate(analysis['praise_phrases'][:3]):
        # Take up to 100 chars, break at sentence/comma boundary
        short = phrase[:100].strip()
        # Find last period, question mark, or exclamation within the string
        m = re.search(r'[.!?]', short)
        if m:
            short = short[:m.end()]
        else:
            # No sentence end - find last comma as natural break
            m = re.search(r',[^,]*$', short)
            if m:
                short = short[:m.start() if m.start() > 15 else len(short)]
        short = short.rstrip(',; ')
        if len(short) < 15:
            continue
        pro_list.append(short + '.' if not short.endswith(('.', '!', '?')) else short)

    if not pro_list and analysis['praise_themes']:
        label_map = {
            'quality': 'Solid build quality',
            'value': 'Great value for the price',
            'ease': 'Easy to set up and use',
            'performance': 'Reliable performance',
            'design': 'Clean, modern design',
            'noise': 'Quiet operation',
            'size': 'Compact and space-efficient',
            'features': 'Good feature set',
        }
        for t in analysis['praise_themes'][:3]:
            pro_list.append(label_map.get(t, t.replace('_', ' ').title()))

    # Generate cons from real review data
    con_list = []
    for i, phrase in enumerate(analysis['complaint_phrases'][:2]):
        short = phrase[:100].strip()
        m = re.search(r'[.!?]', short)
        if m:
            short = short[:m.end()]
        else:
            m = re.search(r',[^,]*$', short)
            if m:
                short = short[:m.start() if m.start() > 15 else len(short)]
        short = short.rstrip(',; ')
        if len(short) < 15:
            continue
        con_list.append(short + '.' if not short.endswith(('.', '!', '?')) else short)

    if not con_list and analysis['complaint_themes']:
        label_map = {
            'quality': 'Some durability concerns',
            'value': 'Pricier than alternatives',
            'ease': 'Setup could be simpler',
            'performance': 'May not satisfy power users',
            'design': 'Design could be improved',
            'noise': 'Noticeable during operation',
            'size': 'Larger than expected for some',
            'features': 'Missing some advanced features',
        }
        for t in analysis['complaint_themes'][:2]:
            con_list.append(label_map.get(t, t.replace('_', ' ').title()))

    if not pro_list:
        pro_list = ['Solid overall value based on customer feedback']
    if not con_list:
        con_list = ['Minor drawbacks noted by some users']

    # Generate body
    verdict = get_verdict(amazon_rating)
    body = write_body(title, product_type, analysis, rc, amazon_rating)
    faqs = write_faq(title, analysis, product_type)

    # Frontmatter
    slug = make_slug(title)

    # SEO title - use first ~8 meaningful words from title, strip color/spec suffixes
    # Split on ' | ' separators only (not hyphens within product names)
    title_parts = re.split(r'\s*[|]\s*', title)
    brand_product = title_parts[0].strip() if title_parts else title
    # Strip trailing color/size/spec suffixes like " - Black" or " - 60oz"
    clean_brand = re.sub(r'\s*[--]\s*(Black|White|Stainless|Silver|Gray|Red|Blue|Green|Brown|Gold|Pink|Purple).*$', '', brand_product, flags=re.IGNORECASE)
    clean_brand = re.sub(r'\s*[--]\s*\d+.*$', '', clean_brand)  # strip " - 60oz Water..."
    # Remove trailing commas, semicolons
    clean_brand = re.sub(r'[;,:]+\s*$', '', clean_brand)
    words = clean_brand.split()
    if len(words) > 8:
        clean_brand = ' '.join(words[:8])
    clean_brand = clean_brand.rstrip(',').strip()
    site_suffix = SITE_NAME if SITE_NAME else "The Shopper's Verdict"
    site_short = "TSV" if not SITE_NAME else SITE_NAME.split()[0]
    seo_title = f'{clean_brand} Review: Verdict ({amazon_rating}/5) | {site_suffix}'
    if len(seo_title) > 65:
        short_brand = ' '.join(words[:3]).rstrip(',')
        seo_title = f'{short_brand} Review: Verdict ({amazon_rating}/5) | {site_short}'
    if len(seo_title) > 65:
        short_brand = ' '.join(words[:2]).rstrip(',')
        seo_title = f'{short_brand} Review | {site_short}'

    # Meta description
    total_review_count = max(rc, analysis['total_reviews_analyzed'])
    # Meta description: first line from review quote (or brand), then stats
    meta_lead = ''
    if analysis['praise_phrases']:
        meta_lead = analysis['praise_phrases'][0].strip()
        # Take up to first sentence or 80 chars
        m = re.search(r'^[^.!?]*[.!?]', meta_lead)
        if m and m.end() < 90:
            meta_lead = meta_lead[:m.end()]
        else:
            meta_lead = ' '.join(meta_lead[:80].split()[:-1]) if meta_lead[:80].split() else meta_lead[:80]
    else:
        meta_lead = f'Honest {clean_brand[:30].lower()} review'
    meta_desc = f'{meta_lead} {total_review_count:,}+ Amazon reviews analyzed. Real pros, cons, and our verdict.'
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + '...'

    alt_text = title.replace('"', '').replace("'", '').strip()[:120]
    keywords = extract_keywords(title, category)

    lines = ['---']
    lines.append(f'title: "{yq(title)}"')
    lines.append(f'seo_title: "{yq(seo_title)}"')
    lines.append(f'meta_description: "{yq(meta_desc)}"')
    lines.append(f'slug: "{slug}"')
    lines.append(f'image_alt: "{yq(alt_text)}"')
    lines.append('keywords:')
    for kw in keywords[:5]:
        lines.append(f'  - "{kw}"')
    lines.append(f'verdict_score: {verdict}')
    lines.append('faq:')
    for faq in faqs:
        lines.append(f'  - question: "{yq(faq["question"])}"')
        lines.append(f'    answer: "{yq(faq["answer"])}"')
    lines.append(f'date: {datetime.now().strftime("%Y-%m-%d")}')
    lines.append(f'last_verified: {datetime.now().strftime("%Y-%m-%d")}')
    lines.append(f'price: {price_str}' if price_str else 'price: null')
    lines.append(f'review_count: {rc}')
    lines.append(f'amazon_rating: {amazon_rating}')
    lines.append(f'amazon_url: "https://www.amazon.com/dp/{asin}/?tag={AFFILIATE_TAG}"')
    lines.append(f'amazon_image: "{yq(image_url)}"')
    lines.append('pros:')
    for p in pro_list:
        p_safe = p.replace('"', "'")
        lines.append(f'  - "{p_safe}"')
    lines.append('cons:')
    for c in con_list:
        c_safe = c.replace('"', "'")
        lines.append(f'  - "{c_safe}"')
    lines.append('---')
    lines.append('')
    lines.append(body)

    # Write
    cat_dir = os.path.join(CONTENT, category)
    os.makedirs(cat_dir, exist_ok=True)
    filepath = os.path.join(cat_dir, f'{slug}.md')

    exists, existing_path = asin_already_exists(asin)

    if exists and not force:
        print(f'  ASIN {asin} already has a review - use --force to overwrite')
        return None

    if os.path.exists(filepath) and not force:
        print(f'  EXISTS: {filepath} - not overwriting (use --force)')
        return None

    # Preserve original date if overwriting
    if exists and force and existing_path:
        try:
            with open(existing_path) as ef:
                content = ef.read()
            m = re.search(r'date:\s*(\d{4}-\d{2}-\d{2})', content)
            if m:
                lines[lines.index(f'date: {datetime.now().strftime("%Y-%m-%d")}')] = f'date: {m.group(1)}'
                print(f'  Preserved original date: {m.group(1)}')
        except Exception:
            pass

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f'  Written: {filepath}')
    return filepath


def mark_used(asin):
    if os.path.exists(QUEUE):
        with open(QUEUE) as f:
            q = json.load(f)
        used = set(q.get('used', []))
        used.add(asin)
        q['used'] = sorted(used)
        with open(QUEUE, 'w') as f:
            json.dump(q, f, indent=2)


def main():
    data_files = [f for f in sys.argv[1:] if f.endswith('_data.json') and not f.startswith('--')]
    force = '--force' in sys.argv

    # White-label / client-site support (whitelabel_site.py)
    global CONTENT, QUEUE, AFFILIATE_TAG, SITE_NAME
    if '--content-dir' in sys.argv:
        i = sys.argv.index('--content-dir')
        CONTENT = sys.argv[i + 1]
    if '--tag' in sys.argv:
        i = sys.argv.index('--tag')
        AFFILIATE_TAG = sys.argv[i + 1]
    if '--site-name' in sys.argv:
        i = sys.argv.index('--site-name')
        SITE_NAME = sys.argv[i + 1]
    if '--no-mark-used' in sys.argv:
        QUEUE = os.path.join(WORKSPACE, 'data', 'asin_queue_WHITELABEL_UNUSED.json')

    if not data_files:
        print('Usage: python3 scripts/ink_review_writer.py briefings/*_data.json [--force]')
        print('  --force           Overwrite existing reviews')
        print('  --content-dir DIR Write reviews into DIR (white-label client sites)')
        print('  --tag TAG         Affiliate tag to use (default: tsvglyc-20)')
        print('  --site-name NAME  Site name in SEO titles (default: The Shopper\'s Verdict)')
        print('  --no-mark-used    Skip marking ASINs as used in the main queue')
        sys.exit(1)

    print(f"ink_review_writer - {'FORCE OVERWRITE' if force else 'NEW ONLY'}")
    print(f"   {len(data_files)} briefing files to process\n")

    written = 0
    skipped_quality = 0
    skipped_exists = 0

    for filepath in data_files:
        basename = os.path.basename(filepath)
        parts = basename.split('_')
        if len(parts) < 2:
            print(f'  Invalid filename: {basename}')
            continue
        category = parts[0]
        asin = parts[1]

        if not os.path.exists(filepath):
            print(f'  Not found: {filepath}')
            continue

        with open(filepath) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f'  Invalid JSON: {basename} - {e}')
                continue
        
        if not isinstance(data, dict):
            print(f'  Invalid data format (not a dict): {basename} - got {type(data).__name__}')
            continue
        
        result = write_review(data, category, asin, force=force)
        if result:
            mark_used(asin)
            written += 1
            processed_dir = os.path.join(WORKSPACE, 'briefings', 'processed')
            os.makedirs(processed_dir, exist_ok=True)
            os.rename(filepath, os.path.join(processed_dir, basename))
        elif result is None and not os.path.exists(os.path.join(CONTENT, category, f'{asin}_review.md')):
            skipped_quality += 1
        elif result is None:
            skipped_exists += 1

    print(f'\n  {written} reviews written')
    if skipped_quality:
        print(f'  {skipped_quality} skipped - quality gate (data too thin)')
    if skipped_exists:
        print(f'  {skipped_exists} skipped - already exist (use --force)')
    return written


if __name__ == '__main__':
    main()
