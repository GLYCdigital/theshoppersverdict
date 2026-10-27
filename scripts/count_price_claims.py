#!/usr/bin/env python3
"""Count prose price claims in content/. The number, reproducible.

We produced four different figures for this one fact in a single night
(477, 934, 1,410, 13,001) because each came from a slightly different
extractor. This script exists so the ticket quotes a method, not an argument.

Method (stated so it can be argued with):
  * body  = everything after the second '---' delimiter
  * claim = a `$` followed by digits, optional thousands separators and cents
  * two scopes are reported separately and never mixed:
      - corpus-wide          : every post with any legal frontmatter
      - dropped-price set    : posts changed by the stale-price drop commits

Usage:
    python3 scripts/count_price_claims.py                 # corpus + known commits
    python3 scripts/count_price_claims.py --git-only      # dropped set only
"""
from __future__ import annotations

import glob
import re
import subprocess
import sys

CONTENT = "content/**/*.md"
DROP_COMMITS = ("ec9b482b0", "309d603cd", "fe4ffc20c")

# strict-ish clause patterns, used only to size the *editable* subset
CLAIM = re.compile(r"\$[0-9][0-9,]*(?:\.[0-9]{2})?")
STRICT = re.compile(
    r"(?:at|costs?|cost|for|priced at|price of|now)\s+\$[0-9][0-9,]*(?:\.[0-9]{2})?",
    re.I,
)


def body_of(text: str) -> str | None:
    """Everything after the closing frontmatter delimiter, or None."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[2]


def scan(paths) -> dict:
    posts_with_any = mentions_any = 0
    posts_strict = mentions_strict = 0
    for path in paths:
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        body = body_of(text)
        if body is None:
            continue
        any_hits = CLAIM.findall(body)
        strict_hits = STRICT.findall(body)
        if any_hits:
            posts_with_any += 1
            mentions_any += len(any_hits)
        if strict_hits:
            posts_strict += 1
            mentions_strict += len(strict_hits)
    return {
        "posts_with_any_$": posts_with_any,
        "mentions_any_$": mentions_any,
        "posts_strict_clause": posts_strict,
        "mentions_strict_clause": mentions_strict,
    }


def dropped_files() -> list[str]:
    files: set[str] = set()
    for commit in DROP_COMMITS:
        try:
            out = subprocess.run(
                ["git", "show", "--name-only", "--format=", commit],
                capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        for line in out.splitlines():
            if line.startswith("content/") and line.endswith(".md"):
                files.add(line)
    return sorted(f for f in files if glob.glob(f))


def main() -> int:
    git_only = "--git-only" in sys.argv
    corpus = sorted(glob.glob(CONTENT, recursive=True))
    if not git_only:
        c = scan(corpus)
        print(f"corpus-wide ({len(corpus)} posts)")
        for k, v in c.items():
            print(f"  {k:26s} {v}")
    dropped = dropped_files()
    if dropped:
        d = scan(dropped)
        print(f"dropped-price set ({len(dropped)} files)")
        for k, v in d.items():
            print(f"  {k:26s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
