#!/usr/bin/env python3
"""floorplan.py — emit a board floor plan (zones + component assignment + fixed
constraints) per FLOORPLAN_SPEC.md.

Generic engine, board-specific geometry as config:
  1. classify every movable component into a subsystem using the schematic sheet
     it lives on (ground truth), with net/refdes fallbacks;
  2. assign each subsystem's parts to a rectangular zone tiled inside Edge.Cuts;
  3. pin fixed/edge-locked parts at their required positions;
  4. emit placement_phase_2/floorplan.json;
  5. validate (every part in one zone, zones inside outline, fixed present);
  6. score (est. inter-zone ratsnest over zone-centroid proxies + violations).

Approaches (selectable; spec requires >=2 scored):
  --approach A   constructive intent-driven (this file's CONFIG zones)
  --approach B   connectivity-driven partition (see floorplan_partition.py; B
                 reuses this module's classify/validate/score, supplies its own
                 region->zone assignment)

Usage:
  floorplan.py defcon_badge/defcon_badge.kicad_pcb --approach A \
      --out placement_phase_2/floorplan.json
"""
from __future__ import annotations

import argparse
import glob
import json
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
from fp_meta import load_pcb            # noqa: E402
from ratsnest import mst_length          # noqa: E402
import _pcb                              # noqa: E402

GROUND = {"GND", "/GND", "AGND", "PGND", "DGND"}

# --------------------------------------------------------------------------- #
# BOARD-SPECIFIC CONFIG (Approach A constructive layout). Geometry only — the
# engine below is generic. Board outline x[100,188] y[80,134].
# --------------------------------------------------------------------------- #
ZONES = {
    "leds":    {"bbox": [110, 82, 182, 93],  "topology": "row",     "flow": "right",
                "note": "4x SK9822 + local caps across the top edge"},
    "mcu":     {"bbox": [124, 94, 156, 118], "topology": "ring",    "anchor": "U3",
                "note": "RP2040 + flash + xtal + decoupling ring, board center"},
    "audio":   {"bbox": [157, 93, 186, 123], "topology": "chain",   "flow": "up",
                "note": "DAC->amp->output coupling, flows up toward J20"},
    "power":   {"bbox": [101, 118, 152, 133],"topology": "chain",   "flow": "right",
                "note": "USB-C/charger/LDO chain along the bottom toward J10/J11"},
    "buttons": {"bbox": [149, 122, 180, 133],"topology": "row",     "flow": "right",
                "note": "3 front tactiles (CH/VOL+/VOL-) in a row, clear of J10 and corner hole H4"},
    "sao":     {"bbox": [101, 98, 121, 116], "topology": "cluster",
                "note": "SAO header + I2C pullups, left edge"},
    "ir":      {"bbox": [176, 114, 186, 123],"topology": "cluster",
                "note": "IR drive resistor near D20 (U30/D20 are fixed edge parts)"},
}

# Fixed / edge-locked parts (LOCKED per HARNESS). pos = anchor target, starting
# point the placement engine legalizes; the *edge/side* is the hard part.
FIXED = {
    "J20": {"pos": [174.0, 85.0],  "rot": 180, "layer": "F.Cu", "edge": "top-right",
            "why": "audio jack, plug exits up off top edge (inboard of corner hole H2)"},
    "J10": {"pos": [144.0, 130.5], "rot": 90,  "layer": "F.Cu", "edge": "bottom",
            "why": "USB-C, plug down off bottom edge"},
    "SW1": {"pos": [113.0, 129.0], "rot": 0,   "layer": "F.Cu", "edge": "bottom-left",
            "why": "slide power switch, bottom-left (inboard of corner hole H3)"},
    "U30": {"pos": [103.5, 110.0], "rot": 0,   "layer": "F.Cu", "edge": "left",
            "why": "IR-RX, left edge y=110 (mirror of D20)"},
    "D20": {"pos": [184.5, 110.0], "rot": 180, "layer": "F.Cu", "edge": "right",
            "why": "IR-LED, right edge y=110 (mirror of U30)"},
    "J31": {"pos": [130.0, 129.5], "rot": 0,   "layer": "B.Cu", "edge": "bottom",
            "why": "microSD on back, slot accessible from bottom edge"},
    "J11": {"pos": [115.0, 124.0], "rot": 0,   "layer": "B.Cu", "edge": "bottom-left",
            "why": "LiPo JST-PH on back near power zone"},
    "SW23": {"pos": [140.0, 113.0],"rot": 0,   "layer": "B.Cu", "edge": "back",
             "why": "BOOTSEL tactile on the back near U2/U3 (flash CS), clear of J31/J11"},
}
# H1..H4 mounting holes stay where they are (corners) — read from board, locked.

# Subsystem (schematic sheet) -> zone. LEDs_IR and IO split by role below.
SHEET_ZONE = {
    "MCU_Core": "mcu",
    "Power":    "power",
    "Audio":    "audio",
}


# --------------------------------------------------------------------------- #
# generic engine
# --------------------------------------------------------------------------- #
def sheet_membership(sch_dir: Path) -> dict:
    """refdes -> schematic sheet basename (ground-truth subsystem)."""
    out = {}
    for f in glob.glob(str(sch_dir / "*.kicad_sch")):
        base = Path(f).stem
        if base == sch_dir.name:           # skip the root sheet
            continue
        t = Path(f).read_text()
        for ref in re.findall(r'\(property "Reference" "([A-Za-z]+\d+)"', t):
            out.setdefault(ref, base)
    return out


