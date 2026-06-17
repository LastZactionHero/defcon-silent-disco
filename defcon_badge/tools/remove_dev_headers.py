#!/usr/bin/env python3
"""Surgically remove the two unused DNP debug headers (J32 UART, J33 SWD) and
their now-orphaned net plumbing from the hand-patched schematic sheets, WITHOUT
regenerating (which would churn every symbol UUID and break PCB linkage).

Removes, by top-level S-expression element:
  IO.kicad_sch        : J32 symbol, #PWR_J32, UART_TX/UART_RX labels at J32,
                        the two UART_TX/UART_RX hierarchical_labels, J32 wires.
  MCU_Core.kicad_sch  : J33 symbol, #PWR_J33, the J33-side +3V3/SWD/SWCLK/RUN
                        labels, the two UART hierarchical_labels + their stub
                        labels, wires in the J33 + UART-stub regions, and the
                        now-unused Conn_01x05 / Conn_01x03 lib_symbol defs.
  defcon_badge.kicad_sch (top): the UART_TX/UART_RX (pin ...) entries on both
                        the IO and MCU_Core sheet symbols.

Kept deliberately (become documented single-pin nets — benign ERC warnings):
  MCU-side SWD/SWCLK labels on the RP2040 debug pins, and the GP0/GP1 UART
  labels on the RP2040 — they document the pin function for future test points.

Geometric matching is by proximity to the header anchor, so it is robust to the
exact wire routing the various patch scripts emitted.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/zach/.local/share/kicad-happy/skills/kicad/scripts")
from sexp_parser import parse  # read-only classifier

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")


# ---------------------------------------------------------------- span finding
def top_level_spans(text):
    """Yield (start, end) byte offsets of every depth-1 child element inside the
    root (kicad_sch ...). start points at the child's '(', end just past its ')'."""
    depth = 0
    in_str = False
    i = 0
    n = len(text)
    child_start = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "(":
                depth += 1
                if depth == 2:
                    child_start = i
            elif c == ")":
                if depth == 2:
                    yield (child_start, i + 1)
                depth -= 1
        i += 1


def child_at(text, span):
    return parse(text[span[0]:span[1]])


def tag(node):
    return node[0] if isinstance(node, list) and node and isinstance(node[0], str) else None


def prop(sym, key):
    for c in sym:
        if isinstance(c, list) and c and c[0] == "property" and len(c) > 2 and c[1] == key:
            return c[2]
    return None


def at_of(node):
    for c in node:
        if isinstance(c, list) and c and c[0] == "at":
            return (float(c[1]), float(c[2]))
    return None


def lib_id_of(node):
    for c in node:
        if isinstance(c, list) and c and c[0] == "lib_id":
            return c[1]
    return None


def near(p, q, r):
    return p is not None and q is not None and abs(p[0] - q[0]) <= r and abs(p[1] - q[1]) <= r


def wire_endpoints(node):
    """Return list of (x,y) endpoints for a (wire (pts (xy..)(xy..))) element."""
    pts = []
    for c in node:
        if isinstance(c, list) and c and c[0] == "pts":
            for xy in c[1:]:
                if isinstance(xy, list) and xy and xy[0] == "xy":
                    pts.append((float(xy[1]), float(xy[2])))
    return pts


# ---------------------------------------------------------------- removal core
def remove_spans(text, spans):
    """Delete the given (start,end) child spans, absorbing the leading line
    indentation (back to the preceding newline) and one trailing newline."""
    out = []
    spans = sorted(spans)
    cursor = 0
    for s, e in spans:
        # extend start back over the line's leading tabs/spaces
        ls = s
        while ls > 0 and text[ls - 1] in "\t ":
            ls -= 1
        # absorb one trailing newline
        ee = e
        if ee < len(text) and text[ee] == "\n":
            ee += 1
        out.append(text[cursor:ls])
        cursor = ee
    out.append(text[cursor:])
    return "".join(out)


def report(label, kept_removed):
    for kind, info in kept_removed:
        print(f"   - {kind}: {info}")
    print(f"  {label}: removing {len(kept_removed)} elements")


