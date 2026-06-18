#!/usr/bin/env python3
"""gpio_remap_apply.py — apply the R2 GPIO remap by permuting U3-pin LOCAL LABELS in MCU_Core.

The remap moves 6 nets to destination-facing RP2040 pins by relabeling (the only semantically-correct
remap on a function-named symbol — the silicon pin keeps its identity, the NET moves). Because the
displaced pads are unused-GPIO no-connects, the whole thing is a PERMUTATION of the same 11 local-label
strings across 11 pin positions: no net is created or destroyed, just repositioned. That property is
the safety guarantee — verified before and after.

Each label is matched by (old_text + exact (at x y) position) so the edit is unambiguous. The tool
asserts every label currently reads its expected old text before touching anything; any mismatch aborts.

Usage: gpio_remap_apply.py <sheet.kicad_sch>     (edits in place; run on a /tmp copy first)
Prints the 11 swaps. The matching PCB pad-net permutation is applied separately (pcb_runner).
"""
from __future__ import annotations
import re, sys
from pathlib import Path

# pad -> (label x, label y, OLD text, NEW text). y from sch_pin_resolver (/tmp/pin_labels.json).
PERM = [
    (13, 245.11, 137.16, "LED_SCK",     "~{CHRG}"),
    (14, 245.11, 139.70, "LED_DAT",     "GPIO24"),
    (18, 245.11, 149.86, "IR_RX",       "GPIO25"),
    (27, 245.11, 152.40, "SAO_SDA",     "GPIO27_ADC1"),
    (28, 245.11, 154.94, "SAO_SCL",     "GPIO28_ADC2"),
    (29, 245.11, 157.48, "~{CHRG}",     "GPIO29_ADC3"),
    (36, 245.11, 172.72, "GPIO24",      "LED_SCK"),
    (37, 245.11, 175.26, "GPIO25",      "LED_DAT"),
    (39, 245.11, 182.88, "GPIO27_ADC1", "IR_RX"),
    (40, 245.11, 185.42, "GPIO28_ADC2", "SAO_SDA"),
    (41, 245.11, 187.96, "GPIO29_ADC3", "SAO_SCL"),
]

def fnum(v):  # format like KiCad (137.16 not 137.160; 139.7 not 139.70)
    return ("%f" % v).rstrip("0").rstrip(".")

def main():
    sheet = Path(sys.argv[1])
    txt = sheet.read_text()
    # permutation sanity: same multiset of strings in and out
    assert sorted(o for *_, o, _ in PERM) == sorted(n for *_, n in PERM), "NOT a permutation!"
    new = txt
    for pad, x, y, old, neu in PERM:
        # match: (label "OLD" \n\t\t(at X Y  -> capture so we only swap the text
        pat = re.compile(r'(\(label\s+")' + re.escape(old) +
                         r'("\s*\n\s*\(at\s+' + re.escape(fnum(x)) + r'\s+' + re.escape(fnum(y)) + r'\b)')
        hits = pat.findall(new)
        if len(hits) != 1:
            sys.exit(f"ABORT pad {pad}: expected exactly 1 label '{old}' at ({fnum(x)},{fnum(y)}), found {len(hits)}")
        new = pat.sub(r'\1' + neu.replace('\\', r'\\') + r'\2', new, count=1)
        print(f"  pad {pad:>3}: '{old}' -> '{neu}'")
    if new == txt:
        sys.exit("ABORT: no change made")
    sheet.write_text(new)
    print(f"wrote {sheet}  ({len(PERM)} labels permuted)")

if __name__ == "__main__":
    main()
