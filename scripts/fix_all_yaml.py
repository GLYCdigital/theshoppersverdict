#!/usr/bin/env python3
"""Fix ALL YAML-breaking frontmatter issues across content/ in one pass."""
import re
from pathlib import Path

content_dir = Path(__file__).resolve().parent.parent / "content"
fixed = 0

for md in content_dir.glob("**/*.md"):
    text = md.read_text(encoding="utf-8")
    
    fm_match = re.match(r'^(---\s*\n)(.*?)(\n---)', text, re.DOTALL)
    if not fm_match:
        continue
    
    pre = fm_match.group(1)
    fm = fm_match.group(2)
    post = fm_match.group(3) + fm_match.string[fm_match.end():]
    orig = fm
    
    # 1. Fix lines with unbalanced double quotes in scalar values
    #    Pattern: key: "value with an odd number of "
    new_lines = []
    for line in fm.split('\n'):
        stripped = line.strip()
        if ':' not in stripped:
            new_lines.append(line)
            continue
        
        # Check if this is a key: "value" line
        m = re.match(r'^(\s*[\w_-]+\s*:\s*)"(.*)"\s*$', line)
        if m:
            prefix = m.group(1)
            value = m.group(2)
            # Count quotes inside value (should be 0 for clean lines)
            inner_quotes = value.count('"')
            if inner_quotes > 0:
                # Strip outer quotes, let YAML parse as bare string
                # Escape any colons at start to avoid YAML confusion
                if value.startswith(':') or value.startswith('{') or value.startswith('['):
                    value = f"'{value}'"
                new_lines.append(f'{prefix}{value}')
                continue
        
        # Fix: key: "value  (missing closing quote)
        m = re.match(r'^(\s*[\w_-]+\s*:\s*)"(.+)$', line)
        if m:
            prefix = m.group(1)
            value = m.group(2)
            # Check next line for closing quote
            new_lines.append(f'{prefix}"{value}"')
            continue
        
        # Count total quotes on this line
        quotes = stripped.count('"')
        if quotes % 2 != 0:
            # Remove all wrapping quotes, use bare string
            key_val = stripped.split(':', 1)
            if len(key_val) == 2:
                key = key_val[0].strip()
                val = key_val[1].strip().strip('"').strip()
                # Re-quote with proper escaping
                val = val.replace('"', ' inch')
                line = f'{key}: "{val}"'
        
        new_lines.append(line)
    
    fm = '\n'.join(new_lines)
    
    if fm != orig:
        result = pre + fm + post
        md.write_text(result, encoding='utf-8')
        fixed += 1

print(f"Fixed {fixed} frontmatter blocks")
