# Iteration state

## Current focus
**Phase 1 — basic correctness.** Outline shrunk (iter 1). Next: sync J10 USB-C
from schematic to PCB (needs a new tool — `tools/sync_pcb_from_sch.py` that
exports the netlist and adds any missing footprints to the PCB). Then begin
moving subsystems inside the new outline (probably one subsystem per iter):
power, MCU, audio, LEDs, connectors, switches.

## Baseline (iter 0, 2026-06-13)
- ERC: 71 violations (58 root sheet, then per-subsheet errors)
- DRC: 91 violations + 180 unconnected pads (no routing yet)
- Schematic parity: 0 (clean)
- Footprints: 22/22 resolve from stock KiCad libs
- Board outline: oversize, roughly rectangular
- USB connectivity: NONE (no USB in schematic — only PJ-320A barrel jack + JST PH battery)
- Audio jack: WQP-PJ398SM vertical through-hole — orientation/placement awkward
- microSD: in middle of board, has keepout violation

## Last 5 iterations
- **iter 11 (2026-06-13)** — DEFCON silk identity. 7 gr_text elements
  added: "DEFCON" wordmark (size 2.5 bold) over MCU, "// SILENT DISCO //"
  tagline above LED row, "[ DC32 ]" label, "0xC0FFEE" and "@LZH" corner
  glyphs, "PRESS A FOR PARTY" bottom tagline, "DC SILENT DISCO BADGE v1.0"
  on B.SilkS centered. Hit a layer-name gotcha: gr_text needs canonical
  "F.SilkS" / "B.SilkS" (not the user alias "F.Silkscreen"). Some silk
  overlap with component refdes silk — visible but acceptable; iter 12+
  can clean up if needed.
- **iter 10 (2026-06-13)** — J30 SAO 2x3 + R40/R41 I2C pullups between
  LED22/LED23 on top edge.
- **iter 9 (2026-06-13)** — Bottom-row buttons + IR to left edge + UART.
- **iter 8 (2026-06-13)** — Power subsystem to right side.
- **iter 7 (2026-06-13)** — Audio subsystem bottom-left quadrant.
- **iter 1 (2026-06-13)** — Set Edge.Cuts to 86×54mm rounded credit-card outline
  at origin (100, 80). All 79 footprints remained in place — most now sit
  outside the new outline; iter 2+ will move them in. Updated render_pcb.sh
  to use page-size-mode 1 so out-of-bounds components are visible.
  USB-C J10 confirmed present in schematic (Power.kicad_sch) but never
  transferred to PCB — needs a sync step.

## Open TODO (you don't have to do these in order, just pick the highest value next)
- [x] ~~USB-C in schematic~~ already there as J10 (USB4085).
- [x] ~~Shrink outline~~ (iter 1, 86×54 rounded).
- [ ] Build `tools/sync_pcb_from_sch.py`: export netlist from kicad-cli,
      diff vs PCB footprints, insert missing footprints with refdes + nets.
      Use it to land J10 USB-C onto the PCB at the right edge.
- [x] ~~Move 4 mounting holes to corners~~ (iter 2).
- [x] ~~Move MCU cluster to center~~ (iter 3).
- [x] ~~Pull decoupling caps in~~ (iter 4).
- [x] ~~LED strip across top~~ (iter 5).
- [x] ~~Relocate IR + SWD + 27R~~ (iter 6).
- [x] ~~Place audio subsystem~~ (iter 7).
- [x] ~~Place power subsystem~~ (iter 8).
- [x] ~~Buttons + IR + UART~~ (iter 9).
- [x] ~~SAO + I2C pullups~~ (iter 10).
- [x] ~~DEFCON silk identity~~ (iter 11).
- [ ] J31 microSD: flip to B.Cu (back side). Need flip tool. Until then,
      microSD is the only off-board part.
- [ ] Land J10 USB-C on PCB (still off — sync tool needed).
- [ ] Add silk vector art (a glyph or small skull) — bigger visual win
      than text, no DC-trademark issues. Could use gr_poly or gr_line.
- [ ] Address 71 ERC errors (label_dangling, power_pin_not_driven, etc).
      Largely schematic-level fixes — may need PWR_FLAG symbols added to
      sheets via Python edits to *.kicad_sch.
- [ ] Fab files: export gerbers + drills via `kicad-cli pcb export gerbers
      / drill` to `fab/` once placement is settled.
- [ ] Land J10 USB-C: build `tools/place_footprint_from_lib.py` that
      reads a stock .kicad_mod, wraps it as a (footprint ...) block with
      a refdes + position, and appends to the PCB. Skip net assignments
      for now (will show as unconnected; fixable later).
- [ ] Move the LED strip (LED20-23 + caps C60-63) along the top edge,
      ~7mm below the top corner-arc clear zone.
- [ ] Move audio subsystem (U20 TM8211, U21 FDA1308, C40-46, audio jack)
      to the bottom-left quadrant.
- [ ] Move power subsystem (U10 TP4056, U11 ME6211C33M5G, J11 JST_PH,
      caps C20-23, R10-15) to the right edge.
- [ ] Fix ERC label_dangling errors on root sheet (likely hierarchical labels
      that don't match net names on subsheets).
- [ ] Add PWR_FLAG symbols for any net showing `power_pin_not_driven`.
- [ ] Move microSD to a board edge (right side, below charger).
- [ ] Decide audio jack orientation — keep PJ398SM vertical if user wants
      "headphones-up" wearable orientation, else switch to SMD horizontal.
- [ ] Cluster placement: MCU+flash+xtal center, power left edge, audio
      bottom-left, LEDs across top, connectors right edge.
- [ ] Add silk art: "DEFCON" wordmark + a small skull/glyph that's clearly
      original, not the official DC pineapple.
- [ ] Ground pours on F.Cu and B.Cu after placement settles.
- [ ] Routing pass (hand-route or freerouting once Java is available).
- [ ] Export gerbers, drills, BOM, CPL to `fab/`.

## Stop conditions
See HARNESS.md "Definition of done (overall)".
