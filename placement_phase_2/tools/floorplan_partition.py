#!/usr/bin/env python3
"""floorplan_partition.py — Approach B: connectivity-driven floor plan.

Where Approach A (floorplan.py) groups parts by their schematic SHEET, Approach B
derives grouping from the NETLIST: build a component graph weighted by shared
signal nets (power/ground rails excluded), seed each board region with its fixed
anchor IC, and let every other part flow by label-propagation to the region it is
most strongly connected to. This lets connectivity — not the schematic's authoring
structure — decide where a part belongs (e.g. a passive whose sheet says "MCU" but
whose real signal ties pull it into the audio chain).

Reuses floorplan.py's zones, fixed constraints, validation and scoring so A and B
are scored identically and comparably.

Usage:
  floorplan_partition.py defcon_badge/defcon_badge.kicad_pcb \
      --out placement_phase_2/floorplan_B.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
from fp_meta import load_pcb            # noqa: E402
import _pcb                            # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import floorplan as A                  # noqa: E402  (reuse ZONES/FIXED/score/validate)

# High-fanout rails carry no grouping signal — exclude from the graph.
RAILS = {"GND", "+3V3", "+1V1", "VBUS", "BAT", "+5V"}

# One movable anchor per region (seeds for label propagation). These are the
# parts whose region is effectively pinned by a fixed neighbour or by intent.
SEEDS = {
    "U3": "mcu", "U2": "mcu",
    "U10": "power", "U11": "power",
    "U20": "audio", "U21": "audio",
    "LED20": "leds", "LED23": "leds",
    "J30": "sao",
    "SW20": "buttons",
    "R30": "ir",
}


def is_signal(net: str | None) -> bool:
    if not net:
        return False
    base = net.rsplit("/", 1)[-1]
    if base in RAILS or "GND" in base or base.startswith("unconnected"):
        return False
    return True


def build_graph(meta: dict) -> dict:
    """comp -> {neighbour: shared signal-net count}."""
    net_to_comps: dict[str, set] = {}
    for ref, m in meta.items():
        for pad in m["pads"]:
            n = pad.get("net")
            if is_signal(n):
                net_to_comps.setdefault(n, set()).add(ref)
    adj: dict[str, dict] = {r: {} for r in meta}
    for comps in net_to_comps.values():
        comps = list(comps)
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a, b = comps[i], comps[j]
                adj[a][b] = adj[a].get(b, 0) + 1
                adj[b][a] = adj[b].get(a, 0) + 1
    return adj


def propagate(meta: dict, adj: dict) -> dict:
    """Seeded label propagation. Returns refdes -> region (movable parts only)."""
    movable = [r for r in meta if r not in A.FIXED and not r.startswith("H")]
    label = {r: SEEDS.get(r) for r in movable}
    seeds = {r for r in movable if label[r]}
    changed = True
    rounds = 0
    while changed and rounds < 50:
        changed = False
        rounds += 1
        for r in movable:
            if r in seeds:
                continue
            tally: dict[str, float] = {}
            for nb, w in adj.get(r, {}).items():
                lab = label.get(nb)
                if lab:
                    tally[lab] = tally.get(lab, 0) + w
            if tally:
                best = max(tally, key=tally.get)
                if best != label[r]:
                    label[r] = best
                    changed = True
    # fallback for parts that never reached a seed: use schematic-sheet classify
    sheets = A.sheet_membership(Path(next(iter(meta))).parent) if False else None
    for r in movable:
        if not label[r]:
            label[r] = "mcu"          # conservative default (orphan/global-only parts)
    return label


def build_plan_B(pcb: Path) -> dict:
    text = pcb.read_text()
    meta = load_pcb(pcb)
    outline = _pcb.board_outline(text)
    adj = build_graph(meta)
    assign = propagate(meta, adj)

    fixed = dict(A.FIXED)
    for ref, m in meta.items():
        if ref.startswith("H"):
            fixed[ref] = {"pos": [round(m["anchor"]["x"], 2), round(m["anchor"]["y"], 2)],
                          "rot": m["anchor"]["rot"], "layer": m["layer"],
                          "edge": "corner", "why": "M2.5 mounting hole (locked)"}

    plan = {
        "board": {"x0": outline[0], "y0": outline[1], "x1": outline[2], "y1": outline[3]},
        "zones": A.ZONES,
        "fixed": fixed,
        "assign": assign,
        "_approach": "B",
    }
    plan["score"] = A.score_plan(plan, meta)
    plan["validation"] = A.validate_plan(plan, meta)
    return plan, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--out", default="placement_phase_2/floorplan_B.json")
    args = ap.parse_args()

    plan, meta = build_plan_B(Path(args.pcb))
    Path(args.out).write_text(json.dumps(plan, indent=2))
    v, s = plan["validation"], plan["score"]
    print(f"approach B: est_ratsnest={s['est_ratsnest_mm']}mm  valid={v['ok']}  "
          f"assigned={len(plan['assign'])}  fixed={len(plan['fixed'])}")
    if not v["ok"]:
        for e in v["violations"]:
            print("  VIOLATION:", e)
    # show where B disagrees with A's sheet-based grouping
    sheets = A.sheet_membership(Path(args.pcb).parent)
    diffs = []
    for r, zone in plan["assign"].items():
        a_zone = A.classify(r, sheets.get(r))
        if a_zone != zone:
            diffs.append(f"{r}:{a_zone}->{zone}")
    print(f"  A/B grouping differences ({len(diffs)}): {' '.join(diffs) if diffs else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
