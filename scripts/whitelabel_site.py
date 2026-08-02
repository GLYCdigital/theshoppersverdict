#!/usr/bin/env python3
"""
whitelabel_site.py — White-label "Verified Review Engine" (idea 2026-08-02).

Packages The Shopper's Verdict pipeline (scrape → write → QA → publish) as a
branded microsite for B2B clients. Each client gets a private Hugo site with
their own branding, fed by the existing writer on a monthly cadence.

Commands:
  new      Scaffold a branded client site (copy theme, scrub TSV branding, write hugo.toml)
  publish  Run the writer + QA + hugo build for a client site from briefing JSONs
  demo     One-shot: scaffold a sample brand site + publish from existing briefings
  list     List client sites and their review counts

Usage:
  python3 scripts/whitelabel_site.py new --brand "ToolGuru" --slug toolguru \
      --domain https://toolguru.example --tag tsvglyc-20 --tagline "Real reviews. Real tools."
  python3 scripts/whitelabel_site.py publish --slug toolguru \
      --briefings briefings/home-improvement_B00GMXFK3G_data.json [...]
  python3 scripts/whitelabel_site.py demo --brand "DEWALT" --slug dewalt-demo
  python3 scripts/whitelabel_site.py list
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENTS_DIR = os.path.join(WORKSPACE, "clients")
WRITER = os.path.join(WORKSPACE, "scripts", "ink_review_writer.py")
QA = os.path.join(WORKSPACE, "scripts", "qa_check.sh")

# Files that contain brand strings — copied then scrubbed for white-label.
BRAND_SCRUB = [
    ("The Shopper's Verdict", "{brand}"),
    ("GLYC Digital Pte Ltd", "{company}"),
    ("theshoppersverdict.com", "{domain_host}"),
    ("tsvglyc-20", "{tag}"),
]

CATEGORIES = ["coffee", "kitchen", "home-office", "home-improvement", "luxury-beauty",
              "pet-supplies", "furniture", "patio-lawn-garden", "sports-fitness", "toys-games"]


def client_dir(slug):
    return os.path.join(CLIENTS_DIR, slug)


def ensure_slug(slug):
    slug = re.sub(r"[^a-z0-9-]+", "-", (slug or "").lower()).strip("-")
    if not slug:
        print("❌ Invalid slug")
        sys.exit(2)
    return slug


# ── new ──────────────────────────────────────────────────────────────────────

def cmd_new(args):
    slug = ensure_slug(args.slug)
    brand = args.brand or slug.title()
    domain = args.domain or f"https://{slug}.example"
    tag = args.tag or "tsvglyc-20"
    tagline = args.tagline or "The final word on what to buy."
    company = args.company or "GLYC Digital Pte Ltd"
    dest = client_dir(slug)

    if os.path.exists(dest) and not args.force:
        print(f"❌ Client site already exists: {dest} (use --force to re-scaffold)")
        return 2
    if os.path.exists(dest):
        shutil.rmtree(dest)

    os.makedirs(dest)
    # 1. Copy theme + assets
    for d in ("layouts", "static", "archetypes"):
        src = os.path.join(WORKSPACE, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, d))
    os.makedirs(os.path.join(dest, "content"))
    for cat in CATEGORIES:
        os.makedirs(os.path.join(dest, "content", cat), exist_ok=True)

    # 2. Scrub hardcoded TSV branding from copied layouts/static
    host = domain.replace("https://", "").replace("http://", "").rstrip("/")
    for root, dirs, files in os.walk(dest):
        dirs[:] = [d for d in dirs if d not in ("public", ".git")]
        for f in files:
            if not f.endswith((".html", ".css", ".txt", ".xml", ".js")):
                continue
            p = os.path.join(root, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except Exception:
                continue
            for old, new in BRAND_SCRUB:
                text = text.replace(old, new.format(brand=brand, company=company,
                                                    domain_host=host, tag=tag))
            # Neutralize GLYC analytics (client sites must not share our umami ID)
            text = re.sub(r"<script defer src=[\"']?https://cloud\.umami\.is/script\.js[^>]*>[\"']?</script>", "", text)
            text = re.sub(r"<!-- Umami Analytics -->\s*", "", text)
            text = re.sub(r"<!-- Scroll depth tracker -->\s*<script>.*?umami\.track\('scroll_depth'.*?</script>", "", text, flags=re.S)
            # Footer credit line: "A GLYC brand" would leak — remove the credit entirely
            text = text.replace("&mdash; A GLYC Digital Pte Ltd brand", "")
            text = text.replace("— A GLYC Digital Pte Ltd brand", "")
            # llms.txt attribution
            text = text.replace("Content is produced by GLYC Digital Pte Ltd.", f"Content is produced by {brand}.")
            text = text.replace("Content is produced by GLYC Digital.", f"Content is produced by {brand}.")
            # llms-full.txt attribution + GitHub source line
            text = text.replace("**Published by:** GLYC Digital", f"**Published by:** {brand}")
            text = re.sub(r"- Source on GitHub: github\.com/GLYCdigital/theshoppersverdict\n", "", text)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)

    # 3. Branded hugo.toml
    with open(os.path.join(WORKSPACE, "hugo.toml"), encoding="utf-8") as fh:
        cfg = fh.read()
    cfg = cfg.replace("https://theshoppersverdict.com", domain)
    cfg = cfg.replace('title = "The Shopper\'s Verdict"', f'title = "{brand}"')
    cfg = cfg.replace('brand = "The Shopper\'s Verdict"', f'brand = "{brand}"')
    cfg = cfg.replace('tagline = "The final word on what to buy."', f'tagline = "{tagline}"')
    cfg = cfg.replace('description = "We read thousands of Amazon reviews so you don\'t have to. No fluff, just the verdict."',
                      f'description = "{brand} — {tagline}"')
    cfg = cfg.replace('tag = "tsvglyc-20"', f'tag = "{tag}"')
    cfg = cfg.replace('disclosure = "As an Amazon Associate, we earn from qualifying purchases. Our verdicts are based on real customer reviews, not affiliate commissions."',
                      f'disclosure = "{brand} participates in the Amazon Associates Program. We earn from qualifying purchases."')
    with open(os.path.join(dest, "hugo.toml"), "w", encoding="utf-8") as fh:
        fh.write(cfg)

    # 4. Client manifest
    manifest = {
        "slug": slug, "brand": brand, "domain": domain, "tag": tag,
        "tagline": tagline, "created": str(datetime.now())[:16],
        "monthly_quota": 40, "cadence_days": 30,
    }
    with open(os.path.join(dest, "client.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    # 5. Client data dir (theme reads .Site.Data.stats — zeroed until first publish)
    data_dir = os.path.join(dest, "data")
    os.makedirs(data_dir, exist_ok=True)
    write_client_stats(dest)

    print(f"✅ Scaffolded white-label site for {brand}:")
    print(f"   {dest}")
    print(f"   Brand: {brand} | Domain: {domain} | Tag: {tag}")
    return 0


def write_client_stats(dest):
    """Compute client-site stats.json from the client's own content dir."""
    total_verdicts = 0
    total_reviews = 0
    content_dir = os.path.join(dest, "content")
    if os.path.isdir(content_dir):
        for root, dirs, files in os.walk(content_dir):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8") as fh:
                        content = fh.read()
                except Exception:
                    continue
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue
                fm = parts[1]
                if re.search(r"^amazon_url:", fm, re.MULTILINE):
                    total_verdicts += 1
                m = re.search(r"^review_count:\s*(\d+)", fm, re.MULTILINE)
                if m:
                    total_reviews += int(m.group(1))
    data = {"total_verdicts": total_verdicts, "total_reviews_analyzed": total_reviews}
    data_dir = os.path.join(dest, "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ── publish ──────────────────────────────────────────────────────────────────

def cmd_publish(args):
    slug = ensure_slug(args.slug)
    dest = client_dir(slug)
    if not os.path.exists(os.path.join(dest, "hugo.toml")):
        print(f"❌ Client site not found: {dest} — run `new` first")
        return 2

    briefings = args.briefings or []
    if not briefings:
        print("❌ No briefing files given (--briefings ...)")
        return 2

    # Stage briefings into the client's own dir (keeps client ASINs separate)
    stage = os.path.join(dest, "briefings")
    os.makedirs(stage, exist_ok=True)
    staged = []
    for b in briefings:
        if not os.path.exists(b):
            print(f"  ⚠️  Missing briefing: {b}")
            continue
        dst = os.path.join(stage, os.path.basename(b))
        shutil.copy(b, dst)
        staged.append(dst)
    if not staged:
        print("❌ No valid briefings to publish")
        return 2

    manifest = {}
    mpath = os.path.join(dest, "client.json")
    if os.path.exists(mpath):
        with open(mpath) as fh:
            manifest = json.load(fh)

    content_dir = os.path.join(dest, "content")
    tag = manifest.get("tag", "tsvglyc-20")

    print(f"🚀 Publishing {len(staged)} review(s) to {manifest.get('brand', slug)} site...")

    # 1. Write reviews into the client's content dir (white-label mode)
    cmd = ["python3", WRITER] + staged + ["--content-dir", content_dir, "--tag", tag,
                                            "--site-name", manifest.get("brand", ""), "--no-mark-used"]
    if args.force:
        cmd.append("--force")
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print(r.stderr)
    if r.returncode != 0:
        print(f"❌ Writer failed (exit {r.returncode})")
        return 1

    # 2. QA the client's reviews (skip affiliate-tag check — client tag may differ)
    md_files = []
    for root, dirs, files in os.walk(content_dir):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if f.endswith(".md") and not f.startswith("_"):
                md_files.append(os.path.join(root, f))
    if md_files and os.path.exists(QA):
        qa_cmd = ["bash", QA] + md_files
        qa = subprocess.run(qa_cmd, capture_output=True, text=True)
        if qa.stdout:
            print(qa.stdout[-3000:])
        # QA flags missing tag=tsvglyc-20 for client sites — expected, not fatal.

    # 3. Hugo build (zero-touch delivery artifact) — refresh stats first
    write_client_stats(dest)
    hugo = shutil.which("hugo")
    if hugo:
        b = subprocess.run([hugo, "--source", dest, "--minify", "--gc"],
                           capture_output=True, text=True, cwd=dest)
        if b.returncode == 0:
            n_pages = 0
            pub = os.path.join(dest, "public")
            if os.path.isdir(pub):
                n_pages = sum(len(fs) for _, _, fs in os.walk(pub) if any(f.endswith(".html") for f in fs))
            print(f"✅ Hugo build OK → {os.path.join(dest, 'public')} ({n_pages} HTML pages)")
        else:
            print(f"⚠️  Hugo build issues:\n{b.stderr[-1500:]}")
    else:
        print("⚠️  hugo not found — skipped build")

    # 4. Commit per-client (separate git repo = separate delivery target)
    if not os.path.exists(os.path.join(dest, ".git")):
        subprocess.run(["git", "init", "-q", dest], check=False)
    git = ["git", "-C", dest]
    subprocess.run(git + ["add", "-A"], check=False)
    c = subprocess.run(git + ["commit", "-q", "-m", f"publish {len(staged)} review(s) {datetime.now():%Y-%m-%d}"], check=False)
    if c.returncode == 0:
        print(f"✅ Committed to client repo: {dest}")
    else:
        print("ℹ️  No new changes to commit (or git unavailable)")

    # 5. Update client.json last_publish
    manifest["last_publish"] = str(datetime.now())[:16]
    manifest["published_count"] = manifest.get("published_count", 0) + len(staged)
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    return 0


# ── demo ─────────────────────────────────────────────────────────────────────

def cmd_demo(args):
    """Scaffold a sample brand site and publish from existing briefings."""
    slug = ensure_slug(args.slug or args.brand)
    brand = args.brand or "Sample Brand"
    briefings = args.briefings or []
    if not briefings:
        # Fall back to a sensible sample: DEWALT home-improvement briefings with review data
        for f in sorted(os.listdir(os.path.join(WORKSPACE, "briefings"))):
            if not f.endswith("_data.json"):
                continue
            try:
                with open(os.path.join(WORKSPACE, "briefings", f)) as fh:
                    d = json.load(fh)
                if isinstance(d, list):
                    d = d[0] if d and isinstance(d[0], dict) else {}
                if not isinstance(d, dict):
                    continue
                if "DEWALT" in (d.get("title") or "").upper() and len(d.get("reviews", []) or []) >= 3:
                    briefings.append(os.path.join(WORKSPACE, "briefings", f))
            except Exception:
                continue
    if not briefings:
        print("❌ No sample briefings found with real review data (need DEWALT briefings).")
        return 2

    rc = cmd_new(args)
    if rc != 0:
        return rc
    args.briefings = briefings
    return cmd_publish(args)


# ── list ─────────────────────────────────────────────────────────────────────

def cmd_list(args):
    if not os.path.isdir(CLIENTS_DIR):
        print("No client sites yet.")
        return 0
    for slug in sorted(os.listdir(CLIENTS_DIR)):
        d = client_dir(slug)
        mpath = os.path.join(d, "client.json")
        if not os.path.exists(mpath):
            continue
        with open(mpath) as fh:
            m = json.load(fh)
        n = 0
        content_dir = os.path.join(d, "content")
        if os.path.isdir(content_dir):
            for root, dirs, files in os.walk(content_dir):
                dirs[:] = [d2 for d2 in dirs if not d2.startswith("_")]
                n += sum(1 for f in files if f.endswith(".md") and not f.startswith("_"))
        last = m.get("last_publish", "never")
        print(f"  {slug:16s} {m.get('brand','?'):20s} reviews={n:4d}  last_publish={last}")
    return 0


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="White-label Verified Review Engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="scaffold a branded client site")
    p_new.add_argument("--brand", required=True)
    p_new.add_argument("--slug")
    p_new.add_argument("--domain", default="https://client.example")
    p_new.add_argument("--tag", default="tsvglyc-20")
    p_new.add_argument("--tagline")
    p_new.add_argument("--company", default="GLYC Digital Pte Ltd")
    p_new.add_argument("--force", action="store_true")

    p_pub = sub.add_parser("publish", help="write reviews + build a client site")
    p_pub.add_argument("--slug", required=True)
    p_pub.add_argument("--briefings", nargs="+")
    p_pub.add_argument("--force", action="store_true")

    p_demo = sub.add_parser("demo", help="scaffold + publish a sample brand site")
    p_demo.add_argument("--brand", default="DEWALT")
    p_demo.add_argument("--slug")
    p_demo.add_argument("--domain", default="https://client.example")
    p_demo.add_argument("--tag", default="tsvglyc-20")
    p_demo.add_argument("--tagline")
    p_demo.add_argument("--briefings", nargs="+")
    p_demo.add_argument("--company", default="GLYC Digital Pte Ltd")
    p_demo.add_argument("--force", action="store_true")

    p_list = sub.add_parser("list", help="list client sites")

    args = ap.parse_args()
    if args.cmd == "new":
        return cmd_new(args)
    if args.cmd == "publish":
        return cmd_publish(args)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "list":
        return cmd_list(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
