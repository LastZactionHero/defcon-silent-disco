# Schematic-cleanup LEDGER — append-only

Entry prefixes: `FIX:` `BLOCKER:` `REVIEW:` `FINDING:`

[2026-06-16] S0 — INSTRUMENT + BASELINE. User: deep-dive the schematic (done early
in the AI process), industry-standard + tool-driven + repeatable, then triage.
Built `tools/sch_health.py` — AUTHORITATIVE health metrics from `kicad-cli sch erc`
+ `kicad-cli sch export netlist` (NOT the over-merging analyzer; Resolution 1).
BASELINE (metrics.jsonl S0): erc 6 err / 60 warn; power_rails_fragmented=1;
power_pins_not_driven=5; pin_to_pin=1; single_pin_nets=7; all 5 gates FAIL.

[2026-06-16] FINDING(P1, board-killer) — +3V3 RAIL FRAGMENTED into 5 disconnected
nets: `+3V3` (MCU/flash, 22 pins) | `/Power/+3V3` (LDO U11.5 output — the SOURCE,
reaching only C23+R13) | `/IO/+3V3` (SAO,microSD) | `/Audio/+3V3` (DAC,amp) |
`/LEDs_IR/+3V3` (LEDs,IR). ROOT CAUSE: MCU_Core declares +3V3 with 5 GLOBAL
`power:+3V3` symbols, but Audio/IO/LEDs_IR/Power declare it with sheet-local
`(label "+3V3")` (0 power symbols) and NO sheet exposes +3V3 as a hierarchical
pin — so the LDO output never reaches any load and each subsystem rail floats.
The analyzer MISSED this (over-merged to one 3.3V rail) — Resolution 1 vindicated.
REPEATABLE FIX (Resolution 2): in the generator, emit `power:+3V3` global symbols
(not local labels) for every rail in every sheet; regenerate; re-measure.
Likely the SAME defect to check on +1V1 and any other rail.

[2026-06-16] FINDING(P1) — 5 ERC power_pin_not_driven (J31.4 VDD, J31.6 VSS, U2.8
VCC, U20.1 VDD, LED20.1 VDD): one representative undriven pin per fragmented island
+ a GND PWR_FLAG gap (J31.6). Expected to mostly resolve once +3V3 is unified and a
PWR_FLAG sits on the LDO output / GND.

