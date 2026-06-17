#!/usr/bin/env python3
"""Inject the RUN 10k pull-up (R6) into MCU_Core.kicad_sch.

badge_hw_design.md + the RP2040 hardware design guide spec a 10k pull-up from RUN
to +3V3 (the RP2040 internal pull-up alone is weak; the external one improves reset
noise immunity). MCU_Core has no generator — it is maintained by patch scripts — so
add R6 the same way inject_dev_header.py adds J33: build a kicad_sheet_gen snippet
and splice it into the existing sheet before (sheet_instances).

RUN once (it appends an instance; re-running would duplicate R6).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen
import inject_dev_header as idh   # reuse inject() + the fixed MCU_Core UUIDs

MCU_CORE = Path("/home/zach/dev/defcon_badge/defcon_badge/MCU_Core.kicad_sch")


def build_snippet():
    sg = SheetGen(name="MCU_passives", title="snippet",
                  file_uuid=idh.MCU_CORE_FILE_UUID,
                  sheet_symbol_uuid=idh.MCU_CORE_SHEET_SYMBOL_UUID, page="3")
    sg.add_stock("Device.kicad_sym", "R")
    sg.add_stock("power.kicad_sym", "+3V3")
    # R6 = 10k RUN pull-up. Place in the free top-right column just below J33 (330,60).
    sg.place("Device:R", "R6", "10k", "Resistor_SMD:R_0402_1005Metric", 330, 88,
             mpn="", lcsc="", desc="RUN pull-up to +3V3 (RP2040 reset noise immunity)")
    sg.label_at_pin("R6", "1", "+3V3")   # -> global power:+3V3 (via RAIL_NAMES)
    sg.label_at_pin("R6", "2", "RUN")    # merges with U3.26 RUN net by name

    # Slice the rendered snippet into (lib_symbols body, instance body) — same logic
    # as inject_dev_header.build_snippet.
    lines = sg.render().splitlines(keepends=True)
    lib_start = lib_end = None
    depth = 0
    in_lib = False
    for i, ln in enumerate(lines):
        if "(lib_symbols" in ln and lib_start is None:
            lib_start = i; in_lib = True; depth = ln.count("(") - ln.count(")"); continue
        if in_lib:
            depth += ln.count("(") - ln.count(")")
            if depth <= 0:
                lib_end = i + 1; in_lib = False; break
    si_idx = next(i for i, ln in enumerate(lines) if "(sheet_instances" in ln)
    lib_body = "".join(lines[lib_start + 1:lib_end - 1])
    instance_body = "".join(lines[lib_end:si_idx])
    return lib_body, instance_body


def main():
    # R6 only needs Device:R + power:+3V3 lib symbols, both already present in
    # MCU_Core, so no lib_symbols injection is needed. MCU_Core has no
    # (sheet_instances) block — it ends with the root close — so splice the
    # instance body in just before that final ")".
    _lib, instance_body = build_snippet()
    text = MCU_CORE.read_text().rstrip()
    if not text.endswith(")"):
        raise RuntimeError("MCU_Core does not end with a root close ')'")
    text = text[:-1].rstrip() + "\n" + instance_body.rstrip() + "\n)\n"
    MCU_CORE.write_text(text)
    print(f"injected R6 (RUN 10k pull-up) into {MCU_CORE.name}")


if __name__ == "__main__":
    main()
