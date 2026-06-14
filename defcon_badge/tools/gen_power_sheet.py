#!/usr/bin/env python3
"""Generate Power.kicad_sch — USB-C → TP4056 → LiPo → SS-12D00 → ME6211C33 → 3V3."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen, CustomPin


def build() -> SheetGen:
    sg = SheetGen(
        name="Power",
        title="DEFCON Silent Disco Badge — Power",
        file_uuid="b1089c49-e1d7-47eb-8d99-ef5080afbd67",
        sheet_symbol_uuid="5744f316-b81d-4687-a6bb-e0b6cbd3f68c",
        page="2",
        paper="A3",
        comments=[
            "USB-C → TP4056 → LiPo (JST-PH) → SS-12D00 → ME6211C33 → +3V3 rail",
            "VBAT divider 100k/100k → VBAT_SENSE; TP4056 CHRG̅ → 100k → +3V3 → ~CHRG to MCU GP18",
        ],
    )

    # ----- lib_symbols: stock -----
    for lib, sym in [
        ("Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P"),
        ("Connector_Generic.kicad_sym", "Conn_01x02"),
        ("Switch.kicad_sym", "SW_SPDT"),
        ("Device.kicad_sym", "R"),
        ("Device.kicad_sym", "C"),
        ("power.kicad_sym", "+3V3"),
        ("power.kicad_sym", "GND"),
        ("power.kicad_sym", "VBUS"),
        ("power.kicad_sym", "PWR_FLAG"),
    ]:
        sg.add_stock(lib, sym)

    # ----- lib_symbols: custom -----
    sg.add_custom(
        "badge:TP4056", "TP4056",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        [
            CustomPin("1", "TEMP",     "input",          "L"),
            CustomPin("2", "PROG",     "output",         "L"),
            CustomPin("3", "GND",      "power_in",       "L"),
            CustomPin("4", "VCC",      "power_in",       "L"),
            CustomPin("5", "BAT",      "power_out",      "R"),
            CustomPin("6", "~{STDBY}", "open_collector", "R"),
            CustomPin("7", "~{CHRG}",  "open_collector", "R"),
            CustomPin("8", "CE",       "input",          "R"),
        ],
        description="1A Li-Ion linear charger (LCSC C16581)",
    )
    sg.add_custom(
        "badge:ME6211C33M5G", "ME6211C33M5G",
        "Package_TO_SOT_SMD:SOT-23-5",
        [
            CustomPin("1", "VIN",  "power_in",   "L"),
            CustomPin("3", "EN",   "input",      "L"),
            CustomPin("2", "GND",  "power_in",   "L"),
            CustomPin("5", "VOUT", "power_out",  "R"),
            CustomPin("4", "NC",   "no_connect", "R"),
        ],
        description="500 mA 3.3V LDO (LCSC C82942)",
    )

    sg.add_text(
        "Power tree per badge_hw_design.md §Power tree.\\n"
        "USB-C VBUS → TP4056 → BAT (cell+ via J11) → slide switch → ME6211C33 → +3V3 rail.\\n"
        "TP4056 PROG = 2.4k → 500 mA charge. VBAT div 100k/100k → VBAT_SENSE → MCU GP26/ADC0.\\n"
        "TP4056 CHRG̅ → 100k pullup to 3V3 → ~CHRG → MCU GP18.\\n"
        "CC1 / CC2 each → 5.1k → GND (UFP advertise).\\n"
        "USB_DP / USB_DM route through 27R series on MCU_Core to RP2040.",
        28, 35,
    )

    # ----- instances -----
    sg.place("Connector:USB_C_Receptacle_USB2.0_16P", "J10",
             "USB_C_Receptacle_USB2.0_16P",
             "Connector_USB:USB_C_Receptacle_GCT_USB4085", 50, 100,
             mpn="USB4085", lcsc="C404969",
             desc="USB-C 16P top-mount (GCT USB4085; USB4520/USB4500 mid-mount drop-in if preferred)")
    sg.place("Device:R", "R10", "5.1k", "Resistor_SMD:R_0402_1005Metric", 50, 130,
             desc="USB-C CC1 pulldown (UFP)")
    sg.place("Device:R", "R11", "5.1k", "Resistor_SMD:R_0402_1005Metric", 63, 130,
             desc="USB-C CC2 pulldown (UFP)")
    sg.place("Device:C", "C20", "1u", "Capacitor_SMD:C_0402_1005Metric", 95, 70,
             desc="TP4056 VCC bypass")
    sg.place("badge:TP4056", "U10", "TP4056",
             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 130, 90,
             mpn="TP4056", lcsc="C16581", desc="Li-Ion 1A linear charger")
    sg.place("Device:R", "R12", "2.4k", "Resistor_SMD:R_0402_1005Metric", 115, 130,
             desc="TP4056 PROG → 500 mA")
    sg.place("Device:R", "R13", "100k", "Resistor_SMD:R_0402_1005Metric", 160, 70,
             desc="~CHRG pullup to 3V3")
    sg.place("Device:C", "C21", "10u", "Capacitor_SMD:C_0603_1608Metric", 180, 90,
             desc="TP4056 BAT bulk")
    sg.place("Connector_Generic:Conn_01x02", "J11", "JST-PH 2P",
             "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal", 210, 90,
             mpn="S2B-PH-K-S", lcsc="C131350",
             desc="JST-PH 2P battery (BAT+, BAT-)")
    sg.place("Device:R", "R14", "100k", "Resistor_SMD:R_0402_1005Metric", 155, 155,
             desc="VBAT divider top")
    sg.place("Device:R", "R15", "100k", "Resistor_SMD:R_0402_1005Metric", 155, 175,
             desc="VBAT divider bottom")
    sg.place("Switch:SW_SPDT", "SW1", "SS-12D00",
             "Button_Switch_SMD:SW_SPDT_PCM12", 225, 90,
             mpn="MSK-12C02", lcsc="C431540",
             desc="Slide power switch (SS-12D00 / MSK-12C02 compatible)")
    sg.place("Device:C", "C22", "1u", "Capacitor_SMD:C_0402_1005Metric", 245, 70,
             desc="ME6211 VIN bypass")
    sg.place("badge:ME6211C33M5G", "U11", "ME6211C33M5G",
             "Package_TO_SOT_SMD:SOT-23-5", 260, 90,
             mpn="ME6211C33M5G", lcsc="C82942",
             desc="500 mA 3.3V LDO")
    sg.place("Device:C", "C23", "1u", "Capacitor_SMD:C_0402_1005Metric", 280, 70,
             desc="ME6211 VOUT bypass")

    # ----- wiring via stubs + labels / power flags -----
    # USB-C VBUS pins (4 redundant) → VBUS net
    for p in ("A4", "A9", "B4", "B9"):
        sg.label_at_pin("J10", p, "VBUS")
    # USB-C GND pins + shield → GND
    for i, p in enumerate(("A1", "A12", "B1", "B12", "SH")):
        sg.power_at_pin("J10", p, "GND", pwr_ref=f"#PWR_J10_{p}")
    sg.label_at_pin("J10", "A5", "CC1")
    sg.label_at_pin("J10", "B5", "CC2")
    sg.label_at_pin("J10", "A6", "USB_DP")
    sg.label_at_pin("J10", "B6", "USB_DP")
    sg.label_at_pin("J10", "A7", "USB_DM")
    sg.label_at_pin("J10", "B7", "USB_DM")
    # SBU1/SBU2 intentionally unconnected (no USB-C alt-mode used)
    sg.nc_at_pin("J10", "A8")
    sg.nc_at_pin("J10", "B8")

    sg.label_at_pin("R10", "1", "CC1")
    sg.power_at_pin("R10", "2", "GND", pwr_ref="#PWR_R10")
    sg.label_at_pin("R11", "1", "CC2")
    sg.power_at_pin("R11", "2", "GND", pwr_ref="#PWR_R11")

    sg.label_at_pin("C20", "1", "VBUS")
    sg.power_at_pin("C20", "2", "GND", pwr_ref="#PWR_C20")

    # TP4056
    sg.power_at_pin("U10", "1", "GND", pwr_ref="#PWR_U10_T")
    sg.label_at_pin("U10", "2", "PROG_SET")
    sg.power_at_pin("U10", "3", "GND", pwr_ref="#PWR_U10_G")
    sg.label_at_pin("U10", "4", "VBUS")
    sg.label_at_pin("U10", "5", "BAT")
    sg.nc_at_pin("U10", "6")  # STDBY open-drain — leave floating
    sg.label_at_pin("U10", "7", "~{CHRG}")
    sg.label_at_pin("U10", "8", "+3V3")

    sg.label_at_pin("R12", "1", "PROG_SET")
    sg.power_at_pin("R12", "2", "GND", pwr_ref="#PWR_R12")

    sg.label_at_pin("R13", "1", "+3V3")
    sg.label_at_pin("R13", "2", "~{CHRG}")

    sg.label_at_pin("C21", "1", "BAT")
    sg.power_at_pin("C21", "2", "GND", pwr_ref="#PWR_C21")

    sg.label_at_pin("J11", "1", "BAT")
    sg.power_at_pin("J11", "2", "GND", pwr_ref="#PWR_J11")

    sg.label_at_pin("SW1", "2", "BAT")
    sg.label_at_pin("SW1", "1", "BAT_SW")
    sg.nc_at_pin("SW1", "3")  # second throw unused

    sg.label_at_pin("C22", "1", "BAT_SW")
    sg.power_at_pin("C22", "2", "GND", pwr_ref="#PWR_C22")

    sg.label_at_pin("U11", "1", "BAT_SW")
    sg.label_at_pin("U11", "3", "BAT_SW")
    sg.power_at_pin("U11", "2", "GND", pwr_ref="#PWR_U11")
    sg.label_at_pin("U11", "5", "+3V3")
    sg.nc_at_pin("U11", "4")  # NC pin on ME6211

    sg.label_at_pin("C23", "1", "+3V3")
    sg.power_at_pin("C23", "2", "GND", pwr_ref="#PWR_C23")

    sg.label_at_pin("R14", "1", "BAT")
    sg.label_at_pin("R14", "2", "VBAT_SENSE")
    sg.label_at_pin("R15", "1", "VBAT_SENSE")
    sg.power_at_pin("R15", "2", "GND", pwr_ref="#PWR_R15")

    # PWR_FLAG for externally-sourced rails (VBUS from USB, BAT from cell)
    sg.place("power:PWR_FLAG", "#FLG_VBUS", "PWR_FLAG", "", 75, 60,
             hide_value=True, desc="Declare VBUS externally driven")
    sg.label_at_pin("#FLG_VBUS", "1", "VBUS", stub=2.54)
    sg.place("power:PWR_FLAG", "#FLG_BAT", "PWR_FLAG", "", 210, 55,
             hide_value=True, desc="Declare BAT externally driven")
    sg.label_at_pin("#FLG_BAT", "1", "BAT", stub=2.54)
    # BAT_SW is the switched-battery LDO input; flag as sourced (via SW1 from BAT)
    sg.place("power:PWR_FLAG", "#FLG_BSW", "PWR_FLAG", "", 240, 55,
             hide_value=True, desc="Declare BAT_SW as sourced (BAT through slide switch)")
    sg.label_at_pin("#FLG_BSW", "1", "BAT_SW", stub=2.54)

    # Cross-sheet hier_labels (boundary to top sheet).
    sg.add_hier("USB_DP",      290, 100, shape="bidirectional", rot=0)
    sg.add_hier("USB_DM",      290, 108, shape="bidirectional", rot=0)
    sg.add_hier("VBAT_SENSE",  200, 165, shape="output",        rot=0)
    sg.add_hier("~{CHRG}",     165,  55, shape="output",        rot=0)

    return sg


if __name__ == "__main__":
    sg = build()
    out = Path(__file__).parent.parent / "Power.kicad_sch"
    out.write_text(sg.render())
    print(f"wrote {out}")
