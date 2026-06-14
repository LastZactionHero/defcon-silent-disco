#!/usr/bin/env python3
"""Generic ref-purge utility — drop a list of (symbol …) instances from a
.kicad_sch file by Reference designator. Works for both MCU_Core (hand-edited)
and any other sheet where the instances aren't easily regenerated.

Usage: python3 purge_refs.py <file.kicad_sch> <REF1> [REF2 ...]
"""
import re
import sys
from pathlib import Path


def find_block_end(text: str, start: int) -> int:
    depth, j, in_str = 0, start, False
    while j < len(text):
        c = text[j]
        if c == '"' and (j == 0 or text[j - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
        j += 1
    raise ValueError


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: purge_refs.py <file.kicad_sch> <REF1> [REF2 ...]")
    path = Path(sys.argv[1])
    drops = set(sys.argv[2:])
    text = path.read_text()
    drop_ranges = []
    found = []
    for m in re.finditer(r"^\t\(symbol\n", text, re.MULTILINE):
        s = m.start()
        e = find_block_end(text, s)
        block = text[s:e]
        rm = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not rm:
            continue
        ref = rm.group(1)
        if ref in drops:
            drop_ranges.append((s, e))
            found.append(ref)
    print(f"  dropping {len(found)}: {found}", file=sys.stderr)
    missing = drops - set(found)
    if missing:
        print(f"  WARNING: not found: {sorted(missing)}", file=sys.stderr)
    if not drop_ranges:
        return
    drop_ranges.sort(reverse=True)
    new_text = text
    for s, e in drop_ranges:
        end = e
        if end < len(new_text) and new_text[end] == "\n":
            end += 1
        new_text = new_text[:s] + new_text[end:]
    path.write_text(new_text)
    print(f"  wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
