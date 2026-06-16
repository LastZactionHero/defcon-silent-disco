#!/usr/bin/env python3
"""orient_check.py — automated 3D/orientation/assembly gate (Resolution 3).

The 2D-geometry + connectivity metrics passed clean while the board was, in 3D,
wrong: the microSD slot faced inward, SW1 hung off the edge, connectors faced the
wrong way, buttons sat under the USB-C. Every one of those lived in the gap
between "the courtyards don't overlap" and "a human looked at the render." This
tool closes that gap with checks computed from AUTHORITATIVE pcbnew geometry, so
"render and LOOK" becomes an enforced, repeatable phase-exit gate instead of
advice the loop could skip.

Checks (all from geom — no eyeballing required):
  1. EDGE-FACING    each edge connector's courtyard reaches its assigned edge and
                    keeps the plan-validated rotation/layer (catches a slot or
                    receptacle that got rotated to face inward — J31/J10/J20).
  2. ON-BOARD       no non-edge part's courtyard pokes outside Edge.Cuts; edge
                    parts may poke only on their own edge (catches SW1 hanging off).
  3. NO-SHADOW      no part's centroid sits inside an edge connector's courtyard
                    footprint (catches buttons-under-USB-C).
  4. AXIS-ALIGNED   every footprint is at a 90° multiple (catches skewed parts and
                    keeps silk/assembly legible).
  5. SYMMETRY       declared mirror pairs (IR U30/D20) stay at equal y and mirrored
                    x about the board centre.

`check(meta, outline, plan)` -> (ok: bool, detail: list[{check, ref, ok, msg}]).
Run standalone to print a human-readable pass/fail table; exit 0 if the gate
passes, 4 if any check fails.

Usage:
  orient_check.py defcon_badge/defcon_badge.kicad_pcb \
      --plan placement_phase_2/floorplan.json [-v]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom                                         # noqa: E402  authoritative geometry

# Plan-validated facing for the edge connectors (kept in sync with floorplan
# `fixed`). Each is the rotation a render confirmed seats the opening/slot at the
# board edge; SA or a fixer drifting off it is the "wrong-facing" bug.
DEFAULT_EDGE_PARTS = {
    "J10": {"edge": "bottom", "rot": 0,   "layer": "F.Cu"},   # USB-C mouth at bottom
    "J20": {"edge": "top",    "rot": 180, "layer": "F.Cu"},   # audio jack exits top
    "J31": {"edge": "bottom", "rot": 0,   "layer": "F.Cu"},   # microSD on FRONT (single-sided assy, user-directed 2026-06-16); flip:false+rot0 keeps slot mouth at bottom edge
    "U30": {"edge": "left",   "rot": 0,   "layer": "F.Cu"},   # IR-RX left
    "D20": {"edge": "right",  "rot": 180, "layer": "F.Cu"},   # IR-LED right (mirror)
    "SW1": {"edge": "bottom", "rot": 0,   "layer": "F.Cu"},   # power slide at bottom
}
# Declared mirror pairs that must stay symmetric (Resolution 2 structure intent).
DEFAULT_MIRROR_PAIRS = [("U30", "D20")]

EDGE_TOL = 3.0       # how close the courtyard edge must reach the board edge (mm)
ROT_TOL = 5.0        # rotation drift tolerance (deg)
POKE_TOL = 0.3       # how far a non-edge courtyard may sit outside Edge.Cuts (mm)


def _norm_rot(r):
    return round(float(r) % 360, 1)


def _rot_ok(actual, want):
    d = abs(_norm_rot(actual) - _norm_rot(want)) % 360
    d = min(d, 360 - d)
    return d <= ROT_TOL


def _edge_parts_from_plan(plan):
    """The facing-critical set is CURATED (DEFAULT_EDGE_PARTS): parts with an
    external mating opening/emitter that must reach a specific edge. We do NOT
    auto-promote every plan `fixed` entry with an `edge` hint — a LiPo JST or a
    header sits in an edge *zone* without its body needing to touch the rim, and
    flagging those is a false positive. The plan may refresh rot/edge/layer for a
    curated ref, or opt a new ref in explicitly via plan['edge_facing']."""
    out = {k: dict(v) for k, v in DEFAULT_EDGE_PARTS.items()}
    if not plan:
        return out
    fixed = plan.get("fixed", {})
    for ref in list(out):                          # refresh curated refs from the plan
        f = fixed.get(ref)
        if not f:
            continue
        edge = f.get("edge", "")
        primary = next((e for e in ("top", "bottom", "left", "right") if e in edge), None)
        if primary:
            out[ref]["edge"] = primary
        if "rot" in f:
            out[ref]["rot"] = f["rot"]
        if "layer" in f:
            out[ref]["layer"] = f["layer"]
    for ref, spec in plan.get("edge_facing", {}).items():   # explicit opt-in
        out[ref] = dict(spec)
    return out


def check(meta, outline, plan=None):
    x0, y0, x1, y1 = outline
    xm = (x0 + x1) / 2
    detail = []

    def add(check_name, ref, ok, msg):
        detail.append({"check": check_name, "ref": ref, "ok": bool(ok), "msg": msg})

    edge_parts = _edge_parts_from_plan(plan)
    mirror_pairs = (plan or {}).get("mirror_pairs", DEFAULT_MIRROR_PAIRS)
    fixed = set((plan or {}).get("fixed", {}).keys()) or set(edge_parts)

    def cy(ref):
        m = meta.get(ref)
        return m.get("courtyard_bbox") if m else None

    # 1. EDGE-FACING ---------------------------------------------------------
    edge_reach = {
        "top":    lambda c: abs(c[1] - y0) < EDGE_TOL,
        "bottom": lambda c: abs(c[3] - y1) < EDGE_TOL,
        "left":   lambda c: abs(c[0] - x0) < EDGE_TOL,
        "right":  lambda c: abs(c[2] - x1) < EDGE_TOL,
    }
    for ref, spec in edge_parts.items():
        m = meta.get(ref)
        c = cy(ref)
        if not m or not c:
            add("edge_facing", ref, False, "missing footprint/courtyard")
            continue
        reaches = edge_reach[spec["edge"]](c)
        rot_ok = _rot_ok(m["anchor"]["rot"], spec["rot"])
        layer_ok = m["layer"] == spec["layer"]
        ok = reaches and rot_ok and layer_ok
        why = []
        if not reaches:  why.append(f"courtyard not at {spec['edge']} edge")
        if not rot_ok:   why.append(f"rot {_norm_rot(m['anchor']['rot'])}≠{spec['rot']} (facing drifted)")
        if not layer_ok: why.append(f"layer {m['layer']}≠{spec['layer']}")
        add("edge_facing", ref, ok, "ok" if ok else "; ".join(why))

    # 2. ON-BOARD (no courtyard poking off the wrong edge) -------------------
    for ref, m in meta.items():
        c = m.get("courtyard_bbox")
        if not c:
            continue
        is_edge = ref in fixed or ref in edge_parts
        poke = {
            "left":   x0 - c[0], "right":  c[2] - x1,
            "top":    y0 - c[1], "bottom": c[3] - y1,
        }
        worst = max(poke.values())
        if worst <= POKE_TOL:
            continue
        if is_edge:
            # an edge part may poke only on the edge(s) it is assigned to
            allowed = edge_parts.get(ref, {}).get("edge", "")
            bad = [s for s, v in poke.items() if v > POKE_TOL and s != allowed]
            if not bad:
                continue
            add("on_board", ref, False,
                f"edge part pokes off {','.join(bad)} (not its {allowed or '—'} edge) by {worst:.1f}mm")
        else:
            sides = ",".join(s for s, v in poke.items() if v > POKE_TOL)
            add("on_board", ref, False, f"courtyard hangs off {sides} edge by {worst:.1f}mm")

    # 3. NO-SHADOW (nothing tucked under an edge connector) ------------------
    for ref, spec in edge_parts.items():
        c = cy(ref)
        if not c:
            continue
        m_conn = meta.get(ref)
        for o, mo in meta.items():
            if o == ref or o in edge_parts or o in fixed:
                continue
            if mo["layer"] != m_conn["layer"]:
                continue                          # opposite side is fine (e.g. caps under B.Cu)
            oc = mo.get("courtyard_bbox")
            if not oc:
                continue
            ocx, ocy = (oc[0] + oc[2]) / 2, (oc[1] + oc[3]) / 2
            if c[0] <= ocx <= c[2] and c[1] <= ocy <= c[3]:
                add("no_shadow", o, False, f"sits under edge connector {ref}")

    # 4. AXIS-ALIGNED --------------------------------------------------------
    for ref, m in meta.items():
        r = _norm_rot(m["anchor"]["rot"])
        if min(r % 90, 90 - (r % 90)) > ROT_TOL:
            add("axis_aligned", ref, False, f"rot {r}° is not a 90° multiple")

    # 5. SYMMETRY ------------------------------------------------------------
    # Measured at the placement ANCHOR, not the courtyard centre: a mirror pair
    # is usually two DIFFERENT footprints (IR-RX vs IR-LED) whose courtyards never
    # mirror even when correctly placed — the anchors are what the design pins.
    for a, b in mirror_pairs:
        ma, mb = meta.get(a), meta.get(b)
        if not (ma and mb):
            add("symmetry", f"{a}/{b}", False, "missing part")
            continue
        ay, by = ma["anchor"]["y"], mb["anchor"]["y"]
        ax, bx = ma["anchor"]["x"], mb["anchor"]["x"]
        dy = abs(ay - by)
        dmir = abs((ax - x0) - (x1 - bx))         # mirror distance about centre
        ok = dy < 1.0 and dmir < 2.0
        add("symmetry", f"{a}/{b}", ok,
            "ok" if ok else f"Δy={dy:.1f}mm, mirror-offset={dmir:.1f}mm about x={xm:.1f}")

    # gate passes only if every recorded check passed (checks that pass for
    # every part emit no failing row; the all() therefore reduces to the fails)
    ok = all(d["ok"] for d in detail)
    fails = [d for d in detail if not d["ok"]]
    return ok, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--plan", default="placement_phase_2/floorplan.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    meta = geom.load_pcb(pcb)
    outline = geom.board_outline(pcb)
    plan = None
    if Path(args.plan).exists():
        plan = json.loads(Path(args.plan).read_text())

    ok, fails = check(meta, outline, plan)
    if ok:
        print("orientation gate: PASS — edge-facing, on-board, no-shadow, "
              "axis-aligned, symmetry all clean")
        return 0
    print(f"orientation gate: FAIL ({len(fails)} issue(s))")
    for d in fails:
        print(f"  [{d['check']:13}] {d['ref']:10} {d['msg']}")
    return 4


if __name__ == "__main__":
    sys.exit(main())
