#!/opt/homebrew/bin/python3
"""blog_daily.py — Daily 16:00 blog pipeline for The Shopper's Verdict.

Picks today's slot from the 7-day rotation, selects real products from the
review corpus (never repeating recently used ones), writes the task config,
generates the post via blog_writer.py (DeepSeek-chat), and commits + pushes.

Usage:
  python3 scripts/blog_daily.py            # full run: generate + commit + push
  python3 scripts/blog_daily.py --dry-run  # generate to /tmp, no git
"""

import os, sys, re, json, subprocess
from datetime import date, datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CONTENT = WORKSPACE / "content"
BLOG_DIR = CONTENT / "blog"
TASKS_DIR = WORKSPACE / "scripts" / "blog_tasks"
STATE_FILE = WORKSPACE / "data" / "blog_used.json"

# Mon..Sun -> slot (matches scripts/blog_rotation.md)
WEEKDAY_SLOTS = ["comparison", "price_bracket", "worth_it", "how_to",
                 "comparison", "seasonal", "deal_alert"]

STOPWORDS = {"a", "an", "the", "and", "of", "for", "to", "in", "on", "with",
             "vs", "v", "best", "review", "reviews", "your", "you", "is", "are"}

CATEGORY_DIRS = [d.name for d in CONTENT.iterdir()
                 if d.is_dir() and d.name not in
                 {"blog", "verdicts", "best-of", "reviews", "search"}]

# Seasonal gift guides: bias toward gift-worthy, high-intent categories so a
# post targets real "[occasion] gift" search demand instead of raw review bulk
# (a "Home Improvement Gift Guide" gets no search volume; beauty/coffee do).
GIFT_CATEGORIES = ["luxury-beauty", "coffee", "kitchen", "toys-games",
                   "sports-fitness", "pet-supplies", "furniture"]


def seasonal_theme(today):
    """Month -> high-volume seasonal keyword for the title (slug stays
    evergreen, so no annual link rot / duplicate-slug churn)."""
    return {1: "New Year", 2: "Valentine's Day", 3: "Spring", 5: "Mother's Day",
            6: "Father's Day", 8: "Back to School", 11: "Holiday",
            12: "Christmas"}.get(today.month, "")


# ── Review corpus ──────────────────────────────────────────────────
def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm = m.group(1)
    out = {}
    for key in ["title", "amazon_url", "amazon_image", "verdict_score",
                "amazon_rating", "review_count", "price"]:
        m2 = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        if m2:
            v = m2.group(1).strip().strip('"').strip("'")
            if key in ("verdict_score", "amazon_rating", "review_count", "price"):
                v = v.replace("$", "").replace(",", "").strip()
                try:
                    out[key] = float(v) if "." in v else int(v)
                except ValueError:
                    out[key] = None if v.lower() in ("null", "none", "", "n/a", "check price on amazon") else v
            else:
                out[key] = v
    pros = re.findall(r"^  - \"(.*?)\"", fm, re.M)
    if not pros:
        pros = re.findall(r"^  - (.*)$", fm, re.M)[:3]
    out["pros"] = [p for p in pros if p][:3]
    return out


def load_corpus():
    """Return list of dicts: {cat, file, title, url, amazon_url, amazon_image,
    verdict, rating, count, price, pros} for every review file."""
    reviews = []
    for cat in CATEGORY_DIRS:
        cat_dir = CONTENT / cat
        if not cat_dir.is_dir():
            continue
        for f in sorted(cat_dir.glob("*.md")):
            if f.name.startswith("_"):
                continue
            fm = parse_frontmatter(f.read_text(errors="ignore"))
            if not fm.get("amazon_url") or not fm.get("title"):
                continue
            reviews.append({
                "cat": cat,
                "title": fm["title"],
                "url": f"/{cat}/{f.stem}/",
                "amazon_url": fm["amazon_url"],
                "amazon_image": fm.get("amazon_image", ""),
                "verdict": fm.get("verdict_score"),
                "rating": fm.get("amazon_rating"),
                "count": fm.get("review_count", 0),
                "price": fm.get("price"),
                "pros": fm.get("pros", []),
            })
    return reviews


