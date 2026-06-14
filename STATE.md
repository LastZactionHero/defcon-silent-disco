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
- **iter 15 (2026-06-14)** — Discovery + cleanup pass.
  * Tried flipping J31 microSD to B.Cu by changing only the top-level
    `(layer)` line — produced a hybrid mess (silk on F.SilkS but topology
    on B.Cu). Reverted. A real flip needs a full F.*↔B.* layer swap.
  * Tried adding GND/+3V3 inner-layer zones — discovered the PCB has
    **zero net declarations at the top level** (`(net N "name")`). The
    original code generator skipped the net list entirely, which means
    every pad in the PCB is netless. Without nets: no zones, no routing,
    no ratsnest, and DRC's 179 "unconnected" complaints are misleading
    because there are no nets to connect.
  * Verified `kicad-cli sch export netlist --format kicadsexpr` works
    and produces 95 nets — the data is there in the schematic.
  * Removed stale backup files (`*.pre_*_backup`, `_autosave-*`,
    freerouting `*.dsn`, `~*.lck`, old `*-drc.rpt`) — they're all
    regenerable. Repo is cleaner.
- **iter 14 (2026-06-14)** — Fab pass + flipped 65 footprints from B.Cu
  to F.Cu (huge bug). Exported gerbers/drill/pos/BOM.
- **iter 13 (2026-06-14)** — Silk reorg: big mirrored DEFCON on back.
- **iter 12 (2026-06-13)** — Landed J10 USB-C + place_lib_footprint.py.
- **iter 11 (2026-06-13)** — DEFCON silk identity (first pass).
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
- [x] ~~Land J10 USB-C~~ (iter 12).
- [x] ~~Silk reorganization~~ (iter 13).
- [x] ~~Components to F.Cu, fab pass exported~~ (iter 14).
- [x] ~~Repo cleanup~~ (iter 15: removed stale backups).
- [ ] **CRITICAL BLOCKER**: PCB has no net declarations. Build
      `tools/sync_nets_from_sch.py`:
      1. Run `kicad-cli sch export netlist --format kicadsexpr ...`
      2. Parse out (net (code N) (name "X")) and each (node (ref R) (pin P))
      3. Add `(net N "name")` blocks at PCB top level (after the layers
         block, before footprints).
      4. For each pad, look up (ref, pin) → net code → add `(net code name)`
         inside the pad's s-expression.
      5. Without this, zones/routing/DRC are all broken.
- [ ] J31 microSD: flip to B.Cu (back side). Watch for collision with
      the big "DEFCON" wordmark — place microSD in the lower-right back
      area where it won't obstruct the silk.
- [ ] Wire J10 USB-C pads to nets (VBUS, GND, D+, D-, CC1, CC2, SHIELD).
      Currently 17 pads unconnected on J10. Use a Python script to set
      each pad's `(net "name")` based on the schematic's J10 connections.
- [ ] Hide the long "USB_C_Receptacle_GCT_USB4085" Value silk text on
      J10 (move it to F.Fab layer or hide the property).
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
