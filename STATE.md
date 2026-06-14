# Iteration state

## Current focus
**STOPPED at iter 29 — natural completion.** Board is placement-complete,
silked, net-synced, zone-filled, fab-exported, documented, licensed.
Routing is the only major remaining item and is the user's call
(blocked by no JRE). See `README.md` § "Known gaps" for the remaining
TODOs the loop chose not to attempt (schematic ERC, hand-routing,
schematic J10 fix).

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
- **iter 29 (2026-06-14)** — Wrap-up commit, loop stopped.
- **iter 28 (2026-06-14)** — Back iso re-rendered with floor shadow.
- **iter 27 (2026-06-14)** — 2400×1500 hero render with floor shadow.
- **iter 26 (2026-06-14)** — MIT LICENSE.
- **iter 25 (2026-06-14)** — microSD rotated 180° — slot opens to bottom edge.
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
- [x] ~~Build net sync tool + add ground zones~~ (iter 16).
- [x] ~~Wire J10 USB-C pads~~ (iter 17: manual UFP mapping applied).
- [ ] Note: the schematic's net assignment for J10 was wrong — the
      netlist exported A1/A4/A5/A9/A12/B1/B12 all as `/Power/CC2` instead
      of separate GND/VBUS/CC nets. Iter 17 hard-coded the correct UFP
      mapping in the PCB; the schematic still has the bug for future fixes.
- [ ] Routing pass. With nets + zones in place, the ratsnest is real.
      Either: (a) install JRE and run freerouting on the exported DSN,
      (b) hand-route the critical USB/SPI/I2C/audio nets via Python
      gr_line additions, (c) leave the PCB as zones-only and let the
      user finish in KiCad.
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
See HARNESS.md "Definition of done (overall)". STOPPED at iter 29.

## Session summary (iter 1 → iter 29)
1. **Tooling foundation** — render_pcb.sh, move_components.py, set_outline.py,
   check_footprints.py, place_lib_footprint.py, flip_footprint.py,
   sync_nets.py, patch_j10_nets.py, Makefile.
2. **Board outline** — 86×54mm credit-card with 3mm rounded corners.
3. **Component placement** — 79 footprints on F.Cu, 1 (microSD) on B.Cu.
   MCU cluster center, LEDs top, audio bottom-left, power right, IR left,
   buttons bottom, USB-C bottom-center.
4. **Critical bug fixes** — Discovered + flipped 65 footprints accidentally
   placed on B.Cu by the original code generator. Discovered + worked
   around KiCad stripping synthetic top-level `(net N "name")` decls
   on save. Documented J10 USB-C schematic wiring bug + patched the PCB
   with correct UFP mapping.
5. **Silk identity** — DEFCON wordmark (mirrored size-5 on back, smaller
   above LEDs on front), chevrons + accent rules + corner brackets
   framing both sides, flavor text (0xC0FFEE, @LZH, PRESS A FOR PARTY,
   DC32 BADGE by LZH, github URL).
6. **Functional fill** — Sync nets from schematic (95 nets, 246+14 pad
   net assignments). GND zone on In1.Cu + B.Cu, +3V3 zone on In2.Cu.
7. **Documentation** — README.md with hero + iso + plan renders,
   schematic.pdf, fab/README.md, fab/bom.csv, fab/pos.csv, MIT LICENSE.
8. **Stopped** — Routing blocked (no JRE), schematic ERC fixes risky;
   handed off as a placement-complete fab-ready-minus-routing board.