# ---------------------------------------------------------------- IO sheet
def clean_io():
    path = PROJECT / "IO.kicad_sch"
    text = path.read_text()
    spans = list(top_level_spans(text))
    # locate J32 anchor
    j32_at = None
    for s, e in spans:
        node = child_at(text, (s, e))
        if tag(node) == "symbol" and prop(node, "Reference") == "J32":
            j32_at = at_of(node)
    if j32_at is None:
        print("  IO: J32 not found (already removed?)")
        return
    # Pass 1: collect anchor points of everything we remove (J32 + all UART
    # labels/hier_labels), so we can sweep up every connecting wire/junction.
    anchors = [j32_at]
    for s, e in spans:
        node = child_at(text, (s, e))
        t = tag(node)
        if t in ("label", "hierarchical_label") and len(node) > 1 and node[1] in ("UART_TX", "UART_RX"):
            anchors.append(at_of(node))

    def touches_anchor(p):
        return any(near(p, a, 0.2) for a in anchors)

    remove, log = [], []
    for s, e in spans:
        node = child_at(text, (s, e))
        t = tag(node)
        keep = True
        if t == "symbol":
            ref = prop(node, "Reference")
            if ref == "J32":
                keep = False; log.append(("symbol", "J32"))
            elif ref == "#PWR_J32":
                keep = False; log.append(("symbol", "#PWR_J32 (GND)"))
        elif t == "label" and len(node) > 1 and node[1] in ("UART_TX", "UART_RX"):
            keep = False; log.append(("label", f"{node[1]} @ {at_of(node)}"))
        elif t == "hierarchical_label" and len(node) > 1 and node[1] in ("UART_TX", "UART_RX"):
            keep = False; log.append(("hier_label", f"{node[1]} @ {at_of(node)}"))
        elif t == "wire":
            eps = wire_endpoints(node)
            if any(touches_anchor(p) for p in eps) or any(near(p, j32_at, 12) for p in eps):
                keep = False; log.append(("wire", f"{eps}"))
        elif t == "junction":
            if touches_anchor(at_of(node)):
                keep = False; log.append(("junction", f"@ {at_of(node)}"))
        if not keep:
            remove.append((s, e))
    report("IO.kicad_sch", log)
    path.write_text(remove_spans(text, remove))


# ---------------------------------------------------------------- MCU_Core
def clean_mcu():
    path = PROJECT / "MCU_Core.kicad_sch"
    text = path.read_text()
    spans = list(top_level_spans(text))
    j33_at = None
    for s, e in spans:
        node = child_at(text, (s, e))
        if tag(node) == "symbol" and prop(node, "Reference") == "J33":
            j33_at = at_of(node)
    if j33_at is None:
        print("  MCU_Core: J33 not found (already removed?)")
        return
    # J33-side label cluster lives around x in [318,334], y in [50,70]
    def in_j33_region(p):
        return p is not None and 316 <= p[0] <= 336 and 48 <= p[1] <= 72
    # UART stub region (right edge, created by wire_mcu_hier_labels) around x~391.
    # Tie to the UART hier-label rows ONLY (y≈215.9/223.52) so neighbouring
    # signals' stubs are not swept up.
    def in_uart_stub_region(p):
        return p is not None and 385 <= p[0] <= 400 and (abs(p[1] - 215.9) < 1 or abs(p[1] - 223.52) < 1)

    # Pass 1: anchors = every J33-side / UART-stub point we delete, so wires are
    # removed by precise endpoint match (NOT by a broad y-band that catches the
    # neighbouring hier-label stubs).
    anchors = [(325.12, 52.07)]  # #PWR_J33 pin
    for s, e in spans:
        node = child_at(text, (s, e))
        t = tag(node)
        if t == "label" and in_j33_region(at_of(node)):
            anchors.append(at_of(node))
        elif t == "label" and len(node) > 1 and node[1] in ("UART_TX", "UART_RX") and in_uart_stub_region(at_of(node)):
            anchors.append(at_of(node))
        elif t == "hierarchical_label" and len(node) > 1 and node[1] in ("UART_TX", "UART_RX") and in_uart_stub_region(at_of(node)):
            anchors.append(at_of(node))

    def touches_anchor(p):
        return any(near(p, a, 0.2) for a in anchors)

    remove, log = [], []
    for s, e in spans:
        node = child_at(text, (s, e))
        t = tag(node)
        keep = True
        if t == "symbol":
            ref = prop(node, "Reference")
            if ref == "J33":
                keep = False; log.append(("symbol", "J33"))
            elif ref == "#PWR_J33":
                keep = False; log.append(("symbol", "#PWR_J33 (GND)"))
        elif t == "label":
            p = at_of(node)
            if in_j33_region(p):
                keep = False; log.append(("label", f"{node[1]} @ {p} (J33 side)"))
            elif node[1] in ("UART_TX", "UART_RX") and in_uart_stub_region(p):
                keep = False; log.append(("label", f"{node[1]} @ {p} (UART stub)"))
        elif t == "hierarchical_label" and len(node) > 1 and node[1] in ("UART_TX", "UART_RX") and in_uart_stub_region(at_of(node)):
            keep = False; log.append(("hier_label", f"{node[1]} @ {at_of(node)}"))
        elif t == "wire":
            eps = wire_endpoints(node)
            if any(touches_anchor(p) for p in eps):
                keep = False; log.append(("wire", f"{eps}"))
        elif t == "junction":
            if touches_anchor(at_of(node)):
                keep = False; log.append(("junction", f"@ {at_of(node)}"))
        if not keep:
            remove.append((s, e))
    report("MCU_Core.kicad_sch", log)
    new_text = remove_spans(text, remove)
    # drop now-unused lib_symbol defs Conn_01x05 (J33) and Conn_01x03 (none left)
    new_text = drop_lib_symbol(new_text, "Connector_Generic:Conn_01x05")
    path.write_text(new_text)


