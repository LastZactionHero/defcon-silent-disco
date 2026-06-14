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
- **iter 1 (2026-06-13)** — Set Edge.Cuts to 86×54mm rounded credit-card outline
  at origin (100, 80). All 79 footprints remained in place — most now sit
  outside the new outline; iter 2+ will move them in. Updated render_pcb.sh
  to use page-size-mode 1 so out-of-bounds components are visible.
  USB-C J10 confirmed present in schematic (Power.kicad_sch) but never
  transferred to PCB — needs a sync step. Realized I was wrong in iter 0
  baseline: USB-C is designed, just not laid out.

## Open TODO (you don't have to do these in order, just pick the highest value next)
- [ ] Add USB-C receptacle (GCT USB4085 footprint exists in stock) to Power schematic.
      Wire VBUS through TP4056 charger input, D+/D- to RP2040 USB pins,
      add 5.1k CC1/CC2 pulldowns for UFP.
- [ ] Shrink board outline to ~86×54mm via `tools/set_outline.py`, then re-place
      mounting holes at corners.
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
