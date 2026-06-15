#!/usr/bin/env python3
"""place.py — constructive placement from a floor plan (Phase C step 1).

Reads the champion floorplan.json, pins fixed/edge parts at their locked
positions, and lays each zone's parts into its bbox with courtyard-aware
shelf-packing (skipping cells that would collide with a fixed part on the same
layer). Gets every part on-board, grouped by subsystem, with minimal overlaps —
the deterministic starting point for legalization + global optimization.

Keeps each zoned part's current rotation (orientation tuning is a later step).
Edge.Cuts and mounting holes are never touched.

Usage:
  place.py defcon_badge/defcon_badge.kicad_pcb \
      --plan placement_phase_2/floorplan.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geom import load_pcb               # noqa: E402  (authoritative pcbnew geometry)

MARGIN = 1.2     # gap inside a zone bbox edge
GAP = 1.0        # gap between packed courtyards

# F.*<->B.* layer pairs for flipping a footprint to the other side.
SWAPS = [("F.Cu", "B.Cu"), ("F.SilkS", "B.SilkS"), ("F.Mask", "B.Mask"),
         ("F.Paste", "B.Paste"), ("F.Fab", "B.Fab"), ("F.CrtYd", "B.CrtYd"),
         ("F.Adhes", "B.Adhes")]


def swap_layers(body: str) -> str:
    """Bidirectional F.*<->B.* swap (placeholder-guarded) — flips a part's side."""
    for f, _ in SWAPS:
        body = body.replace(f, f"__FLIP_{f}__")
    for f, b in SWAPS:
        body = body.replace(b, f)
    for f, b in SWAPS:
        body = body.replace(f"__FLIP_{f}__", b)
    return body


def set_anchor(body: str, x: float, y: float, rot=None) -> str:
    pat = re.compile(r"(^\t\t\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))",
                     re.M)

    def sub(m):
        if rot is not None:
            r = f" {rot}"
        else:
            r = f" {m.group(5)}" if m.group(5) else ""
        return f"{m.group(1)}{x:.3f} {y:.3f}{r}{m.group(6)}"

    return pat.sub(sub, body, count=1)


def size_of(m, rot=None):
    cy = m.get("courtyard_bbox")
    if not cy:
        return 4.0, 4.0
    w, h = cy[2] - cy[0], cy[3] - cy[1]
    if rot in (90, 270, -90):
        w, h = h, w
    return w, h


