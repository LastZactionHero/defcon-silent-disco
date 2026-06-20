# IC schematic ↔ datasheet vetting

Scope: every active IC (and the USB-C receptacle) in `defcon_badge/*.kicad_sch`,
checked symbol-pin-by-pin against the manufacturer datasheet, and the
schematic net on each pin checked against the datasheet's recommended
connection. Connectivity was extracted directly from the schematic
s-expressions (not the PCB — the PCB netlist sync is known-lossy per
`STATE.md`).

Date: 2026-06-20 · Branch: `claude/ic-schematic-datasheet-vet-ygmix5`

## Verdict

| Ref | Part | Symbol pinmap vs datasheet | Connections | Severity |
|---|---|---|---|---|
| U3 | RP2040 | ✅ matches | ✅ (see notes) | LOW notes only |
| U2 | W25Q16JVUXIQ | ✅ matches | ✅ | clean |
| U10 | TP4056 | ✅ matches | ✅ | clean |
| U11 | ME6211C33M5G | ✅ matches | ✅ | clean |
| **U20** | **TM8211 DAC** | ❌ **WRONG — scrambled** | ❌ **mis-wired** | **CRITICAL** |
| U21 | TDA1308 | ✅ matches | ✅ | clean |
| U30 | TSOP4838 | ✅ matches | ✅ | minor note |
| LED20–23 | SK9822-EC20 | ✅ matches (EC20 variant) | ✅ | clean |
| Y1 | ABM8 12 MHz xtal | ✅ | ✅ | clean |
| J10 | USB-C 16P (UFP) | ✅ | ❌ **CC1 Rd missing** | **HIGH** |
| — | IR LED driver (D20/R30) | n/a | ⚠️ no transistor | MEDIUM |

---

## CRITICAL — U20 TM8211: symbol pin map does not match the datasheet

The custom `badge:TM8211` symbol declares this pin map:

| Pin | Symbol says | TM8211 / PT8211 datasheet | Net on that physical pin |
|---|---|---|---|
| 1 | VDD | **BCK** | `+3V3` |
| 2 | VLL (L out) | **WS** | `DAC_OUTL` (→C42→amp) |
| 3 | VRR (R out) | **DIN** | `DAC_OUTR` (→C43→amp) |
| 4 | VSS/GND | GND | `GND` ✅ |
| 5 | WS | **VDD** | `I2S_LRCK` |
| 6 | BCK | **LCH (L out)** | `I2S_BCK` |
| 7 | DIN | **NC** | `I2S_DIN` |
| 8 | NC | **RCH (R out)** | (unconnected) |

Datasheet pinout (Titan Micro TM8211, identical to Princeton PT8211):
**1=BCK, 2=WS, 3=DIN, 4=GND, 5=VDD, 6=LCH, 7=NC, 8=RCH.**

Only pin 4 (GND) happens to land correctly. As drawn the board will:

- drive the **VDD supply pin (5) with the LRCK logic signal** — the DAC has
  no real supply rail and is stressed by a ~44 kHz square wave on VDD;
- put **+3V3 statically on the BCK input (1)** and route the real bit clock
  `I2S_BCK` to the **left analog output (6)**;
- route the data line `I2S_DIN` to a **no-connect (7)**;
- take the audio outputs from pins 2/3 — which are actually the **WS and DIN
  inputs** — and feed the headphone amp from them;
- leave the real right-channel output (8) unconnected.

Net effect: **the DAC is non-functional and the audio chain is dead.** This is
the single most important finding.

Fix: correct the `badge:TM8211` symbol so pin numbers match the datasheet
(1 BCK, 2 WS, 3 DIN, 4 GND, 5 VDD, 6 LCH/out, 7 NC, 8 RCH/out), then re-attach
the existing nets to the correct pins (VDD→3V3, BCK/WS/DIN from the I2S bus,
LCH/RCH → the two 10 µF coupling caps). The surrounding passives (C40 100 n,
C41 10 µ decoupling; C42/C43 10 µ coupling; 47 k/100 k amp network) are all
fine — only the DAC pin assignment is wrong.

---

## HIGH — J10 USB-C: CC1 has no 5.1 kΩ pull-down (Rd)

A USB-C *device* (UFP) must present a 5.1 kΩ Rd to GND on **both** CC1 and CC2
so the host detects attach in either plug orientation.

- CC2 (B5) → R11 5.1 kΩ → GND ✅
- CC1 (A5) → **nothing.** R10 (the part labelled "USB-C CC1 pulldown", 5.1 kΩ)
  has **both of its pads tied to GND** in the schematic, so it is shorted out
  and CC1 floats.

Consequence: the badge enumerates/charges only when the cable is inserted in
the orientation that makes CC2 the active CC line; flipped, it is invisible to
the host. Fix: wire R10 between CC1 (A5) and GND (currently both ends are on
GND).

VBUS handling is correct — VBUS → TP4056 VCC only, with C20; it is **not**
fed to the 3V3 rail (matches `badge_hw_design.md`). D+/D− route through the
27 Ω series R3/R4 into the RP2040 ✅ (the PCB netlist drops R3.1/R4.1, but the
schematic itself is correct).

---

