#!/usr/bin/env python3
"""anneal.py — simulated-annealing global placement refinement (Phase C).

Warm-starts from the current placement and refines movable parts to minimise a
single cost = ratsnest + overlap + offboard + edge-intrusion (+ optional
decoupling), with fixed/edge parts frozen and each part constrained to its
floorplan zone. Metropolis acceptance, geometric cooling. Incremental cost
updates make each move cheap.

Accept the result only if it improves; the caller verifies gates with measure.py
and reverts (git) if any passing gate regressed.

Usage:
  anneal.py defcon_badge/defcon_badge.kicad_pcb --plan placement_phase_2/floorplan.json \
      --iters 40000 --seed 1 [--w-dec 0] [--zone-slack 1.0]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom                             # noqa: E402  (authoritative pcbnew geometry + apply)
from geom import load_pcb               # noqa: E402
from validate_placement import parse_edge_cuts, point_in_polygon  # noqa: E402

GROUND = {"GND", "/GND", "AGND", "PGND", "DGND"}

# Fallback if the plan predates Resolution-2 structure declarations. The live
# source of truth is plan["structured"] (aligned rows) + plan["mirror_pairs"].
STRUCTURED_FALLBACK = {"LED20", "LED21", "LED22", "LED23", "SW20", "SW21", "SW22"}


def structured_members(plan):
    """All refs in declared aligned-row groups + both halves of every mirror pair
    (Resolution 2). These are FROZEN during SA so the ratsnest objective — which
    has no concept of 'aligned row' or 'symmetric pair' — cannot trade the board's
    structure away for a millimetre of wirelength."""
    refs = set()
    for g in (plan.get("structured") or {}).values():
        refs.update(g.get("members", []))
    for a, b in (plan.get("mirror_pairs") or []):
        refs.update((a, b))
    return refs or set(STRUCTURED_FALLBACK)


def rot(dx, dy, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return dx * c - dy * s, dx * s + dy * c


def mst(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    intree = [False] * n
    d = [math.inf] * n
    d[0] = 0.0
    tot = 0.0
    for _ in range(n):
        best, bd = -1, math.inf
        for i in range(n):
            if not intree[i] and d[i] < bd:
                bd, best = d[i], i
        if best < 0:
            break
        intree[best] = True
        tot += bd
        bx, by = pts[best]
        for j in range(n):
            if not intree[j]:
                dd = math.hypot(pts[j][0] - bx, pts[j][1] - by)
                if dd < d[j]:
                    d[j] = dd
    return tot


class Board:
    def __init__(self, pcb, plan):
        self.pcb_parent = pcb.parent
        self.meta = load_pcb(pcb)
        text = pcb.read_text()
        self.poly = parse_edge_cuts(text)
        xs = [p[0] for p in self.poly]; ys = [p[1] for p in self.poly]
        self.bx = (min(xs), min(ys), max(xs), max(ys))
        self.fixed = set(plan["fixed"])
        self.zones = plan["zones"]
        self.assign = plan["assign"]
        # Structured groups (aligned rows + mirror pairs) are placed by place.py and
        # FROZEN here so SA can't scramble them (ratsnest has no notion of alignment
        # or symmetry). Declared in the plan (Resolution 2), not hardcoded. Only free
        # passives get optimized — which is where SA actually helps.
        self.structured = structured_members(plan)
        self.frozen = self.fixed | self.structured

        self.refs = list(self.meta)
        self.idx = {r: i for i, r in enumerate(self.refs)}
        self.movable = [r for r in self.refs if r not in self.frozen]
        self.edge_exempt = self.fixed  # only fixed connectors may poke past edge

        # per-part state — local coords come straight from authoritative geom
        self.x = {}; self.y = {}; self.rot = {}; self.layer = {}
        self.local_pads = {}        # ref -> [(lx,ly,net)]
        self.local_cy = {}          # ref -> [(lx,ly)*4] courtyard corners (local)
        for r, m in self.meta.items():
            a = m["anchor"]
            self.x[r], self.y[r], self.rot[r] = a["x"], a["y"], a["rot"]
            self.layer[r] = m["layer"]
            self.local_pads[r] = [(p["lx"], p["ly"], p.get("net")) for p in m["pads"]]
            cl = m.get("courtyard_local")
            if cl:
                self.local_cy[r] = [(cl[0], cl[1]), (cl[2], cl[1]),
                                    (cl[2], cl[3]), (cl[0], cl[3])]
            else:
                self.local_cy[r] = [(-2, -2), (2, -2), (2, 2), (-2, 2)]

        # net -> [(ref, padlocal_idx)]
        self.net_members = {}
        for r in self.refs:
            for k, (_, _, net) in enumerate(self.local_pads[r]):
                if not net or net in GROUND or net.endswith("/GND"):
                    continue
                self.net_members.setdefault(net, []).append((r, k))
        self.part_nets = {}
        for net, mem in self.net_members.items():
            for r, _ in mem:
                self.part_nets.setdefault(r, set()).add(net)

        # decoupling pairs: (cap, cap_padk, owner, owner_padk)
        self.deco = []
        self._build_deco()
        self.part_deco = {}
        for di, (cap, _, owner, _) in enumerate(self.deco):
            self.part_deco.setdefault(cap, set()).add(di)
            self.part_deco.setdefault(owner, set()).add(di)

    def _build_deco(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import floorplan as fp
        import decouple as dc
        sheets = fp.sheet_membership(self.pcb_parent)
        groups = dc.owners_for_caps(self.meta, 1.1, sheets, exclude=self.fixed)
        for owner, caps in groups.items():
            # DISTINCT-pin assignment: each cap gets its OWN owner power pin on the
            # matching net (greedy nearest, one cap per pin) so caps don't all crowd
            # the same corner and collide — mirrors auto_decouple's pin matching.
            used = set()
            # most-constrained net first; deterministic by refdes
            for cap in sorted(caps, key=lambda r: int(re.search(r"\d+", r).group())):
                capk = capnet = None
                for k, (_, _, net) in enumerate(self.local_pads[cap]):
                    if net and net not in GROUND and dc.POWER_RE.search(net):
                        capk, capnet = k, net
                        break
                if capk is None:
                    continue
                cwx, cwy = self.pad_world(cap, capk)
                best, bd = None, 1e9
                for k, (_, _, net) in enumerate(self.local_pads[owner]):
                    if net == capnet and (owner, k) not in used:
                        owx, owy = self.pad_world(owner, k)
                        d = math.hypot(owx - cwx, owy - cwy)
                        if d < bd:
                            bd, best = d, k
                if best is None:   # ran out of distinct pins: share nearest
                    for k, (_, _, net) in enumerate(self.local_pads[owner]):
                        if net == capnet:
                            owx, owy = self.pad_world(owner, k)
                            d = math.hypot(owx - cwx, owy - cwy)
                            if d < bd:
                                bd, best = d, k
                if best is not None:
                    used.add((owner, best))
                    self.deco.append((cap, capk, owner, best))

    deco_target = 1.2     # SA pulls caps to <=this mm of the pin (tighter than the
                          # 3.4mm gate — conventional front-side decoupling; see R4)

    def deco_excess(self, di):
        cap, capk, owner, ok = self.deco[di]
        cwx, cwy = self.pad_world(cap, capk)
        owx, owy = self.pad_world(owner, ok)
        return max(0.0, math.hypot(owx - cwx, owy - cwy) - self.deco_target)

    # ---- geometry ----
    def pad_world(self, r, k):
        ldx, ldy, _ = self.local_pads[r][k]
        wx, wy = rot(ldx, ldy, self.rot[r])
        return self.x[r] + wx, self.y[r] + wy

    def cy_aabb(self, r):
        pts = [rot(lx, ly, self.rot[r]) for lx, ly in self.local_cy[r]]
        xs = [self.x[r] + p[0] for p in pts]; ys = [self.y[r] + p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- cost terms ----
    def net_len(self, net):
        return mst([self.pad_world(r, k) for r, k in self.net_members[net]])

    CLEAR = 0.06      # min courtyard clearance — just enough to clear DRC touch, not over-constrain

    def overlap_pair(self, a, b):
        if self.layer[a] != self.layer[b]:
            return 0.0
        c = self.CLEAR / 2
        ax0, ay0, ax1, ay1 = self.cy_aabb(a)
        bx0, by0, bx1, by1 = self.cy_aabb(b)
        ix = min(ax1 + c, bx1 + c) - max(ax0 - c, bx0 - c)
        iy = min(ay1 + c, by1 + c) - max(ay0 - c, by0 - c)
        return ix * iy if ix > 0 and iy > 0 else 0.0

    def part_overlap(self, r):
        return sum(self.overlap_pair(r, o) for o in self.refs if o != r)

    def part_off_edge(self, r):
        x0, y0, x1, y1 = self.cy_aabb(r)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        off = 0.0 if point_in_polygon(cx, cy, self.poly) else 1.0
        intr = 0.0
        if r not in self.edge_exempt:
            bx0, by0, bx1, by1 = self.bx
            intr = (max(0, bx0 - x0) + max(0, x1 - bx1)
                    + max(0, by0 - y0) + max(0, y1 - by1))
        return off, intr


# weights: hard constraints dominate ratsnest
W = {"rat": 1.0, "ov": 60.0, "off": 200.0, "edge": 40.0, "dec": 0.0}


def anneal(b: Board, iters: int, seed: int, t0: float, t1: float, slack: float):
    rng = random.Random(seed)
    net_cache = {n: b.net_len(n) for n in b.net_members}
    tot_rat = sum(net_cache.values())
    tot_ov = sum(b.part_overlap(r) for r in b.refs) / 2.0
    offedge = {r: b.part_off_edge(r) for r in b.movable}
    tot_off = sum(v[0] for v in offedge.values())
    tot_edge = sum(v[1] for v in offedge.values())
    deco_cache = {di: b.deco_excess(di) for di in range(len(b.deco))}
    tot_dec = sum(deco_cache.values())

    def cost():
        return (W["rat"] * tot_rat + W["ov"] * tot_ov + W["off"] * tot_off
                + W["edge"] * tot_edge + W["dec"] * tot_dec)

    zone_bbox = {}
    for r in b.movable:
        z = b.zones.get(b.assign.get(r))
        zone_bbox[r] = z["bbox"] if z else list(b.bx)

    best_cost = cost()
    accepts = 0
    for it in range(iters):
        frac = it / iters
        T = t0 * (t1 / t0) ** frac
        sigma = 3.0 * (1 - frac) + 0.3
        r = rng.choice(b.movable)

        ox, oy, orot = b.x[r], b.y[r], b.rot[r]
        # snapshot affected metrics
        a_nets = b.part_nets.get(r, set())
        old_net = {n: net_cache[n] for n in a_nets}
        old_po = b.part_overlap(r)
        old_off, old_edge = offedge[r]
        a_deco = b.part_deco.get(r, ())
        old_deco = {di: deco_cache[di] for di in a_deco}

        # Rotation is allowed for any part (pcbnew rotates pads correctly now).
        if rng.random() < 0.15:
            b.rot[r] = (orot + 90) % 360
        else:
            zx0, zy0, zx1, zy1 = zone_bbox[r]
            nx = ox + rng.gauss(0, sigma)
            ny = oy + rng.gauss(0, sigma)
            b.x[r] = min(max(nx, zx0 - slack), zx1 + slack)
            b.y[r] = min(max(ny, zy0 - slack), zy1 + slack)

        # recompute affected
        d_rat = 0.0
        for n in a_nets:
            nl = b.net_len(n)
            d_rat += nl - old_net[n]
        new_po = b.part_overlap(r)
        d_ov = new_po - old_po
        noff, nedge = b.part_off_edge(r)
        d_off = noff - old_off
        d_edge = nedge - old_edge
        d_dec = 0.0
        new_deco = {}
        for di in a_deco:
            new_deco[di] = b.deco_excess(di)
            d_dec += new_deco[di] - old_deco[di]
        dE = (W["rat"] * d_rat + W["ov"] * d_ov + W["off"] * d_off
              + W["edge"] * d_edge + W["dec"] * d_dec)

        if dE <= 0 or rng.random() < math.exp(-dE / max(T, 1e-6)):
            for n in a_nets:
                net_cache[n] = b.net_len(n)
            tot_rat += d_rat; tot_ov += d_ov; tot_off += d_off; tot_edge += d_edge
            tot_dec += d_dec
            for di, v in new_deco.items():
                deco_cache[di] = v
            offedge[r] = (noff, nedge)
            accepts += 1
        else:
            b.x[r], b.y[r], b.rot[r] = ox, oy, orot

    return cost(), tot_rat, tot_ov, tot_off, tot_edge, tot_dec, accepts


def snap_decouple(b: Board):
    """Deterministic finisher: set each decoupling cap so its power pad sits just
    outboard of its assigned distinct owner pin, searching a small radius/angle
    set for a spot that is overlap-free and <=2.0mm pad-to-pad. Guarantees the
    decoupling gate where geometrically feasible without disturbing anything else."""
    # Coordinate-descent over several passes: re-place each cap aware of the others'
    # latest positions, so caps settle into distinct, overlap-free, <=2.0mm spots.
    order = list(range(len(b.deco)))
    for _pass in range(6):
        for di in order:
            cap, capk, owner, ok = b.deco[di]
            ox0, oy0, ox1, oy1 = b.cy_aabb(owner)
            ocx, ocy = (ox0 + ox1) / 2, (oy0 + oy1) / 2
            pinx, piny = b.pad_world(owner, ok)
            dx, dy = pinx - ocx, piny - ocy
            n = math.hypot(dx, dy) or 1.0
            ux, uy = dx / n, dy / n
            ldx, ldy, _ = b.local_pads[cap][capk]
            best = None
            for r in (0.9, 1.1, 1.3, 1.5, 1.7, 1.9):
                for ang in (0, 20, -20, 40, -40, 65, -65, 90, -90, 120, -120, 155, -155, 180):
                    a = math.radians(ang)
                    vx = ux * math.cos(a) - uy * math.sin(a)
                    vy = ux * math.sin(a) + uy * math.cos(a)
                    tx, ty = pinx + vx * r, piny + vy * r
                    rdx, rdy = rot(ldx, ldy, b.rot[cap])
                    b.x[cap], b.y[cap] = tx - rdx, ty - rdy
                    wx, wy = b.pad_world(cap, capk)
                    dist = math.hypot(wx - pinx, wy - piny)
                    ov = b.part_overlap(cap)
                    cx0, cy0, cx1, cy1 = b.cy_aabb(cap)
                    inside = point_in_polygon((cx0 + cx1) / 2, (cy0 + cy1) / 2, b.poly)
                    score = (round(ov, 3), 0 if inside else 1, round(dist, 3))
                    if best is None or score < best[0]:
                        best = (score, b.x[cap], b.y[cap])
            b.x[cap], b.y[cap] = best[1], best[2]
    return len(b.deco)


def write_back(pcb: Path, b: Board):
    # apply via pcbnew (rotates pads correctly); only movable parts moved
    moves = {r: {"x": b.x[r], "y": b.y[r], "rot": b.rot[r]} for r in b.movable}
    geom.apply(pcb, moves)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--plan", default="placement_phase_2/floorplan.json")
    ap.add_argument("--iters", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--t0", type=float, default=4.0)
    ap.add_argument("--t1", type=float, default=0.02)
    ap.add_argument("--zone-slack", type=float, default=1.0)
    ap.add_argument("--w-dec", type=float, default=0.0,
                    help="decoupling-proximity weight (0 disables the term)")
    ap.add_argument("--w-ov", type=float, default=W["ov"], help="overlap weight")
    ap.add_argument("--deco-target", type=float, default=Board.deco_target,
                    help="pull caps to <=this mm of the pin")
    ap.add_argument("--snap", action="store_true",
                    help="after SA, deterministically snap decoupling caps to their pins")
    ap.add_argument("--dry-run", action="store_true", help="optimize but don't write")
    args = ap.parse_args()

    W["dec"] = args.w_dec
    W["ov"] = args.w_ov
    Board.deco_target = args.deco_target
    pcb = Path(args.pcb)
    plan = json.loads(Path(args.plan).read_text())
    b = Board(pcb, plan)

    rat0 = sum(b.net_len(n) for n in b.net_members)
    fc, rat, ov, off, edge, dec, acc = anneal(b, args.iters, args.seed, args.t0, args.t1, args.zone_slack)
    print(f"SA seed={args.seed} iters={args.iters} w_dec={args.w_dec} accepts={acc}")
    print(f"  ratsnest {rat0:.1f} -> {rat:.1f} mm | overlap_area {ov:.2f} | offboard {off:.0f} | "
          f"edge {edge:.2f} | deco_excess {dec:.2f}")
    if args.snap:
        m = snap_decouple(b)
        print(f"  snapped {m} decoupling caps to their pins")
    if not args.dry_run:
        write_back(pcb, b)
        print(f"  wrote {pcb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

