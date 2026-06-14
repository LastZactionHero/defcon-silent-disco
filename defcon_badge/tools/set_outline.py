#!/usr/bin/env python3
"""set_outline.py — replace Edge.Cuts with a credit-card-ish outline.

Credit card baseline: 85.60 x 53.98mm (ISO/IEC 7810 ID-1). We adopt
86 x 54mm with 3mm rounded corners as a clean default. Optional inner
cutouts (e.g. an eye, skull silhouette) can be added by --cutout.

Usage:
  tools/set_outline.py                 # default 86x54 rounded
  tools/set_outline.py --w 90 --h 56
  tools/set_outline.py --cutout eye    # adds an eye-shaped through-cut

The script rewrites only Edge.Cuts segments and arcs; everything else
in the PCB is preserved. It backs up the prior PCB to .pre_outline_backup.
"""
from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB = REPO_ROOT / "defcon_badge" / "defcon_badge.kicad_pcb"

ORIGIN_X = 100.0  # PCB coords, top-left of board
ORIGIN_Y = 80.0


def new_uuid() -> str:
    return str(uuid.uuid4())


def seg(x1, y1, x2, y2, width=0.1):
    return (
        f'\t(gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
        f'(stroke (width {width}) (type default)) (layer "Edge.Cuts") '
        f'(uuid "{new_uuid()}"))\n'
    )


def arc(sx, sy, mx, my, ex, ey, width=0.1):
    return (
        f'\t(gr_arc (start {sx:.3f} {sy:.3f}) (mid {mx:.3f} {my:.3f}) '
        f'(end {ex:.3f} {ey:.3f}) (stroke (width {width}) (type default)) '
        f'(layer "Edge.Cuts") (uuid "{new_uuid()}"))\n'
    )


def rounded_rect(x, y, w, h, r):
    """Return Edge.Cuts s-expressions for a rounded rectangle."""
    lines = []
    # top edge
    lines.append(seg(x + r, y, x + w - r, y))
    # right edge
    lines.append(seg(x + w, y + r, x + w, y + h - r))
    # bottom edge
    lines.append(seg(x + r, y + h, x + w - r, y + h))
    # left edge
    lines.append(seg(x, y + r, x, y + h - r))
    # corner arcs (start -> mid -> end). Mid is at 45 deg of the arc.
    def corner(cx, cy, start_angle):
        sa = math.radians(start_angle)
        ma = math.radians(start_angle + 45)
        ea = math.radians(start_angle + 90)
        sx, sy = cx + r * math.cos(sa), cy + r * math.sin(sa)
        mx, my = cx + r * math.cos(ma), cy + r * math.sin(ma)
        ex, ey = cx + r * math.cos(ea), cy + r * math.sin(ea)
        return arc(sx, sy, mx, my, ex, ey)

    # TL corner center
    lines.append(corner(x + r, y + r, 180))
    # TR corner
    lines.append(corner(x + w - r, y + r, 270))
    # BR corner
    lines.append(corner(x + w - r, y + h - r, 0))
    # BL corner
    lines.append(corner(x + r, y + h - r, 90))
    return "".join(lines)


def cutout_circle(cx, cy, r):
    """Through-hole circle as Edge.Cuts arcs (two half-arcs)."""
    return (
        arc(cx - r, cy, cx, cy - r, cx + r, cy)
        + arc(cx + r, cy, cx, cy + r, cx - r, cy)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=float, default=86.0)
    ap.add_argument("--h", type=float, default=54.0)
    ap.add_argument("--corner-radius", type=float, default=3.0)
    ap.add_argument("--cutout", choices=("none", "eye", "skull-eye"), default="none")
    ap.add_argument("--origin-x", type=float, default=ORIGIN_X)
    ap.add_argument("--origin-y", type=float, default=ORIGIN_Y)
    args = ap.parse_args()

    if not PCB.is_file():
        print(f"PCB not found: {PCB}", file=sys.stderr)
        return 1

    text = PCB.read_text()
    backup = PCB.with_suffix(PCB.suffix + ".pre_outline_backup")
    shutil.copy2(PCB, backup)

    # Drop existing Edge.Cuts gr_line / gr_arc / gr_rect / gr_circle / gr_poly
    edge_pattern = re.compile(
        r'\n\s*\(gr_(?:line|arc|rect|circle|poly|curve)\b[^\n]*?\(layer "Edge\.Cuts"\)[^\n]*\)',
        re.DOTALL,
    )
    text = edge_pattern.sub("", text)

    # Insert new outline just before the final closing paren of the kicad_pcb block.
    new_edges = rounded_rect(
        args.origin_x, args.origin_y, args.w, args.h, args.corner_radius
    )
    if args.cutout == "eye":
        cx = args.origin_x + args.w * 0.5
        cy = args.origin_y + args.h * 0.32
        new_edges += cutout_circle(cx, cy, 4.0)
    elif args.cutout == "skull-eye":
        cy = args.origin_y + args.h * 0.40
        for cx_off in (-args.w * 0.18, args.w * 0.18):
            new_edges += cutout_circle(
                args.origin_x + args.w * 0.5 + cx_off, cy, 3.5
            )

    # Insert before final ')' of the file (handle trailing whitespace).
    insert_at = text.rstrip().rfind(")")
    if insert_at < 0:
        print("Malformed PCB: no closing paren", file=sys.stderr)
        return 2
    new_text = text[:insert_at] + new_edges + text[insert_at:]
    PCB.write_text(new_text)
    print(f"Outline rewritten: {args.w}x{args.h}mm, cutout={args.cutout}")
    print(f"Backup at {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
