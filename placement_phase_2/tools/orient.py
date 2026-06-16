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
import geom           # authoritative pcbnew apply (rotates pads correctly)


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
    meta = geom.load_pcb(pcb)
    moves = {}
    for ref, (rot, x, y) in spec.items():
        if ref not in meta:
            continue
        if x is None:
            x, y = meta[ref]["anchor"]["x"], meta[ref]["anchor"]["y"]
        moves[ref] = {"x": x, "y": y, "rot": rot}
    geom.apply(pcb, moves)                 # pcbnew apply — rotates pads correctly
    print(f"oriented: {sorted(moves)}")
    miss = set(spec) - set(moves)
    if miss:
        print(f"NOT FOUND: {sorted(miss)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
