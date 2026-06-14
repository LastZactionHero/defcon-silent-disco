# Iteration state

## Current focus
**Phase 1 — basic correctness.** Add the USB-C connector that's missing, fix
the worst ERC/parity errors, and shrink the board outline to credit-card size.
Placement aesthetics come after correctness.

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
(empty — this is iter 0)

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