def load_used():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_used(used, amazon_urls):
    used.update(amazon_urls)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(sorted(used), indent=2))


# ── Topic selection ────────────────────────────────────────────────
SIG_STOP = STOPWORDS | {"count", "pack", "set", "oz", "box", "white", "black", "gloss", "12", "ultra", "2x", "amazon", "replacement", "compatible", "accessory", "for", "with"}
EXCLUDE_TITLE = ["gift card", "egift", "reload", "amazon basics", "subscription", "digital download"]


def is_real_product(title):
    tl = title.lower()
    return not any(x in tl for x in EXCLUDE_TITLE)


def sig_tokens(title):
    """Meaningful alpha tokens (4+ chars, not stopwords) for pairing."""
    words = re.findall(r"[A-Za-z]{4,}", title.lower())
    return set(w for w in words if w not in SIG_STOP)


def display_name(title, max_words=5):
    words = [w for w in re.findall(r"[A-Za-z]+", title) if len(w) > 1]
    return " ".join(words[:max_words])[:60]


def asin_of(url):
    """Extract ASIN from an Amazon URL, or None."""
    m = re.search(r"/dp/([A-Z0-9]{10})", url or "")
    return m.group(1) if m else None


def same_product(a, b):
    """True when two corpus rows are the same product -- including
    near-identical re-listings that share a title but have different ASINs.
    Guards the comparison slot from pairing a product against itself."""
    ia, ib = asin_of(a["amazon_url"]), asin_of(b["amazon_url"])
    if ia and ia == ib:
        return True
    ta, tb = sig_tokens(a["title"]), sig_tokens(b["title"])
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    inter = len(small & big)
    return inter >= 3 and (small <= big or inter / len(small | big) >= 0.6)


def pick_single_category(pool, count, require_price=False):
    """All picks share ONE category — a themed roundup that mixes categories
    (dog treats in a beauty list) kills topical relevance. Picks the category
    that can fill the roundup, else the largest; ranks by review count."""
    by_cat = {}
    for r in pool:
        if require_price and not r["price"]:
            continue
        by_cat.setdefault(r["cat"], []).append(r)
    # Prefer categories whose top items cover the whole roundup.
    usable = {c: v for c, v in by_cat.items() if len(v) >= count} or by_cat
    if not usable:
        return []
    cat = max(usable, key=lambda c: (len(usable[c]),
                                     sum(r["count"] or 0 for r in usable[c])))
    items = sorted(usable[cat], key=lambda r: r["count"] or 0, reverse=True)
    return items[:count]


