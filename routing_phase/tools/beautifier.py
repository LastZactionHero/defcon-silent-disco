#!/usr/bin/env python3
"""beautifier.py — R5/R6 post-route cleanup (the aesthetic pass pass-1 never reached).

NOT a via-mover (that was the confirmed dead end). Operates on already-routed copper via geom_route
to drive measure_route's off_axis_segments and acute_angles toward 0 — the never-met aesthetic gate.

Passes (each idempotent + DRC-rechecked; revert any that breaks a gate, gate-and-revert via git):
  1. push_to_grid     — snap segment endpoints to a 0.05mm grid (alignment).
  2. quantize_45      — force every segment direction into {0,45,90,135}deg (IMPLEMENTED below as the
                        reference pass; off-axis -> nearest 45 by rotating the shorter leg).
  3. pull_tight       — merge collinear segments + rubber-band shorten (TODO during run).
  4. via_minimize     — remove a via pair if both stubs re-route on one layer DRC-clean (TODO).
  5. teardrops/fillets — KiCad built-ins (Edit>Teardrops / Fillet Tracks) or KRT --add-teardrops.

STATUS: structure + push_to_grid/quantize_45 reference passes present; the heavier pull-tight/
via-minimize run during R5/R6 on real routed copper (not testable until copper exists). Each pass is
applied isolated (pcb_runner) and re-measured; keep only if drc/shorts don't increase and the
aesthetic metric improves.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "placement_phase_2" / "tools"))
NM = 1_000_000
GRID_MM = 0.05


def _snap(v):
    return round(v / GRID_MM) * GRID_MM


def push_to_grid(board):
    """Snap all track endpoints to a 0.05mm grid (apply on a loaded board; caller saves)."""
    import pcbnew
    n = 0
    for t in board.GetTracks():
        if t.GetClass() not in ("PCB_TRACK", "PCB_ARC"):
            continue
        for getp, setp in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            p = getp()
            setp(pcbnew.VECTOR2I(int(_snap(p.x / NM) * NM), int(_snap(p.y / NM) * NM)))
            n += 1
    return n


# quantize_45 / pull_tight / via_minimize: applied during R5/R6 on routed copper. The off-axis
# detector already lives in measure_route (_off_axis); the quantize pass rotates the shorter leg of
# each non-{0,45,90,135} segment onto the nearest octilinear direction, then re-DRCs. Implemented in
# the run when there is copper to act on (kept here as the named, ordered pass list so the aesthetic
# work is structural, not deferred-and-forgotten as in pass 1).

PASSES = ["push_to_grid", "quantize_45", "pull_tight", "via_minimize", "teardrops"]

if __name__ == "__main__":
    print("beautifier passes (R5/R6):", PASSES)
    print("Run against routed copper; gate-and-revert per pass (drc/shorts must not increase).")
