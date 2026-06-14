#!/usr/bin/env python3
"""patch_j10_nets.py — wire J10 USB-C pads with the correct UFP mapping.

The schematic generator wired J10's CC/VBUS/GND pins incorrectly into a
single /Power/CC2 net. This script overrides that by directly assigning
each pad based on the standard USB Type-C UFP pin map. Idempotent.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PCB = REPO / "defcon_badge" / "defcon_badge.kicad_pcb"


def main() -> int:
    text = PCB.read_text()
    nets = {
        name: int(code)
        for code, name in re.findall(r'^\t\(net (\d+) "([^"]+)"\)', text, re.MULTILINE)
    }
    gnd = nets.get("GND")
    vbus = nets.get("/Power/VBUS")
    cc2 = nets.get("/Power/CC2")
    usbdp = nets.get("Net-(U3-USB_DP)") or nets.get("/MCU_Core/USB_DP")
    usbdm = nets.get("Net-(U3-USB_DM)") or nets.get("/MCU_Core/USB_DM")
    if not all([gnd, vbus, cc2, usbdp, usbdm]):
        print(
            f"FATAL: missing nets in PCB: gnd={gnd} vbus={vbus} cc2={cc2} "
            f"usbdp={usbdp} usbdm={usbdm}. Run sync_nets first.",
            file=sys.stderr,
        )
        return 1

    pad_to_net = {
        "A1": (gnd, "GND"),
        "B1": (gnd, "GND"),
        "A12": (gnd, "GND"),
        "B12": (gnd, "GND"),
        "A4": (vbus, "/Power/VBUS"),
        "B4": (vbus, "/Power/VBUS"),
        "A9": (vbus, "/Power/VBUS"),
        "B9": (vbus, "/Power/VBUS"),
        "A5": (cc2, "/Power/CC2"),
        "B5": (cc2, "/Power/CC2"),
        "A6": (usbdp, "Net-(U3-USB_DP)"),
        "B6": (usbdp, "Net-(U3-USB_DP)"),
        "A7": (usbdm, "Net-(U3-USB_DM)"),
        "B7": (usbdm, "Net-(U3-USB_DM)"),
        "SH": (gnd, "GND"),
    }

    counter = [0]

    def patch_pad(m: re.Match) -> str:
        block = m.group(0)
        num_m = re.match(r'\(pad "([^"]+)"', block)
        if not num_m:
            return block
        pad_num = num_m.group(1)
        if pad_num not in pad_to_net:
            return block
        code, name = pad_to_net[pad_num]
        block = re.sub(r"\(net [^)]*\)\s*", "", block)
        block = block.replace('(uuid "', f'(net {code} "{name}") (uuid "', 1)
        counter[0] += 1
        return block

    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    i = 1
    while i < len(chunks):
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        if '(property "Reference" "J10"' in body:
            body = re.sub(
                r'\(pad "[^"]+" [^)]*?(?:\([^)]*?\)[^)]*?)*?\(uuid "[^"]+"\)\s*\)',
                patch_pad,
                body,
                flags=re.DOTALL,
            )
        out.append(chunks[i])
        out.append(body)
        i += 2

    PCB.write_text("".join(out))
    print(f"patched {counter[0]} J10 pads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
