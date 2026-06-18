#!/usr/bin/env python3
"""escape_planner.py — R3 QFN escape (the linchpin). See ESCAPE_SPEC.md.

Escapes every signal pin of a QFN to OPEN space BEFORE bulk routing, so via_in_pad==0 by construction
and the bulk router starts from a relieved ring. Multi-layer because a single layer can't hold the
escapes at 0.4mm pitch under the 0.15mm clearance rule (proven: qfn_fanout alone -> 54 clearance errs).

Strategy (per side, pads in index order, ALTERNATE layer):
  - even pads -> F.Cu DIRECT escape via KRT qfn_fanout (no via).
  - odd pads  -> B.Cu DOG-BONE: short F.Cu stub pad->via(off-pad, in the empty annulus)->B.Cu stub out.
  This doubles per-layer pitch to ~0.8mm -> stubs clear 0.15mm. Vias sit in open space (never on a pad).

Emits escape_plan.json (the hand-off contract) and applies copper via pcbnew (geom_route / krt_bridge).

Usage: escape_planner.py <board.kicad_pcb> --ref U3 [--apply] [--nets-exclude GND +3V3 +1V1]
  (run on the RIPPED board — escapes are the first copper laid.)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "placement_phase_2" / "tools"))
import geom_route          # noqa: E402
import krt_bridge          # noqa: E402
from writer_lock import assert_writable  # noqa: E402

NM = 1_000_000
KPY = str(Path.home() / ".local/share/defcon-badge-krt/venv/bin/python")
KRT = str(Path.home() / ".local/share/defcon-badge-krt/KiCadRoutingTools")
TRACK_W = 0.15
VIA_DIA, VIA_DRILL = 0.6, 0.35
DOGBONE_VIA_R = 1.25   # mm past pad center for the B.Cu dog-bone via (in the empty annulus)
DOGBONE_EXIT_R = 1.9   # mm past pad center for the B.Cu escape-point


def classify(board_path, ref, exclude):
    """Per signal pad of `ref`: {pad, net, x, y, side, idx}. Side by angle from footprint center."""
    with geom_route.safe_board(board_path) as b:
        fp = next((f for f in b.GetFootprints() if f.GetReference() == ref), None)
        if fp is None:
            raise SystemExit(f"{ref} not found")
        c = fp.GetPosition()
        pads = []
        for p in fp.Pads():
            net = p.GetNetname()
            if not net or net in exclude or any(net.endswith(e) for e in exclude):
                continue
            pos = p.GetPosition()
            dx, dy = pos.x - c.x, pos.y - c.y
            if abs(dx) >= abs(dy):
                side = "right" if dx > 0 else "left"
            else:
                side = "bottom" if dy > 0 else "top"
            pads.append({"pad": p.GetNumber(), "net": net, "x": pos.x, "y": pos.y,
                         "side": side, "cx": c.x, "cy": c.y})
        # order along each side; assign alternating layer by index
        for side in ("top", "bottom", "left", "right"):
            sp = [p for p in pads if p["side"] == side]
            key = (lambda p: p["x"]) if side in ("top", "bottom") else (lambda p: p["y"])
            sp.sort(key=key)
            for i, p in enumerate(sp):
                p["idx"] = i
                p["layer"] = "F.Cu" if i % 2 == 0 else "B.Cu"
        return pads


def run_qfn_fanout(board_path, ref, nets):
    """KRT qfn_fanout for the F.Cu-direct nets -> extract escape tracks via the bridge."""
    td = Path(tempfile.mkdtemp(prefix="esc_"))
    out = td / "fan.kicad_pcb"
    # copy project so KRT/DRC see the .kicad_pro
    for f in Path(board_path).parent.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_sch"):
            (td / f.name).write_bytes(f.read_bytes())
    src = td / Path(board_path).name
    cmd = [KPY, f"{KRT}/qfn_fanout.py", str(src), "--component", ref, "--output", str(out),
           "--layer", "F.Cu", "--width", str(TRACK_W), "--clearance", "0.15", "--nets", *nets]
    subprocess.run(cmd, capture_output=True)
    tracks = []
    if out.exists():
        tracks, _ = krt_bridge.extract_routing(out)
    import shutil
    shutil.rmtree(td, ignore_errors=True)
    return tracks


def _pad_obstacles(board_path, ref):
    """(x_mm, y_mm, radius_mm) for ALL pads near `ref` — clearance obstacles for dog-bone placement."""
    obs = []
    with geom_route.safe_board(board_path) as b:
        fp = next(f for f in b.GetFootprints() if f.GetReference() == ref)
        c = fp.GetPosition()
        for f in b.GetFootprints():
            for p in f.Pads():
                pos = p.GetPosition()
                if math.hypot(pos.x - c.x, pos.y - c.y) > 8 * NM:   # only near U3
                    continue
                r = max(p.GetSize().x, p.GetSize().y) / 2 / NM
                obs.append((pos.x / NM, pos.y / NM, r, p.GetNetname()))
    return obs


def _seg_pt(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def build_dogbones(pads, fcu_tracks, pad_obs):
    """Collision-VALIDATED B.Cu dog-bones for the B.Cu-assigned pads: sweep radius/angle for a via +
    stubs clear of other-net pads, the F.Cu escapes, and already-placed dog-bones."""
    tracks, vias, plan, placed_v = [], [], [], []   # placed_v: (x,y,net)
    GAP = 0.15
    for p in pads:
        if p["layer"] != "B.Cu":
            continue
        bx, by = p["x"] / NM, p["y"] / NM
        ux, uy = bx - p["cx"] / NM, by - p["cy"] / NM
        L = math.hypot(ux, uy) or 1
        ux, uy = ux / L, uy / L
        done = False
        for rad in (1.1, 1.4, 1.7, 2.0, 2.3):
          for ang in (0, 12, -12, 24, -24, 36, -36):
            a = math.radians(ang)
            dx = ux * math.cos(a) - uy * math.sin(a)
            dy = ux * math.sin(a) + uy * math.cos(a)
            vx, vy = bx + dx * rad, by + dy * rad
            ex, ey = bx + dx * (rad + 0.7), by + dy * (rad + 0.7)
            # via clear of other-net pads
            if any(o[3] != p["net"] and math.hypot(vx - o[0], vy - o[1]) < VIA_DIA / 2 + o[2] + GAP for o in pad_obs):
                continue
            # via clear of placed dog-bone vias (any net within via+gap; same-net ok further)
            if any(math.hypot(vx - v[0], vy - v[1]) < VIA_DIA + GAP for v in placed_v if v[2] != p["net"]):
                continue
            # F.Cu stub pad->via clear of other-net F.Cu escape tracks
            if any(t["net"] != p["net"] and t["layer"] == "F.Cu" and
                   _seg_pt((t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2, bx, by, vx, vy) < TRACK_W + GAP
                   for t in fcu_tracks):
                continue
            tracks.append({"x0": bx, "y0": by, "x1": vx, "y1": vy, "layer": "F.Cu", "net": p["net"], "width": TRACK_W})
            vias.append({"x": vx, "y": vy, "net": p["net"], "drill": VIA_DRILL, "size": VIA_DIA, "top": "F.Cu", "bottom": "B.Cu"})
            tracks.append({"x0": vx, "y0": vy, "x1": ex, "y1": ey, "layer": "B.Cu", "net": p["net"], "width": TRACK_W})
            placed_v.append((vx, vy, p["net"]))
            plan.append({"pad": p["pad"], "net": p["net"], "side": p["side"], "layer": "B.Cu",
                         "mode": "dogbone", "via": [vx, vy], "escape_point": [ex, ey, "B.Cu"]})
            done = True
            break
          if done:
            break
        if not done:
            plan.append({"pad": p["pad"], "net": p["net"], "side": p["side"], "mode": "FAILED"})
    return tracks, vias, plan


def plan_escape(board_path, ref, exclude, apply):
    pads = classify(board_path, ref, exclude)
    fcu_nets = [p["net"] for p in pads if p["layer"] == "F.Cu"]
    fcu_tracks = run_qfn_fanout(board_path, ref, fcu_nets) if fcu_nets else []
    pad_obs = _pad_obstacles(board_path, ref)
    db_tracks, db_vias, db_plan = build_dogbones(pads, fcu_tracks, pad_obs)
    # F.Cu plan records
    plan = db_plan + [{"net": p["net"], "side": p["side"], "layer": "F.Cu", "mode": "vialess"}
                      for p in pads if p["layer"] == "F.Cu"]
    summary = {"ref": ref, "n_signal": len(pads),
               "fcu_direct": len(fcu_nets), "bcu_dogbone": len(db_vias),
               "fcu_track_segs": len(fcu_tracks), "vias": len(db_vias)}
    if apply:
        assert_writable(str(board_path))
        b = pcbnew.LoadBoard(str(board_path))
        for t in fcu_tracks:
            geom_route.add_track(b, t["x0"], t["y0"], t["x1"], t["y1"], t["layer"], t["net"], t["width"])
        for t in db_tracks:
            geom_route.add_track(b, t["x0"], t["y0"], t["x1"], t["y1"], t["layer"], t["net"], t["width"])
        for v in db_vias:
            geom_route.add_via(b, v["x"], v["y"], v["net"], v["drill"], v["size"], v["top"], v["bottom"])
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        pcbnew.SaveBoard(str(board_path), b)
        (HERE.parent / "escape_plan.json").write_text(json.dumps(
            {"summary": summary, "pins": plan}, indent=1))
        sys.stdout.flush(); print(json.dumps(summary)); os._exit(0)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--ref", default="U3")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--nets-exclude", nargs="*", default=["GND", "+3V3", "+1V1"])
    args = ap.parse_args()
    print(json.dumps(plan_escape(args.board, args.ref, set(args.nets_exclude), args.apply)))


if __name__ == "__main__":
    main()
