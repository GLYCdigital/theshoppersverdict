#!/usr/bin/env python3
"""Repair posts whose frontmatter was duplicated by a botched rewrite.

Shape of the corruption:

    ---
    title: ...            <- block 1: the real, valid frontmatter
    ---

    [**Frontmatter:**]    <- optional LLM artifact line
    title: ...            <- block 2: a full second frontmatter block
    pros:                 <-    (richer editorial copy, stale price)
      - ...
    ---

    <article body>

Hugo reads block 1 as frontmatter and renders block 2 as *body text*, so pages
publish raw `seo_title:` / `price:` lines as visible copy.

This script keeps block 1 (valid amazon_url/asin/date/price) as the frontmatter,
adopts the richer editorial fields from block 2 (pros, cons, image_alt,
seo_title, meta_description — only when block 2 is well-formed), drops the second
block, and appends the real body.

Usage:
  python3 scripts/fix_double_frontmatter.py --dry-run   # report only
  python3 scripts/fix_double_frontmatter.py --apply
"""
import argparse
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
NOISE = re.compile(r"^\*\*.*\*\*:?$")
ADOPT = ("pros", "cons", "image_alt", "seo_title", "meta_description")


def noise(line):
    """Blank lines and the LLM's own '**Frontmatter:**' style headings."""
    s = line.strip()
    return s == "" or bool(NOISE.match(s))


def parse(lines):
    if not lines or lines[0].strip() != "---":
        return None
    e1 = next((k for k in range(1, len(lines)) if lines[k].strip() == "---"), None)
    if e1 is None:
        return None
    j = e1 + 1
    while j < len(lines) and noise(lines[j]):
        j += 1
    if j < len(lines) and lines[j].strip() == "---":
        # block 2 carries its own opening delimiter
        j += 1
        while j < len(lines) and noise(lines[j]):
            j += 1
    if not (j < len(lines) and KEY.match(lines[j])):
        return None
    e2 = next((k for k in range(j, len(lines)) if lines[k].strip() == "---"), None)
    if e2 is None:
        # block 2 runs to EOF without its closing delimiter
        return lines[1:e1], lines[j:], []
    return lines[1:e1], lines[j:e2], lines[e2 + 1:]


def chunks(block):
    """Split a frontmatter block into ordered (key, raw_lines) chunks."""
    out = []
    for line in block:
        m = KEY.match(line)
        if m:
            out.append([m.group(1), [line]])
        elif out:
            out[-1][1].append(line)
    return out


def as_dict(block):
    data = yaml.safe_load("\n".join(block))
    if not isinstance(data, dict):
        raise ValueError("frontmatter did not parse to a mapping")
    return data


def meaningful(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def repair_truncated_strings(block):
    """An LLM dropped the value but kept the opening quote: `amazon_image: "`.

    Close it as an empty string so the block parses; the field itself is then
    ignored unless it is one we adopt (adopt list only takes non-empty values).
    """
    out, repaired = [], []
    for line in block:
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):[ \t]*"[ \t]*$', line)
        if m:
            out.append(f'{m.group(1)}: ""')
            repaired.append(m.group(1))
        else:
            out.append(line)
    return out, repaired


def rebuild(b1, b2):
    """Return new frontmatter lines, or (None, reason) when block 2 is unusable."""
    try:
        d1 = as_dict(b1)
    except Exception as exc:
        return None, f"block 1 invalid: {str(exc).splitlines()[0]}"
    b2, repaired = repair_truncated_strings(b2)
    try:
        d2 = as_dict(b2)
    except Exception as exc:
        return None, f"block 2 invalid: {str(exc).splitlines()[0]}"

    adopted = []
    second = dict((k, raw) for k, raw in chunks(b2))
    out = []
    seen = set()
    for key, raw in chunks(b1):
        seen.add(key)
        if key in ADOPT and key in second and meaningful(d2.get(key)) and d2.get(key) != d1.get(key):
            out.extend(second[key])
            adopted.append(key)
        else:
            out.extend(raw)
    for key in ADOPT:
        if key not in seen and key in second and meaningful(d2.get(key)):
            out.extend(second[key])
            adopted.append(key)

    # never carry a price over from block 2, and drop a price block 1 lost
    if "price" not in seen:
        cleaned = [l for l in out if not l.startswith("price:")]
        out = cleaned + ["price: null"]

    result = "\n".join(out).rstrip("\n")
    try:
        final = as_dict(result.split("\n"))
    except Exception as exc:
        return None, f"merged frontmatter invalid: {str(exc).splitlines()[0]}"
    if not final.get("title") or not final.get("slug"):
        return None, "merged frontmatter missing title/slug"
    if repaired:
        adopted = list(adopted) + [f"repaired:{k}" for k in repaired]
    return result, adopted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.apply or args.dry_run):
        ap.error("pass --apply or --dry-run")

    fixed = skipped = empty_body = 0
    problems = []
    for path in sorted(glob.glob(os.path.join(ROOT, "content", "**", "*.md"), recursive=True)):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        lines = text.splitlines()
        parsed = parse(lines)
        if not parsed:
            continue
        b1, b2, body = parsed
        rel = os.path.relpath(path, ROOT)

        merged, info = rebuild(b1, b2)
        if merged is None:
            skipped += 1
            problems.append((rel, info))
            continue

        body_text = "\n".join(body).strip("\n")
        if len([l for l in body if l.strip()]) < 5:
            empty_body += 1
            problems.append((rel, "no article body after dedupe"))

        new_text = "---\n" + merged + "\n---\n" + ("\n" + body_text + "\n" if body_text else "")
        if args.apply:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
        fixed += 1
        print(f"{'FIXED' if args.apply else 'WOULD FIX'} {rel}  adopted={','.join(info) or '-'}")

    print(f"\n{'fixed' if args.apply else 'would fix'}: {fixed}  skipped: {skipped}  no-body: {empty_body}")
    for rel, why in problems:
        print(f"  !! {rel} — {why}")
    return 0 if skipped == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
