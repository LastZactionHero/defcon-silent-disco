#!/usr/bin/env python3
"""decouple.py — drive auto_decouple for every IC on the board, reproducibly.

Derives each bypass cap's owner from connectivity (nearest same-net pad on a
non-passive part: U*/LED*/D*/Y*), groups caps by owner, and runs the tested
pcb-placement auto_decouple primitive per owner so every decoupling cap lands
adjacent to its IC power pin. This is the Phase-C "ring" step; it makes
decoupling_max_mm collapse toward <=2.0 without any hand placement.

Usage:
  decouple.py defcon_badge/defcon_badge.kicad_pcb [--max-uf 1.1] [--dry-run]
"""
from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL = os.environ.get(
    "PCB_PLACEMENT_SCRIPTS",
    str(Path.home() / ".claude/skills/pcb-placement/scripts"),
)
sys.path.insert(0, SKILL)
from fp_meta import load_pcb            # noqa: E402

GROUND = {"GND", "/GND", "AGND", "PGND", "DGND"}
POWER_RE = re.compile(r"(^\+|3V3|3\.3|1V1|1V8|5V|VBUS|VBAT|VDD|VCC|VREG|BAT\b)", re.I)
OWNER_PREFIX = ("U", "LED", "D", "Y")     # parts that actually want decoupling


def parse_farads(value):
    if not value:
        return None
    m = re.match(r"^\s*([\d.]+)\s*([pnumµu]?)\s*[fF]?\s*$", value.strip())
    if not m:
        return None
    scale = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0}
    return float(m.group(1)) * scale.get(m.group(2), 1.0)


def owners_for_caps(meta, max_uf):
    by_net = {}
    for ref, m in meta.items():
        for pad in m["pads"]:
            n = pad.get("net")
            if n:
                by_net.setdefault(n, []).append((pad["x"], pad["y"], ref))

    # collect each cap's candidate owners (same-net non-passive parts)
    cap_cands = {}
    for ref, m in meta.items():
        if not ref.startswith("C"):
            continue
        f = parse_farads(m.get("value"))
        if f is None or f > max_uf * 1e-6:
            continue
        pads = m["pads"]
        if len(pads) != 2:
            continue
        pwr = [p for p in pads if p.get("net") and p["net"] not in GROUND
               and POWER_RE.search(p["net"])]
        if not pwr:
            continue
        p = pwr[0]
        cands = {}
        for q in by_net.get(p["net"], []):
            if q[2] != ref and q[2].startswith(OWNER_PREFIX):
                d = math.hypot(p["x"] - q[0], p["y"] - q[1])
                cands[q[2]] = min(cands.get(q[2], 1e9), d)
        if cands:
            cap_cands[ref] = cands

    # Load-balanced nearest assignment: a cap goes to its nearest candidate owner,
    # but owners already carrying caps are penalised so siblings on a shared rail
    # (e.g. 4 SK9822 LEDs all on +3V3) each get their own bypass cap before any
    # owner doubles up. Resolves the rail-only-cap ambiguity Approach B exposed.
    load = {}
    groups = {}
    # assign caps with the fewest candidates first (most constrained)
    for ref in sorted(cap_cands, key=lambda r: len(cap_cands[r])):
        cands = cap_cands[ref]
        owner = min(cands, key=lambda o: (load.get(o, 0), cands[o]))
        load[owner] = load.get(owner, 0) + 1
        groups.setdefault(owner, []).append(ref)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb")
    ap.add_argument("--max-uf", type=float, default=1.1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pcb = Path(args.pcb)
    meta = load_pcb(pcb)
    groups = owners_for_caps(meta, args.max_uf)
    def num(r):
        m = re.search(r"\d+", r)
        return int(m.group()) if m else 0

    print("owner -> caps:")
    for o in sorted(groups):
        print(f"  {o:6} {','.join(sorted(groups[o], key=num))}")
    if args.dry_run:
        return 0

    ad = str(Path(SKILL) / "auto_decouple.py")
    for owner, caps in groups.items():
        r = subprocess.run(
            ["python3", ad, str(pcb), owner, "--caps", ",".join(caps)],
            capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"  decouple {owner} ({len(caps)} caps): {tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
