#!/opt/homebrew/bin/python3
"""blog_writer.py — SEO blog post writer for The Shopper's Verdict.

Generates one blog post via DeepSeek-chat and writes it to content/blog/.
Designed around a 7-day rotation (see scripts/blog_rotation.md).

Usage:
  python3 scripts/blog_writer.py --config scripts/blog_tasks/2026-08-13-comparison.json

Config JSON shape:
{
  "slug": "breville-barista-express-vs-barista-touch",
  "slot": "comparison",           # one of: comparison, price_bracket, worth_it, how_to, trending, seasonal, deal_alert
  "topic": "Breville Barista Express vs Barista Touch",
  "angle": "Which home espresso machine should you buy in 2026?",
  "reviews": [                    # real reviews to internal-link + affiliate-link
    {"title": "...", "url": "/coffee/slug/", "amazon_url": "https://www.amazon.com/dp/XXXX/?tag=tsvglyc-20", "amazon_image": "https://m.media-amazon.com/images/I/XXX.jpg", "verdict": 4.6, "rating": 4.5, "price": 699.95, "count": 27735, "pros": ["...", "..."]}
  ]
}

Output: content/blog/<date>-<slug>.md with frontmatter (title, seo_title,
meta_description, description, date, slug, image, image_alt, faq) + markdown body.
BLOG_DRY_RUN=1 env var writes to /tmp/blog-dry-run/ instead of content/blog/.
"""

import os, sys, json, re, time
from datetime import date
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────
WORKSPACE = Path(__file__).resolve().parent.parent
CONTENT_DIR = WORKSPACE / "content" / "blog"
ENV_FILE = WORKSPACE / "scripts" / ".env"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOKENS = 4500
API_TIMEOUT = 120
MAX_RETRIES = 2

SLOT_GUIDANCE = {
    "comparison": "A head-to-head comparison of two products. Structure: intro, quick verdict, key specs side by side, where each wins, where each falls short, who each is for, final verdict. End with a clear recommendation.",
    "price_bracket": "A 'best under $X' roundup of 3-5 products in one category. Structure: intro, budget context, a ranked list (each with what it does well and its flaw), buying tips, verdict.",
    "worth_it": "An 'is it worth it?' deep-dive on one product. Structure: the hype, what it actually delivers, what reviewers complain about, the verdict score explained, who should and shouldn't buy.",
    "how_to": "A practical how-to or buying guide answering a common question. Structure: the question, the short answer, step-by-step guidance, common mistakes, recommendations with links.",
    "trending": "A news-y take on a product or category that's currently spiking. Structure: what's happening, why it's trending, the honest verdict, alternatives.",
    "seasonal": "A seasonal or gift guide. Structure: the occasion, gift strategy, ranked picks by budget/persona, verdict.",
    "deal_alert": "A price-drop / deal roundup. Structure: what dropped and by how much, each item's normal price vs now, whether it's worth buying, verdict.",
}