def pick_products(reviews, slot, used, count, avoid=None):
    fresh = [r for r in reviews if r["amazon_url"] not in used and is_real_product(r["title"])]
    pool = fresh if len(fresh) >= count else reviews  # fall back if exhausted
    if avoid:
        pool = [r for r in pool if r["amazon_url"] not in avoid]
    # Dedupe by ASIN — a product can never appear twice in one pick (even if
    # the corpus has duplicate review files for the same ASIN).
    seen, base = {}, pool
    for r in base:
        k = asin_of(r["amazon_url"]) or r["amazon_url"]
        if k not in seen or (r["count"] or 0) > (seen[k]["count"] or 0):
            seen[k] = r
    pool = list(seen.values())
    by_cat = {}
    for r in pool:
        by_cat.setdefault(r["cat"], []).append(r)

    if slot == "comparison":
        # Token frequencies: drop tokens shared by too many titles (brand/generic
        # words like "amazon", "replacement") so overlap means real product type.
        freq = {}
        for r in pool:
            for t in sig_tokens(r["title"]):
                freq[t] = freq.get(t, 0) + 1
        rare = {t for t, n in freq.items() if n <= max(3, int(len(pool) * 0.01))}
        best = None
        for cat, items in by_cat.items():
            items = sorted(items, key=lambda r: r["count"] or 0, reverse=True)[:12]
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if same_product(items[i], items[j]):
                        continue  # never compare a product against itself (or its twin listing)
                    overlap = (sig_tokens(items[i]["title"]) & sig_tokens(items[j]["title"])) & rare
                    if len(overlap) < 2:
                        continue
                    # Prefer the pair sharing the MOST product-defining tokens
                    # (tightest apples-to-apples match), then the most-reviewed.
                    score = (len(overlap),
                             (items[i]["count"] or 0) + (items[j]["count"] or 0))
                    if best is None or score > best[0]:
                        best = (score, items[i], items[j])
        if best:
            return [best[1], best[2]]
        # last resort: top 2 by count in the most specific small category
        small = {c: it for c, it in by_cat.items() if c not in {"home-improvement", "patio-lawn-garden", "luxury-beauty"}}
        if not small:
            small = by_cat
        # Largest categories first; return the top two DISTINCT products so the
        # fallback can never emit a same-product (or twin-listing) mirror pair.
        for c in sorted(small, key=lambda c: len(small[c]), reverse=True):
            out = []
            for r in sorted(small[c], key=lambda r: r["count"] or 0, reverse=True):
                if any(same_product(r, s) for s in out):
                    continue
                out.append(r)
                if len(out) == 2:
                    return out
        return sorted(pool, key=lambda r: r["count"] or 0, reverse=True)[:2]
    if slot == "worth_it":
        return sorted(pool, key=lambda r: r["count"] or 0, reverse=True)[:1]
    if slot == "price_bracket":
        return pick_single_category(pool, count, require_price=True)
    if slot == "seasonal":
        # Gift guides are themed to ONE gift-worthy category (see slug/topic).
        # Rotate by ISO week so each Saturday targets a distinct, non-competing
        # long-tail "<category> gift guide" query and slugs never collide.
        def _used(cat):
            return any(BLOG_DIR.glob(f"*-gift-guide-{cat}.md"))

        gift = [c for c in GIFT_CATEGORIES if c in by_cat]
        if gift:
            n = len(gift)
            ordered = [gift[(date.today().isocalendar()[1] + i) % n] for i in range(n)]
            # Never re-use a slug that already exists on disk: an evergreen
            # gift guide for that category is already published.
            for c in ordered:
                if _used(c):
                    continue
                items = sorted(by_cat[c], key=lambda r: r["count"] or 0, reverse=True)
                if len(items) >= count:
                    return items[:count]
            # every gift category already has a guide — pick any unused category
            for c in sorted(by_cat, key=lambda c: len(by_cat[c]), reverse=True):
                if _used(c):
                    continue
                items = sorted(by_cat[c], key=lambda r: r["count"] or 0, reverse=True)
                if len(items) >= count:
                    return items[:count]
        return pick_single_category(pool, count)
    if slot == "deal_alert":
        priced = [r for r in pool if r["price"] and (r["price"] or 0) < 150]
        priced.sort(key=lambda r: r["count"] or 0, reverse=True)
        return priced[:count] or pool[:count]
    # how_to, trending: top-count picks across categories
    top = sorted(pool, key=lambda r: r["count"] or 0, reverse=True)
    return top[:count]


def short_name(title, max_words=3):
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    words = [w for w in words if w not in STOPWORDS]
    return "-".join(words[:max_words])


