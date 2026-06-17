# Schematic-cleanup HARNESS — industry-standard, authoritative, repeatable

This mirrors `placement_phase_2/` for the SCHEMATIC. The board is the test case;
the **tools + the repeatable process are the deliverable**. Same operating
philosophy as `placement_phase_2/MISSION.md` (tools-over-edits, plan-before-build,
measure-everything, global-rebuild-is-first-class, gates-locked-tighten-only).

## Resolution 1 — Geometry/connectivity is AUTHORITATIVE (the core lesson)
The placement work failed when it trusted a convenient regex parser over pcbnew;
the fix was `geom.py` (pcbnew truth). The schematic has the SAME trap: the
kicad-happy `analyze_schematic.py` **over-merges hierarchical nets by base name**
— it shows `+3V3` as one healthy 3.3 V rail while KiCad's real netlist splits it
into 5 disconnected islands. **Never gate on the analyzer's net model.** All
connectivity/health metrics come from KiCad's own engines via
`tools/sch_health.py` (`kicad-cli sch erc` + `kicad-cli sch export netlist`),
which agree with what KiCad and the board see. The analyzer is fine for
*pattern* findings (single-pin nets, regulator detection, decoupling), not for
net-truth.

## Resolution 2 — The schematic is GENERATED → fix the generator, not the sheets
The sheets are emitted by `defcon_badge/tools/kicad_sheet_gen.py` +
`gen_*_sheet.py`. Systematic defects (e.g. +3V3 declared with sheet-local
`(label "+3V3")` in 4 sheets but global `power:+3V3` symbols in MCU_Core) are
GENERATOR bugs repeated across sheets. The repeatable fix is: fix the generator,
**regenerate** (a global rebuild — first-class), re-measure. Hand-editing one
sheet to patch a symptom is forbidden (it desyncs the generator and won't survive
the next regen). Net-only PCB re-sync afterward via `tools/sync_nets_pcbnew.py`.

## The instrument — `tools/sch_health.py`
Authoritative metrics, append-only to `metrics.jsonl`, gates below. Run every pass.

## LOCKED gates (tighten only; never loosen to declare done)
- `gate_power_rails_unified`   — every logical power rail is ONE electrical net
  (no `+3V3` fragmentation). **Primary gate.**
- `gate_power_pins_driven`     — every IC power-input pin reaches a real source
  (zero ERC `power_pin_not_driven`).
- `gate_no_pin_conflicts`      — zero ERC `pin_to_pin` (e.g. two power outputs shorted).
- `gate_no_floating_nets`      — zero unintended single-pin nets (intentional MCU
  spares may be explicitly waived in the LEDGER with a reason).
- `gate_erc_clean`             — zero ERC errors (warnings triaged, not all fatal).

## Review dimensions (the checklist — cover every one, don't sample)
1. **Power tree** — every rail sourced once and distributed to every load; LDO/
   charger topology per datasheet; PWR_FLAGs where a net's only source is a
   connector/regulator output; decoupling present (caps are out of scope for now
   per user, but note gaps).
2. **Net integrity** — no fragmentation, no unintended shorts (two signals on one
   net), no floating/single-pin nets that should connect, consistent labels.
3. **Connector pinout correctness** — USB-C (CC/VBUS/D±/SBU/shield), SAO 1.69bis
   (GND/3V3/SDA/SCL/GPIO1/2), microSD (1-bit SPI), 3.5 mm jack (TRS) — each
   against its standard/datasheet, pin-by-pin.
4. **MCU reference-design compliance** — RP2040: USB 27 Ω + DP/DM, crystal + load
   caps + 1 kΩ, QSPI flash, BOOTSEL, RUN, every IOVDD/DVDD/USB_VDD/ADC_AVDD pin on
   the right rail, VREG_VOUT→DVDD.
5. **ERC-warning triage** — classify the 60 warnings: real (off-grid endpoints,
   isolated labels, lib_symbol_mismatch, unconnected_wire_endpoint) vs cosmetic;
   say which are fatal.
6. **Symbol-library correctness** — generated symbols (`gen_badge_lib.py`): pin
   electrical types (power_in/out), pin numbering vs the real part's datasheet.

Each finding: severity, evidence (authoritative source), root cause, and the
REPEATABLE fix (generator change preferred). Flag every analyzer-vs-authoritative
disagreement (Resolution 1 in action).

## Durable memory (append-only)
- `metrics.jsonl` — one `sch_health` row per pass.
- `LEDGER.md` — decisions/findings; `BLOCKER:`/`REVIEW:`/`FIX:` prefixes.
