#!/usr/bin/env python3
"""Fix all remaining YAML-breaking double quotes in frontmatter outside pros/cons."""
import re
from pathlib import Path

content_dir = Path(__file__).resolve().parent.parent / "content"
fixed = 0

# Fix pattern: 80" → 80 inch (or similar measurements with " inside frontmatter values)
# These are in title, seo_title, meta_description, image_alt, etc.
patterns = [
    (r'(\d+)"(\s*(?:adjustable|bird|inch|feet|foot|wide|long|tall|high|deep|thick|round|NPT|adapters?|hoses?|models?|sizes?|drill|lcd|display|TV|monitor|screen|hanger|post|pole|grill|burner|grates?|posts?|line|bench|pack|set|propane|natural|gas))', r'\1 inch\2'),
    (r'(\d+)"([^a-zA-Z])', r'\1 inch\2'),  # generic " after number
]

for md in content_dir.glob("**/*.md"):
    text = md.read_text(encoding="utf-8")
    orig = text
    
    # Only fix within frontmatter block
    fm_match = re.match(r'^(---\s*\n)(.*?)(\n---)', text, re.DOTALL)
    if not fm_match:
        continue
    
    pre = fm_match.group(1)
    fm = fm_match.group(2)
    post = fm_match.group(3) + fm_match.string[fm_match.end():]
    
    for pat, rep in patterns:
        fm = re.sub(pat, rep, fm)
    
    result = pre + fm + post
    if result != orig:
        md.write_text(result, encoding='utf-8')
        fixed += 1

print(f"Fixed quote issues in {fixed} frontmatter blocks")
