#!/usr/bin/env python3
"""Generate badge.kicad_sym — shared lib with all custom placeholder symbols.

Pulls the CustomPin definitions from each sheet generator and emits a single
.kicad_sym so the project's sym-lib-table can register them.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import custom_symbol, CustomPin


SYMBOLS: list[tuple[str, str, str, list[CustomPin], str]] = [
    # (lib_id, default_value, footprint, pins, description)
    ("badge:TP4056", "TP4056",
     "Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.3x2.3mm_ThermalVias",
     [
         CustomPin("1", "TEMP",     "input",          "L"),
         CustomPin("2", "PROG",     "output",         "L"),
         CustomPin("3", "GND",      "power_in",       "L"),
         CustomPin("4", "VCC",      "power_in",       "L"),
         CustomPin("5", "BAT",      "power_out",      "R"),
         CustomPin("6", "~{STDBY}", "open_collector", "R"),
         CustomPin("7", "~{CHRG}",  "open_collector", "R"),
         CustomPin("8", "CE",       "input",          "R"),
         CustomPin("9", "EP",       "power_in",       "L"),  # exposed thermal pad -> GND (ESOP-8)
     ],
     "1A Li-Ion linear charger, ESOP-8 (LCSC C16581)"),

    ("badge:ME6211C33M5G", "ME6211C33M5G",
     "Package_TO_SOT_SMD:SOT-23-5",
     [
         CustomPin("1", "VIN",  "power_in",   "L"),
         CustomPin("3", "EN",   "input",      "L"),
         CustomPin("2", "GND",  "power_in",   "L"),
         CustomPin("5", "VOUT", "power_out",  "R"),
         CustomPin("4", "NC",   "no_connect", "R"),
     ],
     "500 mA 3.3V LDO (LCSC C82942)"),

    ("badge:TM8211", "TM8211",
     "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     [
         # PT8211 datasheet pinout (TM8211 = pin-compatible clone), datasheet-verified.
         CustomPin("1", "BCK",  "input",     "L"),
         CustomPin("2", "WS",   "input",     "L"),
         CustomPin("3", "DIN",  "input",     "L"),
         CustomPin("4", "GND",  "power_in",  "L"),
         CustomPin("5", "VDD",  "power_in",  "R"),
         CustomPin("6", "LCH",  "output",    "R"),
         CustomPin("7", "NC",   "no_connect","R"),
         CustomPin("8", "RCH",  "output",    "R"),
     ],
     "Stereo 16-bit DAC, LSBJ I2S (PT8211 clone)"),

    ("badge:TDA1308", "TDA1308",
     "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
     [
         CustomPin("8", "VCC",  "power_in",  "R"),
         CustomPin("7", "OUT2", "output",    "R"),
         CustomPin("6", "IN2-", "input",     "R"),
         CustomPin("5", "IN2+", "input",     "R"),
         CustomPin("1", "OUT1", "output",    "L"),
         CustomPin("2", "IN1-", "input",     "L"),
         CustomPin("3", "IN1+", "input",     "L"),
         CustomPin("4", "VEE",  "power_in",  "L"),
     ],
     "Dual headphone opamp, rail-to-rail"),

    ("badge:PJ-320A", "PJ-320A",
     "Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles",
     [
         CustomPin("T",  "TIP",    "passive",    "R"),
         CustomPin("R",  "RING",   "passive",    "R"),
         CustomPin("S",  "SLEEVE", "passive",    "R"),
         CustomPin("R2", "RING2",  "no_connect", "L"),
         CustomPin("D",  "DETECT", "no_connect", "L"),
     ],
     "3.5mm TRRS jack, used as TRS stereo (sleeve = GND)"),

    # NOTE: footprint must be a 6-pad 5050 SK9822/APA102 land pattern. KiCad has no stock
    # addressable-5050 footprint (LED_RGB_5050-6 is a plain R/G/B part) — create
    # badge:LED_SK9822_5050 from the SK9822 datasheet land pattern in the PCB phase.
    ("badge:SK9822", "SK9822",
     "badge:LED_SK9822_5050",
     [
         # SK9822 5050 datasheet pinout (verified: Adafruit/Pololu/Normand SK9822 datasheets):
         # 1=SDI(DIN) 2=CKI(CIN) 3=GND 4=VDD 5=CKO(COUT) 6=SDO(DOUT). Slot order keeps the
         # chain wires straight: DIN/DOUT aligned (top), CIN/COUT aligned (mid).
         CustomPin("1", "DIN",  "input",      "L"),
         CustomPin("2", "CIN",  "input",      "L"),
         CustomPin("3", "GND",  "power_in",   "L"),
         CustomPin("6", "DOUT", "output",     "R"),
         CustomPin("5", "COUT", "output",     "R"),
         CustomPin("4", "VDD",  "power_in",   "R"),
     ],
     "SK9822 (APA102 clone) 5050 addressable RGB LED, 2-wire SPI clock+data"),

    ("badge:TSOP4838", "TSOP4838",
     "OptoDevice:Vishay_MINICAST-3Pin",
     [
         CustomPin("1", "OUT", "open_collector", "R"),
         CustomPin("2", "GND", "power_in",       "L"),
         CustomPin("3", "VS",  "power_in",       "L"),
     ],
     "38 kHz demodulating IR receiver (TSOP4838 family)"),
]


def to_lib_block(sym: str) -> str:
    """Strip lib prefix on top-level symbol since kicad_sym uses bare names."""
    return sym.replace('(symbol "badge:', '(symbol "', 1)


HEADER = """(kicad_symbol_lib
\t(version 20251024)
\t(generator "kicad_sheet_gen")
\t(generator_version "10.0")
"""


def main():
    parts: list[str] = [HEADER]
    for lib_id, val, fp, pins, desc in SYMBOLS:
        sym, _ = custom_symbol(lib_id, val, fp, pins, desc)
        parts.append(to_lib_block(sym))
    parts.append(")\n")
    out = Path(__file__).parent.parent / "badge.kicad_sym"
    out.write_text("\n".join(parts))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
