#!/usr/bin/env python3
"""Generate LEDs_IR.kicad_sch — 4× SK9822 + IR LED driver + TSOP receiver."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen, CustomPin


def build() -> SheetGen:
    sg = SheetGen(
        name="LEDs_IR",
        title="DEFCON Silent Disco Badge — LEDs + IR Tap",
        file_uuid="ea152a61-1479-4c1c-a9da-8f6cce70d3af",
        sheet_symbol_uuid="5c3b6a90-ee33-4533-a6d3-29c1d6467142",
        page="5",
        paper="A3",
        comments=[
            "4× SK9822-EC20 chained, SPI1 clock+data, 25% global brightness cap (firmware)",
            "Optical tap link: 940 nm IR LED via S8050 + 68Ω; TSOP4838-class 38 kHz RX",
            "LED + RX placed mirror-symmetric about vertical centerline (face-to-face mate)",
        ],
    )

    for lib, sym in [
        ("Device.kicad_sym", "R"),
        ("Device.kicad_sym", "C"),
        ("Device.kicad_sym", "LED"),
        ("power.kicad_sym", "+3V3"),
        ("power.kicad_sym", "GND"),
    ]:
        sg.add_stock(lib, sym)

    # SK9822 6-pin. Pin order chosen so chain connections (DIN↔DOUT, CIN↔COUT)
    # land on the same Y level between adjacent LEDs → straight horizontal wires.
    sg.add_custom(
        "badge:SK9822", "SK9822",
        "badge:LED_SK9822_5050",   # 6-pad 5050 land pattern (create in PCB phase; no stock KiCad fp)
        [
            # SK9822 5050 datasheet pinout: 1=DIN 2=CIN 3=GND 4=VDD 5=COUT 6=DOUT.
            # Slots aligned so chain wires are straight: DIN(1)/DOUT(6) top, CIN(2)/COUT(5) mid.
            CustomPin("1", "DIN",  "input",      "L"),   # slot 0 (top)
            CustomPin("2", "CIN",  "input",      "L"),   # slot 1 (mid)
            CustomPin("3", "GND",  "power_in",   "L"),   # slot 2 (bottom)
            CustomPin("6", "DOUT", "output",     "R"),   # slot 0 (top)  — aligns with next LED's DIN
            CustomPin("5", "COUT", "output",     "R"),   # slot 1 (mid)  — aligns with next LED's CIN
            CustomPin("4", "VDD",  "power_in",   "R"),   # slot 2 (bottom)
        ],
        description="SK9822 (APA102 clone) 5050 addressable RGB LED, SPI clock+data",
    )

    # TSOP4838-class 38 kHz IR receiver (3-pin: VS, OUT, GND)
    sg.add_custom(
        "badge:TSOP4838", "TSOP4838",
        "OptoDevice:Vishay_MINICAST-3Pin",
        [
            CustomPin("1", "OUT", "open_collector", "R"),
            CustomPin("2", "GND", "power_in",       "L"),
            CustomPin("3", "VS",  "power_in",       "L"),
        ],
        description="38 kHz demodulating IR receiver (TSOP4838 family)",
    )

    sg.add_text(
        "LEDs + IR tap — badge_hw_design.md §LEDs and §Optical tap.\\n"
        "4× SK9822 chained, capped at ~25% global brightness in firmware.\\n"
        "Optical link: 940 nm LED direct-drive from GP9 (IR_TX) via R30=150Ω → ~12 mA pulsed at 38 kHz PIO carrier.\\n"
        "Range is intentionally short (~2 cm) — face-to-face tap is the spec.\\n"
        "TSOP4838 RX → active-low IR_RX. Place LED + RX mirror-symmetric on front face.\\n"
        "On contact, SK9822s pulse in unison with peer — that shared flash IS the sync confirmation.",
        25, 25,
    )

    # ----- 4× SK9822 chain at y=80, x=60, 95, 130, 165 -----
    led_x = [60, 95, 130, 165]
    for i, x in enumerate(led_x, start=1):
        ref = f"LED{19 + i}"  # LED20, LED21, LED22, LED23
        sg.place("badge:SK9822", ref, "SK9822",
                 "badge:LED_SK9822_5050", x, 80,
                 mpn="SK9822", lcsc="",
                 desc=f"SK9822 #{i} of 4 chained (5050)")
        # Local 10nF decoupling
        cref = f"C{59 + i}"  # C60-C63
        sg.place("Device:C", cref, "10n", "Capacitor_SMD:C_0402_1005Metric",
                 x, 60, desc=f"SK9822 #{i} bypass")
        sg.label_at_pin(cref, "1", "+3V3")
        sg.power_at_pin(cref, "2", "GND", pwr_ref=f"#PWR_{cref}")
        sg.label_at_pin(ref, "4", "+3V3")          # VDD = pin 4
        sg.power_at_pin(ref, "3", "GND", pwr_ref=f"#PWR_{ref}")  # GND = pin 3

    # LED20 inputs: labels carry the chain-start nets from MCU_Core.
    sg.label_at_pin("LED20", "2", "LED_SCK")    # CIN = pin 2
    sg.label_at_pin("LED20", "1", "LED_DAT")    # DIN = pin 1
    # Chain link wires — pin slots are aligned for straight horizontal wires.
    for src, dst in [("LED20", "LED21"), ("LED21", "LED22"), ("LED22", "LED23")]:
        sg.wire_pins(src, "6", dst, "1")  # DOUT(6) → next DIN(1)
        sg.wire_pins(src, "5", dst, "2")  # COUT(5) → next CIN(2)
    # LED23 chain ends — outputs unconnected.
    sg.nc_at_pin("LED23", "5")  # COUT
    sg.nc_at_pin("LED23", "6")  # DOUT

    # ----- IR LED, direct GPIO drive (no S8050 driver, no base resistor) -----
    # GP9 sinks current: +3V3 → D20 anode → D20 cathode → R30 → GP9 (IR_TX).
    # When GP9 is asserted LOW, ~12 mA flows. R30 sized for that current at
    # Vf ≈ 1.2 V and GPIO Vol ≈ 0.3 V: (3.3 − 1.2 − 0.3) / 150 ≈ 12 mA.
    sg.place("Device:LED", "D20", "IR LED 940 nm",
             "LED_SMD:LED_0805_2012Metric", 60, 130,
             mpn="IR15-21C/TR8", lcsc="C72037",
             desc="940 nm IR transmit LED, 0805")
    sg.place("Device:R", "R30", "150", "Resistor_SMD:R_0402_1005Metric",
             60, 145, desc="IR LED current limit for direct GPIO drive (~12 mA pulsed)")

    sg.label_at_pin("D20", "2", "+3V3")     # anode (pin 2 in KiCad LED symbol)
    sg.label_at_pin("D20", "1", "IR_DRIVE") # cathode
    sg.label_at_pin("R30", "1", "IR_DRIVE")
    sg.label_at_pin("R30", "2", "IR_TX")    # straight to RP2040 GP9

    # ----- TSOP4838 IR receiver -----
    sg.place("badge:TSOP4838", "U30", "TSOP4838",
             "OptoDevice:Vishay_MINICAST-3Pin", 145, 145,
             mpn="TSOP4838", lcsc="C90701",
             desc="38 kHz IR demodulating receiver, side-view")
    sg.place("Device:C", "C70", "100n",
             "Capacitor_SMD:C_0402_1005Metric", 130, 130,
             desc="TSOP VS decoupling")
    sg.place("Device:C", "C71", "10u",
             "Capacitor_SMD:C_0603_1608Metric", 140, 130,
             desc="TSOP VS bulk")

    sg.label_at_pin("U30", "3", "+3V3")  # VS
    sg.power_at_pin("U30", "2", "GND", pwr_ref="#PWR_U30")
    sg.label_at_pin("U30", "1", "IR_RX")
    sg.label_at_pin("C70", "1", "+3V3")
    sg.power_at_pin("C70", "2", "GND", pwr_ref="#PWR_C70")
    sg.label_at_pin("C71", "1", "+3V3")
    sg.power_at_pin("C71", "2", "GND", pwr_ref="#PWR_C71")

    # ----- Cross-sheet hier_labels -----
    sg.add_hier("LED_SCK", 35, 55, shape="input",  rot=0)
    sg.add_hier("LED_DAT", 35, 65, shape="input",  rot=0)
    sg.add_hier("IR_TX",   35, 75, shape="input",  rot=0)
    sg.add_hier("IR_RX",   35, 85, shape="output", rot=0)

    return sg


if __name__ == "__main__":
    sg = build()
    out = Path(__file__).parent.parent / "LEDs_IR.kicad_sch"
    out.write_text(sg.render())
    print(f"wrote {out}")