def make_slug(slot, picks):
    """Evergreen, keyword-only, 3-5 words, no year, no stopwords."""
    if slot == "comparison" and len(picks) >= 2:
        # 3 words, not 2: same-line products ("Owala FreeSip X" vs "Owala
        # FreeSip Y") share their first two tokens, which collided into a
        # duplicate slug. The third word keeps comparisons distinct.
        a, b = short_name(picks[0]["title"], 3), short_name(picks[1]["title"], 3)
        return f"{a}-vs-{b}"
    if slot == "worth_it":
        return f"{short_name(picks[0]['title'], 3)}-worth-it"
    if slot == "price_bracket":
        # Category-only slugs ("best-kitchen-picks") collide as soon as a
        # category rotates back around, which hard-blocks the daily post.
        # Qualify with the price band of the actual picks, then fall back to
        # the lead product name if that band was already used.
        cat = picks[0]["cat"]
        prices = [p["price"] for p in picks if p.get("price")]
        band = "value"
        if prices:
            avg = sum(prices) / len(prices)
            band = "budget" if avg < 30 else ("premium" if avg >= 100 else "midrange")
        slug = f"best-{cat}-{band}"
        if any(slug in f.name for f in BLOG_DIR.glob("*.md")):
            slug = f"{slug}-{short_name(picks[0]['title'], 2)}"
        return slug
    if slot == "deal_alert":
        return f"best-value-{picks[0]['cat'].replace('-', '-')}-deals"
    if slot == "seasonal":
        return f"gift-guide-{picks[0]['cat'].replace('-', '-')}"
    if slot == "how_to":
        return f"how-to-choose-{picks[0]['cat'].replace('-', '-')}"
    return f"{short_name(picks[0]['title'], 3)}-guide"


def build_angle(slot, picks):
    names = ", ".join(r["title"].split(" | ")[0][:60] for r in picks)
    if slot == "comparison":
        return f"Head-to-head: which of these two is the smarter buy for most people?"
    if slot == "worth_it":
        return f"Does {picks[0]['title'].split(' | ')[0][:50]} live up to the hype — and who should actually buy it?"
    if slot == "price_bracket":
        return f"Ranked picks that deliver the most value per dollar."
    if slot == "deal_alert":
        return f"Which products are genuinely worth their current price — and which to skip."
    if slot == "seasonal":
        return f"Gift picks for every budget and type of person."
    if slot == "how_to":
        return f"Step-by-step guidance with concrete product recommendations."
    return f"An honest buyer's guide covering: {names}."


def build_config(slot, picks):
    topic_names = [display_name(r["title"]) for r in picks]
    if slot == "comparison" and len(topic_names) >= 2:
        topic = f"{topic_names[0]} vs {topic_names[1]}"
    elif slot == "worth_it":
        topic = f"Is {topic_names[0]} Worth It?"
    elif slot == "price_bracket":
        topic = f"Best {picks[0]['cat'].replace('-', ' ').title()} Picks"
    elif slot == "deal_alert":
        topic = f"Best Value {picks[0]['cat'].replace('-', ' ').title()} Deals"
    elif slot == "seasonal":
        theme = seasonal_theme(date.today())
        cat = picks[0]['cat'].replace('-', ' ').title()
        topic = f"{theme} Gift Guide: {cat}" if theme else f"Gift Guide: {cat}"
    elif slot == "how_to":
        topic = f"How to Choose {picks[0]['cat'].replace('-', ' ').title()}"
    else:
        topic = topic_names[0]
    reviews = [{
        "title": display_name(r["title"]),
        "url": r["url"],
        "amazon_url": r["amazon_url"],
        "amazon_image": r.get("amazon_image", ""),
        "verdict": r.get("verdict"),
        "rating": r.get("rating"),
        "price": r.get("price"),
        "count": r.get("count", 0),
        "pros": r.get("pros", []),
    } for r in picks]
    return {
        "slug": make_slug(slot, picks),
        "slot": slot,
        "topic": topic,
        "angle": build_angle(slot, picks),
        "reviews": reviews,
    }


def validate_post(slot, picks, cfg):
    """Pre-publish tripwire. Returns a problem string, or None when safe.
    Catches degenerate posts (a product paired with itself / its twin listing,
    missing or duplicate slug) BEFORE generation, so nothing embarrassing ever
    reaches commit/push."""
    if slot == "comparison":
        if len(picks) < 2:
            return "comparison needs two products"
        if same_product(picks[0], picks[1]):
            return f"same product paired: {picks[0]['title'][:50]}"
    if not cfg.get("slug") or len(cfg["slug"]) < 4:
        return f"missing/weak slug: {cfg.get('slug')!r}"
    if any(cfg["slug"] in f.name for f in BLOG_DIR.glob("*.md")):
        return f"duplicate slug: {cfg['slug']}"
    return None



