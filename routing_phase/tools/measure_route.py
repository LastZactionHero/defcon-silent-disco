#!/usr/bin/env python3
"""measure_route.py — objective ROUTING metrics for the DEF CON badge.

The instrument the routing loop flies on (the Phase-D analog of placement_phase_2/
tools/measure.py). Every iteration runs it, appends exactly one JSON row to
routing_phase/metrics.jsonl, and uses the trend to detect thrashing.

Primary objective: completion_pct (-> 100). Then the tie-break J = track_len + via cost.
Plus the hard gates: 0 DRC, 0 shorts, USB pair correct, power widths, 0 acute/off-axis,
zones filled, determinism. See routing_phase/ROUTING_SPEC.md (METRIC ENGINE).

SAFETY (Resolution / learned 2026-06-17): kicad-cli sch erc / BOM export can REWRITE the
frozen approved .kicad_sch/.kicad_pro. So DRC *and* ERC run on a /tmp COPY of the whole
project (board + all sheets + .kicad_pro together). Geometry is read from the REAL board
(pcbnew LoadBoard is read-only). The completion baseline is read from baseline.json if
present (written by D1 after the zone-fill); otherwise the current unconnected count is the
baseline (completion 0 on the unrouted board).

Usage:
  measure_route.py defcon_badge/defcon_badge.kicad_pcb --phase D0 --iter 1 \
      --append routing_phase/metrics.jsonl
  measure_route.py PCB --json            # pretty JSON to stdout
  measure_route.py PCB --no-drc          # fast geometry-only (skip kicad-cli)
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "placement_phase_2" / "tools"))
import geom_route  # noqa: E402
import geom as pgeom  # noqa: E402  (placement geom: load_pcb pads/nets, board_outline)

# nets carried by planes (not routed as traces) + power classifier (reused from measure.py)
GROUND = {"GND", "/GND", "gnd", "AGND", "PGND", "DGND", "GNDA"}
POWER_RE = re.compile(r"(^\+|3V3|3\.3|1V1|1V8|5V|VBUS|VBAT|VDD|VCC|VREG|BAT\b)", re.I)

# --- locked thresholds (module-top; changing a DEFINITION needs a REVIEW, Resolution 6) ---
POWER_MIN_WIDTH_MM = 0.30
USB_SKEW_MAX_MM = 2.5
USB_CLASS = "USB_DIFF_90"
BASELINE_FILE = HERE.parents[1] / "routing_phase" / "baseline.json"   # written in D1


# --------------------------------------------------------------------------- #
# kicad-cli DRC/ERC plumbing — copied from placement measure.py (HARNESS allows AS-IS or copy)
# --------------------------------------------------------------------------- #
def run_kicad_cli(args: list[str]) -> dict | None:
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
    if not report:
        return []
    out: list[dict] = []
    for key in ("violations", "schematic_parity"):
        v = report.get(key)
        if isinstance(v, list):
            out.extend(x for x in v if isinstance(x, dict))
    for sheet in report.get("sheets", []) or []:
        v = sheet.get("violations")
        if isinstance(v, list):
            out.extend(x for x in v if isinstance(x, dict))
    return out


def sev(v: dict) -> str:
    return (v.get("severity") or v.get("severity_level") or "error").lower()


def _project_copy(pcb: Path):
    """Copy board + all sheets + .kicad_pro into a temp dir so kicad-cli DRC/ERC can run
    WITHOUT mutating the frozen approved schematics, and with the .kicad_pro present (so DRC
    reads the real net-class/clearance rules, not stricter defaults). Returns (dir, pcb, sch)."""
    td = Path(tempfile.mkdtemp(prefix="route_measure_"))
    src = pcb.parent
    for f in src.iterdir():
        if f.suffix in (".kicad_pcb", ".kicad_sch", ".kicad_pro"):
            shutil.copy2(f, td / f.name)
    return td, td / pcb.name, (td / pcb.name).with_suffix(".kicad_sch")


# routing-relevant DRC violation types (copper graph), excluding unconnected_items (own metric)
ROUTING_TYPES = {
    "clearance", "track_dangling", "via_dangling", "copper_edge_clearance",
    "track_width", "annular_width", "hole_clearance", "shorting_items",
    "tracks_crossing", "track_angle", "via_diameter", "hole_to_hole", "creepage",
}


# --------------------------------------------------------------------------- #
# geometry metrics (read from the REAL board; pcbnew LoadBoard is read-only)
# --------------------------------------------------------------------------- #
def _seg_angle_deg(t: dict) -> float:
    return math.degrees(math.atan2(t["y1"] - t["y0"], t["x1"] - t["x0"])) % 180.0


def _off_axis(tracks: list[dict], tol=1.0) -> int:
    n = 0
    for t in tracks:
        if t["kind"] == "arc":
            continue
        if abs(t["x1"] - t["x0"]) < 1e-6 and abs(t["y1"] - t["y0"]) < 1e-6:
            continue
        a = _seg_angle_deg(t)
        if min(abs(a - q) for q in (0, 45, 90, 135, 180)) > tol:
            n += 1
    return n


def _acute_angles(tracks: list[dict], tol=1.0) -> int:
    """Count shared-node junctions (same net) where two segments meet at <90deg (acid traps)."""
    nodes: dict = collections.defaultdict(list)
    Q = 1000  # 1um quantization for node coincidence
    for t in tracks:
        if t["kind"] == "arc":
            continue
        a = _seg_angle_deg(t)
        for (x, y) in ((t["x0"], t["y0"]), (t["x1"], t["y1"])):
            nodes[(round(x * Q), round(y * Q), t["net"], t["layer"])].append(a)
    n = 0
    for angs in nodes.values():
        for i in range(len(angs)):
            for j in range(i + 1, len(angs)):
                d = abs(angs[i] - angs[j]) % 180.0
                d = min(d, 180.0 - d)
                if 0.0 + tol < d < 90.0 - tol:
                    n += 1
    return n


def _net_routed_len(tracks, netname) -> float:
    return sum(t["length_mm"] for t in tracks if t["net"] == netname)


def _via_in_pad(b) -> int:
    """Count vias whose body sits on a pad's copper (via-in-pad). USER DIRECTIVE: no via-in-pad
    (it needs filled/plated vias = cost; pointless at this density). A proper fanout via is
    OFFSET from the pad with a short stub track, so it does NOT hit-test inside the pad copper;
    only a via actually landing on a pad is counted. HARD gate: via_in_pad == 0."""
    pads = [p for f in b.GetFootprints() for p in f.Pads()]
    n = 0
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        pos = t.GetPosition()
        top, bot = t.TopLayer(), t.BottomLayer()
        for p in pads:
            # pad copper at the via's XY on a layer the via touches (top/bottom covers SMD + THT)
            if p.HitTest(pos) and (p.IsOnLayer(top) or p.IsOnLayer(bot)):
                n += 1
                break
    return n


def _usb_nets(meta):
    """The two USB diff nets present on the board (connector + MCU sides share a base)."""
    dp = [n for n in {p["net"] for m in meta.values() for p in m["pads"] if p.get("net")}
          if n and re.search(r"USB_DP|USB_D\+", n)]
    dm = [n for n in {p["net"] for m in meta.values() for p in m["pads"] if p.get("net")}
          if n and re.search(r"USB_DM|USB_D-", n)]
    return dp, dm


def measure(pcb: Path, do_drc: bool = True) -> dict:
    # FROZEN-FILE SAFETY: do ALL pcbnew loads AND kicad-cli on a /tmp project copy, never the
    # real files. pcbnew's settings-manager flushes BOM field-defs into the real .kicad_pro on
    # process exit after reading project state; copying first means the real frozen files are
    # never opened. The copy is byte-identical so all reads are exactly the same.
    td, tpcb, tsch = _project_copy(pcb)
    try:
        return _measure_copy(tpcb, tsch, do_drc)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _measure_copy(pcb: Path, tsch: Path, do_drc: bool) -> dict:
    meta = pgeom.load_pcb(pcb)                       # footprints/pads/nets (authoritative)
    tracks = geom_route.load_tracks(pcb)
    vias = geom_route.load_vias(pcb)
    unconnected = geom_route.count_unconnected(pcb)

    # completion baseline (D1 freezes it post-zone-fill); pre-baseline -> baseline = now
    baseline = unconnected
    if BASELINE_FILE.exists():
        try:
            baseline = int(json.loads(BASELINE_FILE.read_text()).get("unconnected_baseline", unconnected))
        except (json.JSONDecodeError, ValueError):
            baseline = unconnected
    completion_pct = round(100.0 * (1 - unconnected / baseline), 2) if baseline > 0 else 100.0

    # track length, per layer, via count
    b = pcbnew.LoadBoard(str(pcb))
    by_layer: dict = collections.defaultdict(float)
    for t in tracks:
        by_layer[t["layer_name"]] += t["length_mm"]
    track_len = round(sum(t["length_mm"] for t in tracks), 2)
    fcu, bcu = by_layer.get("F.Cu", 0.0), by_layer.get("B.Cu", 0.0)
    layer_balance = round(min(fcu, bcu) / max(fcu, bcu), 3) if max(fcu, bcu) > 0 else None
    via_in_pad = _via_in_pad(b)          # USER DIRECTIVE: must be 0

    # power width gate (only routed power-net segments are policed; planes carry the rest)
    pw_ok = all(t["width"] >= POWER_MIN_WIDTH_MM - 1e-6
                for t in tracks if t["net"] and POWER_RE.search(t["net"]) and t["net"] not in GROUND)

    # USB diff pair
    dp, dm = _usb_nets(meta)
    usb_skew = None
    if dp and dm:
        usb_skew = round(abs(_net_routed_len(tracks, dp[0]) - _net_routed_len(tracks, dm[0])), 3)
    usb_paired = None
    try:
        ncmap = {n.GetNetname(): n.GetNetClassName() for n in b.GetNetInfo().NetsByNetcode().values()}
        if dp and dm:
            usb_paired = (ncmap.get(dp[0]) == USB_CLASS and ncmap.get(dm[0]) == USB_CLASS)
    except Exception:
        usb_paired = None

    off_axis = _off_axis(tracks)
    acute = _acute_angles(tracks)
    zones_filled_ok = all(z.IsFilled() for z in b.Zones()) if b.Zones() else True

    # DRC + ERC on a /tmp project copy (protect frozen sch; .kicad_pro present for real rules)
    erc_errors = drc_errors = shorts = unconn_drc = None
    drc_by_type: dict = {}
    if do_drc:
        drc_report = run_kicad_cli(["pcb", "drc", str(pcb)])   # pcb is already the /tmp copy
        drc = collect_violations(drc_report)
        errs = [v for v in drc if sev(v) == "error"]
        drc_by_type = dict(collections.Counter(
            (v.get("type") or "?") for v in errs if (v.get("type") or "") in ROUTING_TYPES))
        drc_errors = sum(drc_by_type.values())
        shorts = drc_by_type.get("shorting_items", 0)
        if isinstance(drc_report, dict):
            uc = drc_report.get("unconnected_items")
            unconn_drc = len(uc) if isinstance(uc, list) else None
        erc = collect_violations(run_kicad_cli(["sch", "erc", str(tsch)]))
        erc_errors = sum(1 for v in erc if sev(v) == "error")

    divergence = abs(unconnected - unconn_drc) if unconn_drc is not None else None

    return {
        "completion_pct": completion_pct,
        "unconnected": unconnected,
        "unconnected_baseline": baseline,
        "unconnected_drc": unconn_drc,
        "unconnected_divergence": divergence,
        "shorts": shorts if shorts is not None else -1,
        "drc_errors": drc_errors if drc_errors is not None else -1,
        "drc_by_type": drc_by_type,
        "track_count": len(tracks),
        "via_count": len(vias),
        "via_in_pad": via_in_pad,       # USER DIRECTIVE: no via-in-pad — HARD gate == 0

        "track_len_mm": track_len,
        "track_len_by_layer": {k: round(v, 2) for k, v in by_layer.items()},
        "layer_balance": layer_balance,
        "usb_diff_paired": usb_paired,
        "usb_diff_skew_mm": usb_skew,
        "power_min_width_ok": pw_ok,
        "acute_angles": acute,
        "off_axis_segments": off_axis,
        "bus_pitch_var": None,          # set once bus_plan groups exist (D3)
        "zones_filled_ok": zones_filled_ok,
        "determinism_ok": None,         # set by the route-twice determinism gate (D5)
        "erc_errors": erc_errors if erc_errors is not None else -1,
        "n_footprints": len(meta),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--phase", default="?")
    ap.add_argument("--iter", default="?")
    ap.add_argument("--approach", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--append", help="metrics.jsonl path to append the row to")
    ap.add_argument("--no-drc", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    m = measure(Path(args.pcb), do_drc=not args.no_drc)
    row = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "phase": args.phase,
           "iter": args.iter, "approach": args.approach, "commit": args.commit, **m}
    if args.append:
        with open(args.append, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    if args.json:
        print(json.dumps(row, indent=2))
    else:
        keys = ["completion_pct", "unconnected", "unconnected_divergence", "shorts",
                "drc_errors", "track_count", "via_count", "via_in_pad", "track_len_mm",
                "usb_diff_paired", "off_axis_segments", "acute_angles", "zones_filled_ok",
                "erc_errors"]
        print(f"[{row['phase']}({row['iter']})] " + "  ".join(f"{k}={row[k]}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
