#!/usr/bin/env python3
"""declutter.py — minimal local legalizer for courtyard touches/overlaps.

Surgical alternative to a global re-anneal: find pairs of same-layer courtyards
that overlap or sit within CLEAR mm, and push ONLY the movable part of each pair
directly apart by just enough to open the gap. Fixed parts (connectors, mounting
holes) and structured rows (LEDs/buttons) never move; decoupling stays put except
the tiny separating nudge. A few passes converge. Uses authoritative geom.

Usage:
  declutter.py defcon_badge/defcon_badge.kicad_pcb [--clear 0.1] [--passes 8] [--dry-run]
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom                                   # noqa: E402
SKILL = os.environ.get("PCB_PLACEMENT_SCRIPTS",
                       str(Path.home() / ".claude/skills/pcb-placement/scripts"))

# parts that must not move
FIXED = {"J20", "J10", "SW1", "U30", "D20", "J31", "J11",
         "H1", "H2", "H3", "H4"}
STRUCTURED = {"LED20", "LED21", "LED22", "LED23", "SW20", "SW21", "SW22"}
IMMOVABLE = FIXED | STRUCTURED


def set_anchor_body(body, x, y):
    pat = re.compile(r"(^\t\t\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+-?\d+\.?\d*)?(\))", re.M)
    return pat.sub(lambda m: f"{m.group(1)}{x:.3f} {y:.3f}{m.group(4) or ''}{m.group(5)}",
                   body, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--clear", type=float, default=0.1)
    ap.add_argument("--pad-clear", type=float, default=0.0,
                    help="also push apart different-net pads closer than this (mm)")
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    m = geom.load_pcb(pcb)
    # working positions (anchor) + courtyard half-extents (world AABB is pose-correct)
    pos = {r: [v["anchor"]["x"], v["anchor"]["y"]] for r, v in m.items()}
    cbb = {r: v["courtyard_bbox"] for r, v in m.items() if v["courtyard_bbox"]}
    layer = {r: v["layer"] for r, v in m.items()}
    # half-size + offset of courtyard center from anchor (constant under translation)
    half = {}; coff = {}
    for r, b in cbb.items():
        half[r] = ((b[2] - b[0]) / 2, (b[3] - b[1]) / 2)
        coff[r] = ((b[0] + b[2]) / 2 - m[r]["anchor"]["x"],
                   (b[1] + b[3]) / 2 - m[r]["anchor"]["y"])

    refs = [r for r in cbb]
    C = args.clear
    moved_total = 0
    for _ in range(args.passes):
        moved = 0
        for i in range(len(refs)):
            a = refs[i]
            for j in range(i + 1, len(refs)):
                b = refs[j]
                if layer[a] != layer[b]:
                    continue
                acx = pos[a][0] + coff[a][0]; acy = pos[a][1] + coff[a][1]
                bcx = pos[b][0] + coff[b][0]; bcy = pos[b][1] + coff[b][1]
                # required separation per axis = sum half-extents + clearance
                sx = half[a][0] + half[b][0] + C
                sy = half[a][1] + half[b][1] + C
                ox = sx - abs(acx - bcx)        # >0 => overlap/too-close in x
                oy = sy - abs(acy - bcy)
                if ox <= 0 or oy <= 0:
                    continue                     # already clear in some axis
                # push apart along the cheaper axis (smaller penetration)
                a_move = a not in IMMOVABLE
                b_move = b not in IMMOVABLE
                if not (a_move or b_move):
                    continue
                if ox < oy:
                    d = ox + 0.01
                    sign = 1 if acx >= bcx else -1
                    if a_move and b_move:
                        pos[a][0] += sign * d / 2; pos[b][0] -= sign * d / 2
                    elif a_move:
                        pos[a][0] += sign * d
                    else:
                        pos[b][0] -= sign * d
                else:
                    d = oy + 0.01
                    sign = 1 if acy >= bcy else -1
                    if a_move and b_move:
                        pos[a][1] += sign * d / 2; pos[b][1] -= sign * d / 2
                    elif a_move:
                        pos[a][1] += sign * d
                    else:
                        pos[b][1] -= sign * d
                moved += 1
        moved_total += moved
        if moved == 0:
            break

    # Optional pad-clearance pass: separate different-net pads that are too close
    # even when courtyards clear (e.g. a resistor pad grazing an IC pad). Push the
    # movable part of the pair directly apart along the pad-to-pad axis.
    if args.pad_clear > 0:
        padoff = {r: [(p["x"] - m[r]["anchor"]["x"], p["y"] - m[r]["anchor"]["y"], p.get("net"))
                      for p in m[r]["pads"]] for r in refs}
        for _ in range(args.passes):
            moved = 0
            for i in range(len(refs)):
                a = refs[i]
                for j in range(i + 1, len(refs)):
                    b = refs[j]
                    if layer[a] != layer[b] or not (a not in IMMOVABLE or b not in IMMOVABLE):
                        continue
                    worst = None
                    for ax, ay, an in padoff[a]:
                        if not an:
                            continue
                        pax, pay = pos[a][0] + ax, pos[a][1] + ay
                        for bx, by, bn in padoff[b]:
                            if not bn or bn == an:
                                continue
                            pbx, pby = pos[b][0] + bx, pos[b][1] + by
                            dist = math.hypot(pax - pbx, pay - pby)
                            if dist < args.pad_clear and (worst is None or dist < worst[0]):
                                worst = (dist, pax - pbx, pay - pby)
                    if not worst:
                        continue
                    d, vx, vy = worst
                    n = math.hypot(vx, vy) or 1.0
                    push = (args.pad_clear - d) + 0.02
                    ux, uy = vx / n, vy / n
                    am, bm = a not in IMMOVABLE, b not in IMMOVABLE
                    if am and bm:
                        pos[a][0] += ux * push / 2; pos[a][1] += uy * push / 2
                        pos[b][0] -= ux * push / 2; pos[b][1] -= uy * push / 2
                    elif am:
                        pos[a][0] += ux * push; pos[a][1] += uy * push
                    else:
                        pos[b][0] -= ux * push; pos[b][1] -= uy * push
                    moved += 1
            moved_total += moved
            if moved == 0:
                break

    # report which parts moved from their original anchor
    changed = {r: pos[r] for r in refs
               if abs(pos[r][0] - m[r]["anchor"]["x"]) > 1e-4
               or abs(pos[r][1] - m[r]["anchor"]["y"]) > 1e-4}
    print(f"declutter: {len(changed)} parts nudged over {args.passes} passes "
          f"({moved_total} separations)")
    for r in changed:
        dx = pos[r][0] - m[r]["anchor"]["x"]; dy = pos[r][1] - m[r]["anchor"]["y"]
        print(f"  {r}: moved ({dx:+.2f},{dy:+.2f}) mm")
    if args.dry_run or not changed:
        return 0

    # apply via pcbnew; declutter only translates (rotation unchanged)
    geom.apply(pcb, {r: {"x": changed[r][0], "y": changed[r][1]} for r in changed})
    print(f"wrote {pcb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