def drop_lib_symbol(text, name):
    """Remove a (symbol \"name\" ...) block from the (lib_symbols ...) section."""
    needle = f'(symbol "{name}"'
    idx = text.find(needle)
    if idx < 0:
        return text
    # walk to matching close paren
    depth = 0
    i = idx
    in_str = False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2; continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    i += 1; break
        i += 1
    # back up over leading indentation
    ls = idx
    while ls > 0 and text[ls - 1] in "\t ":
        ls -= 1
    ee = i
    if ee < len(text) and text[ee] == "\n":
        ee += 1
    print(f"  MCU_Core: dropped lib_symbol {name}")
    return text[:ls] + text[ee:]


# ---------------------------------------------------------------- top sheet
def clean_top():
    path = PROJECT / "defcon_badge.kicad_sch"
    text = path.read_text()

    # Pass A: collect the world coords of the UART sheet pins, then sweep the
    # top-level wires/labels/junctions that routed UART between the two sheets.
    spans = list(top_level_spans(text))
    pin_coords = []
    for s, e in spans:
        node = child_at(text, (s, e))
        if tag(node) == "sheet":
            for c in node:
                if isinstance(c, list) and c and c[0] == "pin" and len(c) > 1 and c[1] in ("UART_TX", "UART_RX"):
                    pin_coords.append(at_of(c))

    def at_pin(p):
        return any(near(p, q, 0.2) for q in pin_coords)

    remove, log = [], []
    for s, e in spans:
        node = child_at(text, (s, e))
        t = tag(node)
        if t == "wire" and any(at_pin(p) for p in wire_endpoints(node)):
            remove.append((s, e)); log.append(("wire", f"{wire_endpoints(node)}"))
        elif t in ("label", "global_label") and at_pin(at_of(node)):
            remove.append((s, e)); log.append((t, f"{node[1]} @ {at_of(node)}"))
        elif t == "junction" and at_pin(at_of(node)):
            remove.append((s, e)); log.append(("junction", f"@ {at_of(node)}"))
    if remove:
        report("defcon_badge.kicad_sch (top) wires/labels", log)
        text = remove_spans(text, remove)

    # Pass B: remove the (pin "UART_TX"/"UART_RX" ...) sub-blocks on the sheets.
    removed = 0
    for name in ("UART_TX", "UART_RX"):
        while True:
            needle = f'(pin "{name}"'
            idx = text.find(needle)
            if idx < 0:
                break
            depth = 0
            i = idx
            in_str = False
            while i < len(text):
                c = text[i]
                if in_str:
                    if c == "\\":
                        i += 2; continue
                    if c == '"':
                        in_str = False
                else:
                    if c == '"':
                        in_str = True
                    elif c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            i += 1; break
                i += 1
            ls = idx
            while ls > 0 and text[ls - 1] in "\t ":
                ls -= 1
            ee = i
            if ee < len(text) and text[ee] == "\n":
                ee += 1
            text = text[:ls] + text[ee:]
            removed += 1
    print(f"  defcon_badge.kicad_sch (top): removed {removed} UART sheet pins")
    path.write_text(text)


if __name__ == "__main__":
    print("Removing J32 (UART) + J33 (SWD) debug headers:")
    clean_io()
    clean_mcu()
    clean_top()
    print("done.")
