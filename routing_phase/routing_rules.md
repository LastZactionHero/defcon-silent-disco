# Routing rules — codified checklist (READ EVERY ITERATION)

This board's net-level routing constraints, condensed from the net-plan research +
`badge_hw_design.md`. The design doc and IPC tables win where they conflict. Distances are
starting points. The board: 88×54mm, 4-layer (F.Cu sig / In1 GND / In2 +3V3-mixed / B.Cu sig),
~62 signal nets, USB the only controlled-impedance net. GND(89 pads)/+3V3(47 pads) ride the
planes — they are NOT routed as traces; each pad drops a via to its plane.

## Order of routing (criticality first, on empty copper)
1. **Critical/structured first:** QSPI flash bus, crystal XIN/XOUT loop, USB diff pair, I2S bus.
2. **Other buses:** SD/SPI0, SAO I2C, SK9822 LED clock/data.
3. **Power stubs** off the planes (LDO out, charger in/out, audio bulk), VBAT_SENSE.
4. **Loose singletons last** into the room that remains.
Freeze each routed net (route_db) as an obstacle for the next — concentrate any ugliness on the
least-important nets, keep the important ones straight.

## Track-width classes
- **Default signal 0.15mm** (~6mil, ≈55Ω over In1 GND): all GPIO/QSPI/I2S/SPI/SAO-I2C/IR/sense/
  button nets. Fits the RP2040 QFN-56 escape (0.2mm pads, 0.4mm pitch).
- **USB D+/D- 0.17mm / gap 0.13mm** diff pair (≈90Ω) — NOT the stored 0.8mm. See STACKUP_SPEC.
- **VBUS, BAT, BAT_SW 0.5mm** (up to 0.6–0.8 where room): 500mA charge + full system current.
- **IR drive (R30 68Ω→D20, D20 cathode/Q1) 0.3mm**: 30mA pulsed 38kHz — keep the loop SMALL.
- **+1V1 (RP2040 VREG_VOUT→DVDD) 0.3mm**: short local low-impedance run near U3.
- **Audio JACK_L/R (220µF C45/C46→PJ-320A) 0.3mm**: tens-of-mA peaks into 16–32Ω.
- **+3V3 / GND: planes.** Only local taps/stubs to the plane need widening (0.4mm taps + vias).

## Critical nets — how to handle
- **USB D+/D- (J10↔R3/R4 27Ω↔U3):** diff pair, route together on F.Cu over solid In1 GND the whole
  way (NO plane split under it), keep short (~21mm), length-match within ~0.5mm, symmetric corners,
  27Ω Rs in-line near U3. Keep away from the crystal and the SK9822 clock.
- **Crystal Y1 XIN/XOUT + C2/C3 loads + R5:** TINY loop, short fat-ish (0.2mm) traces, cap grounds
  stitched to In1 with vias AT the pads, flood F.Cu GND around the oscillator. Most EMC-sensitive
  net — keep USB + LED clock out of this corner.
- **QSPI (U3↔U2, ~8.9mm):** compact 6-bit bus on F.Cu in the U3↔U2 channel, no vias, SCLK central,
  short BOOTSEL/SS stubs (R1/R2). Easiest sub-bus.
- **I2S (GP6/7/8, U3↔U20 DAC):** 3-wire bus on F.Cu over GND, kept together; route on the U3 side
  facing the audio block; keep away from LED_SCK/LED_DAT and IR drive (design-doc audio isolation).
- **SK9822 LED (SPI1 GP10/11 + daisy-chain across the top, ~48mm span):** LED_SCK/LED_DAT to LED20
  then DOUT/COUT 20→21→22→23 along the top edge over a GND reference; sharp clock edges — keep the
  return tight; 10nF local per LED. Keep this clock away from the audio block + crystal.
- **SD/SPI0 (GP2-5, U3↔J31, ~27mm):** 4-wire bus grouped, over GND; drop to B.Cu via a via pair if
  F.Cu congests near U3 south. SD_CD via R42 pullup.
- **SAO I2C (GP16/17→J30, ~22mm):** SDA/SCL to J30 (far left); tie R40/R41 pullup tops to +3V3
  (via each). Low priority — may use B.Cu; route last.
- **Audio web (U20 DAC→couple→U21 amp→220µF→J20):** ANALOG island, keep on the right-center cluster,
  route SHORT over continuous In1 GND (the plane gives the quiet star ground automatically). Keep
  LED clock + IR drive physically OUT of this region; do not run them under the amp. VGND local at U21.
- **VBAT_SENSE (GP26/ADC0 via R14/R15 100k/100k):** high-Z — keep short, over GND, away from LED
  clock/IR/USB. **~CHRG (TP4056→R13→GP18):** slow status, route last, any layer.

## Via strategy
Default via 0.6mm pad / 0.35mm drill. Uses: (1) signal layer-change F.Cu↔B.Cu where F.Cu congests
near U3 (B.Cu is mostly empty → expect few); (2) GND stitch at every decap ground pad into In1; a
3×3/4×4 GND-via array under the RP2040 EP (pad 57) for thermal+return; a GND-via ring around the
crystal; (3) +3V3 stitch from ME6211 VOUT + each bulk/decap 3V3 pad into In2; (4) structured
plane-stitch GND vias tying F.Cu/B.Cu GND pours to In1 near USB/crystal/IR loop/LED-clock + a board-
edge ring. Keep vias STRUCTURED/gridded, not random (aesthetic goal). Via-in-pad OFF.

## Signal-group zones (already placed; route within these clusters)
- **MCU core** (U3+U2+Y1+R1/R2/R5/R6+decaps): tightest, route FIRST, local on F.Cu over GND. EP via array.
- **USB/charge/power** (J10, R3/R4, R10/R11 CC, U10, R12, BAT/BAT_SW, U11): lower-center-right.
- **Audio** (U20, U21, couplings, R20-25, J20, VGND): right-center ANALOG island.
- **LED+IR optical** (LED20-23 top, D20+R30+Q1 far right, U30 far left): the noisy aggressors —
  keep separated from the audio island.
- **Expansion/housekeeping** (J30 SAO, J31 SD, buttons, ~CHRG, VBAT_SENSE, debug UART): route LAST;
  free to use empty B.Cu.
