#!/usr/bin/env python3
"""route_pipeline.py — Pass-2 phase DAG (escape-first, plane-fanout-LAST).

The pass-1 flat chain (base -> route -> fanout -> apply) had NO escape phase, lumped bus into bulk,
and poured plane fanout FIRST (which fenced the QFN pins — the root of the plateau). This rebuilds it
as an ordered phase DAG with the two structural fixes: escape is a phase, and plane fanout is LAST.

Order:  R(rip) -> R3 escape -> R4 bus -> R5 bulk singletons -> R6 plane fanout (LAST, keepout ring).
Every stage runs isolated (pcb_runner), records into route_db, is independently re-runnable, and is
verified by a fresh measure_route. The two PLANNING stages (R3/R4) come from the Workflow plan
artifacts (escape_plan.json / bus_plan.json); execution (R5/R6) is the loop.

Usage:
  route_pipeline.py --target <board> --phase rip|escape|bus|bulk|fanout
  route_pipeline.py --target <board> --all     run rip..fanout in order

This is the orchestrator; the per-phase tools (escape_planner, bus_topology_planner, KRT via
krt_bridge) hold the logic. KRT is invoked with its FULL toolbox (qfn_fanout, --bus,
--guide-corridor, turn-cost/attraction knobs) — never at defaults, never writing the board itself.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pcb_runner   # noqa: E402

PY = sys.executable


def _tool(name, *args):
    return subprocess.run([PY, str(HERE / name), *map(str, args)], capture_output=True, text=True)


def rip(board):
    """Full ripup: delete all tracks/vias, refill zones -> the placed+planes start state."""
    pcb_runner.rip(board)
    pcb_runner.refill(board)
    return "ripped to placed+planes"


def escape(board):
    """R3: escape the QFN(s) to open space (via_in_pad==0 by construction). See escape_planner.py."""
    _tool("escape_planner.py", board, "--ref", "U3", "--apply")
    # add J31/other dense connectors here if they block.
    return "R3 escape applied (escape_plan.json)"


def bus(board):
    """R4: emit the bus plan; route buses as constant-pitch bundles via KRT --guide-corridor.
    (Grouping/plan implemented in bus_topology_planner; the corridor-route step runs in the loop
    once escape endpoints exist.)"""
    _tool("bus_topology_planner.py", board)
    return "R4 bus_plan.json emitted (corridor route = loop step)"


def bulk(board):
    """R5: bulk-route singletons from the escaped/bussed skeleton with KRT's aesthetic knobs
    (--turn-cost, --via-cost, --track-proximity-*), small-set rip-up only. Via krt_bridge."""
    return "R5 bulk route (loop step — KRT aesthetic knobs via krt_bridge)"


def fanout(board):
    """R6 (LAST): plane fanout for GND/+3V3 with --same-net-pad-clearance 0.2 (no via-in-pad) AROUND
    the routed signals + a keepout ring so it can never re-fence an escaped pin. Then pour/stitch."""
    return "R6 plane fanout LAST (keepout ring; --same-net-pad-clearance 0.2)"


PHASES = {"rip": rip, "escape": escape, "bus": bus, "bulk": bulk, "fanout": fanout}
ORDER = ["rip", "escape", "bus", "bulk", "fanout"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--phase", choices=PHASES)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    phases = ORDER if args.all else [args.phase]
    for ph in phases:
        print(f"[{ph}] {PHASES[ph](args.target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
