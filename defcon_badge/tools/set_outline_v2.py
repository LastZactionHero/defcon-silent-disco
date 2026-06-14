#!/usr/bin/env python3
"""set_outline_v2.py — credit-card outline with sawtooth left + right edges.

REAL sawtooth: each tooth is a LONG RAMP followed by a SHARP DROP.
Right edge has teeth (peaks point +X, sticking out). Left edge has
the SAME polyline shape so when two boards meet edge-to-edge, A's right
teeth slot into B's left notches.

All four corners are SHARP (no rounding) so the left/right mating edges
fit flush across their full height.

Outline polygon walk (clockwise from top-left):
  top edge      (x_left, y_top)  →  (x_right, y_top)
  right edge    walk down: ramp+drop, ramp+drop, ...
  bottom edge   (x_right, y_bot) →  (x_left, y_bot)
  left edge     walk up:   ramp+drop, ramp+drop, ... (mirrored)

Each tooth on the right edge:
  ramp: (x_baseline, y_n) → (x_baseline + depth, y_n + T)
  drop: (x_baseline + depth, y_n + T) → (x_baseline, y_n + T)

The left edge polyline has the SAME shape when walked top-to-bottom
(baseline at x_left, notch deepest at x_left + depth). When boards are
placed adjacent (B's left baseline at A's right baseline), the polylines
coincide in world coordinates.

Backs up the prior PCB to .pre_outline_v2_backup.
"""
from __future__ import annotations

import argparse
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


def right_edge_polyline(baseline_x: float, depth: float,
                        y_top: float, y_bot: float, T: float,
                        drop_frac: float = 0.85) -> list[tuple[float, float]]:
    """Vertices walking from (baseline, y_top) DOWN to (baseline, y_bot).

    Each tooth occupies one period T. The ramp goes from baseline at y_n
    up to peak at y_n + drop_frac * T. The drop goes from peak at
    y_n + drop_frac * T down to baseline at y_n + T. This makes the
    polygon walk strictly monotonic in Y (no horizontal segments at
    boundaries) which KiCad's 3D renderer prefers.

    drop_frac = 0.85 makes the tooth's ramp take 85% of the period and
    the drop take 15% — visually still reads as classic sawtooth."""
    n_teeth = round((y_bot - y_top) / T)
    if abs((y_bot - y_top) - n_teeth * T) > 1e-3:
        raise ValueError(f"y range {y_top}..{y_bot} = {y_bot - y_top}mm "
                         f"not a clean multiple of T={T}")
    pts = [(baseline_x, y_top)]
    for i in range(n_teeth):
        y_ramp_end = y_top + i * T + drop_frac * T   # peak
        y_drop_end = y_top + (i + 1) * T             # back to baseline
        pts.append((baseline_x + depth, y_ramp_end))  # peak
        pts.append((baseline_x, y_drop_end))          # baseline (after drop)
    return pts


def left_edge_polyline(baseline_x: float, depth: float,
                       y_top: float, y_bot: float, T: float) -> list[tuple[float, float]]:
    """Vertices walking from (baseline, y_top) DOWN to (baseline, y_bot),
    forming sawtooth NOTCHES that complement the right-edge teeth.

    The polyline shape is the same as the right edge — at each y_peak,
    the polyline reaches (baseline+depth, y_peak) before dropping back.
    Because left-edge baseline is at the LEFT of the board, (baseline+depth)
    is INTO the board (a notch). When two boards mate, A's right tooth
    (sticking right past x=baseline_R) occupies the same world position
    as B's left notch (recess to right of baseline_L)."""
    return right_edge_polyline(baseline_x, depth, y_top, y_bot, T)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=float, default=86.0, help="board width mm")
    ap.add_argument("--h", type=float, default=54.0, help="board height mm")
    ap.add_argument("--origin-x", type=float, default=100.0)
    ap.add_argument("--origin-y", type=float, default=80.0)
    ap.add_argument("--period", type=float, default=6.0, help="sawtooth period mm")
    ap.add_argument("--depth", type=float, default=2.0, help="tooth depth mm")
    ap.add_argument("--y-ir", type=float, default=110.0,
                    help="Y coordinate of the IR pair (must be y_top + n*T)")
    args = ap.parse_args()

    OX = args.origin_x; OY = args.origin_y
    W = args.w; H = args.h
    T = args.period; D = args.depth
    y_top = OY
    y_bot = OY + H

    # Sanity check: IR Y must land on a tooth-peak (= y_top + n*T)
    n_ir = (args.y_ir - y_top) / T
    if abs(n_ir - round(n_ir)) > 1e-3:
        print(f"WARN: y_ir={args.y_ir} not a peak. Valid peaks: "
              f"{[y_top + n*T for n in range(1, int(H/T)+1)]}",
              file=sys.stderr)

    txt = ""
    # Top edge — straight, left to right
    txt += seg(OX, y_top, OX + W, y_top)
    # Right edge — sawtooth teeth, walk down
    right = right_edge_polyline(OX + W, D, y_top, y_bot, T)
    for i in range(len(right) - 1):
        txt += seg(right[i][0], right[i][1], right[i+1][0], right[i+1][1])
    # Bottom edge — straight, right to left
    txt += seg(OX + W, y_bot, OX, y_bot)
    # Left edge — sawtooth notches, walk up. Compute polyline top→bottom,
    # then emit segments in reverse.
    left = left_edge_polyline(OX, D, y_top, y_bot, T)
    for i in range(len(left) - 1, 0, -1):
        txt += seg(left[i][0], left[i][1], left[i-1][0], left[i-1][1])

    # Read PCB, strip every existing Edge.Cuts (balanced-paren walk so we
    # catch both inline and multi-line forms), then insert the new outline.
    text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_outline_v2_backup"))

    def strip_edge_cuts(s: str) -> str:
        out_parts: list[str] = []
        i = 0; n = len(s)
        while i < n:
            m = re.search(r"\n\t\(gr_(?:line|arc|rect|circle|poly|curve)\b", s[i:])
            if not m:
                out_parts.append(s[i:])
                break
            j = i + m.start()
            out_parts.append(s[i:j])
            # Walk balanced parens from the '(' at j+1 (skipping \n\t)
            k = j + 2  # at '('
            depth = 1; k += 1
            while k < n:
                ch = s[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        k += 1
                        break
                k += 1
            block = s[j+1:k]
            if 'layer "Edge.Cuts"' in block:
                pass  # drop
            else:
                out_parts.append("\n" + block)
            i = k
        return "".join(out_parts)

    text = strip_edge_cuts(text)
    insert_at = text.rstrip().rfind(")")
    text = text[:insert_at] + txt + text[insert_at:]
    PCB.write_text(text)

    n_teeth = round((y_bot - y_top) / T)
    print(f"Outline rewritten: {W}×{H}mm, sharp corners, "
          f"{n_teeth} sawtooth teeth per side (T={T}mm, depth={D}mm)")
    print(f"  IR pair: D20 at right peak ({OX+W+D:.1f}, {args.y_ir}), "
          f"U30 at left notch ({OX+D:.1f}, {args.y_ir})")
    print(f"  Backup: {PCB.with_suffix(PCB.suffix + '.pre_outline_v2_backup')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
