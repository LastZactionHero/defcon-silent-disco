#!/usr/bin/env python3
"""set_outline_v2.py — credit-card outline with sawtooth left + right edges.

Geometry:
  Board: W x H rounded rectangle (default 86 x 54mm, corner radius 3mm).
  Right edge: sawtooth with peaks pointing +X (outward).
  Left edge:  sawtooth with peaks pointing -X (outward) offset by T/2 in Y.
  Top + bottom edges: straight (no teeth) — those are the LED row and
                     connector / button row, no pairing happens vertically.

  When boards mate side-to-side (A on left, B on right), A's right peaks
  align with B's left valleys at identical Y values. The chosen IR pair
  Y (Y_IR = 108.75 by default) sits at one such peak/valley pair so
  D20 (A) and U30 (B) face each other across ~1mm air gap when docked.

Defaults match the original 86x54 card. Use --y-ir to choose a different
IR alignment Y (must be one of the peak Y values; the script reports
valid choices).

Backs up the prior PCB to .pre_outline_v2_backup.
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


def seg(x1, y1, x2, y2, w=0.1):
    return (
        f'\t(gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
        f'(stroke (width {w}) (type default)) (layer "Edge.Cuts") '
        f'(uuid "{uuid.uuid4()}"))\n'
    )


def arc(sx, sy, mx, my, ex, ey, w=0.1):
    return (
        f'\t(gr_arc (start {sx:.3f} {sy:.3f}) (mid {mx:.3f} {my:.3f}) '
        f'(end {ex:.3f} {ey:.3f}) (stroke (width {w}) (type default)) '
        f'(layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))\n'
    )


def corner_arc(cx, cy, r, start_angle_deg):
    """Quarter arc centered at (cx,cy), radius r, starting at start_angle_deg
    and sweeping +90°. Returns gr_arc s-expr."""
    sa = math.radians(start_angle_deg)
    ma = math.radians(start_angle_deg + 45)
    ea = math.radians(start_angle_deg + 90)
    sx, sy = cx + r * math.cos(sa), cy + r * math.sin(sa)
    mx, my = cx + r * math.cos(ma), cy + r * math.sin(ma)
    ex, ey = cx + r * math.cos(ea), cy + r * math.sin(ea)
    return arc(sx, sy, mx, my, ex, ey)


def sawtooth_edge_vertices(
    edge_x_baseline: float,
    y_start: float,
    y_end: float,
    direction: int,    # +1 = peaks point +X (right edge), -1 = peaks -X (left)
    period: float,
    depth: float,
    y0: float,         # phase reference: at y0, sawtooth value = -1 (valley
                       # relative to direction, i.e. INWARD recess)
) -> list[tuple[float, float]]:
    """Return list of (x, y) vertices walking from (y_start) to (y_end),
    going DOWN in Y (positive direction). Each tooth is built from line
    segments between vertices."""
    pts: list[tuple[float, float]] = []
    # Per period, the sawtooth has 4 quarter-cycles:
    #   t=0       value=-1 (inward valley)
    #   t=0.25    value=0  (baseline)
    #   t=0.5     value=+1 (outward peak)
    #   t=0.75    value=0  (baseline)
    #   t=1       value=-1 again
    # Triangular wave: linear between these points.
    # We sample at every quarter-period vertex within [y_start, y_end].
    # First quarter-period boundary >= y_start:
    qp = period / 4
    # Quarter index n such that y0 + n*qp >= y_start.
    n_start = math.ceil((y_start - y0) / qp)
    # Last quarter-index n_end such that y0 + n*qp <= y_end.
    n_end = math.floor((y_end - y0) / qp)

    # Initial point at y_start: compute interpolated sawtooth value.
    def saw(y):
        t = (y - y0) / period
        frac = t - math.floor(t)
        # Triangle: rises -1 -> +1 over frac [0, 0.5], falls +1 -> -1 over [0.5, 1].
        if frac <= 0.5:
            return -1 + 4 * frac
        return 3 - 4 * frac

    def x_at(y):
        return edge_x_baseline + direction * depth * saw(y)

    # Start
    pts.append((x_at(y_start), y_start))
    # Quarter-period vertices in [y_start, y_end]
    for n in range(n_start, n_end + 1):
        y = y0 + n * qp
        if y > y_start and y < y_end:
            pts.append((x_at(y), y))
    # End
    pts.append((x_at(y_end), y_end))
    return pts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=float, default=86.0, help="board width mm")
    ap.add_argument("--h", type=float, default=54.0, help="board height mm")
    ap.add_argument("--corner-radius", type=float, default=3.0)
    ap.add_argument("--origin-x", type=float, default=100.0)
    ap.add_argument("--origin-y", type=float, default=80.0)
    ap.add_argument("--period", type=float, default=5.0, help="sawtooth period mm")
    ap.add_argument("--depth", type=float, default=1.5, help="peak-to-baseline mm")
    ap.add_argument("--y-ir", type=float, default=108.75,
                    help="Y coordinate of the IR pair peak/valley")
    args = ap.parse_args()

    OX = args.origin_x; OY = args.origin_y
    W = args.w; H = args.h; R = args.corner_radius
    T = args.period; D = args.depth

    # Phase: right edge peaks at y = y0_R + period/2 + n*period. We want a
    # peak at args.y_ir. So y0_R + period/2 = args.y_ir mod period.
    y0_R = args.y_ir - T / 2
    # Left edge offset by T/2 so left-edge VALLEYS sit at right-edge PEAK Ys.
    y0_L = y0_R + T / 2

    # Sawtooth runs along the straight (non-arc) portion of each edge.
    # Y range of the straight portion = [OY + R, OY + H - R].
    y_top = OY + R
    y_bot = OY + H - R

    # Build outline walking clockwise starting at top-left arc end.
    txt = ""

    # Top edge (straight)
    txt += seg(OX + R, OY, OX + W - R, OY)
    # Top-right corner arc
    txt += corner_arc(OX + W - R, OY + R, R, -90)
    # Right edge (sawtooth, peaks pointing +X)
    right_pts = sawtooth_edge_vertices(
        edge_x_baseline=OX + W,
        y_start=y_top, y_end=y_bot,
        direction=+1,
        period=T, depth=D, y0=y0_R,
    )
    for i in range(len(right_pts) - 1):
        x1, y1 = right_pts[i]; x2, y2 = right_pts[i + 1]
        txt += seg(x1, y1, x2, y2)
    # Bottom-right corner arc
    txt += corner_arc(OX + W - R, OY + H - R, R, 0)
    # Bottom edge (straight)
    txt += seg(OX + W - R, OY + H, OX + R, OY + H)
    # Bottom-left corner arc
    txt += corner_arc(OX + R, OY + H - R, R, 90)
    # Left edge (sawtooth, peaks pointing -X, walking UP from bot to top)
    left_pts = sawtooth_edge_vertices(
        edge_x_baseline=OX,
        y_start=y_top, y_end=y_bot,
        direction=-1,
        period=T, depth=D, y0=y0_L,
    )
    # Walk UP — reverse the list.
    for i in range(len(left_pts) - 1, 0, -1):
        x1, y1 = left_pts[i]; x2, y2 = left_pts[i - 1]
        txt += seg(x1, y1, x2, y2)
    # Top-left corner arc
    txt += corner_arc(OX + R, OY + R, R, 180)

    # Read PCB, strip old Edge.Cuts, insert new.
    text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_outline_v2_backup"))

    # Drop any existing Edge.Cuts geometry. Pattern matches balanced (gr_...).
    chunks = re.split(r"(\n\t\(gr_(?:line|arc|rect|circle|poly|curve))", text)
    rebuilt = [chunks[0]]
    i = 1
    while i < len(chunks):
        delim = chunks[i]
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        # Walk balanced parens to find end of this gr_ block.
        depth = 1; j = 0
        # delim starts with '\n\t(gr_...' — body starts right after.
        # We need to count parens in delim+body. delim has one '(', body has the rest.
        # Easier: rebuild combined and walk.
        combined = delim[1:] + body  # drop leading '\n'
        # Find the balanced end of combined starting from the first '('.
        k = 0; dep = 0; end_idx = -1
        while k < len(combined):
            ch = combined[k]
            if ch == "(":
                dep += 1
            elif ch == ")":
                dep -= 1
                if dep == 0:
                    end_idx = k + 1
                    break
            k += 1
        if end_idx < 0:
            # Malformed — keep as-is
            rebuilt.append(delim); rebuilt.append(body)
            i += 2
            continue
        gr_block = combined[:end_idx]
        rest = body[end_idx - len(delim[1:]):]  # what's left of the body after gr_block
        if 'layer "Edge.Cuts"' in gr_block:
            # Skip this Edge.Cuts block but DON'T drop the leading newline.
            rebuilt.append("\n")
            rebuilt.append(rest)
        else:
            rebuilt.append(delim); rebuilt.append(body)
        i += 2

    text = "".join(rebuilt)

    insert_at = text.rstrip().rfind(")")
    text = text[:insert_at] + txt + text[insert_at:]
    PCB.write_text(text)
    print(f"Outline rewritten: {W}x{H}mm sawtooth (T={T}, d={D}), y_ir={args.y_ir}")
    print(f"Backup at {PCB.with_suffix(PCB.suffix + '.pre_outline_v2_backup')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