def rects_overlap(a, b):
    return (min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--plan", default="placement_phase_2/floorplan.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    plan = json.loads(Path(args.plan).read_text())
    meta = load_pcb(pcb)
    text = pcb.read_text()

    moves = {}            # ref -> (anchor_x, anchor_y, rot|None)
    fixed_aabbs = []      # (x0,y0,x1,y1,layer) reserved by fixed parts

    # 1) fixed / edge parts (skip mounting holes — already locked in place)
    for ref, fx in plan["fixed"].items():
        if ref.startswith("H") or ref not in meta:
            continue
        x, y = fx["pos"]
        rot = fx.get("rot")
        moves[ref] = (float(x), float(y), rot)
        w, h = size_of(meta[ref], rot)
        fixed_aabbs.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2,
                            fx.get("layer", "F.Cu")))

    # 2) zone parts — shelf-pack inside each zone bbox, avoiding fixed AABBs
    zones = plan["zones"]
    by_zone = {}
    for ref, z in plan["assign"].items():
        by_zone.setdefault(z, []).append(ref)

    def courtyard_center_offset(m):
        """(anchor - courtyard_center) so we can land a courtyard center on a target."""
        cyb = m.get("courtyard_bbox")
        if not cyb:
            return 0.0, 0.0
        ccx, ccy = (cyb[0] + cyb[2]) / 2, (cyb[1] + cyb[3]) / 2
        return m["anchor"]["x"] - ccx, m["anchor"]["y"] - ccy

    for zname, refs in by_zone.items():
        z = zones[zname]
        zx0, zy0, zx1, zy1 = z["bbox"]

        # ROW topology: evenly space parts in a single horizontal line, courtyard
        # centered in its slot — guarantees no overlap when slots are wide enough.
        if z.get("topology") == "row":
            ordered = sorted(refs, key=lambda r: (int(re.search(r"\d+", r).group())))
            n = len(ordered)
            slot = (zx1 - zx0) / n
            widest = max(size_of(meta[r])[0] for r in ordered)
            if slot >= widest + 0.4:                 # fits as a single clean row
                row_cy = (zy0 + zy1) / 2
                for i, ref in enumerate(ordered):
                    ox, oy = courtyard_center_offset(meta[ref])
                    tcx = zx0 + (i + 0.5) * slot
                    moves[ref] = (tcx + ox, row_cy + oy, None)
                continue                             # zone done

        refs = sorted(refs, key=lambda r: -size_of(meta[r])[0] * size_of(meta[r])[1])
        cx, cy_shelf, shelf_h = zx0 + MARGIN, zy0 + MARGIN, 0.0
        for ref in refs:
            m = meta[ref]
            layer = m["layer"]
            w, h = size_of(m)
            placed = False
            tries = 0
            while not placed and tries < 400:
                tries += 1
                if cx + w > zx1 - MARGIN:                # wrap shelf
                    cx = zx0 + MARGIN
                    cy_shelf += shelf_h + GAP
                    shelf_h = 0.0
                if cy_shelf + h > zy1 - MARGIN:          # zone full -> overflow downward
                    pass
                box = (cx, cy_shelf, cx + w, cy_shelf + h)
                hit = any(rects_overlap(box, fa[:4]) for fa in fixed_aabbs
                          if fa[4] == layer)
                if hit:
                    cx += w + GAP
                    continue
                # land courtyard top-left at (cx, cy_shelf): anchor offset
                cyb = m.get("courtyard_bbox")
                anc = m["anchor"]
                off_x = (anc["x"] - cyb[0]) if cyb else w / 2
                off_y = (anc["y"] - cyb[1]) if cyb else h / 2
                moves[ref] = (cx + off_x, cy_shelf + off_y, None)
                cx += w + GAP
                shelf_h = max(shelf_h, h)
                placed = True
            if not placed:
                moves[ref] = ((zx0 + zx1) / 2, (zy0 + zy1) / 2, None)

    # clamp every non-fixed part so its courtyard stays inside the board AABB
    bx = plan["board"]
    CM = 0.6
    for ref in list(moves):
        if ref in plan["fixed"]:
            continue
        m = meta[ref]
        cyb = m.get("courtyard_bbox")
        if not cyb:
            continue
        ax, ay, rot = moves[ref]
        off_x = m["anchor"]["x"] - cyb[0]
        off_y = m["anchor"]["y"] - cyb[1]
        w, h = cyb[2] - cyb[0], cyb[3] - cyb[1]
        cx0 = min(max(ax - off_x, bx["x0"] + CM), bx["x1"] - CM - w)
        cy0 = min(max(ay - off_y, bx["y0"] + CM), bx["y1"] - CM - h)
        moves[ref] = (cx0 + off_x, cy0 + off_y, rot)

    print(f"placing {len(moves)} parts "
          f"({sum(1 for r in plan['fixed'] if r in moves)} fixed, "
          f"{len(moves) - sum(1 for r in plan['fixed'] if r in moves)} zoned)")
    if args.dry_run:
        for r in list(moves)[:6]:
            print(f"  {r}: {tuple(round(v,1) if isinstance(v,float) else v for v in moves[r])}")
        print("  ... dry run")
        return 0

    # target layer per ref: fixed parts carry an explicit layer; zoned parts are front
    target_layer = {r: fx.get("layer", "F.Cu") for r, fx in plan["fixed"].items()}

    # 3) one-pass rewrite (move + flip side if the target layer differs)
    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    i = 1
    n = 0
    flips = 0
    while i < len(chunks):
        delim = chunks[i]
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        mref = re.search(r'\(property "Reference" "([^"]+)"', body)
        ref = mref.group(1) if mref else None
        if ref in moves:
            tl = target_layer.get(ref, "F.Cu")
            if ref in meta and meta[ref]["layer"] != tl:
                body = swap_layers(body)
                flips += 1
            x, y, rot = moves[ref]
            body = set_anchor(body, x, y, rot)
            n += 1
        out.append(delim)
        out.append(body)
        i += 2
    pcb.write_text("".join(out))
    print(f"placed {n} footprints onto the board from {args.plan} ({flips} flipped to back)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
