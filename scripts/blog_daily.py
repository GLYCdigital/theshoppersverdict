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


def pick_products(reviews, slot, used, count):
    fresh = [r for r in reviews if r["amazon_url"] not in used and is_real_product(r["title"])]
    pool = fresh if len(fresh) >= count else reviews  # fall back if exhausted
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
                    if asin_of(items[i]["amazon_url"]) == asin_of(items[j]["amazon_url"]):
                        continue  # never compare a product against itself
                    overlap = (sig_tokens(items[i]["title"]) & sig_tokens(items[j]["title"])) & rare
                    if len(overlap) < 2:
                        continue
                    score = (items[i]["count"] or 0) + (items[j]["count"] or 0)
                    if best is None or score > best[0]:
                        best = (score, items[i], items[j])
        if best:
            return [best[1], best[2]]
        # last resort: top 2 by count in the most specific small category
        small = {c: it for c, it in by_cat.items() if c not in {"home-improvement", "patio-lawn-garden", "luxury-beauty"}}
        if not small:
            small = by_cat
        cat = max(small, key=lambda c: len(small[c]))
        return sorted(small[cat], key=lambda r: r["count"] or 0, reverse=True)[:2]
    if slot == "worth_it":
        return sorted(pool, key=lambda r: r["count"] or 0, reverse=True)[:1]
    if slot == "price_bracket":
        priced = [r for r in pool if r["price"]]
        priced.sort(key=lambda r: r["count"] or 0, reverse=True)
        return priced[:count]
    if slot == "deal_alert":
        priced = [r for r in pool if r["price"] and (r["price"] or 0) < 150]
        priced.sort(key=lambda r: r["count"] or 0, reverse=True)
        return priced[:count] or pool[:count]
    # how_to, seasonal, trending: top-count picks across categories
    top = sorted(pool, key=lambda r: r["count"] or 0, reverse=True)
    return top[:count]


def short_name(title, max_words=3):
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    words = [w for w in words if w not in STOPWORDS]
    return "-".join(words[:max_words])


def make_slug(slot, picks):
    """Evergreen, keyword-only, 3-5 words, no year, no stopwords."""
    if slot == "comparison" and len(picks) >= 2:
        a, b = short_name(picks[0]["title"], 2), short_name(picks[1]["title"], 2)
        return f"{a}-vs-{b}"
    if slot == "worth_it":
        return f"{short_name(picks[0]['title'], 3)}-worth-it"
    if slot == "price_bracket":
        cat = picks[0]["cat"].replace("-", "-")
        return f"best-{cat}-picks"
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
        topic = f"Gift Guide: {picks[0]['cat'].replace('-', ' ').title()}"
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


# ── Main ───────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv
    today = date.today()
    slot = WEEKDAY_SLOTS[today.weekday()]
    print(f"📅 {today.isoformat()} ({today.strftime('%A')}) — slot: {slot}")

    reviews = load_corpus()
    if not reviews:
        print("❌ No reviews found in corpus", file=sys.stderr)
        sys.exit(1)

    used = load_used()
    count = 2 if slot == "comparison" else 3
    picks = pick_products(reviews, slot, used, count)
    if not picks:
        print("❌ No products matched", file=sys.stderr)
        sys.exit(1)

    cfg = build_config(slot, picks)
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
