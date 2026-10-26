#!/usr/bin/env python3
"""Backfill `faq:` frontmatter from body ## FAQ sections in legacy reviews,
and clean garbled amazon_url trailing ' inch'. Idempotent."""
import re, sys, pathlib

def parse_faq(body):
    m = re.search(r'^##+ *FAQ *$', body, re.M)
    if not m:
        return []
    rest = body[m.end():]
    nxt = re.search(r'^##+ ', rest, re.M)
    if nxt:
        rest = rest[:nxt.start()]
    pairs = []
    # cut at the next heading or bold section title (e.g. **The Verdict**)
    stop = re.search(r'^ (#{2,} .+|\*\*(?:The Verdict|Rating)[^\n]*\*\*)$', rest, re.M)
    if stop:
        rest = rest[:stop.start()]
    paras = [p.strip() for p in re.split(r'\n\s*\n', rest) if p.strip()]
    i = 0
    while i < len(paras):
        p = paras[i]
        qm = re.match(r'\*\*(?:Q:\s*)?(.+?)\*\*\s*(?:\n+\s*)?(.*)$', p, re.S)
        if not qm:
            i += 1
            continue
        q = ' '.join(qm.group(1).split()).strip()
        a_parts = []
        if qm.group(2):
            a_parts.append(qm.group(2))
        j = i + 1
        while j < len(paras) and not re.match(r'\*\*(?:Q:\s*)?.+?\*\*', paras[j], re.S):
            a_parts.append(paras[j])
            j += 1
        a = ' '.join(' '.join(a_parts).split()).strip()
        a = re.sub(r'^A:\s*', '', a)
        if q.endswith('?') and a:
            pairs.append((q, a))
        i = j if j > i else i + 1
    return pairs

def yq(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')

def main(paths):
    changed = 0
    for p in paths:
        path = pathlib.Path(p)
        txt = path.read_text()
        if not txt.startswith('---'):
            continue
        end = txt.find('\n---', 3)
        if end < 0:
            continue
        fm = txt[3:end]
        body = txt[end + 4:]
        orig_fm = fm
        # clean garbled amazon_url
        fm = re.sub(r'(amazon_url: *"[^"\n]*?) inch"', r'\1"', fm)
        if re.search(r'^faq:', fm, re.M):
            if fm != orig_fm:
                path.write_text('---' + fm + '\n---' + body)
                changed += 1
                print(f"URL-only {path.name}")
            continue
        pairs = parse_faq(body)
        if not pairs:
            print(f"SKIP no-faq-section {path.name}")
            continue
        block = "faq:\n" + "".join(
            f'  - question: "{yq(q)}"\n    answer: "{yq(a)}"\n' for q, a in pairs)
        fm = fm.rstrip('\n') + '\n' + block
        path.write_text('---' + fm + '\n---' + body)
        changed += 1
        print(f"FAQ x{len(pairs)} {path.name}")
    print(f"changed={changed}")

if __name__ == '__main__':
    main(sys.argv[1:])
