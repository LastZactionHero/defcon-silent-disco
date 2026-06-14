#!/usr/bin/env python3
"""move_components.py — relocate footprints by reference designator.

Reads a placement map from JSON (or stdin) and rewrites each footprint's
top-level `(at X Y [ROT])` line in defcon_badge.kicad_pcb.

Map format:
  {
    "H1": {"x": 103.0, "y": 83.0, "rot": 0},
    "H2": {"x": 183.0, "y": 83.0},
    "U3": {"x": 143.0, "y": 107.0, "rot": 90}
  }

Usage:
  tools/move_components.py PLACEMENT.json
  echo '{"H1": {"x": 100, "y": 80}}' | tools/move_components.py -

The script does NOT move child elements (silk text, fab notes) — KiCad
handles those relative to the footprint anchor, so updating `(at ...)` is
sufficient for proper movement.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB = REPO_ROOT / "defcon_badge" / "defcon_badge.kicad_pcb"


def load_map(src: str) -> dict[str, dict]:
    if src == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(src).read_text())


def move_one(text: str, refdes: str, x: float, y: float, rot: float | None) -> tuple[str, bool]:
    """Find the footprint whose Reference property == refdes, replace its (at ...).

    Returns (new_text, moved?).
    """
    # Split into per-footprint chunks. Each chunk starts at "\n\t(footprint ".
    parts = re.split(r'(\n\t\(footprint )', text)
    # parts[0] is preamble, then alternating delimiter / body pairs
    out = [parts[0]]
    moved = False
    i = 1
    while i < len(parts):
        delim = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # Look for (property "Reference" "<refdes>"
        if f'(property "Reference" "{refdes}"' in body:
            # Replace the first (at NUM NUM [NUM]) line at top level
            new_at = f'(at {x:.3f} {y:.3f}'
            if rot is not None:
                new_at += f' {rot:.0f}'
            new_at += ')'
            body, n = re.subn(
                r'\(at [\d.\-]+ [\d.\-]+(?: [\d.\-]+)?\)',
                new_at,
                body,
                count=1,
            )
            if n == 1:
                moved = True
        out.append(delim)
        out.append(body)
        i += 2
    return "".join(out), moved


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    placements = load_map(sys.argv[1])

    text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_move_backup"))

    moved = []
    missed = []
    for refdes, spec in placements.items():
        x = float(spec["x"])
        y = float(spec["y"])
        rot = spec.get("rot")
        rot = float(rot) if rot is not None else None
        text, ok = move_one(text, refdes, x, y, rot)
        (moved if ok else missed).append(refdes)

    PCB.write_text(text)
    print(f"Moved {len(moved)}: {', '.join(moved) if moved else '(none)'}")
    if missed:
        print(f"NOT FOUND {len(missed)}: {', '.join(missed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
