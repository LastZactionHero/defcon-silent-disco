#!/usr/bin/env python3
"""sch_pin_resolver.py — resolve each symbol pin -> net via schematic connectivity.

The safe foundation for the R2 GPIO remap apply: to move a net from one RP2040 pin to another by
swapping LOCAL LABELS (the only semantically-correct remap on a function-named symbol), we must know
which label sits on which pin. This parses a .kicad_sch, computes each pin's sheet coordinate from the
lib_symbol geometry + instance transform, and unions wires/labels/pins into nets (a tiny connectivity
engine). It then CROSS-CHECKS every pin's resolved net against the authoritative PCB pad->net map —
if they don't all agree, the geometry is wrong and the caller MUST abort rather than edit blind.

Usage: sch_pin_resolver.py <sheet.kicad_sch> <ref> <pcb_padnets.json>   (prints match report + JSON)
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

# ---------- minimal s-expression parser ----------
def parse_sexp(s):
    i = 0
    def skip_ws():
        nonlocal i
        while i < len(s) and s[i] in " \t\r\n":
            i += 1
    def parse():
        nonlocal i
        skip_ws()
        if s[i] == '(':
            i += 1
            lst = []
            while True:
                skip_ws()
                if s[i] == ')':
                    i += 1
                    return lst
                lst.append(parse())
        elif s[i] == '"':
            i += 1
            buf = []
            while s[i] != '"':
                if s[i] == '\\':
                    i += 1
                buf.append(s[i]); i += 1
            i += 1
            return ('str', ''.join(buf))
        else:
            buf = []
            while i < len(s) and s[i] not in ' \t\r\n()':
                buf.append(s[i]); i += 1
            return ('sym', ''.join(buf))
    skip_ws()
    return parse()

def atom(x):                       # unwrap ('str'|'sym', v)
    return x[1] if isinstance(x, tuple) else x
def is_list(x):
    return isinstance(x, list)
def head(x):
    return atom(x[0]) if is_list(x) and x else None
def find_all(node, name):
    out = []
    if is_list(node):
        if head(node) == name:
            out.append(node)
        for c in node:
            out.extend(find_all(c, name))
    return out
def get(node, name):               # first direct child list with head==name
    for c in node:
        if is_list(c) and head(c) == name:
            return c
    return None
def nums(node, n):                 # first n numeric atoms after head
    vals = []
    for c in node[1:]:
        if not is_list(c):
            try: vals.append(float(atom(c)))
            except ValueError: pass
        if len(vals) == n: break
    return vals

# ---------- transform ----------
def xform(ox, oy, rot, mirror, lx, ly):
    # KiCad: library Y is inverted vs sheet. Apply mirror, then rotation, then translate.
    x, y = lx, ly
    if mirror == 'y':  x = -x
    if mirror == 'x':  y = -y
    a = math.radians(rot)
    # sheet = origin + R(rot) * (x, -y)   (Y flip lib->sheet)
    sx = ox + (x * math.cos(a) - (-y) * math.sin(a))
    sy = oy + (x * math.sin(a) + (-y) * math.cos(a))
    return (round(sx, 3), round(sy, 3))

# ---------- union-find ----------
class UF:
    def __init__(self): self.p = {}
    def find(self, k):
        self.p.setdefault(k, k)
        while self.p[k] != k:
            self.p[k] = self.p[self.p[k]]; k = self.p[k]
        return k
    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)

def near(p, q, eps=0.05):
    return abs(p[0]-q[0]) < eps and abs(p[1]-q[1]) < eps
def on_seg(p, a, b, eps=0.05):
    # point p on segment a-b
    cross = (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])
    if abs(cross) > eps*max(1.0, math.hypot(b[0]-a[0], b[1]-a[1])):
        return False
    dot = (p[0]-a[0])*(b[0]-a[0]) + (p[1]-a[1])*(b[1]-a[1])
    L2 = (b[0]-a[0])**2 + (b[1]-a[1])**2
    return -eps <= dot <= L2 + eps

def resolve(sheet_path, ref):
    root = parse_sexp(Path(sheet_path).read_text())
    # instance
    inst = None
    for sym in find_all(root, 'symbol'):
        propnodes = [c for c in sym if is_list(c) and head(c) == 'property']
        for pr in propnodes:
            if len(pr) >= 3 and atom(pr[1]) == 'Reference' and atom(pr[2]) == ref:
                inst = sym; break
        if inst: break
    if inst is None:
        raise SystemExit(f"{ref} instance not found")
    lib_id = atom(get(inst, 'lib_id')[1])
    at = get(inst, 'at'); ox, oy, rot = float(atom(at[1])), float(atom(at[2])), float(atom(at[3]))
    mir = get(inst, 'mirror'); mirror = atom(mir[1]) if mir else None
    # lib_symbol pins (search whole tree for the matching lib symbol def)
    pins = []  # (number, sheet_point)
    for libsym in find_all(root, 'symbol'):
        nm = atom(libsym[1]) if len(libsym) > 1 and isinstance(libsym[1], tuple) else None
        if nm != lib_id:
            continue
        for pin in find_all(libsym, 'pin'):
            at_p = get(pin, 'at'); num_n = get(pin, 'number')
            if not at_p or not num_n:
                continue
            lx, ly = float(atom(at_p[1])), float(atom(at_p[2]))
            pins.append((atom(num_n[1]), xform(ox, oy, rot, mirror, lx, ly)))
        break
    # wires, labels, junctions
    wires = [( (float(atom(p[1])), float(atom(p[2]))) ) for p in []]  # placeholder
    segs = []
    for w in find_all(root, 'wire'):
        pts = get(w, 'pts')
        if not pts: continue
        xy = [(float(atom(p[1])), float(atom(p[2]))) for p in pts if head(p) == 'xy']
        for k in range(len(xy)-1):
            segs.append((round(xy[k][0],3), round(xy[k][1],3),
                         round(xy[k+1][0],3), round(xy[k+1][1],3)))
    labels = []; label_meta = {}   # pos -> (text, uuid)
    for lab in find_all(root, 'label'):
        txt = atom(lab[1]); at_l = get(lab, 'at'); uu = get(lab, 'uuid')
        pos = (round(float(atom(at_l[1])),3), round(float(atom(at_l[2])),3))
        uid = atom(uu[1]) if uu else None
        labels.append((txt, pos)); label_meta[pos] = (txt, uid)
    # build connectivity graph over points
    uf = UF()
    pts = set()
    for (x0,y0,x1,y1) in segs:
        uf.union((x0,y0),(x1,y1)); pts.add((x0,y0)); pts.add((x1,y1))
    for _,p in labels: pts.add(p)
    for _,p in pins: pts.add(p)
    # union coincident points and point-on-segment
    plist = list(pts)
    for a in plist:
        for (x0,y0,x1,y1) in segs:
            if on_seg(a,(x0,y0),(x1,y1)):
                uf.union(a,(x0,y0))
    # also union any two near points
    for idx in range(len(plist)):
        for jdx in range(idx+1, len(plist)):
            if near(plist[idx], plist[jdx]):
                uf.union(plist[idx], plist[jdx])
    # component -> label (text, pos)
    comp_lab = {}
    for txt, p in labels:
        comp_lab.setdefault(uf.find(p), p)
    pin_net = {}; pin_label = {}
    for num, p in pins:
        lp = comp_lab.get(uf.find(p))
        if lp is not None:
            txt, uid = label_meta[lp]
            pin_net[num] = txt
            pin_label[num] = {"text": txt, "pos": lp, "uuid": uid}
        else:
            pin_net[num] = None
    return pin_net, pin_label, {"ox":ox,"oy":oy,"rot":rot,"mirror":mirror,"n_pins":len(pins),
                     "n_wires":len(segs),"n_labels":len(labels)}

def main():
    sheet, ref, padnets = sys.argv[1], sys.argv[2], sys.argv[3]
    pin_net, pin_label, meta = resolve(sheet, ref)
    pad = json.load(open(padnets))   # padnum -> full net (e.g. /IO/SD_SCK)
    def tail(n): return n.split('/')[-1] if n else n
    match = miss = 0; misses = []
    for num, fullnet in sorted(pad.items(), key=lambda kv: int(kv[0])):
        if fullnet in ("GND","+3V3","+1V1"):     # planes: pin may be NC/power, skip strict check
            continue
        rn = pin_net.get(num)
        if rn is not None and tail(fullnet) == tail(rn):
            match += 1
        else:
            miss += 1; misses.append((num, fullnet, rn))
    print(f"meta: {meta}")
    print(f"signal pins matched={match}  mismatched/unresolved={miss}")
    for num, fn, rn in misses[:30]:
        print(f"  pad {num:>3}: PCB={fn:28} sch_label={rn}")
    json.dump({k:v for k,v in pin_net.items()}, open("/tmp/pin_net.json","w"), indent=1)
    json.dump(pin_label, open("/tmp/pin_labels.json","w"), indent=1)

if __name__ == "__main__":
    main()
