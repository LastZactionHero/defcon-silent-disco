# STACKUP_SPEC — D1 4-layer rework (committed BEFORE implementation)

The board is 4-copper but everything physical is a **2-layer RP2040 dev-board porting artifact**:
thickness 1.0mm, NO real stackup/dielectric block, In1=full GND + In2=full +3V3 copied from the
dev board, a loose F.Cu GND zone with no B.Cu counterpart, all 3 zones unfilled. The user
directed reworking this. Do it as a tool: `routing_phase/tools/rework_stackup.py` (pcbnew,
single-writer). Numbers below are from the engine-architecture research (JLCPCB published
JLC04161H-3313 data + Hammerstad/IPC-2141 microstrip; verify USB width in JLC's calculator at order).

## Target stackup — JLC 4-layer 1.6mm (JLC04161H-3313)
| Layer | Assignment | Copper | Dielectric to next |
|---|---|---|---|
| F.Cu  | signal + GND fill (USB pair, most signals) | ~1oz fin. | 3313 prepreg **0.0994mm**, Dk 4.1 |
| In1.Cu | **solid GND plane, unbroken** (return reference for both signal layers + USB) | 0.5oz | FR-4 core **1.265mm**, Dk 4.6 |
| In2.Cu | **+3V3-dominant pour** + a little slow signal where F/B congests | 0.5oz | 3313 prepreg **0.0994mm**, Dk 4.1 |
| B.Cu  | signal + GND fill (near-empty today → secondary signal layer) | ~1oz fin. | — (board ≈1.6mm) |

Rationale: In1 solid GND is the reference that matters (return current + USB). In2 as a full +3V3
plane is wasteful (only 47 +3V3 pads, ~150mA, ME6211 rated 500mA, local decoupling at each IC) —
demote it to a +3V3-dominant *mixed* pour that doubles as routing relief, but keep +3V3 continuous
under U3 (RP2040), U2 (flash), U11 (LDO). F.Cu/B.Cu GND pours stitched to In1 give shielding/return.

## Zone plan (after deleting the 3 artifact zones)
- **In1.Cu**: GND, full solid plane, outline inset ~0.3mm (min copper-edge clearance), priority 0.
- **In2.Cu**: +3V3 dominant pour over the digital/power region, priority 0; + optional secondary
  GND pour priority 1 in +3V3-free areas (return stitching).
- **F.Cu**: GND pour in routing gaps, priority 0, stitched to In1.
- **B.Cu**: GND pour in routing gaps, priority 0, stitched to In1.

## Impedance / widths
- **USB D+/D-** (the ONLY controlled-impedance net): edge-coupled microstrip on F.Cu over In1 GND
  through the 0.0994mm 3313 prepreg → **width 0.17mm, gap 0.13mm** ≈ 89Ω diff (0.15mm gap ≈ 91.5Ω).
  Replace the stored 0.8mm (a 2-layer value). Keep tightly coupled, length-matched, over solid In1
  GND with NO plane split under the pair; the two 27Ω series Rs (R3/R4) stay in-line.
- **Default signal 0.15mm** over In1 GND ≈ 55Ω single-ended — fine for QSPI/I2S/SK9822/SD/etc.
  (no controlled impedance required). No change except USB.
- Power widths: see `routing_rules.md` (VBUS/BAT/BAT_SW 0.5mm, IR drive 0.3mm, +1V1 0.3mm, audio
  output 0.3mm; +3V3/GND ride planes via taps).

## Rework steps (rework_stackup.py — pcbnew, writer-lock-guarded)
1. Set board thickness 1.0→1.6mm (`SetBoardThickness(pcbnew.FromMM(1.6))` or setup thickness).
2. Write a real physical stackup block for JLC04161H-3313 with the dielectric heights/Dk above.
   (Hand-writing the stackup via the Python API can trip the wx PROPERTY_ENUM asserts — prefer the
   board-setup preset if interactive; otherwise write the `(stackup ...)` block carefully and verify
   the board still loads via `kicad-cli pcb drc`.)
3. In `(layers ...)`, set In2.Cu type to `mixed` (was power "+3V3"); keep In1.Cu as power "GND".
4. Delete the 3 artifact zones (`for z in list(b.Zones()): b.Remove(z)` — lossless, all unfilled).
5. Recreate zones per the zone plan (polygons = board outline inset ~0.3mm).
6. Fix the USB_DIFF_90 netclass in `defcon_badge.kicad_pro`: change the patterns from the
   non-existent `/USB_D+` `/USB_D-` to the REAL nets `/MCU_Core/USB_DP`, `/MCU_Core/USB_DM` (and
   add the connector-side `Net-(U3-USB_DP)`, `Net-(U3-USB_DM)`); set `diff_pair_width` 0.8→0.17,
   `diff_pair_gap` 0.13 (0.15 ok).
7. `pcbnew.ZONE_FILLER(b).Fill(b.Zones())`, save, then `kicad-cli pcb drc` with the sibling
   `.kicad_pro` PRESENT (per the measure-needs-kicad_pro lesson) to confirm clearance/edge clean
   on the unrouted board before routing adds tracks.

## D1 exit gate (from HARNESS): stackup correct, zones fill clean, USB netclass fixed, unrouted
board DRC clean of NEW stackup/zone errors, baseline measure row, `unconnected_divergence==0`.