## MEDIUM — IR LED driver has no transistor; driven straight off GP9

`badge_hw_design.md` specifies "IR LED driven by S8050/2N7002 from GP9, 68 Ω →
~30 mA pulsed." The schematic has **no transistor** (only a comment mentions
S8050). D20 is wired `+3V3 → D20 → R30 → GP9`, i.e. the RP2040 GPIO sinks the
LED current directly, and R30 is **150 Ω**, not 68 Ω.

- Current ≈ (3.3 − ~1.3 V)/150 ≈ **13 mA**, which sits right at the RP2040's
  maximum 12 mA pad drive strength — marginal, and it loads the GPIO instead
  of a transistor.
- It is also far below the 30 mA the optical-tap link was sized for, so IR
  range/robustness will be well under design intent.

Fix (pick one): add the intended NPN/MOSFET low-side driver (LED to +3V3,
transistor sinks to GND, GP9 → base/gate through 1 kΩ, size R for ~30 mA), or
explicitly accept direct GPIO drive and document the reduced range. Either way
reconcile the schematic, BOM, and `badge_hw_design.md`.

---

## LOW / notes

- **RP2040 RUN (pin 26):** no external pull-up — only the (DNP) J33 debug
  header sits on the net. The RP2040 has an internal ~50 kΩ pull-up so the
  board *will* boot, but the datasheet/hardware-design-guide and this repo's
  own design doc ("RUN: 10 kΩ to 3V3") recommend an external 10 kΩ pull-up
  (+100 nF) for noise immunity on the routed RUN trace. Recommend adding it.
- **RP2040 ADC_AVDD (pin 43):** tied straight to +3V3. Works, but the design
  guide suggests a small ferrite/RC filter from IOVDD for clean ADC readings
  (VBAT_SENSE uses ADC0). Optional.
- **BOOTSEL:** R1 (1 kΩ) runs from flash CS (`QSPI_SS`) to a **dangling net** —
  the tactile BOOTSEL button to GND that `badge_hw_design.md` calls for is not
  in the schematic. First-flash still works (blank flash auto-enters BOOTSEL),
  but there is no manual BOOTSEL/unbrick button. (R2, the +3V3→CS pull-up, is
  DNF.)
- **TSOP4838 (U30):** OUT/GND/VS pinout correct, decoupled with C70 100 n +
  C71 10 µ. Vishay recommends an additional ~100 Ω series resistor in the Vs
  supply (with the cap) to suppress supply disturbance — nice-to-have, not
  required.
- **W25Q16 (U2):** USON-8 exposed pad (pad 9) is left unconnected — fine per
  datasheet (EP is not internally bonded; GND or float both acceptable).

## Things explicitly checked and found CORRECT

- RP2040: TESTEN (19) → GND ✅; DVDD (23/50) and VREG_VOUT (45) on +1V1 ✅;
  VREG_VIN (44), USB_VDD (48), IOVDD (1/10/22/33/42/49), ADC_AVDD on +3V3 ✅;
  6×100 nF IOVDD decoupling + 1 µF/10 µF bulk + 100 nF/1 µF on the 1V1 core ✅;
  USB D±  via 27 Ω ✅.
- Crystal: XIN→Y1 + 15 pF; XOUT→**1 kΩ series (R5)**→Y1 + 15 pF; case pins to
  GND — matches the RP2040 design guide ✅.
- W25Q16 QSPI: CS/IO0–IO3/CLK all correct, /WP and /HOLD driven as IO2/IO3 ✅.
- TP4056: TEMP→GND (correctly disables NTC sensing per datasheet), PROG→2.4 kΩ
  (≈500 mA), CE→3V3 (enabled), CHRG→100 kΩ pull-up→GP18, STDBY NC ✅.
- ME6211: VIN/EN tied to battery-switched node (always-on), VOUT→+3V3, 1 µF
  in/out ✅.
- TDA1308: dual non-inverting buffer with +IN→VGND, 47 k input / 100 k
  feedback (≈2.1× gain), 220 µF output coupling, VGND from 10 k/10 k + 10 µF ✅.
- SK9822-EC20: symbol matches the **EC20** pin order (1 VDD, 2 SDI, 3 CKI,
  4 SDO, 5 CKO, 6 GND — differs from the 5050 SK9822); chain DIN/CIN from MCU,
  DOUT/COUT daisy-chained, 10 nF local each ✅.

## Sources

- RP2040 RUN internal pull-up / external pull-up guidance — Raspberry Pi forums
  & RP2040 hardware design guidance.
- TP4056 TEMP-to-GND when NTC unused — TP4056 datasheet (Nanjing Top Power).
- TM8211 pinout (1 BCK, 2 WS, 3 DIN, 4 GND, 5 VDD, 6 LCH, 7 NC, 8 RCH) —
  Titan Micro TM8211 datasheet / Princeton PT8211 datasheet.
- ME6211 SOT-23-5 pinout — Nanjing Micro One ME6211 datasheet.
- SK9822-EC20 pinout — Normand/OPSCO SK9822-EC20 datasheet.
- USB-C UFP dual-CC 5.1 kΩ Rd requirement — USB Type-C spec / GCT USB4085.
