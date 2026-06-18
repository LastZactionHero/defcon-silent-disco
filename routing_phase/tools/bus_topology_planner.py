#!/usr/bin/env python3
"""bus_topology_planner.py — R4 bus/topology planning (the aesthetic backbone).

Pass 1 lumped bus planning into "bulk route" and never built it, so the board reads autorouted. This
plans the named buses as constant-pitch bundles BEFORE bulk routing. Built on KRT's existing
bus_detection.py (grouping) + chip_boundary.py (crossing-minimal order) + route.py --guide-corridor.

STATUS: grouping + bus_plan.json emit are implemented and testable now. The corridor ROUTING step
consumes R3's escape_plan.json (the escaped-pin endpoints) and so is exercised during the run, after
R3 — left as the run's R4 work with the recipe below.

R4 recipe (per HARNESS):
  1. group_buses(board): from net names + endpoints -> declared buses. IMPLEMENTED below.
  2. for each bus: order members by chip_boundary unroll (two nets cross iff source/target orderings
     invert) so the bundle is planar; pick a trunk axis from the escaped endpoints.
  3. emit bus_plan.json {bus: {nets, member_order, trunk}}.
  4. route each bus with KRT:  route.py --bus --guide-corridor --guide-corridor-layer B.Cu
     --guide-corridor-spacing 0.30  (via krt_bridge), routing escape_point -> destination as a
     constant-pitch bundle. Fills measure_route.bus_pitch_var (the R4 PRIMARY metric).
PRIMARY metric: bus_pitch_var (≈0). Escalation ladder: guide-corridor-bundle -> krt-bus-mode ->
manual-corridor -> singleton-route-the-bus.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_db   # noqa: E402

# bus name -> regex over net names (extend as needed)
BUS_PATTERNS = {
    "QSPI":   r"QSPI_(SCLK|SD0|SD1|SD2|SD3|SS)",
    "SD_SPI0": r"(SD_SCK|SD_MOSI|SD_MISO|SD_CS|SD_CD)\b",
    "I2S":    r"I2S_(DIN|BCK|LRCK)",
    "SAO_I2C": r"SAO_(SDA|SCL)",
    "LED_SPI1": r"(LED_SCK|LED_DAT)",
}


def group_buses(board_path):
    """Group the live signal nets into declared buses by name. Returns {bus: [net_name,...]}."""
    live = route_db.live_nets(board_path)
    names = [r["net_name"] for r in live.values() if not r.get("is_plane")]
    buses, used = {}, set()
    for bus, pat in BUS_PATTERNS.items():
        members = sorted(n for n in names if re.search(pat, n))
        if members:
            buses[bus] = members
            used.update(members)
    buses["_singletons"] = sorted(n for n in names if n not in used)
    return buses


def emit_plan(board_path, out=None):
    buses = group_buses(board_path)
    plan = {"buses": {b: {"nets": m, "n": len(m),
                          "guide_corridor": True, "spacing_mm": 0.30, "layer": "B.Cu"}
                      for b, m in buses.items() if b != "_singletons"},
            "singletons": buses["_singletons"]}
    out = out or (HERE.parent / "bus_plan.json")
    Path(out).write_text(json.dumps(plan, indent=1))
    return plan


# route_bus(): TODO during R4 — drive KRT route.py --bus --guide-corridor per bus via krt_bridge,
# using escape_plan.json escape_points as sources. Measure bus_pitch_var after each.

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    plan = emit_plan(p)
    for b, d in plan["buses"].items():
        print(f"  bus {b:9} ({d['n']}): {d['nets']}")
    print(f"  singletons: {len(plan['singletons'])}")
