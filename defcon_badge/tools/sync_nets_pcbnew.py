#!/usr/bin/env python3
"""sync_nets_pcbnew.py — authoritative schematic→PCB net sync via the pcbnew API.

Replaces the regex-based sync_nets.py for RE-syncs: that tool only matched pads
still in the legacy code-less `(net "name")` form, so pads already carrying a
net code were silently skipped (left R3/R4/C1/C17 and J10's D± stale after the
schematic review fixes). This walks every pad through pcbnew and sets its net
from the kicad-cli netlist by (refdes, pad) — idempotent and complete.

Footprint positions are never touched, so it is safe to run alongside the
placement loop (which only moves footprints).
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[2]
PCB = REPO / "defcon_badge" / "defcon_badge.kicad_pcb"
SCH = REPO / "defcon_badge" / "defcon_badge.kicad_sch"
NETLIST = Path("/tmp/defcon_netlist_pcbnew.net")


def export_netlist() -> None:
    subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
         "--output", str(NETLIST), str(SCH)],
        check=True, capture_output=True,
    )


def parse_pad_to_net(text: str) -> dict:
    pad_to_net = {}
    for m in re.finditer(
        r'\(net\s+\(code "\d+"\)\s+\(name "([^"]+)"\)\s+\(class "[^"]*"\)(.*?)\n\t\t\)',
        text, re.DOTALL,
    ):
        name, body = m.group(1), m.group(2)
        for nm in re.finditer(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', body):
            pad_to_net[(nm.group(1), nm.group(2))] = name
    return pad_to_net


def main() -> int:
    export_netlist()
    pad_to_net = parse_pad_to_net(NETLIST.read_text())
    print(f"netlist: {len(pad_to_net)} pad assignments")

    board = pcbnew.LoadBoard(str(PCB))

    # Ensure every needed net exists; cache NETINFO_ITEM by name.
    def get_or_add(name: str):
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        return net

    changed = 0
    missing = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            key = (ref, pad.GetPadName())
            if key not in pad_to_net:
                # No schematic node for this pad (e.g. mounting holes, shield)
                continue
            want = pad_to_net[key]
            if pad.GetNetname() != want:
                pad.SetNet(get_or_add(want))
                changed += 1
    pcbnew.SaveBoard(str(PCB), board)
    print(f"reassigned {changed} pad nets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
