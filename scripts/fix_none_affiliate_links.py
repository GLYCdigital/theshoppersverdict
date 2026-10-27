#!/usr/bin/env python3
"""Repair body CTA links that point at amazon.com/dp/None/.

The rewrite pipeline emitted "Check Price on Amazon" CTAs with a null ASIN,
so those buttons went nowhere and earned no affiliate commission. The
frontmatter `amazon_url` on the same page is valid in 157 of 159 cases, so
the fix is a substitution rather than a re-scrape.

Usage:
    python3 scripts/fix_none_affiliate_links.py            # dry run
    python3 scripts/fix_none_affiliate_links.py --apply
"""

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
BAD = re.compile(r'https?://www\.amazon\.[a-z.]{2,6}/dp/None/?[^"\')\s]*')
AMZ = re.compile(r'(?m)^amazon_url:\s*"?([^"\n]+?)"?\s*$')
TAG = "tsvglyc-20"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    fixed, skipped = [], []
    for path in CONTENT.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "dp/None" not in text:
            continue
        m = AMZ.search(text)
        url = m.group(1).strip() if m else ""
        if not url or "dp/None" in url:
            skipped.append(path)
            continue
        if "tag=" not in url:
            url += ("&" if "?" in url else "?") + "tag=" + TAG
        new = BAD.sub(url, text)
        if new == text:
            skipped.append(path)
            continue
        fixed.append(path)
        if args.apply:
            path.write_text(new, encoding="utf-8")

    print(f"repairable: {len(fixed)}  skipped: {len(skipped)}")
    if not args.apply:
        print("dry run — pass --apply to write")
    for p in skipped[:5]:
        print("  skipped:", p.relative_to(ROOT))
    return 0 if not skipped else 0


if __name__ == "__main__":
    sys.exit(main())
