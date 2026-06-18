# Silent Disco Badge — Hardware Design v0.1

Target: ~$2.50 BOM ex-battery/SD at qty 500. 2-layer, standard spec (8/8 mil floor — stays in APCT standard pricing). Single-sided placement if layout allows; buttons and switch are the only things fighting for the front.

---

## Power tree

```
USB-C 5V ──→ TP4056 ──→ BAT+ (503450 LiPo, protected cell)
                              │
                        SS-12D00 slide switch
                              │
                          ME6211C33 ──→ 3V3 rail (everything)
```

- **TP4056** (ESOP-8, LCSC C16581): RPROG = 2.4 kΩ → 500 mA charge (0.5C on 1000 mAh). CE tied high. CHRG̅ (pin 7) → GP18 via 100k pullup to 3V3 so firmware can show charge state on the LEDs — no dedicated status LEDs.
- **Protected cell** — skip DW01/FS8205, the cell's PCM covers it.
- No load-sharing path. System always runs off the battery node; charging-while-playing slightly confuses TP4056 termination. Acceptable for a badge; note in docs "charges fastest when off."
- **ME6211C33M5G** (SOT-23-5, C82942): 1 µF in/out. 500 mA rated, system peak ~150 mA, fine.
- **VBAT sense:** 100k/100k divider → GP26/ADC0. Always connected; 16 µA standing drain is negligible vs self-discharge.
- **USB-C:** 16-pin mid-mount (e.g. GCT USB4520 or HQB equivalent TYPE-C-31-M-12). 5.1 kΩ on each CC to GND (UFP). VBUS → TP4056 only — do not feed VBUS to the 3V3 rail.

## RP2040 core

- **RP2040** (C2040) + **W25Q16JVUXIQ** 2 MB QSPI flash (C2843335). 2 MB is plenty: firmware + channel table; all audio lives on SD.
- **Crystal:** 12 MHz 3225, stock tolerance (software trim handles drift), 15 pF load caps, 1 kΩ series resistor per the RP2040 hardware design guide.
- VREG_VIN ← 3V3, VREG_VOUT → DVDD pins with 1 µF. 100 nF at every IOVDD pin, 1 µF bulk ×2.
- USB D+/D− through 27 Ω series resistors to the connector. No external pullups (internal).
- RUN: 10 kΩ to 3V3. No reset button.
- **BOOTSEL button:** tactile from flash CS to GND via 1 kΩ, back side of board. Needed for first flash and unbrick; after that, track loading is USB MSC so users never touch it.

### GPIO map

| GPIO | Function | Notes |
|---|---|---|
| GP0/GP1 | UART0 TX/RX | debug header, 3-pin |
| GP2 | SD SCK | SPI0 |
| GP3 | SD MOSI | SPI0 |
| GP4 | SD MISO | SPI0 |
| GP5 | SD CS | |
| GP6 | I2S DIN → DAC | PIO0 |
| GP7 | I2S BCK | PIO0, keep 6/7/8 contiguous for PIO side-set |
| GP8 | I2S WS (LRCK) | PIO0 |
| GP9 | IR_TX | via S8050, 68 Ω, 38 kHz PIO carrier |
| GP10 | LED SCK | SPI1, SK9822 clock |
| GP11 | LED MOSI | SPI1, SK9822 data |
| GP12 | BTN_CH | internal pullup, switch to GND |
| GP13 | BTN_VOL_UP | " |
| GP14 | BTN_VOL_DN | " |
| GP15 | IR_RX | TSOP output, active low |
| GP16 | SAO SDA | 4.7k pullups |
| GP17 | SAO SCL | " |
| GP18 | CHRG̅ sense | from TP4056 |
| GP19 | BTN_SYNC | internal pullup, switch to GND |
| GP26 | ADC0 VBAT | 100k/100k divider |

## Audio chain

```
RP2040 PIO I2S → TM8211 DAC → 10µF coupling → TDA1308 → 220µF coupling → PJ-320A jack
```

- **TM8211** (SOP-8) — the Shenzhen PT8211 clone, rated 2.0–5.5 V so it's happy at 3.3 V. **Do not sub a genuine PT8211 without checking — PT8211 datasheet wants ~5 V.** TM8211 takes LSBJ-format 16-bit I2S (justified, not standard I2S — firmware note: PIO program shifts WS timing by one BCK vs standard I2S).
- 100 nF + 10 µF decoupling at DAC Vcc.
- **TDA1308** (SOP-8) headphone amp, runs at 3.3 V:
  - Inputs: 10 µF coupling caps from DAC outs, 47 kΩ input resistors.
  - Gain: 100 kΩ feedback / 47 kΩ input ≈ 2.1×. Loudness headroom is the flagged risk — leave feedback Rs as discrete 0402s so gain is a resistor swap, not a respin.
  - Virtual ground: 10k/10k divider + 10 µF to the VREF pin.
  - Outputs: **220 µF / 6.3 V** electrolytic or large MLCC per channel to the jack. 220 µF into 32 Ω → −3 dB at 23 Hz; into cheap 16 Ω buds → 45 Hz. Don't cheap to 100 µF; this is a disco.
