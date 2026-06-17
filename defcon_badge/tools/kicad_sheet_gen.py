#!/usr/bin/env python3
"""Reusable KiCad 10 child-sheet generator for the DEFCON badge.

Used by gen_power_sheet.py, gen_audio_sheet.py, gen_leds_ir_sheet.py,
gen_io_sheet.py. Handles stock symbol extraction, custom placeholder symbols,
component instances (with the body_style/in_pos_files/pin uuid fields that
kicad-cli requires), and pin-position-based wire stubs with net labels or
power flags.

Top sheet UUID is fixed to the existing one so child sheets re-attach to the
already-laid-out top sheet without renumbering.
"""
from __future__ import annotations
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

TOP_FILE_UUID = "8c0b3d8b-46d3-4173-ab1e-a61765f77d61"
SYM_ROOT = Path("/usr/share/kicad/symbols")

# Global power rails MUST be emitted as global `power:<name>` symbols, never as a
# sheet-local `(label "<name>")`. A local label is scoped to its sheet and does NOT
# cross the hierarchy, which silently FRAGMENTS the rail. This was the board-dead
# bug: MCU_Core declared +3V3 via power:+3V3 symbols while Power/Audio/IO/LEDs_IR
# used local labels -> +3V3 split into 5 disconnected islands and the LDO output
# reached zero loads. label_at_pin() reroutes any RAIL_NAMES to power_at_pin().
# (Scoped to +3V3 — the rail that was broken; GND already uses power_at_pin and
# VBUS/BAT/+1V1 are unified by their own paths. Add others here if ever fragmented.)
RAIL_NAMES = {"+3V3"}


def new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Stock symbol extraction (one-time per lib lookup)
# ---------------------------------------------------------------------------
_LIB_CACHE: dict[str, str] = {}


def _lib_text(lib_filename: str) -> str:
    if lib_filename not in _LIB_CACHE:
        path = SYM_ROOT / lib_filename
        _LIB_CACHE[lib_filename] = path.read_text()
    return _LIB_CACHE[lib_filename]


