#!/usr/bin/env python3
"""route_db.py — incremental routing database (the re-runnability engine).

The user's hard requirement: when a part goes out of stock and gets swapped (schematic +
placement re-sync), re-routing must touch ONLY the changed nets and replay everything else
byte-for-byte — cost proportional to the change, not the board. This module is the data
model + diff that makes that structural, built in D0 before any router exists.

Core idea (ROUTING_SPEC INCREMENTAL MODEL): identify each net by a STABLE SIGNATURE derived
from its physical pad membership, NOT its KiCad net name (auto-names churn: Net-(U3-USB_DP),
hierarchical-path renames). A swap that keeps a net's pad set leaves its signature identical
=> that net is UNCHANGED => its stored copper is REPLAYED, never re-searched.

  net_sig         = sha1(sorted pin_set of "REFDES-PADNUM")[:16]
  record          = {net_sig, net_name, pin_set, pad_xy(nm), netclass, input_hash, route}
  input_hash      = sha1(pin_set + pad_xy + netclass)  -> detects a moved pad / class change
  diff(live, db)  -> NEW / CHANGED / DELETED / UNCHANGED
  stable_order    -> perturbation-stable routing sequence (intrinsic key per net)
  record_routes   -> snapshot current copper into records (called after routing)
  replay          -> re-emit stored routes for given sigs (unchanged nets)
  fingerprint     -> canonical copper tuple for the determinism gate (route twice -> identical)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geom_route  # noqa: E402

DB_PATH = HERE.parents[1] / "routing_phase" / "route_db.json"
NM = 1_000_000
# nets carried by planes (fanout vias, not point-to-point traces) — ranked/handled separately
PLANE_NETS = {"GND", "+3V3"}


# --------------------------------------------------------------------------- #
# signatures
# --------------------------------------------------------------------------- #
def net_signature(pin_set) -> str:
    return hashlib.sha1("|".join(sorted(pin_set)).encode()).hexdigest()[:16]


def _input_hash(pin_set, pad_xy: dict, netclass: str) -> str:
    payload = json.dumps({"p": sorted(pin_set),
                          "xy": {k: pad_xy[k] for k in sorted(pad_xy)},
                          "nc": netclass}, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# live nets (read from a /tmp project copy — never touches the frozen files)
# --------------------------------------------------------------------------- #
def live_nets(path) -> dict:
    """{net_sig: record} for every net with >=2 pads (a routable connection)."""
    with geom_route.safe_board(path) as b:
        by_net: dict = {}
        for fp in b.GetFootprints():
            ref = fp.GetReference()
            for p in fp.Pads():
                nn = p.GetNetname()
                if not nn:
                    continue
                pos = p.GetPosition()
                by_net.setdefault(nn, {})[f"{ref}-{p.GetNumber()}"] = [int(pos.x), int(pos.y)]
        out = {}
        for nn, pads in by_net.items():
            if len(pads) < 2:
                continue
            pin_set = sorted(pads.keys())
            net = b.FindNet(nn)
            nc = net.GetNetClassName() if net is not None else "Default"
            sig = net_signature(pin_set)
            out[sig] = {
                "net_sig": sig, "net_name": nn, "pin_set": pin_set,
                "pad_xy": pads, "netclass": nc,
                "input_hash": _input_hash(pin_set, pads, nc),
                "is_plane": nn in PLANE_NETS,
            }
        return out


# --------------------------------------------------------------------------- #
# persistence + diff
# --------------------------------------------------------------------------- #
def load_db(path=DB_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        return {"version": 1, "router_version": 0, "nets": {}}
    return json.loads(p.read_text())


def save_db(db: dict, path=DB_PATH) -> None:
    Path(path).write_text(json.dumps(db, indent=1, sort_keys=True))


def diff(live: dict, db: dict) -> dict:
    """Classify live nets vs the stored db by signature + input_hash."""
    dbnets = db.get("nets", {})
    new, changed, unchanged = [], [], []
    for sig, rec in live.items():
        if sig not in dbnets:
            new.append(sig)
        elif dbnets[sig].get("input_hash") != rec["input_hash"]:
            changed.append(sig)
        else:
            unchanged.append(sig)
    deleted = [sig for sig in dbnets if sig not in live]
    return {"new": sorted(new), "changed": sorted(changed),
            "deleted": sorted(deleted), "unchanged": sorted(unchanged)}


# --------------------------------------------------------------------------- #
# stable, perturbation-proof routing order
# --------------------------------------------------------------------------- #
def _netclass_rank(rec) -> int:
    nc, nn = rec["netclass"], rec["net_name"]
    if "DIFF" in nc.upper() or "USB_D" in nn.upper():
        return 0                         # diff pairs / USB first
    if rec.get("is_plane"):
        return 4                         # plane nets handled by fanout, not the trace router
    # crystal / flash bus are critical, route early
    if any(k in nn.upper() for k in ("XIN", "XOUT", "QSPI", "I2S")):
        return 1
    from re import search
    if search(r"(^\+|3V3|1V1|5V|VBUS|VBAT|VDD|VCC|VREG|BAT\b|GND)", nn, 2):
        return 3                         # power stubs
    return 2                             # generic signal buses + singletons


def _half_perim(rec) -> float:
    xs = [v[0] for v in rec["pad_xy"].values()]
    ys = [v[1] for v in rec["pad_xy"].values()]
    return ((max(xs) - min(xs)) + (max(ys) - min(ys))) / NM


def stable_order(live: dict, include_planes=False) -> list:
    """Deterministic AND perturbation-stable: each key component is intrinsic to the net, so
    adding/removing one net only inserts/removes its row — survivors keep their relative order."""
    sigs = [s for s, r in live.items() if include_planes or not r.get("is_plane")]
    return sorted(sigs, key=lambda s: (
        _netclass_rank(live[s]),
        -len(live[s]["pin_set"]),
        round(_half_perim(live[s]), 2),
        s,
    ))


# --------------------------------------------------------------------------- #
# copper snapshot / replay / determinism fingerprint
# --------------------------------------------------------------------------- #
def record_routes(path, live: dict) -> dict:
    """Snapshot the board's current copper into each live net's record['route'] (call AFTER
    routing to persist). Buckets tracks/vias by net name."""
    tracks = geom_route.load_tracks(path)
    vias = geom_route.load_vias(path)
    name_to_sig = {r["net_name"]: s for s, r in live.items()}
    routes: dict = {s: {"tracks": [], "vias": []} for s in live}
    for t in tracks:
        s = name_to_sig.get(t["net"])
        if s:
            routes[s]["tracks"].append({"layer": t["layer_name"], "x0": t["x0"], "y0": t["y0"],
                                        "x1": t["x1"], "y1": t["y1"], "w": t["width"]})
    for v in vias:
        s = name_to_sig.get(v["net"])
        if s:
            routes[s]["vias"].append({"x": v["x"], "y": v["y"], "top": v["top"],
                                      "bottom": v["bottom"], "drill": v["drill"], "w": v["width"]})
    return routes


def replay(board, records: dict, sigs, live: dict) -> int:
    """Re-emit stored routes (tracks+vias) for the given net signatures onto a loaded board.
    Used to preserve UNCHANGED nets byte-for-byte on a re-run. Returns segments+vias emitted."""
    n = 0
    for sig in sigs:
        rec = records.get(sig)
        net_name = live[sig]["net_name"] if sig in live else (rec or {}).get("net_name")
        if not rec:
            continue
        for t in rec.get("route", {}).get("tracks", []):
            geom_route.add_track(board, t["x0"], t["y0"], t["x1"], t["y1"], t["layer"], net_name, t["w"])
            n += 1
        for v in rec.get("route", {}).get("vias", []):
            geom_route.add_via(board, v["x"], v["y"], net_name, v["drill"], v["w"], v["top"], v["bottom"])
            n += 1
    return n


def fingerprint(path) -> tuple:
    """Canonical, order-independent copper fingerprint for the DETERMINISM gate (route twice ->
    assert identical). Operates on a board path (use temp boards in the gate)."""
    tracks = tuple(sorted(
        (round(t["x0"], 4), round(t["y0"], 4), round(t["x1"], 4), round(t["y1"], 4),
         t["layer_name"], round(t["width"], 4), t["net"] or "")
        for t in geom_route.load_tracks(path)))
    vias = tuple(sorted(
        (round(v["x"], 4), round(v["y"], 4), v["top"], v["bottom"], round(v["drill"], 4), v["net"] or "")
        for v in geom_route.load_vias(path)))
    return (tracks, vias)


def routes_identical(path_a, path_b) -> bool:
    return fingerprint(path_a) == fingerprint(path_b)


def _selftest(path) -> int:
    live = live_nets(path)
    db = load_db()
    d = diff(live, db)
    order = stable_order(live)
    planes = [s for s, r in live.items() if r["is_plane"]]
    fp = fingerprint(path)
    print(f"live routable nets: {len(live)}  (planes: {len(planes)} -> {[live[s]['net_name'] for s in planes]})")
    print(f"diff vs db: new={len(d['new'])} changed={len(d['changed'])} "
          f"deleted={len(d['deleted'])} unchanged={len(d['unchanged'])}")
    print(f"stable route order: {len(order)} signal nets; first 6 ->")
    for s in order[:6]:
        r = live[s]
        print(f"   rank{_netclass_rank(r)} {r['net_name']:<26} pins={len(r['pin_set'])} class={r['netclass']} sig={s}")
    print(f"fingerprint: {len(fp[0])} tracks, {len(fp[1])} vias (empty on unrouted board)")
    # determinism of the model itself: signatures are stable across two reads
    live2 = live_nets(path)
    assert set(live) == set(live2), "net signatures not reproducible!"
    print("signature reproducibility: OK (two reads -> identical sig set)")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    sys.exit(_selftest(p))
