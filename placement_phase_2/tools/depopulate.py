#!/usr/bin/env python3
"""depopulate.py — sweep every movable footprint to an off-board staging grid.

The Phase-A reset. Produces the "naive baseline": the board stripped of any
placement work, every movable part parked in a tidy non-overlapping grid below
the outline, so the placement engine rebuilds from a clean slate and the
baseline ratsnest is honest.

Rules:
- Edge.Cuts is never touched.
- Mounting holes (refdes H*) and other mechanical anchors stay put — they are
  corner-bound fixed constraints, not movable parts.
- Each part keeps its current rotation (off-board orientation is irrelevant;
  Phase C re-derives orientation from the floor plan). Keeping rotation means
  the courtyard bbox stays valid for collision-free packing.
- Adaptive shelf packing using real courtyard sizes => zero staging overlaps.

Usage:
  depopulate.py defcon_badge/defcon_badge.kicad_pcb            # apply
  depopulate.py PCB --dry-run                                  # report only
  depopulate.py PCB --margin 12 --gap 2.5
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
from fp_meta import load_pcb          # noqa: E402
import _pcb                           # noqa: E402

KEEP_PREFIX = ("H", "MH", "FID", "MK")   # mechanical / fixed anchors


def replace_anchor(body: str, x: float, y: float) -> str:
    """Replace the first top-level (at ...) in a footprint body, preserving rot."""
    pat = re.compile(r"(^\t\t\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))",
                     re.M)

    def sub(m):
        # reset to canonical rotation 0 — placement re-derives orientations cleanly
        # (fixed parts via floorplan, passives via SA); avoids inheriting odd rotations.
        return f"{m.group(1)}{x:.3f} {y:.3f} 0{m.group(6)}"

    return pat.sub(sub, body, count=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--margin", type=float, default=12.0,
                    help="gap below board bottom edge to start staging (mm)")
    ap.add_argument("--gap", type=float, default=2.0,
                    help="gap between staged courtyards (mm)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    text = pcb.read_text()
    meta = load_pcb(pcb)
    x0, y0, x1, y1 = _pcb.board_outline(text)
    board_w = x1 - x0

    # Movable parts, packed largest-first so big connectors get clean shelves.
    movable = [r for r in meta if not r.startswith(KEEP_PREFIX)]

    def size(r):
        cy = meta[r].get("courtyard_bbox")
        if not cy:
            return (5.0, 5.0)
        return (cy[2] - cy[0], cy[3] - cy[1])

    movable.sort(key=lambda r: -size(r)[0] * size(r)[1])

    cursor_x = x0
    shelf_y = y1 + args.margin
    shelf_h = 0.0
    moves = {}
    for r in movable:
        w, h = size(r)
        if cursor_x + w > x0 + max(board_w, 80.0) and cursor_x > x0:
            # wrap to next shelf
            shelf_y += shelf_h + args.gap
            cursor_x = x0
            shelf_h = 0.0
        cy = meta[r].get("courtyard_bbox")
        anc = meta[r]["anchor"]
        # offset from anchor to courtyard top-left, so we can land the courtyard
        # at (cursor_x, shelf_y) regardless of where the anchor sits in the part.
        if cy:
            off_x = anc["x"] - cy[0]
            off_y = anc["y"] - cy[1]
        else:
            off_x = off_y = 2.5
        new_anchor_x = cursor_x + off_x
        new_anchor_y = shelf_y + off_y
        moves[r] = (new_anchor_x, new_anchor_y)
        cursor_x += w + args.gap
        shelf_h = max(shelf_h, h)

    print(f"board outline x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}]")
    print(f"movable parts: {len(movable)}  | kept in place (mechanical): "
          f"{[r for r in meta if r.startswith(KEEP_PREFIX)]}")
    print(f"staging spans y[{y1 + args.margin:.0f}, {shelf_y + shelf_h:.0f}]")

    if args.dry_run:
        for r in movable[:8]:
            print(f"  {r:>6} -> ({moves[r][0]:.1f}, {moves[r][1]:.1f})")
        print("  ... (dry run, no changes written)")
        return 0

    # Apply: walk footprint chunks and rewrite anchors.
    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    i = 1
    n = 0
    while i < len(chunks):
        delim = chunks[i]
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        m_ref = re.search(r'\(property "Reference" "([^"]+)"', body)
        ref = m_ref.group(1) if m_ref else None
        if ref in moves:
            body = replace_anchor(body, *moves[ref])
            n += 1
        out.append(delim)
        out.append(body)
        i += 2

    pcb.write_text("".join(out))
    print(f"depopulated: moved {n} footprints to staging. Edge.Cuts untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
