# IC schematic ↔ datasheet vetting (branch: `routing-phase`)

Scope: every active IC + the USB-C receptacle in the `routing-phase`
schematic (`defcon_badge/*.kicad_sch`, tip `573ebae`). Connectivity was
extracted directly from the schematic s-expressions and each custom symbol's
pin-number→name map was checked against the manufacturer datasheet.

Date: 2026-06-20

> **Correction:** an earlier version of this file vetted a branch cut from
> `main` (2026-06-15), which predates `49a05f8 "fix TM8211 DAC + SK9822
> pinouts"` and `5bf811d "fix +3V3 power-tree"`. Those stale findings
> (scrambled TM8211, missing CC1 Rd, missing RUN pull-up) are **already fixed
> on `routing-phase`** and do **not** apply. This version supersedes it.

## Verdict — `routing-phase`

| Ref | Part | Symbol vs datasheet | Connections | Status |
|---|---|---|---|---|
| U4 | RP2040 | ✅ | ✅ | clean (1 minor) |
| U3 | W25Q16JVUXIQ | ✅ | ✅ | clean |
| U1 | TP4056 | ✅ | ✅ | clean |
| U2 | ME6211C33M5G | ✅ | ✅ | clean |
| U5 | TM8211 DAC | ✅ **now matches** | ✅ | clean |
| U6 | TDA1308 | ✅ | ✅ | clean |
| U7 | TSOP4838 | ✅ | ✅ | minor note |
| LED1–4 | SK9822(-EC20) | ✅ (datasheet-confirmed) | ✅ | clean |
| Y1 | ABM8 12 MHz | ✅ | ✅ | clean |
| J1 | USB-C 16P (UFP) | ✅ | ✅ | clean |
| D1/R22 | IR LED driver | n/a | ⚠️ direct GPIO drive | MEDIUM |

No board-killing issues found on this branch. The only substantive item is the
IR LED drive; the rest are minor/optional.

---

## MEDIUM — IR LED driven straight off the GPIO (no transistor)

`D1` (940 nm IR LED) is wired `+3V3 → D1 → R22 (150 Ω) → IR_TX (GPIO)`. There is
**no driver transistor**, even though `badge_hw_design.md` and the LEDs_IR sheet
comment both still say *"940 nm IR LED via S8050 + 68 Ω."*

- Sink current ≈ (3.3 − ~1.3 V)/150 ≈ **13 mA**, just over the RP2040's
  maximum **12 mA** configurable pad drive strength — marginal, and it loads
  the GPIO directly instead of a transistor.
- It's also well under the ~30 mA the optical-tap link was sized for, so IR
  range/robustness will be below design intent.

Recommend one of: (a) add the intended low-side NPN/MOSFET (LED→+3V3,
transistor sink to GND, GPIO→base/gate via 1 kΩ, R sized for ~30 mA), or
(b) explicitly accept reduced-range direct drive and update the design doc +
schematic comment so they stop referencing a non-existent S8050/68 Ω.

---

## SK9822 — confirmed correct (datasheet provided)

Resolved against the SK9822 datasheet pinout (`1 SDI, 2 CKI, 3 GND, 4 VDD,
5 CKO, 6 SDO`). The `badge:SK9822` symbol (`1 DIN, 2 CIN, 3 GND, 4 VDD,
5 COUT, 6 DOUT`) matches, and the footprint's **local** pad geometry lines up
exactly with the datasheet top view (pad 1 = bottom-right = SDI … pad 6 =
bottom-left = SDO), same handedness (CCW) — **no mirror**. The part is placed
with `rot=180`, which only rotates the package on the board (pad 1 appears at
top-left in the layout) without changing the pad↔pin correspondence. Net
connections give the correct chain direction (LEDn DOUT/COUT → LEDn+1 SDI/CKI).
✅

---

## Minor / optional

- **TSOP4838 (U7):** OUT/GND/VS correct; decoupled with 100 nF + 10 µF. Vishay
  recommends an additional ~100 Ω series resistor in the Vs line (with the cap)
  to suppress supply disturbance. Nice-to-have.
- **RP2040 ADC_AVDD (pin 43):** tied straight to +3V3. Works; the design guide
  suggests a ferrite/RC filter from IOVDD for cleaner ADC (VBAT_SENSE uses
  ADC0). Optional.

## Checked and CORRECT on `routing-phase`

- **U5 TM8211** — symbol now `1 BCK, 2 WS, 3 DIN, 4 GND, 5 VDD, 6 LCH, 7 NC,
  8 RCH`, exactly per the Titan Micro datasheet; nets land right (BCK←I2S_BCK,
  WS←I2S_LRCK, DIN←I2S_DIN, VDD←+3V3, LCH/RCH→10 µF coupling caps, NC open). ✅
- **J1 USB-C (UFP)** — **both** CC1 and CC2 now carry their own 5.1 kΩ Rd to
  GND (R1, R2). VBUS→TP4056 only (not the 3V3 rail), with C1; D+/D− via 27 Ω
  series R13/R14 into the RP2040. ✅
- **U4 RP2040** — TESTEN(19)→GND; DVDD(23/50)+VREG_VOUT(45) on +1V1;
  VREG_VIN(44)/USB_VDD(48)/ADC_AVDD(43)/IOVDD all on +3V3; **RUN(26)→10 kΩ
  (R15)→+3V3** pull-up now present; 6×100 nF IOVDD + 1 µF/1 µF bulk, 100 nF×2 +
  1 µF on 1V1; USB D± via 27 Ω. ✅
- **Crystal** — XIN→Y1+15 pF; XOUT→**1 kΩ series (R12)**→Y1+15 pF; case→GND. ✅
- **U3 W25Q16** — CS/IO0–IO3/CLK correct; /WP, /HOLD driven as IO2/IO3. ✅
- **U1 TP4056** — TEMP(1)→GND (NTC disabled, per datasheet); PROG→2.4 kΩ
  (≈500 mA); VCC→VBUS; CE(8)→VBUS (enabled); CHRG→100 kΩ pull-up→GPIO;
  STDBY open; **EP(9)→GND** added. ✅
- **U2 ME6211** — VIN/EN→battery-switched node (always-on), VOUT→+3V3,
  1 µF in/out. ✅
- **U6 TDA1308** — dual non-inverting buffer, +IN→VGND, 47 k in / 100 k fb
  (≈2.1×), 220 µF output coupling, VGND from 10 k/10 k + 10 µF. ✅
- **BOOTSEL** — flash CS via 1 kΩ (R10) to a `BOOTSEL` **test point (TP1)**,
  not a button (short-to-GND to enter the bootloader). Functional. ✅

## Sources

- TM8211 pinout (1 BCK…8 RCH) — Titan Micro TM8211 / Princeton PT8211 datasheet.
- TP4056 TEMP-to-GND when NTC unused — TP4056 datasheet (Nanjing Top Power).
- ME6211 SOT-23-5 pinout — Nanjing Micro One ME6211 datasheet.
- RP2040 RUN internal pull-up + external 10 k recommendation; ADC_AVDD filter —
  RP2040 datasheet / hardware design guidance.
- USB-C UFP dual-CC 5.1 kΩ Rd — USB Type-C spec.
- SK9822 pinout — Normand/OPSCO SK9822 datasheet (EC20 variant unconfirmed via
  sandbox).
