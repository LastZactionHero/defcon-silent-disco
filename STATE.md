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
- **iter 8 (2026-06-13)** — Power subsystem to right side. J11 JST-PH battery
  at top-right (180,100), TP4056 charger U10 at (165,114), ME6211 LDO U11
  at (172,114), SW1 SS-12D00 power slide switch at (180,127) bottom-right.
  Charge/sense passives in cluster: R12 2.4k PROG, R13/R14/R15 100k,
  C20/C21/C22/C23 (1u/10u/1u/1u), R10/R11 5.1k CC pulldowns near future
  USB-C site. Right half of board now densely populated.
- **iter 7 (2026-06-13)** — Audio subsystem in bottom-left quadrant
  (U20 TM8211 + U21 FDA1308 + caps + Rs + J20 audio jack).
- **iter 6 (2026-06-13)** — Cleared LED-row collisions.
- **iter 5 (2026-06-13)** — LED strip across top edge.
- **iter 4 (2026-06-13)** — Decoupling cap ring around RP2040.
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
- [ ] Remaining off-board parts: SW20/21/22 push buttons (~6mm, TS-1187A)
      → bottom edge of board, x ≈ 122/138/154, y ≈ 130. J31 microSD →
      right edge or left edge interior, hard to fit at this density.
      J30 SAO 2x3 → ?, J32 UART debug 1x03 → bottom-right somewhere,
      R40/R41 4.7k I2C pullups for SAO.
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
