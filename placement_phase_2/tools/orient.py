#!/usr/bin/env python3
"""orient.py — set rotation (and optionally position) of named footprints.

Targeted post-placement fixer for orientation/edge issues that the placement
metrics don't capture (consistent part rotation, connector facing, edge seating).
Operates on specific parts only — does NOT disturb the optimized passive
placement. Rotation is applied by KiCad on load (we set the (at x y rot) line),
so courtyards/pads transform correctly.

Usage:
  orient.py PCB --set "LED20=0,LED21=0,SW22=0"          # rotation only
  orient.py PCB --set "J10=270@144,131.2"               # rotation @ x,y
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import place as P     # set_anchor


def parse_spec(s):
    """Parse 'REF=ROT' or 'REF=ROT@X,Y' tokens. Uses a regex so the X,Y comma
    doesn't collide with the token separator (the bug that silently no-op'd this
    tool: comma-splitting first broke every @x,y spec)."""
    out = {}
    for m in re.finditer(
            r"([A-Za-z]+\d+)\s*=\s*(-?\d+\.?\d*)(?:@\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*))?",
            s):
        ref, rot, x, y = m.group(1), float(m.group(2)), m.group(3), m.group(4)
        out[ref] = (rot, float(x) if x else None, float(y) if y else None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--set", required=True, help="ref=rot[@x,y],...")
    args = ap.parse_args()
    spec = parse_spec(args.set)

    pcb = Path(args.pcb)
    text = pcb.read_text()
    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    i = 1
    done = set()
    while i < len(chunks):
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        m = re.search(r'\(property "Reference" "([^"]+)"', body)
        ref = m.group(1) if m else None
        if ref in spec:
            rot, x, y = spec[ref]
            if x is None:
                cur = re.search(r"^\t\t\(at (-?\d+\.?\d*) (-?\d+\.?\d*)", body, re.M)
                x, y = float(cur.group(1)), float(cur.group(2))
            body = P.set_anchor(body, x, y, rot)
            done.add(ref)
        out.append(chunks[i]); out.append(body)
        i += 2
    pcb.write_text("".join(out))
    print(f"oriented: {sorted(done)}")
    miss = set(spec) - done
    if miss:
        print(f"NOT FOUND: {sorted(miss)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