def validate_generated_post(path):
    """Post-generation tripwire. Returns a problem string, or None when safe.

    Catches what the pre-generation check cannot see: an LLM that emitted a
    shell (frontmatter only), a duplicated frontmatter block, a dead affiliate
    link, or a non-numeric price. Runs before commit, so nothing degenerate
    reaches the live site.

    Note: fences are matched over the WHOLE file, not the first N lines — long
    frontmatters (keywords/pros/cons) run past 40 lines and a windowed parse
    reports every such post as a shell."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return "missing frontmatter"
    fences = [m.end() for m in re.finditer(r"(?m)^---\s*$", text)]
    body = text[fences[1]:] if len(fences) > 1 else ""
    # A duplicated frontmatter block does NOT announce itself as an early fence:
    # block 1 is long (keywords/pros/cons) and block 2 is unfenced YAML. Detect
    # it by shape — several leading `key:` lines before any prose.
    probe = [ln.strip() for ln in body.split("\n") if ln.strip()][:4]
    kv = [ln for ln in probe if re.match(r"^[a-z_]+:\s", ln)]
    if len(kv) >= 2:
        return f"duplicate frontmatter block (leading YAML keys: {kv[0][:40]})"
    words = len(body.split())
    if words < 150:
        return f"body too short: {words} words (shell post?)"
    # Single-product reviews must carry a working affiliate link; roundup/blog
    # posts legitimately have none (they link per product in the body).
    if path.name.endswith("-review.md"):
        url = re.search(r'(?m)^amazon_url:\s*"?([^"\n]*)"?\s*$', text)
        url_val = (url.group(1).strip() if url else "")
        if not url_val:
            return "missing amazon_url — a page without an affiliate link earns nothing"
        if "dp/None" in url_val:
            return f"dead affiliate link: {url_val[:60]}"
    if "dp/None" in body:
        return "dead affiliate link: /dp/None/"
    # Fabricated-rating guard (2026-10-27 audit). review_count in this corpus is
    # not measured — it is a ladder keyed to the star rating (8 values cover 89%
    # of 25.8k pages). The ladder is detected with a +/-1 tolerance because the
    # corpus stores 204/229 where the naive formula gives 205/230, and those two
    # bands are the modal case (4.6 x 229 alone is ~5,000 pages).
    rating = re.search(r"(?m)^amazon_rating:\s*([\d.]+)", text)
    count = re.search(r"(?m)^review_count:\s*(\d+)", text)
    if rating and count:
        r = float(rating.group(1))
        ladder = max(150, 150 + 5 * round((r - 3.0) * 10))
        if abs(int(count.group(1)) - ladder) <= 1:
            return (
                f"review_count {count.group(1)} looks derived from amazon_rating {r:g} "
                f"(ladder ~{ladder}) — needs an observed count"
            )
    price = re.search(r"(?m)^price:\s*(.+)$", text)
    if price:
        val = price.group(1).strip().strip('"')
        if val not in ("null", "") and not re.fullmatch(r"\$?\d+(\.\d+)?", val):
            return f"non-numeric price: {val!r}"
    return None


def post_warnings(path):
    """Non-blocking advisory checks. Returns a list of strings.

    amazon_rating == verdict_score is NOT evidence of fabrication: several
    hundred pages carry genuine 5-6 figure counts with an identical star value
    (e.g. 547,591 ratings @ 4.6). Warning, never a block."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    r = re.search(r"(?m)^amazon_rating:\s*([\d.]+)", text)
    v = re.search(r"(?m)^verdict_score:\s*([\d.]+)", text)
    if r and v and abs(float(r.group(1)) - float(v.group(1))) < 0.05:
        out.append(
            f"amazon_rating {r.group(1)} equals verdict_score — confirm the rating was "
            "observed, not copied (warning only)"
        )
    return out


