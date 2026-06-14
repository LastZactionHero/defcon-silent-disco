#!/usr/bin/env python3
"""Extract specific stock KiCad symbol definitions into a self-contained
lib_symbols block formatted for inclusion in a .kicad_sch file."""
import sys
import re
from pathlib import Path

WANT = {
    "Connector.kicad_sym": ["USB_C_Receptacle_USB2.0_16P"],
    "Connector_Generic.kicad_sym": ["Conn_01x02"],
    "Switch.kicad_sym": ["SW_SPDT"],
    "Device.kicad_sym": ["R", "C"],
    "power.kicad_sym": ["+3V3", "GND", "VBUS", "PWR_FLAG"],
}
SYM_ROOT = Path("/usr/share/kicad/symbols")


def read_symbol_block(path: Path, name: str) -> str | None:
    text = path.read_text()
    pat = re.compile(rf'^\t\(symbol "{re.escape(name)}"', re.MULTILINE)
    m = pat.search(text)
    if not m:
        return None
    # Find the matching close paren by depth counting from m.start().
    depth = 0
    i = m.start()
    in_str = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[m.start():i + 1]
        i += 1
    return None


def rename_lib_id(block: str, lib_prefix: str, name: str) -> str:
    # Stock lib symbol just uses the name e.g. (symbol "R" ...) — when embedded
    # into a project schematic's lib_symbols block, KiCad expects the form
    # (symbol "LibName:SymName" ...) to match the lib_id used by instances.
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib_prefix}:{name}"', 1)


def main():
    out = []
    for fname, syms in WANT.items():
        path = SYM_ROOT / fname
        if not path.exists():
            print(f"# MISSING: {path}", file=sys.stderr)
            continue
        lib_prefix = fname.replace(".kicad_sym", "")
        for sym in syms:
            block = read_symbol_block(path, sym)
            if block is None:
                print(f"# NOT FOUND: {sym} in {fname}", file=sys.stderr)
                continue
            block = rename_lib_id(block, lib_prefix, sym)
            out.append(block)
    print("\n".join(out))


if __name__ == "__main__":
    main()
