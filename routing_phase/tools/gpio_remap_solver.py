#!/usr/bin/env python3
"""gpio_remap_solver.py — R2 pinmux-legal remap solver (the move-1 lever).

Reads the assignment dataset emitted by the extractor (pure numbers: U3 GPIO pads with
side/pos, movable nets with destination centroids), and finds the pad-net permutation that
minimises total escape-routing cost (distance from each net's assigned pad to its destination),
subject to RP2040 pinmux constraints:
  - VBAT_SENSE (ADC0) may only land on ADC-capable pads (GPIO26-29).
  - The I2S triple (DIN/BCK/LRCK, PIO side-set) must occupy 3 CONTIGUOUS GPIO numbers.
  - Fixed nets (USB/QSPI/XIN/XOUT/SWD/SWCLK/RUN/UART) are out of the problem entirely.
  - A churn penalty keeps a net on its current pad unless moving it clearly helps (fewer
    schematic edits = lower apply risk).

Solve = Hungarian (scipy linear_sum_assignment) over (nets x pads), with the I2S contiguity
handled by enumerating contiguous-3 GPIO windows and keeping the best.

Reports the side-mismatch count BEFORE vs AFTER (same metric as gpio_reassigner) and writes
gpio_remap.json: the per-net {net, cur_pad, new_pad, cur_gpio, new_gpio} permutation + the
pad-net swap list for the schematic apply. Run under the KRT venv (has scipy/numpy).

Usage: gpio_remap_solver.py /tmp/remap_data.json [--churn 0.6] [--out routing_phase/gpio_remap.json]
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment

BIG = 1e6

def side_of(px, py, cx, cy):
    dx, dy = px - cx, py - cy
    return ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("bottom" if dy > 0 else "top")

def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)

def solve(data, churn):
    cx, cy = data["center"]["x"], data["center"]["y"]
    pads = data["pads"]                       # 30 GPIO-capable pads
    nets = data["nets"]                       # 22 movable nets
    pad_by_idx = {i: p for i, p in enumerate(pads)}
    gpio_to_padidx = {p["gpio"]: i for i, p in enumerate(pads)}
    n_nets, n_pads = len(nets), len(pads)

    OPP = {"right": "left", "left": "right", "top": "bottom", "bottom": "top"}
    OPP_PEN = data.get("_opp_pen", 12.0)   # mm-equiv: removing an opposite-side crossing dominates

    def base_cost(net, pad):
        """cost = dist(pad,dest) + opposite-side penalty + churn-if-moving, with legality gates.
        The opposite-side term is what actually targets escape congestion: a net whose pad sits on
        the side OPPOSITE its destination must route around the QFN keep-out (the pass-1 failure mode).
        Distance alone shuffled same-side pads for ~0 gain; this only moves nets that kill a crossing."""
        if net["is_adc_net"] and not pad["adc"]:
            return BIG                         # VBAT_SENSE only on ADC pads
        pad_side = side_of(pad["x"], pad["y"], cx, cy)
        c = dist(pad["x"], pad["y"], net["dest_x"], net["dest_y"])
        if pad_side == OPP.get(net["dest_side"]):
            c += OPP_PEN
        if pad["pad"] != net["cur_pad"]:
            c += churn                          # mm-equivalent penalty for moving
        return c

    # ---- I2S contiguity: enumerate contiguous-3 GPIO windows, keep the best total ----
    i2s = [i for i, n in enumerate(nets) if n["is_i2s"]]
    best = None
    if len(i2s) == 3:
        gpios = sorted(p["gpio"] for p in pads)
        windows = [(g, g + 1, g + 2) for g in range(0, 30)
                   if all((g + k) in gpio_to_padidx for k in range(3))]
        for win in windows:
            win_padidx = [gpio_to_padidx[g] for g in win]
            # cost of placing the 3 I2S nets onto these 3 pads (best internal perm via tiny Hungarian)
            sub = np.array([[base_cost(nets[i], pad_by_idx[pj]) for pj in win_padidx] for i in i2s])
            if sub.min() >= BIG:
                continue
            r, cidx = linear_sum_assignment(sub)
            i2s_cost = sub[r, cidx].sum()
            i2s_assign = {i2s[r[k]]: win_padidx[cidx[k]] for k in range(3)}
            # Hungarian for the REST over the remaining pads
            rest = [i for i in range(n_nets) if i not in i2s]
            rest_pads = [pj for pj in range(n_pads) if pj not in win_padidx]
            M = np.array([[base_cost(nets[i], pad_by_idx[pj]) for pj in rest_pads] for i in rest])
            rr, rc = linear_sum_assignment(M)
            rest_cost = M[rr, rc].sum()
            total = i2s_cost + rest_cost
            if best is None or total < best[0]:
                assign = dict(i2s_assign)
                for k in range(len(rr)):
                    assign[rest[rr[k]]] = rest_pads[rc[k]]
                best = (total, win, assign)
    if best is None:  # no I2S or no legal window — plain Hungarian
        M = np.array([[base_cost(n, p) for p in pads] for n in nets])
        rr, rc = linear_sum_assignment(M)
        best = (M[rr, rc].sum(), None, {rr[k]: rc[k] for k in range(len(rr))})

    _, i2s_win, assign = best
    # build result
    res = []
    mism_before = mism_after = 0
    for i, net in enumerate(nets):
        pj = assign[i]
        pad = pad_by_idx[pj]
        cur_side = side_of(*[v for v in (
            next(p for p in pads if p["pad"] == net["cur_pad"])["x"],
            next(p for p in pads if p["pad"] == net["cur_pad"])["y"])], cx, cy)
        new_side = side_of(pad["x"], pad["y"], cx, cy)
        if cur_side != net["dest_side"]:
            mism_before += 1
        if new_side != net["dest_side"]:
            mism_after += 1
        res.append({"net": net["net"], "cur_pad": net["cur_pad"], "cur_gpio": net["cur_gpio"],
                    "new_pad": pad["pad"], "new_gpio": pad["gpio"],
                    "cur_side": cur_side, "new_side": new_side, "dest_side": net["dest_side"],
                    "moved": pad["pad"] != net["cur_pad"]})
    return res, mism_before, mism_after, i2s_win

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--churn", type=float, default=0.6)
    ap.add_argument("--opp", type=float, default=12.0)
    ap.add_argument("--out", default="routing_phase/gpio_remap.json")
    args = ap.parse_args()
    data = json.load(open(args.data))
    data["_opp_pen"] = args.opp
    res, mb, ma, i2s_win = solve(data, args.churn)

    # verify it's a valid permutation of pads among the assigned nets (no pad used twice)
    new_pads = [r["new_pad"] for r in res]
    assert len(new_pads) == len(set(new_pads)), "INVALID: a pad assigned twice"

    moved = [r for r in res if r["moved"]]
    print(f"side-mismatch (escape-crossing) BEFORE={mb}  AFTER={ma}   nets moved={len(moved)}")
    print(f"I2S contiguous window (GPIO) = {i2s_win}")
    print("moves:")
    for r in sorted(moved, key=lambda r: r["cur_gpio"]):
        flag = "" if r["new_side"] == r["dest_side"] else "  (still off-side: no GPIO faces dest)"
        print(f"  {r['net']:28} GP{r['cur_gpio']}(pad{r['cur_pad']}) {r['cur_side']:6} "
              f"-> GP{r['new_gpio']}(pad{r['new_pad']}) {r['new_side']:6}  dest={r['dest_side']:6}{flag}")
    # swap list: pairs of pads whose nets exchange (for the schematic/PCB apply)
    out = {"mismatch_before": mb, "mismatch_after": ma, "i2s_window": i2s_win,
           "assignments": res,
           "pad_net_after": {str(r["new_pad"]): r["net"] for r in res}}
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")

if __name__ == "__main__":
    main()