def classify(ref: str, sheet: str | None) -> str:
    """Map a component to a zone name. Fixed parts return 'fixed'."""
    if ref in FIXED:
        return "fixed"
    if ref.startswith("H"):                # mounting holes
        return "fixed"
    if sheet == "LEDs_IR":
        if ref.startswith("LED") or ref.startswith("C"):
            return "leds"
        return "ir"                        # R30 (U30/D20 are fixed)
    if sheet == "IO":
        if ref.startswith("SW"):
            return "buttons"
        return "sao"                       # J30, R40, R41
    if sheet in SHEET_ZONE:
        return SHEET_ZONE[sheet]
    # fallbacks for PCB parts not found on a sheet
    if ref.startswith("SW"):
        return "buttons"
    if ref.startswith("LED"):
        return "leds"
    return "mcu"                           # conservative default (core decoupling)


def zone_centroid(z):
    x0, y0, x1, y1 = z["bbox"]
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def build_plan(pcb: Path) -> dict:
    text = pcb.read_text()
    meta = load_pcb(pcb)
    outline = _pcb.board_outline(text)
    sheets = sheet_membership(pcb.parent)

    assign = {}
    for ref in meta:
        if ref in FIXED or ref.startswith("H"):
            continue
        assign[ref] = classify(ref, sheets.get(ref))

    # record mounting holes' current (locked) positions as fixed
    fixed = dict(FIXED)
    for ref, m in meta.items():
        if ref.startswith("H"):
            fixed[ref] = {"pos": [round(m["anchor"]["x"], 2), round(m["anchor"]["y"], 2)],
                          "rot": m["anchor"]["rot"], "layer": m["layer"],
                          "edge": "corner", "why": "M2.5 mounting hole (locked)"}

    plan = {
        "board": {"x0": outline[0], "y0": outline[1], "x1": outline[2], "y1": outline[3]},
        "zones": ZONES,
        "fixed": fixed,
        "assign": assign,
    }
    plan["score"] = score_plan(plan, meta)
    plan["validation"] = validate_plan(plan, meta)
    return plan


def proxy_positions(plan: dict, meta: dict) -> dict:
    """refdes -> (x,y) proxy: fixed parts at their pos, others at zone centroid."""
    pos = {}
    for ref, fx in plan["fixed"].items():
        pos[ref] = tuple(fx["pos"])
    for ref, zone in plan["assign"].items():
        pos[ref] = zone_centroid(plan["zones"][zone])
    return pos


def score_plan(plan: dict, meta: dict) -> dict:
    """est_ratsnest = MST over per-net component proxy positions (GND excluded)."""
    pos = proxy_positions(plan, meta)
    by_net = {}
    for ref, m in meta.items():
        if ref not in pos:
            continue
        for pad in m["pads"]:
            net = pad.get("net")
            if not net or net in GROUND or net.endswith("/GND"):
                continue
            by_net.setdefault(net, set()).add(pos[ref])
    est = sum(mst_length(list(pts)) for pts in by_net.values() if len(pts) > 1)
    # zone capacity: sum member courtyard area vs zone area
    cap = {}
    for zname, z in plan["zones"].items():
        x0, y0, x1, y1 = z["bbox"]
        zarea = (x1 - x0) * (y1 - y0)
        used = 0.0
        for ref, zn in plan["assign"].items():
            if zn != zname:
                continue
            cy = meta[ref].get("courtyard_bbox")
            if cy:
                used += (cy[2] - cy[0]) * (cy[3] - cy[1])
        cap[zname] = {"zone_area": round(zarea, 1), "used_area": round(used, 1),
                      "util": round(used / zarea, 2) if zarea else None}
    return {"approach": plan.get("_approach", "A"),
            "est_ratsnest_mm": round(est, 1),
            "capacity": cap}


def validate_plan(plan: dict, meta: dict) -> dict:
    errs = []
    bx = plan["board"]
    movable = [r for r in meta if r not in plan["fixed"]]
    # every movable in exactly one zone
    for r in movable:
        if r not in plan["assign"]:
            errs.append(f"{r} unassigned")
    for r in plan["assign"]:
        if r not in meta:
            errs.append(f"assigned non-existent {r}")
    # zones inside outline
    for zn, z in plan["zones"].items():
        x0, y0, x1, y1 = z["bbox"]
        if x0 < bx["x0"] or y0 < bx["y0"] or x1 > bx["x1"] or y1 > bx["y1"]:
            errs.append(f"zone {zn} outside Edge.Cuts")
    # capacity overflow (>100% util can't physically fit)
    for zn, c in plan["score"]["capacity"].items() if "score" in plan else []:
        if c["util"] and c["util"] > 1.0:
            errs.append(f"zone {zn} over capacity ({c['util']})")
    # fixed parts present
    for r in FIXED:
        if r not in meta:
            errs.append(f"fixed part {r} missing from board")
    return {"ok": not errs, "violations": errs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--approach", default="A")
    ap.add_argument("--out", default="placement_phase_2/floorplan.json")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    meta = load_pcb(pcb)
    plan = build_plan(pcb)
    plan["_approach"] = args.approach
    plan["score"] = score_plan(plan, meta)
    plan["validation"] = validate_plan(plan, meta)

    Path(args.out).write_text(json.dumps(plan, indent=2))
    v = plan["validation"]
    s = plan["score"]
    print(f"approach {args.approach}: est_ratsnest={s['est_ratsnest_mm']}mm  "
          f"valid={v['ok']}  zones={len(plan['zones'])}  "
          f"assigned={len(plan['assign'])}  fixed={len(plan['fixed'])}")
    if not v["ok"]:
        for e in v["violations"]:
            print("  VIOLATION:", e)
    over = {z: c["util"] for z, c in s["capacity"].items() if c["util"] and c["util"] > 0.85}
    if over:
        print("  tight/over-capacity zones (util):", over)
    return 0


if __name__ == "__main__":
    sys.exit(main())