- **PJ-320A** 3.5 mm TRRS-style SMD jack — wire as TRS stereo, leave sleeve-detect unconnected.
- Layout: keep DAC/amp and their ground pour away from the SK9822 data lines and the IR LED driver (30 mA pulsed bursts); star the audio ground back at the LDO.

## Optical tap-to-sync (replaces RF)

Badges sync by touching face-to-face. No radio — at DEFCON specifically, any unauthenticated RF beacon **will** be spoofed for sport within the hour, and signing packets drags crypto/key management onto a $5 badge. Physical contact is proximity-authenticated for free, and the social mechanic ("we drifted — tap me") is the feature.

- **Link:** 940 nm IR LED + **TSOP4838**-class 38 kHz demodulating receiver (~$0.22 pair + driver). Not a bare photoresistor/phototransistor: LDRs are far too slow (tens of ms), and a bare PT makes you own the analog ambient-rejection problem in a room full of strobes. The TSOP is IR-remote tech — carrier-filtered, AGC'd, bulletproof, trivial firmware (NEC-style bursts).
- IR LED driven by S8050/2N7002 from **GP9**, 68 Ω → ~30 mA pulsed. TSOP out → **GP15** (active low).
- **Placement:** LED and receiver mirror-symmetric about the badge's vertical centerline, front face, so two badges pressed face-to-face cross-align LED↔receiver automatically in both directions. Badges themselves shade the link from ambient at contact.
- **Protocol:** every badge chirps `{version:u16, epoch_ms:u48, table_hash, CRC}` (~12 B, NEC-style framing, TSOP AGC needs burst gaps) every ~2 s. Hearing a higher version → adopt clock + version, pulse the SK9822s in unison with the peer — that shared flash is the sync confirmation and the moment of delight. No button, no mode: touch = sync.
- **Same-version contact → average the two clocks** (slew-limited to ±150 ms per contact so a hacked badge can't yank the network). This is what makes peer taps *maintain* sync between staff passes — pairwise averaging is a consensus algorithm; clusters that tap converge to their mean. Without this, only organizer contact corrects drift.
- **Software drift trim:** on repeat contact with the same peer (or any correction event), estimate own ppm error from accumulated offset and trim the tick rate. Two taps gets a badge from ±30 ppm to single digits — makes the ±10 ppm crystal optional rather than required.
- **Root of trust:** a couple of organizer badges are the only ones that increment `version` (long-press combo). Everyone else propagates. Staff circulating keeps the room coherent.
- **Drift budget (be honest about this):** stock 20–30 ppm crystals → up to ~200 ms relative drift/hr between two badges worst case, but software ppm trim calibrates out static offset after 2–3 taps, leaving only temperature drift (small indoors). Stock crystal is fine — don't pay for tighter tolerance; trim fixes what tolerance specs, and nothing cheap fixes tempco. Flash sync is cluster-coherent — groups that tap each other stay locked, which is the aesthetic anyway. Friends pulse together.

## LEDs

- **4× SK9822 (5050)**, chained, SPI1 clock+data. (Switched from the on-hand EC20 2020 to the larger 5050 for a brighter, more decorative disco look — see PCB footprint badge:LED_SK9822_5050, datasheet-verified pinout 1=DIN 2=CIN 3=GND 4=VDD 5=COUT 6=DOUT.) 5 V part driven at 3.3 V logic and 3.3 V supply — SK9822 runs visibly fine at 3.3 V supply with slightly shifted color balance; data threshold is met since VDD = logic rail. ~10 nF per LED.
- Brightness budget: global brightness register capped at ~25% in firmware. 4 LEDs full white at 3.3 V would eat the battery and blind people at eye level on a lanyard.

## Buttons / switch

- 4× **TS-1187A** 6 mm tactile (CH / VOL+ / VOL- / SYNC; silkscreen labels), to GND, internal pullups. Front face, 2×2 grid (CH·SYNC top, VOL+·VOL- bottom) — a single row of 4 doesn't fit between USB-C and the corner mounting hole.
- 1× **MSK-12C02 / SS-12D00** slide power switch.
- 1× BOOTSEL tactile, back side.

## SAO header

- Standard SAO v1.69: 2×3 female header, 3V3 / GND / SDA / SCL / GPIO×2 → use GP20/GP21 for the two SAO GPIOs (add to GPIO map). Costs a connector, buys DEFCON cred.

## Connectors summary

USB-C 16P · PJ-320A · microSD push socket (e.g. TF-PUSH, ~$0.10) · JST-PH 2-pin for battery · SAO 2×3 · 3-pin debug UART (unpopulated).

---

## BOM (qty 500, est.)

### Active / connectors / electromech

| Ref | Qty | Part | Package | Est. |
|---|---|---|---|---|
| U1 | 1 | RP2040 | QFN-56 | $0.80 |
| U2 | 1 | W25Q16JVUXIQ 2 MB QSPI flash | USON-8 | $0.20 |
| U3 | 1 | TM8211 stereo DAC (PT8211 clone, 2.0–5.5 V) | SOP-8 | $0.15 |
| U4 | 1 | TDA1308 headphone amp | SOP-8 | $0.25 |
| U5 | 1 | TP4056 Li-ion charger | ESOP-8 | $0.08 |
| U6 | 1 | ME6211C33M5G LDO | SOT-23-5 | $0.03 |
| U7 | 1 | IRM-H638T / TSOP4838-class 38 kHz IR RX | side-view | $0.15 |
| Q1 | 1 | S8050 NPN (IR LED driver) | SOT-23 | $0.01 |
| D1 | 1 | 940 nm IR LED | 0805 side-fire | $0.02 |
| LED20–23 | 4 | SK9822 | 5050 | switched from EC20 2020 for brightness |
| Y1 | 1 | 12 MHz crystal, stock tol. | 3225 | $0.08 |
| J1 | 1 | USB-C 16P mid-mount | — | $0.10 |
| J2 | 1 | PJ-320A 3.5 mm jack | SMD | $0.08 |
| J3 | 1 | microSD push socket | — | $0.10 |
| J4 | 1 | JST-PH 2P (battery) | SMD RA | $0.04 |
| J5 | 1 | SAO 2×3 female header | THT | $0.06 |
| J6 | 1 | debug UART 1×3 | THT | DNP |
| SW1–3 | 3 | TS-1187A tactile (CH, V+, V−) | SMD | $0.09 |
| SW4 | 1 | BOOTSEL tactile | SMD | $0.01 |
| SW5 | 1 | MSK-12C02 slide power switch | SMD | $0.03 |

### Passives (0402 unless noted)

| Value | Qty | Where |
|---|---|---|
| 27 Ω | 2 | USB D+/D− series |
| 68 Ω | 1 | IR LED current set |
| 1 kΩ | 3 | crystal series, BOOTSEL, Q1 base |
| 2.4 kΩ | 1 | TP4056 PROG (500 mA) |
| 4.7 kΩ | 2 | SAO I2C pullups |
| 5.1 kΩ | 2 | USB-C CC |
| 10 kΩ | 3 | RUN pullup, amp vground divider ×2 |
| 47 kΩ | 2 | amp input |
| 100 kΩ | 5 | amp feedback ×2, VBAT divider ×2, CHRG̅ pullup |
| 15 pF | 2 | crystal load |
| 10 nF | 4 | SK9822 local |
| 100 nF | 10 | IOVDD ×6, DAC, TSOP, TP4056, misc |
| 1 µF | 5 | VREG, DVDD, LDO in/out, bulk |
| 10 µF | 6 | DAC bulk, DAC→amp coupling ×2, vground, charger in/out |
| 220 µF 6.3 V | 2 | headphone output coupling (electrolytic) |

### Rollup

| Group | Est. |
|---|---|
| ICs | $1.66 |
| Connectors | $0.38 |
| Electromech (buttons/switch) | $0.13 |
| Crystal | $0.08 |
| Passives | ~$0.25 |
| **Board parts subtotal** | **~$2.50** |
| 503450 1000 mAh protected LiPo | $1.80 |
| 512 MB–1 GB bulk microSD | $0.70 |
| **All-in (ex-PCB)** | **~$5.00** |

~58 placements, 15 unique passive values, all 0402-or-larger / SOP / SOT — deliberately easy on the Lumen line. Only THT items are the SAO header and (optional) battery connector and debug UART.

Verified LCSC C-numbers: RP2040 C2040, W25Q16 C2843335, TP4056 C16581, ME6211C33 C82942. Everything else — verify at order time, don't trust from memory.

---

## v1 validation order (before layout freeze)

1. **Audio pipeline on a Pico + TM8211 breakout:** minimp3 decode of 192k CBR + SPI SD streaming + PIO I2S, both cores. This is the only real firmware risk.
2. **TDA1308 loudness** into 16 Ω earbuds at 3.3 V, gain 2×. If quiet, bump gain to 3–4× and check clipping.
3. **IR tap link:** two Picos + TSOP/IR LED pairs face-to-face — confirm clean decode at contact and ~2 cm, confirm rejection with a strobe pointed at it. Then measure real crystal drift between two boards over 2 hrs to size the re-tap interval honestly.
4. SK9822 at 3.3 V supply — confirm acceptable color at 25% brightness.

## Layout notes

- Badge outline is free real estate — front face: 4 buttons (2×2 grid) bottom edge, jack top or bottom edge (cable hangs down → bottom), LEDs spread across front, art everywhere else.
- All silicon on back except LEDs if you want a clean front. Single-side placement target: put LEDs on back firing through FR4 windows? No — reverse-mount adds cost; two-side placement is fine, it's your own line.
- IR LED + TSOP front face, mirror-symmetric about vertical centerline (face-to-face mating cross-aligns them). Audio lower left, USB/charge lower right, SD back center.
