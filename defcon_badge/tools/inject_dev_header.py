#!/usr/bin/env python3
"""Inject a 5-pin DNP debug header (J33) into MCU_Core.kicad_sch.

Pinout: GND / +3V3 / SWD_DIO / SWD_CLK / RUN — covers SWD flashing + reset.
Uses the kicad_sheet_gen framework to build a self-contained snippet, then
splices it into the existing MCU_Core sheet before its (sheet_instances).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen, snap, new_uuid

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")
MCU_CORE = PROJECT / "MCU_Core.kicad_sch"

# Fixed UUIDs so this can be re-run idempotently.
MCU_CORE_FILE_UUID = "9be08914-1d4d-40f9-ad49-2cd2a26f11f2"
MCU_CORE_SHEET_SYMBOL_UUID = "614c6d9e-c93d-4105-a0eb-565eebb554cc"
TOP_FILE_UUID = "8c0b3d8b-46d3-4173-ab1e-a61765f77d61"


def build_snippet() -> str:
    """Build a SheetGen, place J33 + its connections, render, then extract just
    the new content (skip header / lib_symbols / trailer)."""
    sg = SheetGen(
        name="MCU_Core_snippet",
        title="snippet",
        file_uuid=MCU_CORE_FILE_UUID,
        sheet_symbol_uuid=MCU_CORE_SHEET_SYMBOL_UUID,
        page="3",
    )
    sg.add_stock("Connector_Generic.kicad_sym", "Conn_01x05")
    sg.add_stock("power.kicad_sym", "+3V3")
    sg.add_stock("power.kicad_sym", "GND")

    # Place the 5-pin header up in the empty top-right area of MCU_Core (right
    # column where I already put hier_labels). Use grid-aligned coordinates.
    sg.place(
        "Connector_Generic:Conn_01x05", "J33", "Dev/SWD header",
        "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
        330, 60,
        desc="Debug header — SWD + reset + power (DNP, first bring-up only)",
    )

    # Standard SWD-style ordering (pin 1 closest to corner):
    #   1: GND   2: +3V3   3: SWD_DIO (= SWD)   4: SWD_CLK (= SWCLK)   5: RUN
    # Connect via flat labels matching existing MCU_Core net names so name
    # matching does the cross-net merging.
    sg.power_at_pin("J33", "1", "GND", pwr_ref="#PWR_J33")
    sg.label_at_pin("J33", "2", "+3V3")
    sg.label_at_pin("J33", "3", "SWD")
    sg.label_at_pin("J33", "4", "SWCLK")
    sg.label_at_pin("J33", "5", "RUN")

    rendered = sg.render()

    # Slice the rendered output into (lib_symbols_body, instance_body) parts.
    # rendered structure: header / lib_symbols / instances+wires+labels / sheet_instances trailer.
    lines = rendered.splitlines(keepends=True)
    lib_start_idx = lib_end_idx = None
    in_lib = False
    lib_depth = 0
    for i, ln in enumerate(lines):
        if "(lib_symbols" in ln and lib_start_idx is None:
            lib_start_idx = i
            in_lib = True
            lib_depth = ln.count("(") - ln.count(")")
            continue
        if in_lib:
            lib_depth += ln.count("(") - ln.count(")")
            if lib_depth <= 0:
                lib_end_idx = i + 1
                in_lib = False
                break
    si_idx = next(i for i, ln in enumerate(lines) if "(sheet_instances" in ln)
    # lib_symbols body = lines BETWEEN the opening "(lib_symbols\n" and closing "\t)" — exclusive
    lib_body = "".join(lines[lib_start_idx + 1:lib_end_idx - 1])
    instance_body = "".join(lines[lib_end_idx:si_idx])
    return lib_body, instance_body


def inject(lib_body: str, instance_body: str):
    text = MCU_CORE.read_text()

    # 1. Splice lib_body INTO MCU_Core's existing (lib_symbols ...) block.
    # Skip symbols already present to avoid duplicates.
    import re
    existing_libs = set(re.findall(r'\(symbol "([^"]+:[^"]+)"', text))
    new_blocks = []
    # Walk lib_body and pick out top-level (symbol "Lib:Name" ...) blocks.
    i = 0
    while i < len(lib_body):
        # Find next (symbol "Lib:Name"
        m = re.search(r'\(symbol "([^"]+:[^"]+)"', lib_body[i:])
        if not m:
            break
        block_start_abs = i + m.start()
        name = m.group(1)
        # Find end of this symbol block
        depth = 0
        j = block_start_abs
        in_str = False
        while j < len(lib_body):
            c = lib_body[j]
            if c == '"' and (j == 0 or lib_body[j - 1] != "\\"):
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
            j += 1
        block = lib_body[block_start_abs:j]
        if name not in existing_libs:
            new_blocks.append(block)
        i = j

    lib_injection = ""
    if new_blocks:
        # MCU_Core's lib_symbols entries are at depth 2 (2 tabs). Re-indent.
        for blk in new_blocks:
            lib_injection += "\n".join("\t" + ln if ln.strip() else ln for ln in blk.splitlines()) + "\n"

    if lib_injection:
        # Find the closing of MCU_Core's lib_symbols block — it's the "\t)" that
        # closes the (lib_symbols block opening at line "\t(lib_symbols".
        lib_open = text.find("\t(lib_symbols")
        depth = 0
        k = lib_open
        in_str = False
        while k < len(text):
            c = text[k]
            if c == '"' and (k == 0 or text[k - 1] != "\\"):
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
            k += 1
        # Insert just BEFORE the closing ")"
        text = text[:k] + lib_injection + text[k:]
        print(f"injected {len(new_blocks)} new lib_symbol blocks", file=sys.stderr)

    # 2. Splice instance_body BEFORE (sheet_instances).
    marker_idx = text.find("\t(sheet_instances")
    if marker_idx < 0:
        raise RuntimeError("(sheet_instances not found after lib injection")
    text = text[:marker_idx] + instance_body + text[marker_idx:]
    MCU_CORE.write_text(text)
    print(f"injected {len(instance_body)} bytes of instances before sheet_instances", file=sys.stderr)


def main():
    lib_body, instance_body = build_snippet()
    inject(lib_body, instance_body)


if __name__ == "__main__":
    main()
