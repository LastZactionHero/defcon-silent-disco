#!/usr/bin/env python3
"""krt_bridge.py — use KiCadRoutingTools as a SOLVER, not a writer.

Finding (D2, 2026-06-17): KRT's own board writer emits `(net "GND")` (net NAME) inside
(segment ...)/(via ...) blocks, but KiCad 10 requires `(net <integer netcode>)`. So KRT's
output board does NOT load in pcbnew or kicad-cli ("Failed to load board") — KRT cannot be our
board writer. But the route geometry it computes is correct and good. This bridge keeps KRT's
intelligence behind OUR authoritative writer:

  KRT solves -> KRT writes its (unloadable) board -> extract its tracks/vias (net names are
  right there) -> re-apply via pcbnew/geom_route onto a CLEAN copy of the real board -> pcbnew
  writes a loadable, DRC-able, frozen-placement-preserving board.

This is the single integration seam for ALL KRT use (planes in D2, signals in D3): KRT never
touches the real board; pcbnew is the only writer (HARNESS Resolution 1).

API:
  extract_routing(krt_pcb_path) -> (tracks, vias)   parse KRT's output (net by name)
  apply_routing(real_pcb_path, tracks, vias, refill=True)  -> counts   (pcbnew, single-writer)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom_route  # noqa: E402  (authoritative pcbnew track/via writer + writer_lock)


def _sexpr_blocks(text: str, tag: str):
    """Yield balanced top-level `(tag ...)` blocks. Requires the char after `tag` to be a
    delimiter so tag='via' doesn't match '(vias ...)'."""
    needle = "(" + tag
    i = 0
    while True:
        i = text.find(needle, i)
        if i < 0:
            return
        after = text[i + len(needle): i + len(needle) + 1]
        if after and after not in " \t\r\n(":     # '(vias' when tag='via' -> skip
            i += len(needle)
            continue
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield text[i:j + 1]
        i = j + 1


def extract_routing(krt_pcb) -> tuple[list, list]:
    text = Path(krt_pcb).read_text()
    tracks, vias = [], []
    for blk in _sexpr_blocks(text, "segment"):
        s = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", blk)
        e = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", blk)
        w = re.search(r"\(width ([-\d.]+)\)", blk)
        ly = re.search(r'\(layer "([^"]+)"\)', blk)
        n = re.search(r'\(net "([^"]*)"\)', blk)
        if s and e and w and ly:
            tracks.append({"x0": float(s[1]), "y0": float(s[2]), "x1": float(e[1]), "y1": float(e[2]),
                           "width": float(w[1]), "layer": ly[1], "net": n[1] if n else None})
    for blk in _sexpr_blocks(text, "via"):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", blk)
        sz = re.search(r"\(size ([-\d.]+)\)", blk)
        dr = re.search(r"\(drill ([-\d.]+)\)", blk)
        lm = re.search(r"\(layers\s+([^)]*)\)", blk)
        layers = re.findall(r'"([^"]+)"', lm[1]) if lm else []
        n = re.search(r'\(net "([^"]*)"\)', blk)
        if at and sz and dr:
            vias.append({"x": float(at[1]), "y": float(at[2]), "size": float(sz[1]), "drill": float(dr[1]),
                         "top": layers[0] if layers else "F.Cu", "bottom": layers[-1] if layers else "B.Cu",
                         "net": n[1] if n else None})
    return tracks, vias


def apply_routing(real_pcb, tracks, vias, refill=True, replace=False) -> dict:
    """Apply extracted tracks/vias onto the real board via pcbnew (the ONLY writer). One
    LoadBoard + one SaveBoard (the swig registry corrupts on re-read in-process).

    replace=True rips ALL existing routing first, then lays the supplied set. Use this when the
    supplied (tracks, vias) is the COMPLETE current solution (KRT routes on a board that already
    holds all prior routing and emits prior+new, so extracting its full output and applying with
    replace keeps the real board == the latest full KRT solution with no duplication). replace=False
    appends (only for a known-disjoint delta)."""
    from writer_lock import assert_writable
    assert_writable(str(real_pcb))
    b = pcbnew.LoadBoard(str(real_pcb))
    if replace:
        geom_route.delete_routing(b)
    nt = nv = 0
    for t in tracks:
        geom_route.add_track(b, t["x0"], t["y0"], t["x1"], t["y1"], t["layer"], t["net"], t["width"])
        nt += 1
    for v in vias:
        geom_route.add_via(b, v["x"], v["y"], v["net"], v["drill"], v["size"], v["top"], v["bottom"])
        nv += 1
    if refill:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(real_pcb), b)
    return {"tracks": nt, "vias": nv}


if __name__ == "__main__":
    t, v = extract_routing(sys.argv[1])
    print(f"extracted {len(t)} tracks, {len(v)} vias from {sys.argv[1]}")
    from collections import Counter
    print("track nets:", dict(Counter(x["net"] for x in t)))
    print("via nets:", dict(Counter(x["net"] for x in v)))
