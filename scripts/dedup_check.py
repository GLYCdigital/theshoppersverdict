#!/usr/bin/env python3
"""
dedup_check.py — ROCK-SOLID ASIN deduplication for The Shopper's Verdict.

Usage:
  python3 dedup_check.py <ASIN>          # Check single ASIN (exit 0=OK, 1=already exists)
  python3 dedup_check.py --batch <file>   # Check all ASINs in a newline-separated file
  python3 dedup_check.py --sync           # Rebuild used list from all content files

Exit codes:
  0 — ASIN is NEW (not yet reviewed) or --sync completed
  1 — ASIN already reviewed (DUPLICATE)
  2 — Error (invalid args, file not found, etc.)
"""

import json
import os
import re
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(WORKSPACE, "content")
QUEUE_FILE = os.path.join(WORKSPACE, "data", "asin_queue.json")
ARCHIVE_DIR = os.path.join(CONTENT_DIR, "_archive")

# ── CORE: Scan ALL content files for ASINs ──────────────────────────────

def scan_content_for_asins():
    """Scan all .md files in content/ (excluding _archive) and return set of ASINs found."""
    reviewed = set()
    if not os.path.isdir(CONTENT_DIR):
        return reviewed

    for root, dirs, files in os.walk(CONTENT_DIR):
        # Skip archive
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    content = fh.read()
            except Exception:
                continue
            # Find ASINs in amazon_url lines
            matches = re.findall(r"/dp/([A-Z0-9]{10,14})", content)
            for asin in set(matches):
                reviewed.add(asin)

    return reviewed


def load_used_set():
    """Load the 'used' list from asin_queue.json."""
    if not os.path.exists(QUEUE_FILE):
        return set()
    try:
        with open(QUEUE_FILE) as fh:
            queue = json.load(fh)
        return set(queue.get("used", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_used_set(asins):
    """Replace the 'used' list in asin_queue.json."""
    if not os.path.exists(QUEUE_FILE):
        print(f"ERROR: Queue file not found at {QUEUE_FILE}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(QUEUE_FILE) as fh:
            queue = json.load(fh)
    except (json.JSONDecodeError, FileNotFoundError):
        queue = {"kitchen": [], "coffee": [], "home-office": [], "home-improvement": [], "luxury-beauty": [], "pet-supplies": [], "used": []}

    # Update used list
    queue["used"] = sorted(asins)

    # Remove any used ASINs from pending categories
    for cat in ["kitchen", "coffee", "home-office", "home-improvement", "luxury-beauty", "pet-supplies"]:
        queue[cat] = [a for a in queue.get(cat, []) if a not in queue["used"]]

    with open(QUEUE_FILE, "w") as fh:
        json.dump(queue, fh, indent=2)

    return True


def is_already_reviewed(asin):
    """
    TWO-layer check:
      1. Scan all content/.md files for the ASIN in amazon_url
      2. Check asin_queue.json 'used' list
    Returns True if ASIN already has a review.
    """
    asin = asin.strip().upper()

    # Layer 1: scan content files
    content_asins = scan_content_for_asins()
    if asin in content_asins:
        return True

    # Layer 2: check queue used list
    used = load_used_set()
    if asin in used:
        return True

    return False


# ── CLI Commands ────────────────────────────────────────────────────────

def cmd_check(asin):
    """Check a single ASIN."""
    if is_already_reviewed(asin):
        print(f"⛔ DUPLICATE: ASIN {asin} already has a published review.")
        sys.exit(1)
    else:
        print(f"✅ NEW: ASIN {asin} is not yet reviewed.")
        sys.exit(0)


def cmd_batch(filepath):
    """Check all ASINs in a file (one per line)."""
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        sys.exit(2)

    with open(filepath) as fh:
        asins = [line.strip() for line in fh if line.strip() and not line.strip().startswith("#")]

    results = {"new": [], "duplicate": []}
    for asin in asins:
        if is_already_reviewed(asin):
            results["duplicate"].append(asin)
        else:
            results["new"].append(asin)

    print(f"Checked {len(asins)} ASINs")
    print(f"  ✅ New: {len(results['new'])}")
    print(f"  ⛔ Duplicate: {len(results['duplicate'])}")

    for asin in results["duplicate"]:
        print(f"    ⛔ {asin}")
    for asin in results["new"]:
        print(f"    ✅ {asin}")

    if results["duplicate"]:
        sys.exit(1)


def cmd_sync():
    """Rebuild the 'used' list from content files + _archive only. Does NOT preserve stale entries."""
    reviewed = scan_content_for_asins()

    # Also scan _archive for deleted reviews (they still count as used)
    archived = set()
    if os.path.isdir(ARCHIVE_DIR):
        for root, dirs, files in os.walk(ARCHIVE_DIR):
            for f in files:
                if not f.endswith(".md"):
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path) as fh:
                        matches = re.findall(r"/dp/([A-Z0-9]{10,14})", fh.read())
                    for asin in set(matches):
                        archived.add(asin)
                except Exception:
                    continue

    # Use content + archive as ground truth — NO merge with stale used list
    rebuilt = reviewed | archived
    save_used_set(rebuilt)

    stale_count = 0
    old_used = load_used_set()
    if old_used:
        stale = old_used - rebuilt
        stale_count = len(stale)

    print(f"✅ Synchronized ASIN queue (REPLACED — no merge):")
    print(f"   Content-scanned ASINs: {len(reviewed)}")
    print(f"   Archived (deleted) ASINs: {len(archived)}")
    print(f"   Total 'used' after rebuild: {len(rebuilt)}")
    if stale_count:
        print(f"   🧹 Purged {stale_count} stale entries that were in 'used' but not in content/archive")
    print(f"   File: {QUEUE_FILE}")
    sys.exit(0)


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print(f"  python3 {sys.argv[0]} <ASIN>           # Check single ASIN", file=sys.stderr)
        print(f"  python3 {sys.argv[0]} --batch <file>    # Check batch from file", file=sys.stderr)
        print(f"  python3 {sys.argv[0]} --sync            # Rebuild used list", file=sys.stderr)
        sys.exit(2)

    arg = sys.argv[1]

    if arg == "--sync":
        cmd_sync()
    elif arg == "--batch":
        if len(sys.argv) < 3:
            print("ERROR: --batch requires a file path", file=sys.stderr)
            sys.exit(2)
        cmd_batch(sys.argv[2])
    elif arg.startswith("--"):
        print(f"ERROR: Unknown flag: {arg}", file=sys.stderr)
        sys.exit(2)
    else:
        cmd_check(arg)
