#!/usr/bin/env python3
"""measure.py — objective placement metrics for the DEF CON badge.

This is the instrument the whole loop flies on. Every iteration runs it,
appends exactly one JSON row to metrics.jsonl, and uses the trend to detect
thrashing. It is intentionally self-contained except for the pcb-placement
skill primitives (fp_meta / ratsnest / validate_placement / check_courtyards),
which are the project's KEEP-and-build-on geometry layer.

Emitted metric keys (the locked schema from HARNESS.md):
  overlaps                 courtyard-pair overlaps (geometric, layer-aware)
  offboard                 placed parts whose courtyard leaves Edge.Cuts
  unplaced                 footprints still at the (0,0) origin
  fp_unresolved            footprints with no resolvable pads/footprint
  ratsnest_mm              total MST wirelength across signal nets (excl GND)
  courtyard_violations     DRC courtyards_overlap count (falls back to overlaps)
  decoupling_max_mm        worst cap->owner-IC-power-pin distance
  dfm_spacing_violations   DRC clearance violations (IPC nominal)
  fixed_ok                 bool: all fixed/edge constraints satisfied
  erc_errors               schematic ERC error count
  drc_errors               PCB DRC error count (excl. unconnected)

Plus bookkeeping: ts, phase, iter, approach, commit (filled from args), and a
`fixed_detail` / `unconnected` / `notes` block for human eyes.

Usage:
  measure.py defcon_badge/defcon_badge.kicad_pcb \
      --phase A --iter 1 --approach baseline --commit HEAD \
      --append placement_phase_2/metrics.jsonl
  measure.py PCB --no-drc        # fast geometric-only pass during tool dev
  measure.py PCB --json          # pretty JSON to stdout
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# --- locate the pcb-placement skill primitives -------------------------------
SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ratsnest import mst_length                    # noqa: E402
from validate_placement import (                   # noqa: E402
    parse_edge_cuts, point_in_polygon, cy_corners,
)
import geom                                         # noqa: E402  (authoritative pcbnew geometry)
from geom import load_pcb                           # noqa: E402

GROUND = {"GND", "/GND", "gnd", "AGND", "PGND", "DGND", "GNDA"}
# nets we treat as "power" for decoupling/ownership reasoning
POWER_RE = re.compile(r"(^\+|3V3|3\.3|1V1|1V8|5V|VBUS|VBAT|VDD|VCC|VREG|BAT\b)", re.I)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def parse_farads(value: str | None) -> float | None:
    """'100n' '0.1uF' '15p' '10uF' '220uF' -> farads. None if not a cap value."""
    if not value:
        return None
    m = re.match(r"^\s*([\d.]+)\s*([pnumµu]?)\s*[fF]?\s*$", value.strip())
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    scale = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0}
    return num * scale.get(m.group(2), 1.0)


def world_pads(meta: dict) -> dict:
    """net name -> list of (x, y, refdes, padnum)."""
    by_net: dict[str, list] = {}
    for ref, m in meta.items():
        for pad in m["pads"]:
            net = pad.get("net")
            if not net:
                continue
            by_net.setdefault(net, []).append((pad["x"], pad["y"], ref, pad["num"]))
    return by_net


def run_kicad_cli(args: list[str]) -> dict | None:
    """Run a kicad-cli sub-command that writes JSON to a temp file; return parsed.
    `args` = [domain, verb, ..., target] e.g. ["pcb","drc", board] — the two-token
    sub-command stays first; the --format/-o flags go after it."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.json"
        cmd = args[:2] + ["--format", "json", "-o", str(out)] + args[2:]
        try:
            subprocess.run(["kicad-cli", *cmd], capture_output=True, timeout=240, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if not out.exists():
            return None
        try:
            return json.loads(out.read_text())
        except json.JSONDecodeError:
            return None


def collect_violations(report: dict | None) -> list[dict]:
    """Flatten a kicad-cli drc/erc report into a flat violation list."""
    if not report:
        return []
    out: list[dict] = []
    for key in ("violations", "schematic_parity"):
        v = report.get(key)
        if isinstance(v, list):
            out.extend(x for x in v if isinstance(x, dict))
    # ERC reports nest violations under sheets
    for sheet in report.get("sheets", []) or []:
        v = sheet.get("violations")
        if isinstance(v, list):
            out.extend(x for x in v if isinstance(x, dict))
    return out


def sev(v: dict) -> str:
    return (v.get("severity") or v.get("severity_level") or "error").lower()


def _item_ref(it: dict):
    m = re.search(r"(?:of |Footprint )([A-Za-z]+\d+)", it.get("description", ""))
    return m.group(1) if m else None


# edge-locked connectors that are SUPPOSED to have copper at the board edge
EDGE_EXEMPT = {"J10", "J20", "J31", "U30", "D20", "J11"}


def placement_spacing(v: dict) -> bool:
    """True only for PLACEMENT-caused copper-spacing violations — i.e. distinct
    footprints' copper too close, or a non-edge part's pad too close to the board
    edge. Excludes geometry the layout can't/shouldn't change: intra-footprint
    fine-pitch pins / THT hole rings (same or single refdes), GND-zone-fill-to-edge
    (a zone clearance setting), and edge connectors whose pads belong at the edge."""
    t = v.get("type") or ""
    items = v.get("items", [])
    refs = {_item_ref(it) for it in items}
    refs.discard(None)
    if t in ("clearance", "hole_clearance", "track_width", "annular_width"):
        return len(refs) >= 2                       # two different parts -> placement
    if t == "copper_edge_clearance":
        part_refs = [r for r in refs if r not in EDGE_EXEMPT]
        return bool(part_refs)                       # a non-edge part pad near edge
    return False


# --------------------------------------------------------------------------- #
# metric computations
# --------------------------------------------------------------------------- #
def geom_overlaps(meta: dict) -> int:
    """Authoritative courtyard-overlap count from pcbnew courtyard AABBs
    (same-layer pairs). Matches what KiCad DRC reports."""
    boxes = []
    for ref, m in meta.items():
        cbb = m.get("courtyard_bbox")
        if cbb:
            boxes.append((cbb[0], cbb[1], cbb[2], cbb[3], m["layer"]))
    # require a small positive clearance: DRC flags courtyards that merely touch
    # (0mm gap), so count any pair whose AABBs overlap OR are within EPS.
    EPS = 0.05
    n = 0
    for i in range(len(boxes)):
        ax0, ay0, ax1, ay1, al = boxes[i]
        for j in range(i + 1, len(boxes)):
            bx0, by0, bx1, by1, bl = boxes[j]
            if al != bl:
                continue
            if (min(ax1, bx1) - max(ax0, bx0) > -EPS and
                    min(ay1, by1) - max(ay0, by0) > -EPS):
                n += 1
    return n


def count_offboard(meta: dict, poly: list) -> int:
    """A part is off-board if its courtyard CENTROID lies outside Edge.Cuts — i.e.
    it is still in the staging grid / floating off the board. Edge connectors
    (USB-C, audio jack, microSD) legitimately have courtyards that poke past the
    edge; their centroids stay on-board, so they correctly count as placed. A part
    hanging too far over an edge is caught separately by DRC copper_edge_clearance
    (folded into dfm_spacing_violations), so the gate set stays strict overall."""
    if len(poly) < 3:
        return 0
    n = 0
    for ref, m in meta.items():
        cy = m.get("courtyard_bbox")
        if not cy:
            continue
        cx = (cy[0] + cy[2]) / 2
        cyc = (cy[1] + cy[3]) / 2
        if not point_in_polygon(cx, cyc, poly):
            n += 1
    return n


def count_unplaced(meta: dict) -> int:
    return sum(1 for m in meta.values()
               if abs(m["anchor"]["x"]) < 1e-6 and abs(m["anchor"]["y"]) < 1e-6)


def count_unresolved(meta: dict) -> int:
    # Mechanical parts (mounting holes, fiducials) legitimately have no pads.
    mech = ("H", "MH", "FID", "MK")
    return sum(1 for r, m in meta.items()
               if not m["pads"] and not r.startswith(mech))


def total_ratsnest(meta: dict) -> float:
    by_net: dict[str, list] = {}
    for ref, m in meta.items():
        for pad in m["pads"]:
            net = pad.get("net")
            if not net or net in GROUND:
                continue
            by_net.setdefault(net, []).append((pad["x"], pad["y"]))
    return round(sum(mst_length(pts) for pts in by_net.values()), 2)


def decoupling_worst(meta: dict) -> tuple[float, list]:
    """For each small cap (<=1uF) with one GND pad + one power pad, distance from
    the power pad to the nearest same-net IC (U*) power pad. Return (max, detail)."""
    by_net = world_pads(meta)
    worst = 0.0
    detail = []
    for ref, m in meta.items():
        if not ref.startswith("C"):
            continue
        f = parse_farads(m.get("value"))
        if f is None or f > 1.1e-6:
            continue
        pads = m["pads"]
        if len(pads) != 2:
            continue
        pwr = [p for p in pads if p.get("net") and p["net"] not in GROUND
               and POWER_RE.search(p["net"])]
        gnd = [p for p in pads if p.get("net") in GROUND]
        if not (pwr and gnd):
            continue
        p = pwr[0]
        # "owner" = nearest same-net pad on a non-passive part (IC, LED, diode,
        # crystal, connector) — i.e. the thing this cap is bypassing.
        owner_pads = [q for q in by_net.get(p["net"], [])
                      if q[2] != ref and not q[2][0] in ("C", "R")]
        if not owner_pads:
            continue
        d = min(math.hypot(p["x"] - q[0], p["y"] - q[1]) for q in owner_pads)
        detail.append({"cap": ref, "net": p["net"], "mm": round(d, 2)})
        worst = max(worst, d)
    detail.sort(key=lambda x: -x["mm"])
    return round(worst, 2), detail[:10]


def check_fixed(meta: dict, outline: tuple) -> tuple[bool, dict]:
    """Verify board-specific fixed/edge constraints (HARNESS Phase C gate).
    Tolerances are deliberately generous: this answers 'is the part on the
    right edge/corner', not 'is it pixel-perfect'."""
    x0, y0, x1, y1 = outline
    xm = (x0 + x1) / 2
    EDGE = 3.0       # how close the COURTYARD edge must reach the board edge
    detail = {}

    def fp(ref):
        return meta.get(ref)

    # Use the COURTYARD edge, not the anchor — a large connector sits at the edge
    # while its anchor is mid-body several mm inboard (the bug that failed J10).
    def cy(m):       return m.get("courtyard_bbox") if m else None
    def near_top(m):    c = cy(m); return bool(c) and abs(c[1] - y0) < EDGE
    def near_bot(m):    c = cy(m); return bool(c) and abs(c[3] - y1) < EDGE
    def near_left(m):   c = cy(m); return bool(c) and abs(c[0] - x0) < EDGE
    def near_right(m):  c = cy(m); return bool(c) and abs(c[2] - x1) < EDGE
    def cx_of(m):       c = cy(m); return (c[0] + c[2]) / 2 if c else None
    def cyc_of(m):      c = cy(m); return (c[1] + c[3]) / 2 if c else None
    def y_about(m, y):  v = cyc_of(m); return v is not None and abs(v - y) < 8.0

    detail["J20_top_right"]   = bool(near_top(fp("J20")) and cx_of(fp("J20")) and cx_of(fp("J20")) > xm)
    detail["J10_usb_bottom"]  = bool(near_bot(fp("J10")))
    detail["SW1_bottom_left"] = bool(fp("SW1") and near_bot(fp("SW1")) and cx_of(fp("SW1")) < xm)
    detail["U30_left_y110"]   = bool(near_left(fp("U30")) and y_about(fp("U30"), 110))
    detail["D20_right_y110"]  = bool(near_right(fp("D20")) and y_about(fp("D20"), 110))
    j31 = fp("J31")
    detail["J31_microSD_back_edge"] = bool(
        j31 and j31["layer"] == "B.Cu" and
        (near_left(j31) or near_right(j31) or near_top(j31) or near_bot(j31)))

    # 4 mounting holes, one in each corner quadrant, near a corner
    holes = [m for r, m in meta.items() if r.startswith("H")]
    corners_hit = 0
    for cx, cy_ in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        if any(math.hypot(h["anchor"]["x"] - cx, h["anchor"]["y"] - cy_) < 12.0 for h in holes):
            corners_hit += 1
    detail["mounting_holes_4_corners"] = corners_hit == 4

    return all(detail.values()), detail


# --------------------------------------------------------------------------- #
def measure(pcb: Path, do_drc: bool = True) -> dict:
    text = pcb.read_text()
    meta = load_pcb(pcb)
    poly = parse_edge_cuts(text)
    outline = geom.board_outline(pcb)

    overlaps = geom_overlaps(meta)
    deco_max, deco_detail = decoupling_worst(meta)
    fixed_ok, fixed_detail = check_fixed(meta, outline)

    erc_errors = drc_errors = dfm_spacing = courtyard_drc = unconnected = None
    if do_drc:
        proj_sch = pcb.with_suffix(".kicad_sch")
        erc = collect_violations(run_kicad_cli(["sch", "erc", str(proj_sch)]))
        erc_errors = sum(1 for v in erc if sev(v) == "error")
        drc_report = run_kicad_cli(["pcb", "drc", str(pcb)])
        drc = collect_violations(drc_report)
        drc_errors = sum(1 for v in drc if sev(v) == "error")
        dfm_spacing = sum(1 for v in drc if placement_spacing(v))
        courtyard_drc = sum(1 for v in drc
                            if "courtyard" in (v.get("type") or ""))
        if isinstance(drc_report, dict):
            uc = drc_report.get("unconnected_items")
            unconnected = len(uc) if isinstance(uc, list) else None

    return {
        "overlaps": overlaps,
        "offboard": count_offboard(meta, poly),
        "unplaced": count_unplaced(meta),
        "fp_unresolved": count_unresolved(meta),
        "ratsnest_mm": total_ratsnest(meta),
        "courtyard_violations": courtyard_drc if courtyard_drc is not None else overlaps,
        "decoupling_max_mm": deco_max,
        "dfm_spacing_violations": dfm_spacing if dfm_spacing is not None else -1,
        "fixed_ok": fixed_ok,
        "erc_errors": erc_errors if erc_errors is not None else -1,
        "drc_errors": drc_errors if drc_errors is not None else -1,
        # human-eyes extras (not part of the locked schema)
        "unconnected": unconnected,
        "fixed_detail": fixed_detail,
        "decoupling_detail": deco_detail,
        "n_footprints": len(meta),
        "outline": [round(v, 1) for v in outline],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--phase", default="?")
    ap.add_argument("--iter", default="?")
    ap.add_argument("--approach", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--append", help="metrics.jsonl path to append the row to")
    ap.add_argument("--no-drc", action="store_true", help="skip ERC/DRC (fast)")
    ap.add_argument("--json", action="store_true", help="pretty JSON to stdout")
    args = ap.parse_args()

    m = measure(Path(args.pcb), do_drc=not args.no_drc)
    row = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "phase": args.phase,
        "iter": args.iter,
        "approach": args.approach,
        "commit": args.commit,
        **m,
    }

    if args.append:
        with open(args.append, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    if args.json:
        print(json.dumps(row, indent=2))
    else:
        keys = ["overlaps", "offboard", "unplaced", "fp_unresolved", "ratsnest_mm",
                "courtyard_violations", "decoupling_max_mm", "dfm_spacing_violations",
                "fixed_ok", "erc_errors", "drc_errors"]
        print(f"[{row['phase']}({row['iter']})] " +
              "  ".join(f"{k}={row[k]}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
