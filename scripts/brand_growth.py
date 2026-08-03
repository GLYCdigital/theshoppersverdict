#!/usr/bin/env python3
"""brand_growth.py — Amazon Growth Engine deliverable generators (idea 2026-08-03).

Managed-service arm: $2,500/mo retainers for DTC brands covering weekly
competitive monitoring, monthly listing-content refreshes, auto-drafted replies
to negative reviews, and a monthly growth report. This script generates the
CLIENT-FACING deliverables from our existing scrape/sentiment/history pipeline:

  1. --monitor   → weekly competitive monitor for a client's ASINs (price/rating/
                   review-count deltas vs rivals) — reads the ShelfWatch history
                   store (data/history/) built by shelfwatch.py
  2. --replies   → auto-drafted responses to negative reviews (≤3★) from a
                   briefing JSON. Brand-safe, complaint-aware, never fake.
  3. --listing   → monthly listing-content refresh draft: hero copy mined from
                   what buyers praise + objection-handling for top complaints.
  4. --report    → monthly growth report combining all of the above (markdown).

Usage:
  python3 scripts/brand_growth.py --monitor data/clients/acme.json [--since 7]
  python3 scripts/brand_growth.py --replies briefings/coffee_B00AF7WUO2_data.json [--out replies.md]
  python3 scripts/brand_growth.py --listing briefings/coffee_B00AF7WUO2_data.json [--out listing.md]
  python3 scripts/brand_growth.py --report data/clients/acme.json [--out report.md]

Client config (data/clients/<name>.json):
  {"name": "Acme Coffee", "asins": ["B00AF7WUO2", "..."], "competitor_asins": ["..."],
   "brand_voice": "warm, helpful, honest"}
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(WORKSPACE, "data", "history")
CLIENTS_DIR = os.path.join(WORKSPACE, "data", "clients")

POSITIVE_WORDS = {"love", "great", "perfect", "excellent", "amazing", "best",
                  "easy", "solid", "quiet", "fast", "good", "works", "recommend",
                  "durable", "sturdy", "quality", "happy", "nice", "clean",
                  "value", "simple", "comfortable"}
NEGATIVE_WORDS = {"leak", "loud", "broke", "broken", "cheap", "flimsy", "return",
                  "defective", "waste", "poor", "bad", "awful", "crack", "stop",
                  "dead", "noise", "disappoint", "wobble", "rust", "smell", "melt",
                  "cheaply", "stopped", "quit", "malfunction", "damaged"}


# ── shared helpers ───────────────────────────────────────────────────────────

def star(v):
    if v is None:
        return 5
    m = re.search(r"([0-9.]+)", str(v))
    return float(m.group(1)) if m else 5


def to_float(v):
    try:
        if v is None or v == "null":
            return None
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def read_history(asin):
    path = os.path.join(HISTORY_DIR, f"{asin}.jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def topic_of(body, words):
    hits = [w for w in words if w in (body or "").lower()]
    return Counter(hits).most_common(3)


# ── 1. weekly monitor ────────────────────────────────────────────────────────

def load_client(path):
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    c.setdefault("asins", [])
    c.setdefault("competitor_asins", [])
    c.setdefault("brand_voice", "warm, helpful, honest")
    return c


def monitor(client, since_days=7):
    """Deltas for client ASINs + competitors over the window (from ShelfWatch history)."""
    cutoff = datetime.now().astimezone() - timedelta(days=since_days)
    out = {"client": client["name"], "since_days": since_days,
           "products": [], "competitors": []}

    def delta_for(asin):
        rows = read_history(asin)
        recent = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["ts"]).astimezone()
            except (ValueError, TypeError):
                continue
            if ts >= cutoff:
                recent.append(r)
        if len(recent) < 2:
            return None
        first, last = recent[0], recent[-1]
        def d(a, b):
            if a is None or b is None:
                return None
            return round(b - a, 2)
        return {
            "asin": asin,
            "title": (last.get("title") or asin)[:60],
            "points": len(recent),
            "price_delta": d(first.get("price"), last.get("price")),
            "rating_delta": d(first.get("rating"), last.get("rating")),
            "count_delta": int(d(first.get("review_count"), last.get("review_count")))
                           if first.get("review_count") is not None
                           and last.get("review_count") is not None else None,
            "first_price": first.get("price"),
            "last_price": last.get("price"),
            "first_rating": first.get("rating"),
            "last_rating": last.get("rating"),
        }

    for a in client.get("asins", []):
        m = delta_for(a)
        if m:
            out["products"].append(m)
    for a in client.get("competitor_asins", []):
        m = delta_for(a)
        if m:
            out["competitors"].append(m)
    return out


def render_monitor(m, client):
    lines = [
        f"# 📊 Weekly Monitor — {m['client']}",
        "",
        f"_Price/rating/review-count deltas over the last {m['since_days']} days · "
        f"generated {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}_",
        "",
        "## Your products",
        "",
        "| Product | Price | Price Δ | Rating Δ | Reviews Δ |",
        "|---|---|---|---|---|",
    ]
    if not m["products"]:
        lines.append("_No tracked history yet for your ASINs — accumulating from first snapshot._")
    for p in m["products"]:
        pd = f"{p['price_delta']:+.2f}" if p["price_delta"] is not None else "—"
        rd = f"{p['rating_delta']:+.2f}" if p["rating_delta"] is not None else "—"
        cd = f"{p['count_delta']:+d}" if p["count_delta"] is not None else "—"
        pr = f"${p['last_price']:.2f}" if p["last_price"] is not None else "—"
        lines.append(f"| {p['title']} | {pr} | {pd} | {rd} | {cd} |")
    lines += ["", "## Competitors", "", "| Product | Price | Price Δ | Rating Δ | Reviews Δ |", "|---|---|---|---|---|"]
    if not m["competitors"]:
        lines.append("_No tracked competitor history yet._")
    for p in m["competitors"]:
        pd = f"{p['price_delta']:+.2f}" if p["price_delta"] is not None else "—"
        rd = f"{p['rating_delta']:+.2f}" if p["rating_delta"] is not None else "—"
        cd = f"{p['count_delta']:+d}" if p["count_delta"] is not None else "—"
        pr = f"${p['last_price']:.2f}" if p["last_price"] is not None else "—"
        lines.append(f"| {p['title']} | {pr} | {pd} | {rd} | {cd} |")
    return "\n".join(lines) + "\n"


# ── 2. review replies ────────────────────────────────────────────────────────

def draft_reply(review, product_title, voice):
    """Draft a brand-safe reply to one negative review. Never fabricates fixes —
    acknowledges, empathizes, offers a resolution path, invites contact."""
    title = review.get("title") or "Your recent experience"
    body = (review.get("body") or "").strip()
    topics = [w for w, _ in topic_of(body, NEGATIVE_WORDS)]
    complaint = ", ".join(topics[:2]) if topics else "your experience"

    if "leak" in complaint:
        specific = "the leaking issue you described"
    elif "loud" in complaint or "noise" in complaint:
        specific = "the noise level you mentioned"
    elif "broke" in complaint or "broken" in complaint or "stopped" in complaint:
        specific = "the durability problem you ran into"
    elif "smell" in complaint or "smell" in body.lower():
        specific = "the odor issue you described"
    else:
        specific = "the problems you outlined"

    reply = (
        f"Hi {review.get('author') or 'there'}, thank you for sharing your honest "
        f"feedback about the {product_title}. We're sorry to hear about {specific} — "
        f"that's not the experience we want any customer to have. We've passed your "
        f"notes to our product team, and if you'd like a replacement or refund, "
        f"please reach out to us through Amazon's messaging system and we'll make "
        f"it right. — The {product_title.split(' ')[0] if product_title else 'Brand'} Team"
    )
    return {"review_title": title, "stars": star(review.get("rating")),
            "date": review.get("date"), "complaint_topics": topics, "reply": reply}


def render_replies(briefing, voice="warm, helpful, honest"):
    d = briefing
    product = d.get("title") or d.get("asin") or "the product"
    lines = [
        f"# ✍️ Draft Review Replies — {product}",
        "",
        f"_Auto-drafted from buyer sentiment · review and approve before posting · "
        f"brand voice: {voice}_",
        "",
    ]
    revs = [r for r in (d.get("reviews") or []) if isinstance(r, dict) and star(r.get("rating")) <= 3]
    if not revs:
        return "".join(lines) + "_No negative reviews (≤3★) in this batch — nothing to draft._\n"
    for r in revs:
        dr = draft_reply(r, product, voice)
        lines.append(f"## ⭐ {dr['stars']}/5 — {dr['review_title']}" +
                     (f" ({dr['date']})" if dr["date"] else ""))
        lines.append(f"**Reviewer:** {r.get('author') or 'anonymous'}")
        body = (r.get("body") or "").strip()
        if body:
            lines.append(f"> {body[:200]}{'…' if len(body) > 200 else ''}")
        if dr["complaint_topics"]:
            lines.append(f"**Detected topics:** {', '.join(dr['complaint_topics'])}")
        lines.append("")
        lines.append(dr["reply"])
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ── 3. listing refresh ───────────────────────────────────────────────────────

def render_listing(briefing, voice="warm, helpful, honest"):
    d = briefing
    product = d.get("title") or d.get("asin") or "the product"
    revs = [r for r in (d.get("reviews") or []) if isinstance(r, dict) and r.get("body")]
    pos_topics = Counter()
    neg_topics = Counter()
    praise = []
    for r in revs:
        body = r.get("body") or ""
        pos_topics.update([w for w, _ in topic_of(body, POSITIVE_WORDS)])
        neg_topics.update([w for w, _ in topic_of(body, NEGATIVE_WORDS)])
        if star(r.get("rating")) >= 4:
            sentence = re.split(r"(?<=[.!?])\s+", body.strip())
            if sentence:
                praise.append(sentence[0][:140])
    pos = [w for w, _ in pos_topics.most_common(4)]
    neg = [w for w, _ in neg_topics.most_common(4)]
    features = d.get("features") or []

    # Filter generic praise words for hero copy — keep concrete attributes
    GENERIC = {"love", "great", "good", "best", "perfect", "amazing", "nice", "happy"}
    attrs = [w for w in pos if w not in GENERIC] or [w for w in pos[:2]] or ["reliable"]
    hero = (f"Loved by buyers for being {attrs[0]} — and for the details that matter "
            f"({', '.join(attrs[1:3])}) — this is the {d.get('title', 'product')[:60]}.")
    objection = (f"We know some shoppers have mentioned {neg[0]} — here's how we handle it: "
                 f"quality checks before shipping, and a no-hassle replacement if anything "
                 f"isn't right." if neg
                 else "We stand behind every product with a no-hassle return policy.")
    reassurance = ("Every batch is quality-checked before it ships, and if anything "
                   "isn't right, our team will make it right — just message us.")

    lines = [
        f"# 🛠️ Listing Refresh Draft — {product}",
        "",
        f"_Mined from {len(revs)} buyer reviews · brand voice: {voice}_",
        "",
        "## Suggested hero copy",
        "",
        f"{hero}",
        "",
        "## Objection handling (from real complaints)",
        "",
        f"{objection}",
        "",
        f"{reassurance}",
        "",
        "## Bullet points (candidate — rewrite from features)",
        "",
    ]
    for feat in (features or [])[:5]:
        lines.append(f"- {feat}")
    if praise:
        lines += ["", "## Social proof (real buyer language)", ""]
        for p in praise[:3]:
            lines.append(f"> “{p}”")
    if neg:
        lines += ["", "## Watch items (rising complaints)", ""]
        lines.append(", ".join(neg))
    return "\n".join(lines) + "\n"


# ── 4. monthly report ────────────────────────────────────────────────────────

def render_report(client, since_days=30):
    mon = monitor(client, since_days)
    lines = [
        f"# 📈 Monthly Growth Report — {mon['client']}",
        "",
        f"_Generated {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')} · "
        f"deltas over {since_days} days_",
        "",
        "## Product performance",
        "",
    ]
    if not mon["products"]:
        lines.append("_History still accumulating — first monthly report needs 2+ snapshots._")
    for p in mon["products"]:
        lines.append(f"- **{p['title']}**: " +
                     (f"price ${p['first_price']:.2f} → ${p['last_price']:.2f}"
                      if p["first_price"] is not None and p["last_price"] is not None else "price n/a") +
                     (f", rating {p['first_rating']} → {p['last_rating']}" if p["first_rating"] else "") +
                     (f", {p['count_delta']:+d} reviews" if p["count_delta"] is not None else ""))
    lines += ["", "## Competitor movement", ""]
    if not mon["competitors"]:
        lines.append("_No competitor history tracked yet._")
    for p in mon["competitors"]:
        lines.append(f"- **{p['title']}**: " +
                     (f"price ${p['first_price']:.2f} → ${p['last_price']:.2f}"
                      if p["first_price"] is not None and p["last_price"] is not None else "price n/a") +
                     (f", rating {p['first_rating']} → {p['last_rating']}" if p["first_rating"] else ""))
    lines += ["", "## Recommended actions", ""]
    lines.append("- Refresh listings where complaints are rising (see listing drafts).")
    lines.append("- Reply to new negative reviews within 48h (see reply drafts).")
    lines.append("- Re-check pricing if a competitor moved ≥5%.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Amazon Growth Engine deliverables")
    ap.add_argument("--monitor", metavar="CLIENT_JSON", help="weekly monitor from client config")
    ap.add_argument("--replies", metavar="BRIEFING_JSON", help="draft replies for a briefing's negative reviews")
    ap.add_argument("--listing", metavar="BRIEFING_JSON", help="draft listing refresh for a briefing")
    ap.add_argument("--report", metavar="CLIENT_JSON", help="monthly growth report")
    ap.add_argument("--since", type=int, default=7, help="monitor window days (default 7)")
    ap.add_argument("--voice", default="warm, helpful, honest", help="brand voice override")
    ap.add_argument("--out", help="write output to file")
    args = ap.parse_args()

    if not (args.monitor or args.replies or args.listing or args.report):
        ap.print_help()
        return

    if args.monitor or args.report:
        client = load_client(args.monitor or args.report)

    if args.monitor:
        text = render_monitor(monitor(client, args.since), client)
    elif args.report:
        text = render_report(client, max(args.since, 30))
    elif args.replies:
        with open(args.replies, encoding="utf-8") as f:
            text = render_replies(json.load(f), args.voice)
    elif args.listing:
        with open(args.listing, encoding="utf-8") as f:
            text = render_listing(json.load(f), args.voice)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ {args.out} ({len(text)} bytes)")
    else:
        print(text)


if __name__ == "__main__":
    main()
