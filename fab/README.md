# Fabrication package — DEF CON silent disco badge

## Spec at a glance
- **Outline:** 86 × 54 mm, 3 mm rounded corners (credit-card form factor)
- **Layers:** 4-layer (F.Cu, In1.Cu = GND, In2.Cu = +3V3, B.Cu)
- **Components:** 80 SMD + THT, all on F.Cu (top side)
- **Hole sizes:** see `gerbers/defcon_badge.drl` (Excellon)
- **Mounting:** 4× M2.5 holes (2.7 mm dia) at corners
- **Connectors:** USB-C (J10), JST-PH 2 mm battery (J11), 3.5 mm audio jack (J20), microSD (J31 — currently off-board, pending iter 11 layer flip), SAO 2×3 (J30), Dev/SWD 1×5 (J33), UART 1×3 (J32)
- **Hero parts:** RP2040 (U3), 4× SK9822 RGB LEDs (LED20-23), TP4056 charger + ME6211 LDO, TM8211 DAC + FDA1308 headphone amp, TSOP4838 IR receiver + 940 nm IR LED

## Files
- `gerbers/` — Gerber RS-274X for all layers + Excellon drill file
- `defcon_badge-pos.csv` — pick-and-place position file (KiCad format, mm)
- `defcon_badge-bom.csv` — grouped BOM with MPN + LCSC where assigned

## Caveats
This package was generated mid-iteration by the autonomous design loop
(see `HARNESS.md`). Known gaps before fab:
- No copper routing yet — all nets are unconnected ratsnest. The board
  is currently a parts-placed PCB. Routing pass (auto or hand) required.
- ERC reports ~71 schematic violations (mostly `label_dangling`,
  `power_pin_not_driven`, off-grid endpoints). Most are cosmetic /
  pre-PWR_FLAG issues, none change topology, but DRC will refuse fab
  until cleared.
- J10 USB-C pads carry no net assignments — they sit in the PCB as a
  raw footprint. Iter 14+ will wire them.
- J31 microSD remains off-board (no front-side space; iter 11 plans
  layer-flip to B.Cu).

## Regenerating
```sh
tools/render_pcb.sh                    # SVG/PNG renders to renders/
kicad-cli pcb export gerbers ...       # see Makefile or this README
```
