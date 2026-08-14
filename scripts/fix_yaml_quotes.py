#!/usr/bin/env python3
"""Fix pros/cons lines where double-quote inch marks break YAML strings."""
import re
from pathlib import Path

count = 0
files_fixed = set()
content_dir = Path(__file__).resolve().parent.parent / "content"

for md in sorted(content_dir.glob("**/*.md")):
    text = md.read_text(encoding="utf-8")
    lines = text.split("\n")
    fixed = False
    new_lines = []

    for line in lines:
        m = re.match(r'^(\s+-\s+)"(.*)"$', line)
        if m:
            prefix = m.group(1)
            value = m.group(2)
            # Contains unescaped double quotes (inch marks like 3/8")
            if '"' in value:
                # Strip outer quotes — bare YAML string is fine without special starting chars
                if value and value[0] not in '{[&*!|>%@`#':
                    new_lines.append(f'{prefix}{value}')
                    fixed = True
                    count += 1
                    continue
        new_lines.append(line)

    if fixed:
        md.write_text("\n".join(new_lines), encoding="utf-8")
        files_fixed.add(str(md.relative_to(content_dir)))

print(f"Fixed {count} lines in {len(files_fixed)} files")
if files_fixed:
    for f in sorted(files_fixed)[:10]:
        print(f"  {f}")
    if len(files_fixed) > 10:
        print(f"  ... and {len(files_fixed) - 10} more")