[2026-06-16] S0 — multi-dimension audit (5 dims + synthesis, all P0/P1 adversarially
re-verified against kicad-cli) — PRIORITIZED DIAGNOSIS:
  #1 P0 — +3V3 fragmented into 5 nets, LDO reaches ZERO loads, board DEAD. Root: child
     sheets emit +3V3 via SheetGen.label_at_pin() (kicad_sheet_gen.py:337, sheet-local
     label) while MCU_Core uses global power: symbols (power_at_pin, :360); +3V3 never a
     hier pin. Call sites: gen_power_sheet 164/183/186, gen_audio 104/106/108/136/174,
     gen_io 72/83/85/107, gen_leds_ir 83/85/110/127/130/132, inject_dev_header J33.2.
  #2 P1 — TM8211 DAC (U20) symbol PIN NUMBERING wrong vs PT8211 datasheet (gen_badge_lib:
     1=VDD..5=WS.. should be 1=WS,2=BCK,3=DIN,4=VDD,5=VOUTL,6=AGND,7=VOUTR,8=NC). Audio
     dead. ERC-INVISIBLE (self-consistent wrong symbol) — only datasheet cross-ref catches.
  #3 P1 — SK9822 LED (LED20-23) uses 4-pad SK6812 footprint for a 6-pin part
     (gen_badge_lib LED_SK6812_PLCC4); CIN/COUT clock pads don't exist → string
     unbuildable. ERC-INVISIBLE (surfaces only at PCB pad/pin sync).
  #4 P1 — GND has no PWR_FLAG/power_out → ERC power_pin_not_driven (J31.6 VSS). Add one
     #FLG_GND in gen_power_sheet.
  #5 P1 — redundant #FLG_BAT (gen_power_sheet:198-200) on TP4056 BAT output → pin_to_pin
     (two power outputs). Delete it.
  #6 P2 — RUN has no external 10k→+3V3 (design-intent deviation; relies on internal PU +
     DNP header J33). Add R6.
  #7 P2 — microSD card-detect (J31.9/pad10) unwired + DAT1/DAT2 (J31.1/.8) no pull-ups.
  #8 P2 — TP4056 symbol is plain SOIC-8, omits EP thermal pad (part is ESOP-8, EP=GND).
  #9 P3 — 60 ERC warnings: 36 off-grid + 9 lib_symbol_mismatch + 7 isolated_label + 6
     unconnected_wire_endpoint + 2 footprint_link (TP1/TP2 empty footprint). Cosmetic
     except TP1/TP2 before fab; the 6 unconnected_wire_endpoint need a visual confirm.
  #10 P3 — 7 single-pin nets = intentional RP2040 GPIO spares (GP22-25,27-29) → WAIVE.
  REPEATABLE FIX ORDER (generator-first, then regenerate + net-only re-sync via
  sync_nets_pcbnew.py, then re-measure to gates): (1) centralize rail emission through a
  rail_at_pin()/global power: symbol + make label_at_pin raise on rail names [fixes #1 +
  4 of 5 ERC power errors]; (2) gen_power_sheet: drop #FLG_BAT, add #FLG_GND [#4,#5];
  (3) gen_badge_lib: TM8211 renumber, SK9822 6-pad fp, TP4056 EP [#2,#3,#8]; (4) RUN 10k +
  microSD CD/pull-ups [#6,#7]; (5) REGENERATE; (6) sch_health to gates; (7) P3 cleanup.
  TRIAGE (what worked/didn't): kicad-cli = authoritative truth (caught the dead board);
  the kicad-happy analyzer OVER-MERGED the 5 +3V3 islands into one healthy 51-pin rail and
  would have PASSED a dead board (Resolution 1 vindicated) — but it independently caught
  the GND-PWR_FLAG gap (#4) and the 7 GPIO spares (#10), so it's useful for PATTERN
  findings. #2 and #3 (library pin#/pad-count vs datasheet) are invisible to BOTH net tools
  → datasheet cross-reference is mandatory for symbol correctness. CORRECTION: the netlist
  DOES carry power_in/power_out pintypes (34/3) — symbol typing is fine; the ERC power
  errors are pure net-topology (fragmentation + missing GND flag).
  OPEN Qs: (a) 6 unconnected_wire_endpoint stubs near Y1/TP1/TP2 — visual-confirm not real
  opens; (b) microSD card-detect wanted? symbol can't express DM3D-SF pad10 — design call;
  (c) U2 flash footprint USON-8 vs stock SOIC-8 symbol (pinout identical, BOM check);
  (d) ADC_AVDD tied straight to IOVDD, no RC/ferrite (coarse VBAT sense, guide deviation).
  metrics.jsonl S0 unchanged (audit = read-only diagnosis; no schematic writes yet).

[2026-06-16] FIX: S1 — POWER TREE FIXED (generator-level, regenerated). User answered open
Qs (a: I'll investigate stubs — DONE: 0.0127-0.0254mm grid-snap artifacts, connectivity
intact, P3 cosmetic; b: pick a CD-capable microSD part; c: verify+fix flash footprint;
d: add best-practice ADC_AVDD ferrite+cap).
  CHANGES (all in the generator, NOT hand-edited sheets):
  - kicad_sheet_gen.py: added RAIL_NAMES={'+3V3'} + label_at_pin() reroutes rail names to
    power_at_pin() (global power: symbol). Fixes the #1 P0 fragmentation at the source.
  - gen_power_sheet.py: removed #FLG_BAT (cleared pin_to_pin #5); added #FLG_GND PWR_FLAG
    (cleared GND power_pin_not_driven #4).
  - Regenerated Power/Audio/IO/LEDs_IR sheets (MCU_Core untouched — already correct).
  GENERATOR-DRIFT CAUGHT (important for the triage): the first regen DROPPED SW23 (the SYNC
  button) + BTN_SYNC -> new hier_label_mismatch + floating net. The committed schematic had
  SW23 but gen_io_sheet.py only generated 3 buttons (drift: sheets were edited/patched after
  the generator was last run, so the generator was NOT the source of truth). Verified via
  schematic-vs-PCB refdes diff that SW23 was the ONLY drop; added SW23+BTN_SYNC to
  gen_io_sheet.py and regenerated. LESSON: regenerating from a drifted generator silently
  loses post-gen edits — always diff component set vs the PCB after a regen.
  RESULT (sch_health S1): erc 6->0 errors (ERC CLEAN), power_rails_fragmented 1->0,
  power_pins_not_driven 5->0, pin_to_pin 1->0, nets 91->87 (the 5 +3V3 islands merged to 1).
  GATES: power_rails_unified PASS, power_pins_driven PASS, no_pin_conflicts PASS, erc_clean
  PASS. Only no_floating_nets FAIL = the 7 intentional RP2040 GPIO spares (#10) -> WAIVED
  (badge_hw_design confirms GP22-25/27-29 unused; P3 cleanup may emit no_connect markers).
  Board went from DEAD -> powers up + ERC-error-clean. 60 ERC warnings (P3) remain.
  STILL TODO (next passes): #2 TM8211 pinout + #3 SK9822 footprint + #8 TP4056 EP + #c flash
  footprint (all need DATASHEET verification before changing — the symbol-correctness bug
  class is invisible to ERC); #6 RUN 10k pull-up; #7 microSD card-detect part (user: pick
  CD-capable); #d ADC_AVDD ferrite+cap; then PCB net re-sync (sync_nets_pcbnew.py) +
  P3 warning cleanup. metrics.jsonl S1 appended.

[2026-06-16] VERIFY + FIX: S2 — datasheet-verified the 4 library defects (workflow, web access,
each cited). RESULTS:
  - TM8211 (#2): CONFIRMED wrong (high conf, 4 sources: Princeton PT8211 datasheet V1.5 +3 cross-
    checks). NOTE the audit's own guessed pinout was ALSO wrong — real PT8211 SOP-8 is
    1=BCK,2=WS,3=DIN,4=GND,5=VDD,6=LCH,7=NC,8=RCH (audit had guessed 1=WS,2=BCK,4=VDD,5=VOUTL...).
    This is exactly why datasheet verify is mandatory for symbol correctness.
    >>> FIXED: corrected the pinout in BOTH defs (gen_badge_lib.py + the duplicate inline def in
    gen_audio_sheet.py) AND re-mapped the U20 wiring (gen_audio_sheet.py) to the real pins.
    Regenerated lib+Audio; netlist verified: U20.1=I2S_BCK .2=I2S_LRCK .3=I2S_DIN .4=GND .5=+3V3
    .6=DAC_OUTL .7=NC .8=DAC_OUTR — all correct. Footprint SOIC-8 unchanged (no PCB footprint swap;
    only a net re-sync needed). ERC still 0. Audio subsystem now electrically correct.
  - flash W25Q16JVUXIQ (#c): FALSE ALARM (high conf, Winbond W25Q16JV datasheet). The symbol pinout
    AND the footprint (Package_SON:Winbond_USON-8-1EP_3x2mm) are ALREADY correct; only a cosmetic
    symbol-name (W25Q128JVS). NO fix needed. (Another triage point: audit raised it as an open Q,
    verify cleared it.)
  - SK9822 (#3): CONFIRMED wrong (high conf, OPSCO SK9822-EC20 Rev05). BOTH the footprint (4-pad
    SK6812 PLCC4 on a 6-pin part) AND the pin numbering are wrong. Real EC20 = 2.0x2.0mm "2020",
    6 pads: 1=SDO,2=GND,3=SDI,4=CKI,5=VDD,6=CKO. >>> BLOCKED on a part decision: 2020 (EC20) vs a
    5050 SK9822 — they have DIFFERENT pin maps + footprints + PCB placement. Needs user input.
  - TP4056 (#8): CONFIRMED (high conf, Toppower TP4056 datasheet). ESOP-8; pins 1-8 correct, must
    ADD pin9=EP->GND + an ESOP-8 thermal-pad footprint. >>> schematic side trivial; PCB footprint
    swap (SOIC-8 -> SOIC-8-1EP ThermalVias) required.
  TRIAGE so far (what worked/didn't): the off-the-shelf analyzer would have passed a dead board
  (over-merge); the audit caught the real defects but GUESSED two specifics wrong (TM8211 pinout
  detail; flash false alarm) — datasheet verification (cited, multi-source) was the decisive layer.
  STILL TODO: SK9822 part decision -> symbol+footprint+PCB; TP4056 EP + ESOP-8 (PCB); microSD CD
  part (#7, user: pick CD-capable); RUN 10k pull-up (#6) + ADC_AVDD ferrite+cap (#d) [both in
  MCU_Core — check its generation path]; PCB net re-sync; P3 warning cleanup.

[2026-06-16] FIX: S2b — SK9822 LED chain corrected (user chose 5050 "large/bright/decorative";
confirmed SK9822 is addressable RGB so per-LED color is firmware, no HW change). VERIFIED the
5050 pinout against the official SK9822 datasheet (Adafruit/Pololu/Normand, multi-source):
1=SDI(DIN) 2=CKI(CIN) 3=GND 4=VCC(VDD) 5=CKO(COUT) 6=SDO(DOUT) — prior symbol (1=VDD,2=DIN,3=CIN,
4=DOUT,5=COUT,6=GND) was fully scrambled like the DAC. FIXED the pinout in both defs
(gen_badge_lib.py + inline in gen_leds_ir_sheet.py) AND re-mapped the chain wiring (VDD->pin4,
GND->pin3, LED_DAT->pin1, LED_SCK->pin2, DOUT(6)->next DIN(1), COUT(5)->next CIN(2), LED23 NC 5/6).
Netlist verified: chain DOUT->DIN + COUT->CIN linked, VDD/GND/data/clock on the right pads. Value ->
"SK9822". FOOTPRINT -> badge:LED_SK9822_5050, but KiCad has NO stock addressable-5050 footprint
(LED_RGB_5050-6 is plain R/G/B), so this .kicad_mod must be CREATED from the SK9822 datasheet land
pattern in the PCB phase (= the +4 footprint-link warnings, now 64). ERC errors still 0.
  SUBSYSTEM-FATAL LIBRARY BUGS NOW FIXED: TM8211 DAC (#2) + SK9822 LEDs (#3) — both ERC-invisible,
  both caught only by datasheet cross-reference.
  REMAINING: #8 TP4056 EP+ESOP-8; #6 RUN 10k + #d ADC ferrite+cap (both in MCU_Core, gen path TBD);
  #7 microSD CD part; then PCB PHASE = net re-sync + create/swap footprints (SK9822-5050, TP4056
  ESOP-8, microSD-CD) + re-place; then P3 cleanup.

[2026-06-16] FIX: S3 — TP4056 exposed thermal pad (#8). Added CustomPin 9 "EP" (power_in) tied to
GND in BOTH TP4056 defs (gen_badge_lib + inline in gen_power_sheet); footprint -> stock
Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.3x2.3mm_ThermalVias (exists, no creation needed, unlike
SK9822); wired U10.9->GND. Verified U10.9=GND, U10.7=~CHRG, ERC 0.
  GENERATOR BUG FIXED (bonus, kicad_sheet_gen.py): adding the 9th pin (5 left / 4 right) exposed a
  pin_y layout bug — the shorter side was distributed over the taller body to OFF-GRID Y, so the
  label stubs snapped off pins 6/7 -> 2 spurious opens. Fixed pin_y to snap to the 1.27mm grid
  (no-op for equal-side symbols, verified). Now the generator handles odd/unequal pin counts.
  MCU_Core INVESTIGATED: it has NO gen_*_sheet.py — maintained by PATCH scripts (inject_dev_header,
  wire_mcu_hier_labels, patch_mcu_usb_bulk...). So #6 RUN 10k pull-up + #d ADC_AVDD ferrite+cap need
  a small patch script (model: inject_dev_header.py), not a regen — that's the next step.
  STATE: ERC 0 errors / 64 warnings (4 = SK9822 footprint TODO). metrics S3 appended.
