#!/usr/bin/env python3
"""Remove stray top-level gr_text silkscreen annotations left over from the
RP2040 minimal reference design: '3V3', 'GP11', 'GND', '\\nUSB_BOOT'.

These are not tied to any current footprint; they were silkscreen art on the
original board that no longer makes sense for the badge layout."""
import re
import sys
from pathlib import Path

PCB = Path("/home/zach/dev/defcon_badge/defcon_badge/defcon_badge.kicad_pcb")
STRIP_TEXTS = {"3V3", "GP11", "GND", "\\nUSB_BOOT"}


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
    text = PCB.read_text()
    drops = []
    for m in re.finditer(r'^\t\(gr_text\s+"([^"]+)"', text, re.MULTILINE):
        if m.group(1) in STRIP_TEXTS:
            s = m.start()
            e = find_block_end(text, s)
            drops.append((s, e, m.group(1)))
    print(f"  found {len(drops)} legacy gr_text blocks to drop:", file=sys.stderr)
    for _, _, t in drops:
        print(f"    - {t!r}", file=sys.stderr)
    drops.sort(reverse=True)
    new_text = text
    for s, e, _ in drops:
        end = e
        if end < len(new_text) and new_text[end] == "\n":
            end += 1
        new_text = new_text[:s] + new_text[end:]
    PCB.write_text(new_text)
    print(f"  wrote {PCB}", file=sys.stderr)


if __name__ == "__main__":
    main()
