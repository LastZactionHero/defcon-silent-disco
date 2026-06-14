#!/usr/bin/env python3
"""Drop specific (footprint …) blocks from defcon_badge.kicad_pcb by Reference."""
import re
import sys
from pathlib import Path

PCB = Path("/home/zach/dev/defcon_badge/defcon_badge/defcon_badge.kicad_pcb")


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
    if len(sys.argv) < 2:
        sys.exit("usage: purge_pcb_refs.py <REF1> [REF2 ...]")
    drops = set(sys.argv[1:])
    text = PCB.read_text()
    drop_ranges = []
    found = []
    for m in re.finditer(r'^\t\(footprint "', text, re.MULTILINE):
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
    print(f"  dropping {len(found)} footprints: {found}", file=sys.stderr)
    missing = drops - set(found)
    if missing:
        print(f"  WARNING: not found: {sorted(missing)}", file=sys.stderr)
    drop_ranges.sort(reverse=True)
    new_text = text
    for s, e in drop_ranges:
        end = e
        if end < len(new_text) and new_text[end] == "\n":
            end += 1
        new_text = new_text[:s] + new_text[end:]
    PCB.write_text(new_text)
    print(f"  wrote {PCB}", file=sys.stderr)


if __name__ == "__main__":
    main()