# ── Main ───────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv
    force_cat = None
    for i, a in enumerate(sys.argv):
        if a == "--cat" and i + 1 < len(sys.argv):
            force_cat = sys.argv[i + 1]
    today = date.today()
    slot = WEEKDAY_SLOTS[today.weekday()]
    print(f"📅 {today.isoformat()} ({today.strftime('%A')}) — slot: {slot}")

    reviews = load_corpus()
    if force_cat:
        reviews = [r for r in reviews if r["cat"] == force_cat]
        print(f"🎯 Forced category: {force_cat} ({len(reviews)} reviews)")
    if not reviews:
        print("❌ No reviews found in corpus", file=sys.stderr)
        sys.exit(1)

    used = load_used()
    count = 2 if slot == "comparison" else 3
    # Pick, validate, and self-rectify: if the pick would make a degenerate
    # post, exclude those products and re-pick automatically (up to 4 tries).
    picks, cfg, problem, avoid = None, None, None, set()
    for attempt in range(4):
        picks = pick_products(reviews, slot, used, count, avoid=avoid)
        if not picks:
            print("❌ No products matched", file=sys.stderr)
            sys.exit(1)
        cfg = build_config(slot, picks)
        problem = validate_post(slot, picks, cfg)
        if not problem:
            break
        print(f"⚠️  Pre-publish check failed (attempt {attempt + 1}): {problem} — re-picking",
              file=sys.stderr)
        avoid.update(r["amazon_url"] for r in picks)
    else:
        print(f"🛑 Pre-publish check still failing: {problem}", file=sys.stderr)
        sys.exit(1)

    print(f"🎯 Topic: {cfg['topic']}")
    print(f"🔗 Products: {', '.join(p['title'][:40] for p in picks)}")

    # skip if a post for this slug already exists today (or any post today)
    existing = sorted(BLOG_DIR.glob(f"{today.isoformat()}-*.md"))
    if existing:
        print(f"⏭️  Post already published today ({existing[0].name}) — skipping")
        sys.exit(0)
    if any(cfg["slug"] in f.name for f in BLOG_DIR.glob("*.md")):
        print(f"⏭️  Post for '{cfg['slug']}' already exists — skipping")
        sys.exit(0)

    # write task config
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    task_file = TASKS_DIR / f"{today.isoformat()}-{slot}.json"
    task_file.write_text(json.dumps(cfg, indent=2))

    env = os.environ.copy()
    if dry_run:
        env["BLOG_DRY_RUN"] = "1"
    print("🤖 Running blog_writer.py…")
    r = subprocess.run(
        [sys.executable, str(WORKSPACE / "scripts" / "blog_writer.py"),
         "--config", str(task_file)],
        env=env, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("🧪 DRY RUN — no commit/push")
        sys.exit(0)

    # mark products used, then commit + push
    save_used(used, [r["amazon_url"] for r in picks])
    post = BLOG_DIR / f"{today.isoformat()}-{cfg['slug']}.md"
    problem = validate_generated_post(post)
    if problem:
        print(f"❌ Post failed validation: {problem}", file=sys.stderr)
        print(f"   {post}", file=sys.stderr)
        sys.exit(1)

    if not post.exists():
        print(f"❌ Post not found: {post}", file=sys.stderr)
        sys.exit(1)

    subprocess.run(["git", "add", str(post), str(task_file), str(STATE_FILE)],
                   cwd=WORKSPACE, check=True)
    subprocess.run(
        ["git", "commit", "-m",
         f"blog: {cfg['topic']} ({slot}, {len(cfg['reviews'])} products, "
         f"deepseek-chat)"],
        cwd=WORKSPACE, check=True)
    push = subprocess.run(["git", "push", "origin", "main"], cwd=WORKSPACE,
                          capture_output=True, text=True)
    if push.returncode != 0:
        print(f"⚠️ Push failed: {push.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    print(f"🚀 Pushed: {post.name}")


if __name__ == "__main__":
    main()
