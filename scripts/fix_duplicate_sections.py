#!/usr/bin/env python3
"""Merge duplicate pros:/cons: sections in frontmatter that break Hugo builds."""
from pathlib import Path
import re

content_dir = Path(__file__).resolve().parent.parent / "content"
fixed_count = 0

for md in content_dir.glob("**/*.md"):
    text = md.read_text(encoding="utf-8")

    fm_match = re.match(r'^(---\s*\n)(.*?)(\n---)', text, re.DOTALL)
    if not fm_match:
        continue

    pre = fm_match.group(1)
    fm = fm_match.group(2)
    post = fm_match.group(3) + fm_match.string[fm_match.end():]
    
    fixed = False
    
    for section in ['pros', 'cons']:
        # Find all instances of "section:" and their items
        pattern = re.compile(rf'^{section}:\s*$', re.MULTILINE)
        matches = list(pattern.finditer(fm))
        
        if len(matches) <= 1:
            continue
        
        # Get all items between sections
        lines = fm.split('\n')
        
        # Find ranges for each section block
        sections = []
        for m in matches:
            start = m.start()
            # Find all indented items after the section header
            items = []
            # Get line index
            line_idx = fm[:start].count('\n')
            section_start_line = line_idx + 1  # next line after header
            
            # Collect items - find the next unindented non-item line
            idx = section_start_line
            while idx < len(lines):
                stripped = lines[idx].strip()
                if stripped.startswith('- '):
                    items.append(lines[idx])
                    idx += 1
                elif not stripped or stripped.startswith('#'):
                    break
                elif not stripped.startswith('-') and not stripped.startswith('  -') and stripped and ':' not in stripped.split(' ')[0] if ' ' in stripped else True:
                    # Check if the next line looks like a new top-level YAML key
                    # If it's "something:" at column 0, it's a new section
                    if re.match(r'^[a-zA-Z_]+:', stripped):
                        break
                    else:
                        idx += 1
                else:
                    break
            
            sections.append((section_start_line, idx, items))
        
        if len(sections) <= 1:
            continue
        
        # Merge: keep first section, collect all items, delete subsequent section headers
        all_items = []
        for (start_line, end_line, items) in sections:
            for item in items:
                if item not in all_items:
                    all_items.append(item)
        
        # Find the line index of the first section header
        first_header_line = fm[:matches[0].start()].count('\n')
        
        # Delete from first items to end of last section
        last_section = sections[-1]
        last_end = last_section[1]
        
        # Find the lines before first header
        before = lines[:first_header_line + 1]  # include the header line
        
        # Find lines after the last section
        after = lines[last_section[1]:]
        
        # Build new lines with merged items
        new_lines = before + all_items
        
        # Remove empty section headers from remaining lines
        remaining_sections = [f'{section}:' in l for l in after if l.strip() == f'{section}:']
        if any(remaining_sections):
            after = [l for l in after if l.strip() != f'{section}:' or l.startswith(' ')]
        
        fm = '\n'.join(new_lines + after)
        fixed = True
    
    if fixed:
        result = pre + fm + post
        md.write_text(result, encoding='utf-8')
        fixed_count += 1

print(f"Fixed duplicate pros/cons in {fixed_count} files")
