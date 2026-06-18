#!/usr/bin/env python3
"""Generate IO.kicad_sch — 4× tactile + SAO 2×3 + microSD."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from kicad_sheet_gen import SheetGen, CustomPin


def build() -> SheetGen:
    sg = SheetGen(
        name="IO",
        title="DEFCON Silent Disco Badge — IO",
        file_uuid="2b85d325-facd-43cf-ba3c-e148f65c3ed6",
        sheet_symbol_uuid="608539de-722a-4bca-b1da-2c313b60cd6f",
        page="6",
        paper="A3",
        comments=[
            "3× TS-1187A tactile (CH / VOL+ / VOL−) via internal RP2040 pullups",
            "Standard SAO v1.69 2×3 (3V3 / GND / SDA / SCL / GP1 / GP2), 4.7k SAO_SDA/SCL pullups",
            "microSD push socket on SPI0",
        ],
    )

    for lib, sym in [
        ("Device.kicad_sym", "R"),
        ("Switch.kicad_sym", "SW_Push"),
        ("Connector.kicad_sym", "Micro_SD_Card_Det2"),
        ("Connector_Generic.kicad_sym", "Conn_02x03_Odd_Even"),
        ("Connector_Generic.kicad_sym", "Conn_01x03"),
        ("power.kicad_sym", "+3V3"),
        ("power.kicad_sym", "GND"),
    ]:
        sg.add_stock(lib, sym)

    sg.add_text(
        "IO — badge_hw_design.md §Buttons, §SAO, §Connectors.\\n"
        "Buttons → GND with RP2040 internal pullups. SAO 2×3 standard pinout.\\n"
        "microSD on SPI0 (SCK=GP2, MOSI=GP3, MISO=GP4, CS=GP5).\\n"
        "4.7k I2C pullups for SAO bus (RP2040 internal pulls are too weak).",
        25, 25,
    )

    # ----- Four tactile buttons (CH / VOL+ / VOL- / SYNC) -----
    sg.place("Switch:SW_Push", "SW20", "TS-1187A",
             "Button_Switch_SMD:SW_SPST_TL3342", 50, 60,
             mpn="TS-1187A-B-A-B", lcsc="C455257",
             desc="Channel button (CH), 6mm tactile")
    sg.place("Switch:SW_Push", "SW21", "TS-1187A",
             "Button_Switch_SMD:SW_SPST_TL3342", 70, 60,
             mpn="TS-1187A-B-A-B", lcsc="C455257",
             desc="Volume up")
    sg.place("Switch:SW_Push", "SW22", "TS-1187A",
             "Button_Switch_SMD:SW_SPST_TL3342", 90, 60,
             mpn="TS-1187A-B-A-B", lcsc="C455257",
             desc="Volume down")
    sg.place("Switch:SW_Push", "SW23", "TS-1187A",
             "Button_Switch_SMD:SW_SPST_TL3342", 110, 60,
             mpn="TS-1187A-B-A-B", lcsc="C455257",
             desc="Sync (tap-to-sync) button")

    sg.label_at_pin("SW20", "1", "BTN_CH")
    sg.power_at_pin("SW20", "2", "GND", pwr_ref="#PWR_SW20")
    sg.label_at_pin("SW21", "1", "BTN_VOL_UP")
    sg.power_at_pin("SW21", "2", "GND", pwr_ref="#PWR_SW21")
    sg.label_at_pin("SW22", "1", "BTN_VOL_DN")
    sg.power_at_pin("SW22", "2", "GND", pwr_ref="#PWR_SW22")
    sg.label_at_pin("SW23", "1", "BTN_SYNC")
    sg.power_at_pin("SW23", "2", "GND", pwr_ref="#PWR_SW23")

    # ----- SAO 2×3 header -----
    # Standard SAO v1.69bis pinout (official badge.team / Hackaday spec):
    #   1: +3V3, 2: GND, 3: SDA, 4: SCL, 5: GPIO1, 6: GPIO2
    # (pin1=VCC, pin2=GND — NOT the reverse; a swapped pair reverse-powers any
    #  standards-compliant SAO add-on.)
    sg.place("Connector_Generic:Conn_02x03_Odd_Even", "J30", "SAO 2x3",
             "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical", 130, 70,
             mpn="PRPC003DAAN-RC", lcsc="C124378",
             desc="SAO v1.69 2x3 header — DEFCON shitty add-on")
    sg.label_at_pin("J30", "1", "+3V3")
    sg.power_at_pin("J30", "2", "GND", pwr_ref="#PWR_J30_1")
    sg.label_at_pin("J30", "3", "SAO_SDA")
    sg.label_at_pin("J30", "4", "SAO_SCL")
    sg.label_at_pin("J30", "5", "SAO_GPIO1")
    sg.label_at_pin("J30", "6", "SAO_GPIO2")

    # SAO I2C pullups (4.7k each on SDA, SCL, to +3V3)
    sg.place("Device:R", "R40", "4.7k", "Resistor_SMD:R_0402_1005Metric",
             160, 60, desc="SAO_SDA pullup")
    sg.place("Device:R", "R41", "4.7k", "Resistor_SMD:R_0402_1005Metric",
             170, 60, desc="SAO_SCL pullup")
    sg.label_at_pin("R40", "1", "+3V3")
    sg.label_at_pin("R40", "2", "SAO_SDA")
    sg.label_at_pin("R41", "1", "+3V3")
    sg.label_at_pin("R41", "2", "SAO_SCL")

    # ----- microSD card socket -----
    # Det2 symbol exposes BOTH card-detect switch terminals (pin 9 DET_B, pin 10
    # DET_A). The DM3D-SF detect switch sits between 9 and 10 — pin 10 MUST go to
    # GND so a card closing the switch pulls the pulled-up SD_CD (pin 9) low.
    # (Det1 has no pin 10, which left the switch's far side floating = dead CD.)
    sg.place("Connector:Micro_SD_Card_Det2", "J31", "microSD",
             "Connector_Card:microSD_HC_Hirose_DM3D-SF", 80, 130,
             mpn="TF-PUSH-A", lcsc="C146885",
             desc="microSD push socket, hinged tray")
    # SPI mode wiring:
    #   pin 1: DAT2/RSV (no_connect)
    #   pin 2: CD/DAT3 = CS
    #   pin 3: CMD = MOSI
    #   pin 4: VDD
    #   pin 5: CLK = SCK
    #   pin 6: VSS = GND
    #   pin 7: DAT0 = MISO
    #   pin 8: DAT1/RSV (no_connect)
    #   pin 9: CD (card detect, optional)
    #   SH: shield → GND
    sg.nc_at_pin("J31", "1")     # DAT2 / RSV
    sg.label_at_pin("J31", "2", "SD_CS")
    sg.label_at_pin("J31", "3", "SD_MOSI")
    sg.label_at_pin("J31", "4", "+3V3")
    sg.label_at_pin("J31", "5", "SD_SCK")
    sg.power_at_pin("J31", "6", "GND", pwr_ref="#PWR_J31_6")
    sg.label_at_pin("J31", "7", "SD_MISO")
    sg.nc_at_pin("J31", "8")     # DAT1 / RSV
    sg.global_label_at_pin("J31", "9", "SD_CD")  # DET_B: CD switch -> spare GPIO via global net
    sg.power_at_pin("J31", "10", "GND", pwr_ref="#PWR_J31_10")  # DET_A: switch other terminal -> GND
    sg.power_at_pin("J31", "SH", "GND", pwr_ref="#PWR_J31_SH")
    # Card-detect pull-up: the DET switch shorts pin 9 to the grounded shield when a
    # card is inserted, so SD_CD reads LOW = card present; R42 holds it high when empty.
    sg.place("Device:R", "R42", "10k", "Resistor_SMD:R_0402_1005Metric", 110, 110,
             desc="microSD card-detect pull-up to +3V3")
    sg.global_label_at_pin("R42", "1", "SD_CD")
    sg.label_at_pin("R42", "2", "+3V3")

    # (Debug UART header J32 removed — not used; programming is via BOOTSEL/USB.)

    # ----- Cross-sheet hier_labels -----
    sg.add_hier("SD_SCK",     35, 55, shape="input",         rot=0)
    sg.add_hier("SD_MOSI",    35, 65, shape="input",         rot=0)
    sg.add_hier("SD_MISO",    35, 75, shape="output",        rot=0)
    sg.add_hier("SD_CS",      35, 85, shape="input",         rot=0)
    sg.add_hier("BTN_CH",     35, 100, shape="output",       rot=0)
    sg.add_hier("BTN_VOL_UP", 35, 110, shape="output",       rot=0)
    sg.add_hier("BTN_VOL_DN", 35, 120, shape="output",       rot=0)
    sg.add_hier("BTN_SYNC",   35, 130, shape="output",       rot=0)
    sg.add_hier("SAO_SDA",    35, 135, shape="bidirectional", rot=0)
    sg.add_hier("SAO_SCL",    35, 145, shape="input",        rot=0)
    sg.add_hier("SAO_GPIO1",  35, 155, shape="bidirectional", rot=0)
    sg.add_hier("SAO_GPIO2",  35, 165, shape="bidirectional", rot=0)

    return sg


if __name__ == "__main__":
    sg = build()
    out = Path(__file__).parent.parent / "IO.kicad_sch"
    out.write_text(sg.render())
    print(f"wrote {out}")
