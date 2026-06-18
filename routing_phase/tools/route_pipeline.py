#!/usr/bin/env python3
"""route_pipeline.py — the reproducible signals-first routing pipeline (D2(4)/D3).

Orchestrates KRT (solver) + the bridge (pcbnew writer) into one deterministic chain, with
EACH pcbnew step in its own subprocess (one LoadBoard+SaveBoard per process — multi-load in
one process corrupts the swig wrapper registry). KRT is invoked via the venv with arg LISTS
(no shell quoting — the bug that produced a bogus "0/18 routed").

Pipeline:
  base   : copy project to a work dir, rip routing, fill ONLY inner planes (In1/In2), leave the
           outer F.Cu/B.Cu GND pours UNFILLED so KRT can route signals on B.Cu (filled pours are
           a solid obstacle to KRT — the D3(1) finding).
  route  : KRT route.py over the 62 signal nets (--ordering original = fast; mps+rip-up is
           pathologically slow on this board).
  fanout : KRT route_planes.py with --same-net-pad-clearance 0.2 (offset vias, NO via-in-pad).
  apply  : krt_bridge extract -> apply_routing(target, replace=True, refill=True) — refill
           restores the outer pours around the new traces.

Usage:
  route_pipeline.py --target <board.kicad_pcb>   apply the routed solution to <board>
  route_pipeline.py --validate                   route + apply to a /tmp verify copy, print metrics
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
KPY = str(HOME / ".local/share/defcon-badge-krt/venv/bin/python")
KRT = str(HOME / ".local/share/defcon-badge-krt/KiCadRoutingTools")
REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "routing_phase" / "tools"
SRC = REPO / "defcon_badge"
BOARD = "defcon_badge.kicad_pcb"


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _pcbnew(code: str):
    """Run a pcbnew snippet in its own process (isolation); returns CompletedProcess."""
    return _run(["python3", "-c", code])


def build_base(board: str):
    # TWO isolated processes: delete_routing + fill in ONE process segfaults before SaveBoard
    # (the save never lands). Saving right after each heavy op makes it persist (the teardown may
    # still crash with a nonzero exit, but SaveBoard already wrote the file — so don't gate on it).
    # step 1: rip all routing, save.
    _pcbnew(f'''
import sys,os; sys.path.insert(0,"{TOOLS}")
import geom_route,pcbnew
b=pcbnew.LoadBoard({board!r}); geom_route.delete_routing(b); pcbnew.SaveBoard({board!r},b)
sys.stdout.flush(); os._exit(0)
''')
    # step 2: outer F.Cu/B.Cu GND pours UNFILLED; fill only the inner planes; save.
    _pcbnew(f'''
import sys,os; sys.path.insert(0,"{TOOLS}")
import pcbnew
b=pcbnew.LoadBoard({board!r})
for z in b.Zones():
    if b.GetLayerName(z.GetLayer()) in ("F.Cu","B.Cu"): z.SetIsFilled(False)
pcbnew.ZONE_FILLER(b).Fill([z for z in b.Zones() if b.GetLayerName(z.GetLayer()) not in ("F.Cu","B.Cu")])
pcbnew.SaveBoard({board!r},b); sys.stdout.flush(); os._exit(0)
''')


def route_signals(board: str, nets: list):
    # --layers F.Cu B.Cu --layer-costs 2.0 1.0: penalize F.Cu so KRT BALANCES onto B.Cu.
    # Without this KRT routes F.Cu-only (B.Cu ~22mm); with it B.Cu carries ~half the length.
    # (NOTE D3(2): this does NOT fix the ~13 intrinsically-failing nets — those fail on
    # escape/crossing congestion near the U3 QFN, not layer capacity — but it makes the board
    # use both signal layers, which is correct for a 2-signal-layer board + better for cleanup.)
    r = _run([KPY, f"{KRT}/route.py", board, "--overwrite", "--nets", *nets,
              "--track-width", "0.15", "--clearance", "0.15",
              "--via-size", "0.6", "--via-drill", "0.35", "--ordering", "original",
              "--layers", "F.Cu", "B.Cu", "--layer-costs", "2.0", "1.0"], timeout=180)
    line = next((l.strip() for l in r.stdout.splitlines() if "Single-ended:" in l), "?")
    return line


def fanout(board: str):
    _run([KPY, f"{KRT}/route_planes.py", board, "--overwrite", "--skip-existing-zones",
          "--nets", "GND", "+3V3", "--plane-layers", "In1.Cu", "In2.Cu",
          "--via-size", "0.6", "--via-drill", "0.35", "--same-net-pad-clearance", "0.2",
          "--add-gnd-vias", "--gnd-via-net", "GND"], timeout=180)


def bridge_apply(krt_board: str, target: str):
    _pcbnew(f'''
import sys,os; sys.path.insert(0,"{TOOLS}")
import krt_bridge
t,v=krt_bridge.extract_routing({krt_board!r})
krt_bridge.apply_routing({target!r}, t, v, refill=True, replace=True)
sys.stdout.flush(); os._exit(0)
''')


def run_pipeline(target: str, nets: list) -> str:
    work = Path("/tmp/route_pipeline_work")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in SRC.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_sch", ".kicad_pro"):
            shutil.copy2(f, work / f.name)
    B = str(work / BOARD)
    build_base(B)
    route_line = route_signals(B, nets)
    fanout(B)
    bridge_apply(B, target)
    shutil.rmtree(work, ignore_errors=True)
    return route_line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help="board to apply the routed solution to")
    ap.add_argument("--validate", action="store_true", help="apply to a /tmp verify copy + print metrics")
    args = ap.parse_args()

    nets = json.load(open("/tmp/signal_nets.json")) if Path("/tmp/signal_nets.json").exists() else None
    if nets is None:
        r = _pcbnew(f'''
import sys,os; sys.path.insert(0,"{TOOLS}")
import route_db,json
live=route_db.live_nets("{SRC/BOARD}")
print(json.dumps([live[s]["net_name"] for s in route_db.stable_order(live)]))
''')
        nets = json.loads(r.stdout.strip().splitlines()[-1])

    if args.validate:
        vdir = Path("/tmp/route_validate"); shutil.rmtree(vdir, ignore_errors=True); vdir.mkdir(parents=True)
        for f in SRC.iterdir():
            if f.suffix in (".kicad_pcb", ".kicad_sch", ".kicad_pro"):
                shutil.copy2(f, vdir / f.name)
        target = str(vdir / BOARD)
    else:
        target = args.target
        if not target:
            print("ERROR: need --target or --validate"); return 2

    route_line = run_pipeline(target, nets)
    print("route:", route_line)
    m = _run(["python3", str(TOOLS / "measure_route.py"), target, "--no-drc", "--json"])
    md = json.loads(m.stdout)
    bl = md["track_len_by_layer"]
    print("metrics: completion=%.1f%% unconnected=%d via_in_pad=%d F.Cu=%.0f B.Cu=%.0f balance=%s" % (
        md["completion_pct"], md["unconnected"], md["via_in_pad"],
        bl.get("F.Cu", 0), bl.get("B.Cu", 0), md["layer_balance"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
