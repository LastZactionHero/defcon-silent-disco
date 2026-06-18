#!/usr/bin/env python3
"""rework_stackup.py — D1: rework the ported 2-layer-dev-board stackup into a proper 4-layer
badge arrangement (per routing_phase/STACKUP_SPEC.md).

The inherited zones are crude 4-point rectangles that miss the right ~3.6mm of the board and
don't follow the sawtooth Edge.Cuts. This recreates the copper zones to follow the real board
outline (inset 0.3mm = min copper-edge clearance): In1 solid GND plane, In2 +3V3-dominant pour,
F.Cu + B.Cu GND pours — and sets board thickness 1.0->1.6mm. Single-writer (writer_lock); does
NOT move footprints. The dielectric stackup block (fab metadata) and the USB_DIFF_90 netclass fix
are handled in their own steps (see STATE/LEDGER) to keep this write focused.

Usage: rework_stackup.py <board.kicad_pcb> [--dry-run-on COPY.kicad_pcb]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "placement_phase_2" / "tools"))
from writer_lock import assert_writable   # noqa: E402

INSET_MM = 0.3
ZONE_CLEARANCE_MM = 0.2
ZONE_MIN_THICK_MM = 0.25
BOARD_THICKNESS_MM = 1.6
ZONE_PLAN = [("In1.Cu", "GND"), ("In2.Cu", "+3V3"), ("F.Cu", "GND"), ("B.Cu", "GND")]


def rework(path, guard_lock=True):
    if guard_lock:
        assert_writable(str(path))
    b = pcbnew.LoadBoard(str(path))

    ds = b.GetDesignSettings()             # hold one ref (a fresh call after SaveBoard goes stale)
    ds.SetBoardThickness(int(BOARD_THICKNESS_MM * 1e6))

    try:                                   # cosmetic: In2 now carries +3V3 pour + signals
        b.SetLayerType(b.GetLayerID("In2.Cu"), pcbnew.LT_MIXED)
    except Exception:
        pass

    for z in list(b.Zones()):              # drop the artifact rectangles (all unfilled, lossless)
        b.Remove(z)

    poly = pcbnew.SHAPE_POLY_SET()         # real board outline, inset by the edge clearance
    b.GetBoardPolygonOutlines(poly, False)
    poly.Inflate(int(-INSET_MM * 1e6), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, int(0.01 * 1e6))

    for layer, net in ZONE_PLAN:
        z = pcbnew.ZONE(b)
        z.SetLayer(b.GetLayerID(layer))
        z.SetNet(b.FindNet(net))
        z.SetIsFilled(False)
        z.SetLocalClearance(int(ZONE_CLEARANCE_MM * 1e6))
        z.SetMinThickness(int(ZONE_MIN_THICK_MM * 1e6))
        # SOLID pad/via connection: these are GND/+3V3 PLANES — full copper is the textbook
        # choice (lowest impedance, best return path) and eliminates starved_thermal (1-spoke)
        # edge pads that thermal relief produced on the F.Cu pour.
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.AddPolygon(poly.Outline(0))
        b.Add(z)

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(path), b)
    # IMPORTANT: do NOT introspect the board after Fill/Save — the LoadBoard->mutate->Fill->Save
    # sequence corrupts pcbnew's swig wrapper registry within one process (Zones()/GetDesignSettings
    # start returning raw pointers). One LoadBoard + one SaveBoard per process; verify with a fresh
    # measure_route subprocess. Return only what we set/created, no board reads.
    return {"thickness_mm": BOARD_THICKNESS_MM, "zones_created": [f"{net}@{layer}" for layer, net in ZONE_PLAN]}


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    r = rework(p)
    print("thickness:", r["thickness_mm"], "mm")
    print("zones created (verify fill via measure_route in a fresh process):", r["zones_created"])
    # pcbnew's swig teardown can segfault at interpreter exit AFTER a successful save (harmless to
    # the written board, but it yields a nonzero exit code). The work is done + saved above; exit
    # cleanly so callers see success. Flush first since os._exit skips normal buffer flushing.
    import os
    sys.stdout.flush()
    os._exit(0)
