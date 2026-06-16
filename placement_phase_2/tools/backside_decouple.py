#!/usr/bin/env python3
"""backside_decouple.py — move selected decoupling caps to B.Cu directly under
their IC power pin.

Standard dense-IC practice: when an IC's front perimeter is saturated, put the
last decoupling caps on the back, under the power pins (short via to the plane).
The placement metric is pad-XY (layer-agnostic), so a back cap under the pin is
<=2mm by construction, and the front courtyard frees up.

For each named cap: find its power net, the nearest non-passive part's pad on
that net (the pin), flip the cap to B.Cu, and set its anchor at that pin's XY.

Usage:
  backside_decouple.py defcon_badge/defcon_badge.kicad_pcb --caps C16[,C11,...]
  backside_decouple.py PCB --auto 2.0    # auto-pick every cap currently >2.0mm
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom                             # noqa: E402  (authoritative pcbnew geometry + apply)
from geom import load_pcb               # noqa: E402

GROUND = {"GND", "/GND", "AGND", "PGND", "DGND"}
POWER_RE = re.compile(r"(^\+|3V3|3\.3|1V1|1V8|5V|VBUS|VBAT|VDD|VCC|VREG|BAT\b)", re.I)


def cap_power_pad(m):
    for p in m["pads"]:
        n = p.get("net")
        if n and n not in GROUND and POWER_RE.search(n):
            return p
    return None


def find_pin(meta, cap, capnet, cap_xy, used=None, placed=None, min_gap=1.3):
    """Nearest non-passive part's pad on capnet (the IC power pin), not already
    claimed and not within min_gap of an already-placed back cap (so caps land on
    distinct, non-overlapping pins instead of stacking on adjacent ones)."""
    used = used or set()
    placed = placed or []
    best, bd = None, 1e9
    for ref, m in meta.items():
        if ref == cap or ref[0] in ("C", "R") or not ref[0].isalpha():
            continue
        for p in m["pads"]:
            if p.get("net") == capnet:
                key = (round(p["x"], 2), round(p["y"], 2))
                if key in used:
                    continue
                if any(math.hypot(p["x"] - qx, p["y"] - qy) < min_gap for qx, qy in placed):
                    continue
                d = math.hypot(p["x"] - cap_xy[0], p["y"] - cap_xy[1])
                if d < bd:
                    bd, best = d, (p["x"], p["y"], ref)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--caps", default="")
    ap.add_argument("--auto", type=float, default=None,
                    help="auto-select caps whose decoupling distance exceeds this mm")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    meta = load_pcb(pcb)

    caps = [c for c in args.caps.split(",") if c]
    if args.auto is not None:
        for ref, m in meta.items():
            if not ref.startswith("C"):
                continue
            pp = cap_power_pad(m)
            if not pp:
                continue
            pin = find_pin(meta, ref, pp["net"], (pp["x"], pp["y"]))
            if pin and math.hypot(pp["x"] - pin[0], pp["y"] - pin[1]) > args.auto:
                caps.append(ref)

    targets = {}
    used = set()                       # claimed pins (exact)
    placed = []                        # placed cap centers, to keep spacing
    for cap in caps:
        m = meta.get(cap)
        if not m:
            print(f"  skip {cap}: not found"); continue
        pp = cap_power_pad(m)
        if not pp:
            print(f"  skip {cap}: no power pad"); continue
        pin = find_pin(meta, cap, pp["net"], (pp["x"], pp["y"]), used, placed)
        if not pin:   # all distinct pins exhausted/blocked — allow nearest (declutter fixes)
            pin = find_pin(meta, cap, pp["net"], (pp["x"], pp["y"]), used)
        if not pin:
            print(f"  skip {cap}: no owner pin on {pp['net']}"); continue
        used.add((round(pin[0], 2), round(pin[1], 2)))
        placed.append((pin[0], pin[1]))
        targets[cap] = (pin[0], pin[1], m["anchor"]["rot"], pin[2])
        print(f"  {cap} ({pp['net']}) -> B.Cu under {pin[2]} pin at ({pin[0]:.2f},{pin[1]:.2f})")

    if not targets:
        print("no caps to move"); return 0

    # apply via pcbnew: flip to back + position under the pin (rotation preserved)
    geom.apply(pcb, {cap: {"x": x, "y": y, "rot": rotd, "flip": True}
                     for cap, (x, y, rotd, _) in targets.items()})
    print(f"moved {len(targets)} cap(s) to the back side")
    return 0


if __name__ == "__main__":
    sys.exit(main())