def load_api_key():
    if DEEPSEEK_API_KEY:
        return DEEPSEEK_API_KEY
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def call_deepseek(system_prompt, user_prompt, api_key):
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL, timeout=API_TIMEOUT)
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
            return resp.choices[0].message.content, (resp.usage.total_tokens if resp.usage else 0)
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = (attempt + 1) * 3
                print(f"  ⚠️ API attempt {attempt+1} failed ({e}) — retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                raise


def build_prompts(cfg):
    slot = cfg.get("slot", "comparison")
    guidance = SLOT_GUIDANCE.get(slot, SLOT_GUIDANCE["comparison"])

    review_lines = []
    for r in cfg.get("reviews", []):
        bits = f"- {r['title']} — internal review URL {r['url']}"
        if r.get("amazon_url"):
            bits += f", Amazon affiliate URL {r['amazon_url']}"
        if r.get("amazon_image"):
            bits += f", product image URL {r['amazon_image']}"
        if r.get("verdict"):
            bits += f", our verdict score {r['verdict']}/5"
        if r.get("rating"):
            bits += f", Amazon rating {r['rating']}/5"
        if r.get("price"):
            bits += f", ~${r['price']}"
        if r.get("count"):
            bits += f", {r['count']:,} reviews"
        if r.get("pros"):
            bits += f", top pros: {'; '.join(r['pros'][:2])}"
        review_lines.append(bits)

    system = (
        "You are Ink, the in-house writer for The Shopper's Verdict, an affiliate review site "
        "that analyzes thousands of real Amazon reviews and scores every product with a verdict.\n"
        "Voice: sharp, honest, opinionated, no fluff. Write for humans but SEO-aware.\n"
        "Rules:\n"
        "- Write 1500-2500 words.\n"
        "- Use Markdown with ## and ### headings and bullet lists. You MAY include simple HTML for affiliate buttons ONLY (see button format below).\n"
        "- AFFILIATE LINKS: every product must get its Amazon affiliate URL linked from its product name at first mention AND in a prominent button. Use EXACTLY the provided amazon_url values. Never invent links or ASINs.\n"
        "- BUTTON HTML format: <a href=\"AMAZON_URL\" class=\"btn btn-gold btn-block\" target=\"_blank\" rel=\"nofollow sponsored\">Check Price on Amazon</a>\n"
        "- BUTTON COPY RULES: never use the word 'Buy'. Use low-friction copy: 'Check Price on Amazon', 'View Amazon Deals', 'Check Availability', 'See Today's Price'.\n"
        "- IMAGES: do NOT add any <img> tags. A product image gallery (showing EVERY product in this post) is generated automatically and inserted after the Quick Summary. Focus on the words, tables and buttons.\n"
        "- GEMINI BLUEPRINT LAYOUT:\n"
        "  1. Within the FIRST 200 words include a '## Quick Summary' box: a one-line winner verdict (e.g. 'Best overall: [Product] — verdict 4.6/5') followed by a Check Price on Amazon button for the recommended product.\n"
        "  2. Interweave contextual text links on product names throughout the body (link the product name itself, not 'click here').\n"
        "  3. If the post covers 2+ products, include a comparison table (| Feature | Product A | Product B |) with price, rating, verdict, and a button row for each.\n"
        "  4. End with a '## Final Verdict' section: clear recommendation + a large full-width button (btn btn-green btn-block) for the winner.\n"
        "- Include the provided internal review URLs naturally in the body (at least 2-3). Do NOT invent other product links or ASINs.\n"
        "- Do NOT fabricate stats. Use only the numbers we give you; otherwise speak qualitatively.\n"
        "- Disclose affiliate relationship subtly where relevant (we earn from qualifying purchases).\n"
        "- No image tags, no emoji spam.\n"
        "- EVERGREEN SEO: keep the title free of years where possible so the post stays rankable long-term.\n"
        "Output ONLY a JSON object with keys: title, seo_title, meta_description, body, faq. "
        "seo_title ≤ 60 chars, meta_description ≤ 155 chars. body is the full markdown. "
        "faq is an array of 3-4 objects {question, answer} answering common buyer questions (used for FAQPage schema)."
    )

    user = (
        f"Write a blog post for slot '{slot}'.\n"
        f"Topic: {cfg.get('topic','')}\n"
        f"Angle: {cfg.get('angle','')}\n\n"
        f"{guidance}\n\n"
        f"Real products with internal review URLs, affiliate URLs and data:\n" + "\n".join(review_lines)
    )
    return system, user


def parse_json(text):
    # strip code fences and any prose around the JSON
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(t[start:end + 1])


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _yaml_quote(s):
    return json.dumps(str(s), ensure_ascii=False)


def build_gallery(cfg):
    """Side-by-side image gallery of EVERY product in the post (unbiased).
    Only for posts covering 2+ products that have images."""
    items = [r for r in cfg.get("reviews", []) if r.get("amazon_image")]
    if len(items) < 2:
        return ""
    cards = []
    for r in items:
        img = r["amazon_image"].replace("SL1500", "SL600")
        meta = []
        if r.get("verdict"):
            meta.append(f"Our verdict: {r['verdict']}/5")
        if r.get("rating"):
            meta.append(f"Amazon: {r['rating']}/5")
        if r.get("price"):
            meta.append(f"~${r['price']}")
        if r.get("count"):
            meta.append(f"{r['count']:,} reviews")
        btn = (f"<a href=\"{r['amazon_url']}\" class=\"btn btn-gold btn-block\" "
               f"target=\"_blank\" rel=\"nofollow sponsored\" "
               f"data-umami-event=\"affiliate_click\" data-umami-event-value=\"{r['title']}\">"
               f"Check Price on Amazon</a>")
        cards.append(
            f"<div class=\"blog-compare-item\">\n"
            f"  <img src=\"{img}\" alt=\"{r['title']}\" loading=\"lazy\" width=\"600\" height=\"600\">\n"
            f"  <h3>{r['title']}</h3>\n"
            f"  <p class=\"blog-compare-meta\">{' · '.join(meta)}</p>\n"
            f"  {btn}\n"
            f"</div>"
        )
    return "<div class=\"blog-compare-gallery\">\n" + "\n".join(cards) + "\n</div>"


def insert_gallery(body, gallery):
    """Insert gallery right after the Quick Summary block (fallback: after first heading)."""
    if not gallery:
        return body
    marker = "## Quick Summary"
    idx = body.find(marker)
    if idx != -1:
        sep = body.find("---", idx)
        if sep != -1:
            end = sep + 3
            return body[:end] + "\n\n" + gallery + "\n" + body[end:]
        return body[:idx] + gallery + "\n\n" + body[idx:]
    h = body.find("## ")
    if h != -1:
        nl = body.find("\n\n", h)
        if nl != -1:
            return body[:nl] + "\n\n" + gallery + "\n" + body[nl:]
    return gallery + "\n\n" + body


def write_post(cfg, data, slug):
    out_dir = Path(os.environ.get("BLOG_DRY_RUN", "") and "/tmp/blog-dry-run") if os.environ.get("BLOG_DRY_RUN") else CONTENT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    fname = f"{today}-{slug}.md"
    path = out_dir / fname

    # Featured image: prefer config image, else first review's amazon_image
    image = cfg.get("image") or next((r.get("amazon_image") for r in cfg.get("reviews", []) if r.get("amazon_image")), "")
    image_alt = cfg.get("image_alt") or (f"{cfg.get('topic','')} — product photo" if cfg.get("topic") else "")

    fm = (
        "---\n"
        f"title: {_yaml_quote(data['title'])}\n"
        f"seo_title: {_yaml_quote(data['seo_title'])}\n"
        f"meta_description: {_yaml_quote(data['meta_description'])}\n"
        f"description: {_yaml_quote(data['meta_description'])}\n"
        f"date: {today}\n"
        f"slug: {_yaml_quote(slug)}\n"
    )
    if image:
        fm += f"image: {_yaml_quote(image)}\n"
        fm += f"image_alt: {_yaml_quote(image_alt)}\n"
    if data.get("faq"):
        fm += "faq:\n"
        for item in data["faq"][:4]:
            fm += f"  - question: {_yaml_quote(item.get('question',''))}\n"
            fm += f"    answer: {_yaml_quote(item.get('answer',''))}\n"
    fm += "---\n\n"
    body = data["body"].strip()
    gallery = build_gallery(cfg)
    body = insert_gallery(body, gallery)
    path.write_text(fm + body + "\n")
    return path


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--config":
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    cfg = json.loads(Path(sys.argv[2]).read_text())
    api_key = load_api_key()
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    system, user = build_prompts(cfg)
    print(f"🤖 Generating '{cfg.get('topic')}' ({cfg.get('slot')})…", file=sys.stderr)
    text, tokens = call_deepseek(system, user, api_key)
    data = parse_json(text)
    slug = cfg.get("slug") or slugify(data["title"])
    path = write_post(cfg, data, slug)
    print(f"✅ {path}  ({tokens} tokens, {len(data['body'].split())} words)")


if __name__ == "__main__":
    main()
