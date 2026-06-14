#!/usr/bin/env python3
"""Generate Audio.kicad_sch — TM8211 DAC + TDA1308 amp + PJ-320A jack.

Topology (badge_hw_design.md §Audio):
  RP2040 PIO I2S → TM8211 → 10µF coupling → TDA1308 → 220µF coupling → PJ-320A
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen, CustomPin


def build() -> SheetGen:
    sg = SheetGen(
        name="Audio",
        title="DEFCON Silent Disco Badge — Audio",
        file_uuid="3d9b69cc-52eb-484c-b3ed-11c220b9e0a4",
        sheet_symbol_uuid="364073ca-f27d-4fe0-b5d8-4811b493895d",
        page="4",
        paper="A3",
        comments=[
            "TM8211 (PT8211 clone, 2.0-5.5V) — LSBJ-format 16-bit I2S in, stereo current-out",
            "TDA1308 dual opamp headphone amp, ~2.1× gain (100k/47k), virtual ground 10k/10k",
            "PJ-320A wired as TRS stereo, sleeve to GND, mic ring and detect left NC",
        ],
    )

    for lib, sym in [
        ("Device.kicad_sym", "R"),
        ("Device.kicad_sym", "C"),
        ("Device.kicad_sym", "C_Polarized"),
        ("power.kicad_sym", "+3V3"),
        ("power.kicad_sym", "GND"),
    ]:
        sg.add_stock(lib, sym)

    # TM8211 stereo DAC (PT8211 footprint clone), SOP-8 LSBJ-format
    sg.add_custom(
        "badge:TM8211", "TM8211",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        [
            CustomPin("1", "VDD",  "power_in",  "L"),
            CustomPin("2", "VLL",  "output",    "L"),
            CustomPin("3", "VRR",  "output",    "L"),
            CustomPin("4", "VSS",  "power_in",  "L"),
            CustomPin("8", "NC",   "no_connect","R"),
            CustomPin("7", "DIN",  "input",     "R"),
            CustomPin("6", "BCK",  "input",     "R"),
            CustomPin("5", "WS",   "input",     "R"),
        ],
        description="Stereo 16-bit DAC, LSBJ-format I2S (PT8211 clone)",
    )

    # TDA1308 dual headphone opamp, SOP-8
    sg.add_custom(
        "badge:TDA1308", "TDA1308",
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
        description="Dual headphone opamp, rail-to-rail",
    )

    # PJ-320A 3.5mm TRRS jack — wired as TRS stereo
    sg.add_custom(
        "badge:PJ-320A", "PJ-320A",
        "Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles",
        [
            CustomPin("T", "TIP",     "passive",    "R"),   # left output
            CustomPin("R", "RING",    "passive",    "R"),   # right output
            CustomPin("S", "SLEEVE",  "passive",    "R"),   # GND return
            CustomPin("R2","RING2",   "no_connect", "L"),   # mic (NC)
            CustomPin("D", "DETECT",  "no_connect", "L"),   # NC
        ],
        description="3.5mm TRRS jack, used as TRS stereo (sleeve = GND)",
    )

    sg.add_text(
        "Audio chain — badge_hw_design.md §Audio chain.\\n"
        "I2S BCK/LRCK/DIN → TM8211 DAC → 10µF coupling → TDA1308 amp → 220µF coupling → PJ-320A.\\n"
        "Gain ≈ 2.1× (100k feedback / 47k input). Virtual ground 10k/10k + 10µF.\\n"
        "220µF/32Ω → −3 dB at 23 Hz; into 16Ω earbuds → 45 Hz. Don't cheap to 100µF — this is a disco.\\n"
        "DAC needs LSBJ-format I2S (WS shifted by one BCK vs standard I2S) — firmware PIO note.",
        25, 25,
    )

    # ----- DAC section -----
    sg.place("badge:TM8211", "U20", "TM8211",
             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 75, 80,
             mpn="TM8211", lcsc="C82978",
             desc="Stereo DAC, LSBJ I2S (PT8211 clone)")
    sg.place("Device:C", "C40", "100n", "Capacitor_SMD:C_0402_1005Metric", 55, 60,
             desc="DAC VDD decoupling")
    sg.place("Device:C", "C41", "10u", "Capacitor_SMD:C_0402_1005Metric", 65, 60,
             desc="DAC VDD bulk")

    sg.label_at_pin("U20", "1", "+3V3")
    sg.power_at_pin("U20", "4", "GND", pwr_ref="#PWR_U20")
    sg.label_at_pin("C40", "1", "+3V3")
    sg.power_at_pin("C40", "2", "GND", pwr_ref="#PWR_C40")
    sg.label_at_pin("C41", "1", "+3V3")
    sg.power_at_pin("C41", "2", "GND", pwr_ref="#PWR_C41")

    # I2S in from hier_labels (added below). Pin order: BCK, LRCK(WS), DIN
    sg.label_at_pin("U20", "6", "I2S_BCK")
    sg.label_at_pin("U20", "5", "I2S_LRCK")
    sg.label_at_pin("U20", "7", "I2S_DIN")
    sg.nc_at_pin("U20", "8")  # TM8211 pin 8 NC

    # DAC outputs → coupling caps → amp inputs
    sg.label_at_pin("U20", "2", "DAC_OUTL")
    sg.label_at_pin("U20", "3", "DAC_OUTR")

    # 10 µF DAC→amp coupling (vertical caps, spaced apart so stub labels don't collide)
    sg.place("Device:C", "C42", "10u", "Capacitor_SMD:C_0603_1608Metric", 100, 65,
             desc="L channel DAC→amp coupling")
    sg.place("Device:C", "C43", "10u", "Capacitor_SMD:C_0603_1608Metric", 100, 95,
             desc="R channel DAC→amp coupling")
    sg.label_at_pin("C42", "1", "DAC_OUTL")
    sg.label_at_pin("C42", "2", "AMP_INL")
    sg.label_at_pin("C43", "1", "DAC_OUTR")
    sg.label_at_pin("C43", "2", "AMP_INR")

    # ----- Amp section -----
    sg.place("badge:TDA1308", "U21", "TDA1308",
             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 145, 80,
             mpn="TDA1308AT", lcsc="C8434",
             desc="Dual headphone amp (rail-to-rail)")
    sg.label_at_pin("U21", "8", "+3V3")
    sg.power_at_pin("U21", "4", "GND", pwr_ref="#PWR_U21")

    # 47k input resistors (spaced so stub labels don't collide)
    sg.place("Device:R", "R20", "47k", "Resistor_SMD:R_0402_1005Metric", 120, 65,
             desc="L amp input")
    sg.place("Device:R", "R21", "47k", "Resistor_SMD:R_0402_1005Metric", 120, 95,
             desc="R amp input")
    sg.label_at_pin("R20", "1", "AMP_INL")
    sg.label_at_pin("R20", "2", "AMP_IN1-")
    sg.label_at_pin("R21", "1", "AMP_INR")
    sg.label_at_pin("R21", "2", "AMP_IN2-")
    # connect inverting inputs of each opamp half
    sg.label_at_pin("U21", "2", "AMP_IN1-")
    sg.label_at_pin("U21", "6", "AMP_IN2-")

    # 100k feedback resistors
    sg.place("Device:R", "R22", "100k", "Resistor_SMD:R_0402_1005Metric", 145, 65,
             desc="L feedback")
    sg.place("Device:R", "R23", "100k", "Resistor_SMD:R_0402_1005Metric", 145, 95,
             desc="R feedback")
    sg.label_at_pin("R22", "1", "AMP_IN1-")
    sg.label_at_pin("R22", "2", "AMP_OUTL")
    sg.label_at_pin("R23", "1", "AMP_IN2-")
    sg.label_at_pin("R23", "2", "AMP_OUTR")

    # Amp outputs
    sg.label_at_pin("U21", "1", "AMP_OUTL")
    sg.label_at_pin("U21", "7", "AMP_OUTR")

    # Virtual ground (non-inverting inputs)
    # 10k/10k divider + 10µF cap
    sg.place("Device:R", "R24", "10k", "Resistor_SMD:R_0402_1005Metric", 165, 105,
             desc="VGND top")
    sg.place("Device:R", "R25", "10k", "Resistor_SMD:R_0402_1005Metric", 165, 120,
             desc="VGND bottom")
    sg.place("Device:C", "C44", "10u", "Capacitor_SMD:C_0402_1005Metric", 175, 113,
             desc="VGND bypass")
    sg.label_at_pin("R24", "1", "+3V3")
    sg.label_at_pin("R24", "2", "VGND")
    sg.label_at_pin("R25", "1", "VGND")
    sg.power_at_pin("R25", "2", "GND", pwr_ref="#PWR_R25")
    sg.label_at_pin("C44", "1", "VGND")
    sg.power_at_pin("C44", "2", "GND", pwr_ref="#PWR_C44")
    # IN+ inputs to VGND
    sg.label_at_pin("U21", "3", "VGND")  # IN1+
    sg.label_at_pin("U21", "5", "VGND")  # IN2+

    # 220µF output coupling caps (electrolytic — use CP polarized symbol)
    sg.place("Device:C_Polarized", "C45", "220u",
             "Capacitor_SMD:CP_Elec_6.3x5.4", 180, 70,
             desc="L output coupling (electrolytic, 6.3V)")
    sg.place("Device:C_Polarized", "C46", "220u",
             "Capacitor_SMD:CP_Elec_6.3x5.4", 180, 90,
             desc="R output coupling (electrolytic, 6.3V)")
    sg.label_at_pin("C45", "1", "AMP_OUTL")
    sg.label_at_pin("C45", "2", "JACK_L")
    sg.label_at_pin("C46", "1", "AMP_OUTR")
    sg.label_at_pin("C46", "2", "JACK_R")

    # ----- Jack -----
    sg.place("badge:PJ-320A", "J20", "PJ-320A",
             "Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles",
             215, 80, mpn="PJ-320A", lcsc="C720466",
             desc="3.5mm TRRS jack wired as TRS stereo")
    sg.label_at_pin("J20", "T", "JACK_L")
    sg.label_at_pin("J20", "R", "JACK_R")
    sg.power_at_pin("J20", "S", "GND", pwr_ref="#PWR_J20")
    sg.nc_at_pin("J20", "R2")  # mic ring — TRS-only use
    sg.nc_at_pin("J20", "D")   # sleeve-detect not used

    # ----- Cross-sheet hier_labels (matching top sheet pins) -----
    sg.add_hier("I2S_BCK",  35, 55, shape="input", rot=0)
    sg.add_hier("I2S_LRCK", 35, 65, shape="input", rot=0)
    sg.add_hier("I2S_DIN",  35, 75, shape="input", rot=0)

    return sg


if __name__ == "__main__":
    sg = build()
    out = Path(__file__).parent.parent / "Audio.kicad_sch"
    out.write_text(sg.render())
    print(f"wrote {out}")
