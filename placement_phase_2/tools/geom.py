#!/usr/bin/env python3
"""geom.py — AUTHORITATIVE board geometry via the pcbnew API.

Replaces the regex-based fp_meta parser, which mis-handled rotated footprints
(wrong pad positions by up to several mm, and badly wrong courtyards for
connectors like the USB-C). Everything here comes straight from KiCad, so it
matches what DRC and the 3D viewer see. All tools (measure/place/anneal/
decouple) build on this.

load_pcb(path) -> { refdes: {
    value, layer ('F.Cu'|'B.Cu'), flipped,
    anchor: {x, y, rot},                 # mm, degrees (KiCad orientation)
    courtyard_bbox: [x0,y0,x1,y1],        # WORLD AABB at current pose (authoritative)
    courtyard_local: [x0,y0,x1,y1],       # AABB in the footprint's own (un-rotated) frame
    pads: [ {num, x, y, net, lx, ly} ],   # world XY + local (un-rotated) offsets
} }

The forward transform world = R(rot)*local + anchor (standard CCW) round-trips
against pcbnew at the current rot, so an optimizer that moves/rotates a part with
the same R stays consistent with what KiCad will render.
"""
from __future__ import annotations

import math
from pathlib import Path

import pcbnew

NM = 1e6


def rot(dx, dy, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return dx * c - dy * s, dx * s + dy * c


def load_pcb(path):
    b = pcbnew.LoadBoard(str(path))
    out = {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        ax, ay = pos.x / NM, pos.y / NM
        orient = fp.GetOrientationDegrees()
        flipped = fp.IsFlipped()
        layer = "B.Cu" if flipped else "F.Cu"

        pads = []
        for p in fp.Pads():
            pp = p.GetPosition()
            px, py = pp.x / NM, pp.y / NM
            net = p.GetNetname() or None
            lx, ly = rot(px - ax, py - ay, -orient)
            pads.append({"num": p.GetNumber(), "x": px, "y": py,
                         "net": net, "lx": lx, "ly": ly})

        side = pcbnew.B_CrtYd if flipped else pcbnew.F_CrtYd
        cbb = clocal = None
        try:
            cy = fp.GetCourtyard(side)
        except Exception:
            cy = None
        if cy and cy.OutlineCount() > 0:
            xs = []; ys = []; lxs = []; lys = []
            ol = cy.Outline(0)
            for i in range(ol.PointCount()):
                pt = ol.CPoint(i)
                wx, wy = pt.x / NM, pt.y / NM
                xs.append(wx); ys.append(wy)
                llx, lly = rot(wx - ax, wy - ay, -orient)
                lxs.append(llx); lys.append(lly)
            cbb = [min(xs), min(ys), max(xs), max(ys)]
            clocal = [min(lxs), min(lys), max(lxs), max(lys)]
        else:
            bb = fp.GetBoundingBox(False, False)
            cbb = [bb.GetLeft() / NM, bb.GetTop() / NM,
                   bb.GetRight() / NM, bb.GetBottom() / NM]
            w = (cbb[2] - cbb[0]) / 2
            h = (cbb[3] - cbb[1]) / 2
            clocal = [-w, -h, w, h]

        out[ref] = {
            "value": fp.GetValue(),
            "layer": layer,
            "flipped": flipped,
            "anchor": {"x": ax, "y": ay, "rot": orient},
            "courtyard_bbox": cbb,
            "courtyard_local": clocal,
            "pads": pads,
        }
    return out


def apply(pcb_path, moves):
    """Apply placement via the pcbnew API (NOT text-editing the (at) line).

    moves: { refdes: {x?, y? (mm), rot? (deg), flip? (bool)} }

    CRITICAL: rotation MUST go through SetOrientationDegrees so pad shapes rotate
    with the part. Text-editing only the footprint (at) angle rotates pad POSITIONS
    but not their orientations — pads smear together into unusable junk. This is
    the single writer for all placement tools."""
    b = pcbnew.LoadBoard(str(pcb_path))
    n = 0
    for fp in b.GetFootprints():
        r = fp.GetReference()
        if r not in moves:
            continue
        mv = moves[r]
        tgt_flip = mv.get("flip")
        if tgt_flip is not None and bool(tgt_flip) != fp.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        if mv.get("rot") is not None:
            fp.SetOrientationDegrees(float(mv["rot"]))
        if mv.get("x") is not None:
            fp.SetPosition(pcbnew.VECTOR2I(int(round(mv["x"] * NM)),
                                           int(round(mv["y"] * NM))))
        n += 1
    pcbnew.SaveBoard(str(pcb_path), b)
    return n


def board_outline(path):
    """Edge.Cuts AABB (mm) from pcbnew."""
    b = pcbnew.LoadBoard(str(path))
    bb = b.GetBoardEdgesBoundingBox()
    return (bb.GetLeft() / NM, bb.GetTop() / NM, bb.GetRight() / NM, bb.GetBottom() / NM)


if __name__ == "__main__":
    import sys
    m = load_pcb(Path(sys.argv[1]))
    print(f"{len(m)} footprints; outline {board_outline(sys.argv[1])}")
