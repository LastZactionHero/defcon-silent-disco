#!/usr/bin/env python3
"""Generate IO.kicad_sch — 3× tactile + SAO 2×3 + microSD + debug UART."""
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
            "microSD push socket on SPI0; debug UART 1×3 header (DNP)",
        ],
    )

    for lib, sym in [
        ("Device.kicad_sym", "R"),
        ("Switch.kicad_sym", "SW_Push"),
        ("Connector.kicad_sym", "Micro_SD_Card_Det1"),
        ("Connector_Generic.kicad_sym", "Conn_02x03_Odd_Even"),
        ("Connector_Generic.kicad_sym", "Conn_01x03"),
        ("power.kicad_sym", "+3V3"),
        ("power.kicad_sym", "GND"),
    ]:
        sg.add_stock(lib, sym)

    sg.add_text(
        "IO — badge_hw_design.md §Buttons, §SAO, §Connectors.\\n"
        "Buttons → GND with RP2040 internal pullups. SAO 2×3 standard pinout.\\n"
        "microSD on SPI0 (SCK=GP2, MOSI=GP3, MISO=GP4, CS=GP5). UART debug on GP0/GP1 (DNP).\\n"
        "4.7k I2C pullups for SAO bus (RP2040 internal pulls are too weak).",
        25, 25,
    )

    # ----- Three tactile buttons -----
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

    sg.label_at_pin("SW20", "1", "BTN_CH")
    sg.power_at_pin("SW20", "2", "GND", pwr_ref="#PWR_SW20")
    sg.label_at_pin("SW21", "1", "BTN_VOL_UP")
    sg.power_at_pin("SW21", "2", "GND", pwr_ref="#PWR_SW21")
    sg.label_at_pin("SW22", "1", "BTN_VOL_DN")
    sg.power_at_pin("SW22", "2", "GND", pwr_ref="#PWR_SW22")

    # ----- SAO 2×3 header -----
    # Standard SAO pinout (looking at the connector pins 1-6):
    #   1: GND, 2: 3V3, 3: SDA, 4: SCL, 5: GPIO1, 6: GPIO2
    sg.place("Connector_Generic:Conn_02x03_Odd_Even", "J30", "SAO 2x3",
             "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical", 130, 70,
             mpn="PRPC003DAAN-RC", lcsc="C124378",
             desc="SAO v1.69 2x3 header — DEFCON shitty add-on")
    sg.power_at_pin("J30", "1", "GND", pwr_ref="#PWR_J30_1")
    sg.label_at_pin("J30", "2", "+3V3")
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
    sg.place("Connector:Micro_SD_Card_Det1", "J31", "microSD",
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
    sg.nc_at_pin("J31", "9")     # CD switch — not wired this rev
    sg.power_at_pin("J31", "SH", "GND", pwr_ref="#PWR_J31_SH")

    # ----- Debug UART header (3-pin: GND, TX, RX). DNP -----
    sg.place("Connector_Generic:Conn_01x03", "J32", "UART debug",
             "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 200, 130,
             dnp=True,
             desc="Debug UART header (DNP — pads laid out, header not stuffed)")
    sg.power_at_pin("J32", "1", "GND", pwr_ref="#PWR_J32")
    sg.label_at_pin("J32", "2", "UART_TX")
    sg.label_at_pin("J32", "3", "UART_RX")

    # ----- Cross-sheet hier_labels -----
    sg.add_hier("SD_SCK",     35, 55, shape="input",         rot=0)
    sg.add_hier("SD_MOSI",    35, 65, shape="input",         rot=0)
    sg.add_hier("SD_MISO",    35, 75, shape="output",        rot=0)
    sg.add_hier("SD_CS",      35, 85, shape="input",         rot=0)
    sg.add_hier("BTN_CH",     35, 100, shape="output",       rot=0)
    sg.add_hier("BTN_VOL_UP", 35, 110, shape="output",       rot=0)
    sg.add_hier("BTN_VOL_DN", 35, 120, shape="output",       rot=0)
    sg.add_hier("SAO_SDA",    35, 135, shape="bidirectional", rot=0)
    sg.add_hier("SAO_SCL",    35, 145, shape="input",        rot=0)
    sg.add_hier("SAO_GPIO1",  35, 155, shape="bidirectional", rot=0)
    sg.add_hier("SAO_GPIO2",  35, 165, shape="bidirectional", rot=0)
    sg.add_hier("UART_TX",    35, 180, shape="input",        rot=0)
    sg.add_hier("UART_RX",    35, 190, shape="output",       rot=0)

    return sg


if __name__ == "__main__":
    sg = build()
    out = Path(__file__).parent.parent / "IO.kicad_sch"
    out.write_text(sg.render())
    print(f"wrote {out}")