def _extract_symbol_block(text: str, sym_name: str) -> str | None:
    m = re.search(rf'^\t\(symbol "{re.escape(sym_name)}"', text, re.MULTILINE)
    if not m:
        return None
    depth, j, in_str = 0, m.start(), False
    while j < len(text):
        c = text[j]
        if c == '"' and (j == 0 or text[j - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[m.start():j + 1]
        j += 1
    return None


def stock_symbol(lib_filename: str, sym_name: str) -> str:
    """Return the (symbol ...) block for a stock symbol, renamed to "Lib:Sym"."""
    text = _lib_text(lib_filename)
    block = _extract_symbol_block(text, sym_name)
    if block is None:
        raise KeyError(f"{sym_name} not found in {lib_filename}")
    lib_prefix = lib_filename.replace(".kicad_sym", "")
    return block.replace(f'(symbol "{sym_name}"', f'(symbol "{lib_prefix}:{sym_name}"', 1)


def stock_pin_positions(lib_filename: str, sym_name: str) -> dict[str, tuple[float, float]]:
    """Return {pin_number: (x, y)} in symbol-local coords for a stock symbol.
    Position is the OUTER endpoint of the pin (where wires attach)."""
    text = _lib_text(lib_filename)
    block = _extract_symbol_block(text, sym_name)
    if block is None:
        return {}
    pins = {}
    for m in re.finditer(
        r"\(pin\s+\w+\s+\w+\s*\n\s*\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+\d+\)\s*\n"
        r"\s*\(length\s+-?\d+\.?\d*\)",
        block,
    ):
        x, y = float(m.group(1)), float(m.group(2))
        rest = block[m.end():m.end() + 500]
        nm = re.search(r'\(number "([^"]+)"', rest)
        if nm:
            pins[nm.group(1)] = (x, y)
    return pins


# ---------------------------------------------------------------------------
# Custom symbol builder — simple rectangle with named pins
# ---------------------------------------------------------------------------
@dataclass
class CustomPin:
    number: str
    name: str
    etype: str  # input | output | bidirectional | passive | power_in | power_out | open_collector | unspecified
    side: str   # 'L' or 'R'


def custom_symbol(
    lib_id: str,
    default_value: str,
    footprint: str,
    pins: list[CustomPin],
    description: str = "",
    pin_length: float = 2.54,
    body_width: float = 7.62,
) -> tuple[str, dict[str, tuple[float, float]]]:
    """Returns (symbol-block string, {pin_num: (x, y)} pin-position dict)."""
    half_w = body_width / 2
    left = [p for p in pins if p.side == "L"]
    right = [p for p in pins if p.side == "R"]
    rows = max(len(left), len(right), 1)
    height = max(2.54 * (rows + 1), 5.08)
    half_h = height / 2

    def pin_y(slot: int, total: int) -> float:
        if total <= 1:
            return 0.0
        y_top = half_h - 2.54
        step = (2 * y_top) / (total - 1)
        # Snap to the 1.27mm pin grid. With even L/R counts the result is already
        # on-grid (no-op), but when the two sides differ (e.g. the TP4056 9-pin
        # ESOP: 5 left / 4 right) the shorter side is otherwise distributed over the
        # taller body to off-grid Y, and the label stubs snap OFF the pin -> opens.
        return round((y_top - step * slot) / 1.27) * 1.27

    pin_lines: list[str] = []
    pin_positions: dict[str, tuple[float, float]] = {}
    for slot, p in enumerate(left):
        y = pin_y(slot, len(left))
        px = -half_w - pin_length
        pin_positions[p.number] = (px, y)
        pin_lines.append(
            f"\t\t\t(pin {p.etype} line\n"
            f"\t\t\t\t(at {px:.2f} {y:.2f} 180)\n"
            f"\t\t\t\t(length {pin_length})\n"
            f'\t\t\t\t(name "{p.name}" (effects (font (size 1.27 1.27))))\n'
            f'\t\t\t\t(number "{p.number}" (effects (font (size 1.27 1.27))))\n'
            f"\t\t\t)"
        )
    for slot, p in enumerate(right):
        y = pin_y(slot, len(right))
        px = half_w + pin_length
        pin_positions[p.number] = (px, y)
        pin_lines.append(
            f"\t\t\t(pin {p.etype} line\n"
            f"\t\t\t\t(at {px:.2f} {y:.2f} 0)\n"
            f"\t\t\t\t(length {pin_length})\n"
            f'\t\t\t\t(name "{p.name}" (effects (font (size 1.27 1.27))))\n'
            f'\t\t\t\t(number "{p.number}" (effects (font (size 1.27 1.27))))\n'
            f"\t\t\t)"
        )
    pin_block = "\n".join(pin_lines)
    bare = lib_id.split(":", 1)[1] if ":" in lib_id else lib_id

    sym = f"""	(symbol "{lib_id}"
		(pin_names (offset 0.508))
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
		(property "Reference" "U" (at 0 {half_h + 2.54:.2f} 0)
			(effects (font (size 1.27 1.27))))
		(property "Value" "{default_value}" (at 0 {-half_h - 2.54:.2f} 0)
			(effects (font (size 1.27 1.27))))
		(property "Footprint" "{footprint}" (at 0 0 0)
			(show_name no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "" (at 0 0 0)
			(show_name no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Description" "{description}" (at 0 0 0)
			(show_name no) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "{bare}_0_1"
			(rectangle
				(start {-half_w:.2f} {-half_h:.2f}) (end {half_w:.2f} {half_h:.2f})
				(stroke (width 0.254) (type default))
				(fill (type background))
			)
		)
		(symbol "{bare}_1_1"
{pin_block}
		)
		(embedded_fonts no)
	)"""
    return sym, pin_positions


# ---------------------------------------------------------------------------
# Pin position math
# ---------------------------------------------------------------------------
def rotated(point: tuple[float, float], deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    x, y = point
    rx = x * math.cos(rad) - y * math.sin(rad)
    ry = x * math.sin(rad) + y * math.cos(rad)
    return (rx, ry)


def pin_abs(inst_x: float, inst_y: float, inst_rot: float, sym_pin: tuple[float, float]) -> tuple[float, float]:
    # Symbol coords are math-standard (Y up); schematic coords are display (Y down).
    # Apply rotation in math coords first, then flip Y, then translate.
    rx, ry = rotated(sym_pin, inst_rot)
    return (inst_x + rx, inst_y - ry)


GRID = 1.27  # KiCad fine grid in mm


def snap(v: float, grid: float = GRID) -> float:
    return round(v / grid) * grid


# Known LCSC numbers for common (value, footprint) passive combos.
# Used by SheetGen.fill_passive_mpns() to lift MPN coverage above the 50% pre-fab gate.
PASSIVE_LCSC: dict[tuple[str, str], tuple[str, str]] = {
    # (value, footprint) -> (mpn, lcsc)
    # Resistors 0402 1% (Uniroyal / Yageo equivalents)
    ("100k", "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-07100KL", "C25741"),
    ("47k",  "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-0747KL",  "C25819"),
    ("10k",  "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-0710KL",  "C25744"),
    ("5.1k", "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-075K1L",  "C23186"),
    ("4.7k", "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-074K7L",  "C25900"),
    ("2.4k", "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-072K4L",  "C25789"),
    ("1k",   "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-071KL",   "C11702"),
    ("68",   "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-0768RL",  "C22785"),
    ("27",   "Resistor_SMD:R_0402_1005Metric"): ("RC0402FR-0727RL",  "C25092"),
    # Caps 0402 X7R
    ("100n", "Capacitor_SMD:C_0402_1005Metric"): ("CL05B104KO5NNNC", "C1525"),
    ("10n",  "Capacitor_SMD:C_0402_1005Metric"): ("CL05B103KB5NNNC", "C57112"),
    ("1u",   "Capacitor_SMD:C_0402_1005Metric"): ("CL05A105KP5NNNC", "C52923"),
    ("15p",  "Capacitor_SMD:C_0402_1005Metric"): ("CL05C150JB5NNNC", "C1626"),
    # Caps 0603 / 0805
    ("10u",  "Capacitor_SMD:C_0603_1608Metric"): ("CL10A106KP8NNNC", "C19702"),
    ("10u",  "Capacitor_SMD:C_0805_2012Metric"): ("CL21A106KAYNNNE", "C15850"),
}


# ---------------------------------------------------------------------------
# Sheet builder
# ---------------------------------------------------------------------------
@dataclass
class Instance:
    lib_id: str
    ref: str
    value: str
    footprint: str
    x: float
    y: float
    rot: float = 0
    desc: str = ""
    mpn: str | None = None
    lcsc: str | None = None
    hide_value: bool = False
    dnp: bool = False
    uuid: str = field(default_factory=new_uuid)


@dataclass
class SheetGen:
    name: str
    title: str
    file_uuid: str
    sheet_symbol_uuid: str
    page: str
    parent_file_uuid: str = TOP_FILE_UUID
    paper: str = "A3"
    company: str = ""
    rev: str = "v0.1"
    date: str = "2026-06-13"
    comments: list[str] = field(default_factory=list)

    instances: list[Instance] = field(default_factory=list)
    pin_positions: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)
    """{lib_id: {pin_num: (x_local, y_local)}}"""
    wires: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    junctions: list[tuple[float, float]] = field(default_factory=list)
    labels: list[tuple[str, float, float, float]] = field(default_factory=list)
    """(name, x, y, rot)"""
    hier_labels: list[tuple[str, float, float, float, str]] = field(default_factory=list)
    global_labels: list[tuple[str, float, float, float, str]] = field(default_factory=list)
    """(name, x, y, rot, shape)"""
    text_notes: list[tuple[str, float, float, float]] = field(default_factory=list)
    """(text, x, y, font_size)"""
    no_connects: list[tuple[float, float]] = field(default_factory=list)

    custom_symbols: list[str] = field(default_factory=list)
    stock_symbol_refs: list[tuple[str, str]] = field(default_factory=list)
    """(lib_filename, sym_name)"""

    def add_stock(self, lib_filename: str, sym_name: str):
        full = f"{lib_filename.replace('.kicad_sym', '')}:{sym_name}"
        if (lib_filename, sym_name) not in self.stock_symbol_refs:
            self.stock_symbol_refs.append((lib_filename, sym_name))
            self.pin_positions[full] = stock_pin_positions(lib_filename, sym_name)

    def add_custom(self, lib_id: str, default_value: str, footprint: str,
                   pins: list[CustomPin], description: str = ""):
        sym, pos = custom_symbol(lib_id, default_value, footprint, pins, description)
        self.custom_symbols.append(sym)
        self.pin_positions[lib_id] = pos

    def place(self, lib_id: str, ref: str, value: str, footprint: str,
              x: float, y: float, rot: float = 0, **kwargs) -> Instance:
        if lib_id not in self.pin_positions:
            raise ValueError(f"Symbol {lib_id} not registered. Call add_stock/add_custom first.")
        # Auto-fill MPN/LCSC from PASSIVE_LCSC if caller didn't supply one.
        if "mpn" not in kwargs and "lcsc" not in kwargs:
            hit = PASSIVE_LCSC.get((value, footprint))
            if hit:
                kwargs["mpn"], kwargs["lcsc"] = hit
        inst = Instance(lib_id=lib_id, ref=ref, value=value, footprint=footprint,
                        x=snap(x), y=snap(y), rot=rot, **kwargs)
        self.instances.append(inst)
        return inst

    def _pin_abs(self, ref: str, pin_num: str) -> tuple[float, float]:
        inst = next(i for i in self.instances if i.ref == ref)
        sym_pin = self.pin_positions[inst.lib_id][pin_num]
        return pin_abs(inst.x, inst.y, inst.rot, sym_pin)

    def wire(self, p1: tuple[float, float], p2: tuple[float, float]):
        self.wires.append((p1, p2))

    def wire_pins(self, ref1: str, pin1: str, ref2: str, pin2: str):
        """Draw a direct wire between two component pins. If they're not on the
        same X or Y axis, emits an L-shaped 2-segment wire (horizontal first)."""
        p1 = self._pin_abs(ref1, pin1)
        p2 = self._pin_abs(ref2, pin2)
        p1 = (snap(p1[0]), snap(p1[1]))
        p2 = (snap(p2[0]), snap(p2[1]))
        if abs(p1[0] - p2[0]) < 0.01 or abs(p1[1] - p2[1]) < 0.01:
            self.wires.append((p1, p2))
        else:
            elbow = (p2[0], p1[1])
            self.wires.append((p1, elbow))
            self.wires.append((elbow, p2))

    def label_at_pin(self, ref: str, pin_num: str, label: str,
                     stub: float = 2.54, dir_override: str | None = None,
                     label_rot: float = 0):
        """Emit a stub wire from a pin to a labeled endpoint."""
        if label in RAIL_NAMES:
            # Global power rail: emit a power:<name> symbol (crosses the hierarchy),
            # NOT a sheet-local label (which would fragment the rail).
            self._rail_seq = getattr(self, "_rail_seq", 0) + 1
            return self.power_at_pin(ref, pin_num, label,
                                     pwr_ref=f"#PWR_RAIL{self._rail_seq}",
                                     stub=stub, dir_override=dir_override)
        px, py = self._pin_abs(ref, pin_num)
        px, py = snap(px), snap(py)
        inst = next(i for i in self.instances if i.ref == ref)
        dx = px - inst.x
        dy = py - inst.y
        if dir_override:
            sx, sy = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[dir_override]
        else:
            if abs(dx) > abs(dy):
                sx, sy = (1 if dx > 0 else -1), 0
            elif abs(dy) > 0:
                sx, sy = 0, (1 if dy > 0 else -1)
            else:
                sx, sy = 0, 1
        end = (snap(px + sx * stub), snap(py + sy * stub))
        if stub > 0:
            self.wires.append(((px, py), end))
        self.labels.append((label, end[0], end[1], label_rot))

    def global_label_at_pin(self, ref: str, pin_num: str, name: str,
                            shape: str = "bidirectional", stub: float = 2.54,
                            dir_override: str | None = None):
        """Emit a stub from a pin to a GLOBAL label. Global labels connect across
        the whole hierarchy by name WITHOUT needing top-sheet sheet-pins/wires —
        used for the microSD card-detect (SD_CD) signal between IO and MCU_Core."""
        px, py = self._pin_abs(ref, pin_num)
        px, py = snap(px), snap(py)
        inst = next(i for i in self.instances if i.ref == ref)
        dx, dy = px - inst.x, py - inst.y
        if dir_override:
            sx, sy = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[dir_override]
        elif abs(dx) > abs(dy):
            sx, sy = (1 if dx > 0 else -1), 0
        elif abs(dy) > 0:
            sx, sy = 0, (1 if dy > 0 else -1)
        else:
            sx, sy = 0, 1
        end = (snap(px + sx * stub), snap(py + sy * stub))
        if stub > 0:
            self.wires.append(((px, py), end))
        self.global_labels.append((name, end[0], end[1], 0, shape))

    def power_at_pin(self, ref: str, pin_num: str, power_name: str,
                     pwr_ref: str, stub: float = 2.54, dir_override: str | None = None):
        """Emit a stub wire from a pin to a power flag symbol (e.g. GND, +3V3, VBUS).
        Adds the power symbol as an Instance."""
        lib_id = f"power:{power_name}"
        if lib_id not in self.pin_positions:
            self.add_stock("power.kicad_sym", power_name)
        px, py = self._pin_abs(ref, pin_num)
        px, py = snap(px), snap(py)
        inst = next(i for i in self.instances if i.ref == ref)
        dx = px - inst.x
        dy = py - inst.y
        if dir_override:
            sx, sy = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[dir_override]
        else:
            if abs(dx) > abs(dy):
                sx, sy = (1 if dx > 0 else -1), 0
            elif abs(dy) > 0:
                sx, sy = 0, (1 if dy > 0 else -1)
            else:
                sx, sy = 0, 1
        end = (snap(px + sx * stub), snap(py + sy * stub))
        if stub > 0:
            self.wires.append(((px, py), end))
        # Place power symbol at endpoint. Rotation: GND points down naturally; +3V3 / VBUS up.
        # For a power symbol whose pin sym-local is at (0,0), the symbol drawing extends in
        # one direction (e.g. GND symbol extends downward). We want the symbol to point AWAY
        # from the wire/component, so:
        #   - if stub goes DOWN (sy=1), place GND with rot=0 → symbol below pin ✓
        #   - if stub goes UP (sy=-1), place +3V3 with rot=0 → symbol above pin ✓
        # GND placed with rot=180 would put the GND symbol ABOVE the pin (flipped).
        # For simplicity always rot=0; KiCad handles symbol orientation per-symbol.
        # But if stub_dir is UP and we use GND, we should flip → rot=180.
        rot = 0
        if power_name == "GND" and sy < 0:
            rot = 180  # flip so GND points up
        elif power_name in ("+3V3", "VBUS") and sy > 0:
            rot = 180  # flip so rail points down
        self.instances.append(Instance(
            lib_id=lib_id, ref=pwr_ref, value=power_name,
            footprint="", x=end[0], y=end[1], rot=rot, hide_value=True,
        ))

    def add_hier(self, name: str, x: float, y: float, shape: str = "bidirectional",
                 rot: float = 0, stub: float = 2.54):
        """Add a hierarchical_label. By default also emits a short wire stub +
        matching flat-label at the stub end so the hier_label sits on a wire
        endpoint (eliminates 'label_dangling' ERC warnings) and merges by name
        with the labeled nets inside the sheet."""
        x, y = snap(x), snap(y)
        self.hier_labels.append((name, x, y, rot, shape))
        if stub > 0:
            # rot: 0 = label text points right (pin extends right from anchor),
            # 180 = points left. Stub goes OUTWARD from the anchor in the same
            # direction the label text points.
            dx, dy = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}.get(int(rot), (1, 0))
            end = (snap(x + dx * stub), snap(y + dy * stub))
            self.wires.append(((x, y), end))
            self.labels.append((name, end[0], end[1], 0))

    def nc_at_pin(self, ref: str, pin_num: str):
        """Mark a pin as intentionally unconnected with a no_connect marker."""
        px, py = self._pin_abs(ref, pin_num)
        self.no_connects.append((snap(px), snap(py)))

    def add_text(self, text: str, x: float, y: float, size: float = 1.27):
        self.text_notes.append((text, x, y, size))

    # ----- rendering -----
    @property
    def instance_path(self) -> str:
        return f"/{self.parent_file_uuid}/{self.sheet_symbol_uuid}"

    def render(self) -> str:
        parts: list[str] = []
        parts.append(self._render_header())
        parts.append(self._render_lib_symbols())
        for t in self.text_notes:
            parts.append(self._render_text(*t))
        for inst in self.instances:
            parts.append(self._render_instance(inst))
        for w in self.wires:
            parts.append(self._render_wire(*w))
        for j in self.junctions:
            parts.append(self._render_junction(*j))
        for nc in self.no_connects:
            parts.append(self._render_nc(*nc))
        for l in self.labels:
            parts.append(self._render_label(*l))
        for h in self.hier_labels:
            parts.append(self._render_hier(*h))
        for g in self.global_labels:
            parts.append(self._render_global(*g))
        parts.append(self._render_trailer())
        return "\n".join(parts) + "\n"

    def _render_header(self) -> str:
        comments = "\n".join(f'\t\t(comment {i + 1} "{c}")' for i, c in enumerate(self.comments))
        return f"""(kicad_sch
\t(version 20260306)
\t(generator "eeschema")
\t(generator_version "10.0")
\t(uuid "{self.file_uuid}")
\t(paper "{self.paper}")
\t(title_block
\t\t(title "{self.title}")
\t\t(date "{self.date}")
\t\t(rev "{self.rev}")
\t\t(company "{self.company}")
{comments}
\t)"""

    def _render_lib_symbols(self) -> str:
        blocks: list[str] = []
        for lib_filename, sym_name in self.stock_symbol_refs:
            blocks.append(stock_symbol(lib_filename, sym_name))
        for sym in self.custom_symbols:
            blocks.append(sym)
        if not blocks:
            return "\t(lib_symbols)"
        # Each block is at depth 1; nest under lib_symbols (depth 1 too, but content at 2).
        # The stock symbols come from /usr/share with 1-tab leading; re-indent by one tab.
        reindented: list[str] = []
        for b in blocks:
            reindented.append("\n".join("\t" + ln if ln.strip() else ln for ln in b.splitlines()))
        body = "\n".join(reindented)
        return f"\t(lib_symbols\n{body}\n\t)"

    def _render_instance(self, inst: Instance) -> str:
        pin_nums = list(self.pin_positions[inst.lib_id].keys())
        pin_lines = "\n".join(
            f'\t\t(pin "{n}" (uuid "{new_uuid()}"))' for n in pin_nums
        )
        hide = " (hide yes)" if inst.hide_value else ""
        # Power flag symbols don't need value visible
        props = [
            f'\t\t(property "Reference" "{inst.ref}" (at {inst.x:.2f} {inst.y - 7.62:.2f} 0)'
            f' (effects (font (size 1.27 1.27))))',
            f'\t\t(property "Value" "{inst.value}" (at {inst.x:.2f} {inst.y + 7.62:.2f} 0)'
            f' (effects (font (size 1.27 1.27)){hide}))',
            f'\t\t(property "Footprint" "{inst.footprint}" (at {inst.x:.2f} {inst.y:.2f} 0)'
            f' (show_name no) (hide yes) (effects (font (size 1.27 1.27))))',
            f'\t\t(property "Datasheet" "" (at {inst.x:.2f} {inst.y:.2f} 0)'
            f' (show_name no) (hide yes) (effects (font (size 1.27 1.27))))',
            f'\t\t(property "Description" "{inst.desc}" (at {inst.x:.2f} {inst.y:.2f} 0)'
            f' (show_name no) (hide yes) (effects (font (size 1.27 1.27))))',
        ]
        if inst.mpn:
            props.append(
                f'\t\t(property "MPN" "{inst.mpn}" (at {inst.x:.2f} {inst.y:.2f} 0)'
                f' (show_name no) (hide yes) (effects (font (size 1.27 1.27))))'
            )
        if inst.lcsc:
            props.append(
                f'\t\t(property "LCSC" "{inst.lcsc}" (at {inst.x:.2f} {inst.y:.2f} 0)'
                f' (show_name no) (hide yes) (effects (font (size 1.27 1.27))))'
            )
        dnp_str = "yes" if inst.dnp else "no"
        return f"""	(symbol
		(lib_id "{inst.lib_id}")
		(at {inst.x:.2f} {inst.y:.2f} {inst.rot:g})
		(unit 1)
		(body_style 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(dnp {dnp_str})
		(fields_autoplaced yes)
		(uuid "{inst.uuid}")
{chr(10).join(props)}
{pin_lines}
		(instances
			(project "defcon_badge"
				(path "{self.instance_path}"
					(reference "{inst.ref}")
					(unit 1)
				)
			)
		)
	)"""

    def _render_wire(self, p1, p2) -> str:
        return (f"\t(wire (pts (xy {p1[0]:.2f} {p1[1]:.2f}) (xy {p2[0]:.2f} {p2[1]:.2f}))"
                f" (stroke (width 0) (type default)) (uuid \"{new_uuid()}\"))")

    def _render_junction(self, x, y) -> str:
        return f'\t(junction (at {x:.2f} {y:.2f}) (diameter 0) (color 0 0 0 0) (uuid "{new_uuid()}"))'

    def _render_nc(self, x, y) -> str:
        return f'\t(no_connect (at {x:.2f} {y:.2f}) (uuid "{new_uuid()}"))'

    def _render_label(self, name, x, y, rot) -> str:
        return (f'\t(label "{name}" (at {x:.2f} {y:.2f} {rot:g})'
                f' (effects (font (size 1.27 1.27)) (justify left bottom))'
                f' (uuid "{new_uuid()}"))')

    def _render_hier(self, name, x, y, rot, shape) -> str:
        return (f'\t(hierarchical_label "{name}" (shape {shape}) (at {x:.2f} {y:.2f} {rot:g})'
                f' (effects (font (size 1.524 1.524)) (justify left))'
                f' (uuid "{new_uuid()}"))')

    def _render_global(self, name, x, y, rot, shape) -> str:
        return (f'\t(global_label "{name}" (shape {shape}) (at {x:.2f} {y:.2f} {rot:g})'
                f' (effects (font (size 1.27 1.27)) (justify left))'
                f' (uuid "{new_uuid()}"))')

    def _render_text(self, text, x, y, size) -> str:
        return (f'\t(text "{text}" (exclude_from_sim no) (at {x:.2f} {y:.2f} 0)'
                f' (effects (font (size {size:g} {size:g})) (justify left top))'
                f' (uuid "{new_uuid()}"))')

    def _render_trailer(self) -> str:
        return f"""	(sheet_instances
		(path "{self.instance_path}"
			(page "{self.page}")
		)
	)
	(embedded_fonts no)
)"""
