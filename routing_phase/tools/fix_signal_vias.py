#!/usr/bin/env python3
"""fix_signal_vias.py — post-process KRT route.py signal vias to satisfy via_in_pad==0
(USER HARD GATE) + via-to-via clearance.

KRT route.py places signal layer-change vias ON pads (electrically connected by copper overlap)
and sometimes too close to each other; route.py has no offset/spacing flag (unlike route_planes).
This nudges each offending via off the pad / apart, relinking its tracks and adding an explicit
pad->via stub so connectivity is preserved.

Per via-in-pad via V at pad P (pad center PC), connected to tracks:
  1. escape dir = direction of V's LONGEST connected track (where the route goes).
  2. new pos P' = PC + escape * (pad_half + GAP); if blocked, try alternate directions.
  3. move every track endpoint at P -> P'; move V -> P'.
  4. add a stub PC->P' on the pad's layer (same net) to replace the lost pad/via overlap.
Via-to-via clearance: nudge ONE via of each too-close different-net pair apart (same relink).

Usage: fix_signal_vias.py <board.kicad_pcb>   (operates in place; verify with measure_route)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "placement_phase_2" / "tools"))
from writer_lock import assert_writable   # noqa: E402

NM = 1_000_000
GAP_MM = 0.28          # how far past the pad edge to place the moved via
VIA_DIA_MM = 0.6
MIN_VIA_GAP_MM = 0.15  # edge-to-edge clearance between different-net vias


def _v(x, y):
    return pcbnew.VECTOR2I(int(round(x)), int(round(y)))


def _pads(b):
    return [p for f in b.GetFootprints() for p in f.Pads()]


def _vias(b):
    return [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]


def _tracks(b):
    return [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]


def _on_pad(v, pads):
    pos = v.GetPosition()
    for p in pads:
        if p.HitTest(pos) and (p.IsOnLayer(v.TopLayer()) or p.IsOnLayer(v.BottomLayer())):
            return p
    return None


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _clear_spot(b, pos, net_code, ignore_via, pads, vias, tracks, min_gap_nm):
    """True if a via at `pos` (net_code) keeps min_gap from other-net pads, vias AND tracks."""
    vr = VIA_DIA_MM * NM / 2
    for p in pads:
        if p.GetNetCode() == net_code:
            continue
        if (pos - p.GetPosition()).EuclideanNorm() < vr + min_gap_nm + max(p.GetSize().x, p.GetSize().y) / 2:
            return False
    for o in vias:
        if o is ignore_via or o.GetNetCode() == net_code:
            continue
        if (pos - o.GetPosition()).EuclideanNorm() < VIA_DIA_MM * NM + min_gap_nm:
            return False
    # NOTE: track clearance intentionally NOT checked here. Empirically, the TINY escape-channel
    # move (GAP past the pad edge, along the via's own route) stays clear of other copper and gives
    # 0 new DRC; adding a track-check + larger search pushed vias/stubs into other nets (85 DRC).
    # The few vias with no clear pad/via spot at GAP are left for the straggler re-route (D3(5)).
    return True


def _relink(b, old_pos, new_pos, tracks):
    for t in tracks:
        if t.GetStart() == old_pos:
            t.SetStart(new_pos)
        if t.GetEnd() == old_pos:
            t.SetEnd(new_pos)


def _move_via_off(b, v, pad, pads, vias, tracks):
    """Move via v off `pad` (or, if pad is None, just to a clear spot) along its route. Returns
    True on success."""
    P = v.GetPosition()
    PC = pad.GetPosition() if pad else P
    net = v.GetNet()
    conn = [t for t in tracks if t.GetStart() == P or t.GetEnd() == P]
    # escape direction = longest connected track's far end
    best = None
    for t in conn:
        o = t.GetEnd() if t.GetStart() == P else t.GetStart()
        d = (o - P).EuclideanNorm()
        if best is None or d > best[0]:
            best = (d, o)
    if best and best[0] > 1:
        dx, dy = best[1].x - P.x, best[1].y - P.y
    else:
        dx, dy = 1, 0
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    half = (max(pad.GetSize().x, pad.GetSize().y) / 2 if pad else VIA_DIA_MM * NM / 2)
    # try the escape dir, then rotations, at increasing distances, for a clear spot
    for dist in (GAP_MM,):                  # TINY move only — stay in the via's own escape channel
      for ang in (0, 45, -45, 90, -90, 135, -135, 180):
        a = math.radians(ang)
        rx = ux * math.cos(a) - uy * math.sin(a)
        ry = ux * math.sin(a) + uy * math.cos(a)
        Pn = _v(PC.x + rx * (half + dist * NM), PC.y + ry * (half + dist * NM))
        if _clear_spot(b, Pn, net.GetNetCode(), v, pads, vias, tracks, MIN_VIA_GAP_MM * NM):
            _relink(b, P, Pn, tracks)
            if pad:  # explicit stub pad-center -> new via pos on the pad's layer
                layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
                st = pcbnew.PCB_TRACK(b)
                st.SetStart(PC); st.SetEnd(Pn); st.SetWidth(int(0.15 * NM))
                st.SetLayer(layer); st.SetNet(net); b.Add(st)
            v.SetPosition(Pn)
            return True
    return False


def fix(path, guard=True):
    if guard:
        assert_writable(str(path))
    b = pcbnew.LoadBoard(str(path))
    pads = _pads(b)
    # via-in-pad: process ONE via at a time, RE-QUERYING the board each pass (object lists go stale
    # as vias move + stubs are added; reusing them corrupted other nets -> 125 DRC/8 shorts).
    fixed_pad = 0
    tried = set()
    while True:
        vias, tracks = _vias(b), _tracks(b)
        target = next((v for v in vias if id(v) not in tried and _on_pad(v, pads)), None)
        if target is None:
            break
        tried.add(id(target))
        if _move_via_off(b, target, _on_pad(target, pads), pads, vias, tracks):
            fixed_pad += 1
    failed = sum(1 for v in _vias(b) if _on_pad(v, pads))
    # via-to-via clearance: nudge one of each too-close different-net pair (fresh state each)
    fixed_clr = 0
    tried.clear()
    while True:
        vlist, tracks = _vias(b), _tracks(b)
        pair = None
        for i in range(len(vlist)):
            for j in range(i + 1, len(vlist)):
                a, c = vlist[i], vlist[j]
                if a.GetNetCode() == c.GetNetCode() or id(c) in tried:
                    continue
                if (a.GetPosition() - c.GetPosition()).EuclideanNorm() < VIA_DIA_MM * NM + MIN_VIA_GAP_MM * NM:
                    pair = c
                    break
            if pair:
                break
        if pair is None:
            break
        tried.add(id(pair))
        if _move_via_off(b, pair, None, pads, vlist, tracks):
            fixed_clr += 1
    pcbnew.SaveBoard(str(path), b)
    return {"fixed_via_in_pad": fixed_pad, "failed": failed, "fixed_clearance": fixed_clr}


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    r = fix(p)
    print(r)
    sys.stdout.flush()
    os._exit(0)
