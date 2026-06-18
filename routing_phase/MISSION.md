# MISSION — Badge Routing, Pass 2 (plan-first, escape-first)

A clean-slate re-run of the DEF CON badge routing, rebuilt around the lessons in
`RETROSPECTIVE.md` + `NEXT_PASS_PLAN.md`. Pass 1 reached a structurally-correct **75%** then
ground on the RP2040 QFN-56 escape congestion. This pass fixes that **by construction**.

## What you are building
A routing run that produces a **100%-routed (or cleanly-handed-off), DRC-clean, via-in-pad-free,
hand-designed-looking** board from the FROZEN, user-approved placement — by **planning before
routing**, not correcting reactively. The tools are the deliverable; the board is the test case.

## The four goals (unchanged, all gated)
1. **Aesthetic** — looks hand-designed (constant-pitch buses, clean radial QFN escapes, minimal
   structured vias). Gated by metrics AND a render-and-look at every phase exit.
2. **Deterministic** — same inputs → byte-identical copper (route-twice gate).
3. **Re-runnable / incremental** — a part/pin swap re-routes only changed nets (`route_db`).
4. **Ours, but not reinvented** — built on KRT's *full* toolbox (not a custom router).

## The five structural changes from pass 1 (this is the whole point — read these)
1. **Escape-first, plane-fanout-LAST.** Escape every QFN signal pin to open space BEFORE bulk
   routing and BEFORE plane fanout. Pass 1 poured plane vias first and fenced the pins (the root of
   the plateau). Now signals escape + route first; planes fill in around them last with a keepout
   ring. The QFN escape is a PHASE (R3), not an afterthought.
2. **Use ALL of KRT — it already had the tools we "missed."** `qfn_fanout/` (via-in-pad-free escape,
   PROVEN on U3 — 43 pads, 0 vias), `chip_boundary.py`/`bus_detection.py` + `--bus`/
   `--guide-corridor` (bus/topology), and the Rust router's turn-cost/cross-layer-attraction knobs
   (the aesthetic levers). Pass 1 ran `route.py` at defaults and rebuilt these by hand. Invoke them
   on iteration 1.
3. **Bus planning is its own phase (R4), before bulk.** Aesthetics are a tracked objective and a
   hard render-gate per phase — not a deferred cleanup that never happened.
4. **Plan deterministically, execute adaptively.** Planning (GPIO eval, escape geometry, bus
   corridors) is a one-shot **Workflow** that MUST complete before routing starts (in a pure loop it
   was always "next iteration"). Only adaptive bulk routing is a loop.
5. **Anti-thrash with TEETH + a defined hand-off.** A machine-enforced dead-end detector BANS a
   stalled approach family (pass 1's worst miss: 4 variants of the dead via-fixer). When the
   congested tail stops yielding, the loop STOPS and packages the board for a human + KiCad
   push-and-shove (the right tool; PNS is confirmed un-scriptable) — it does NOT grind.

## The upstream lever (R2, approval-gated)
The RP2040's IO is firmware-flexible. Pass 1's failed nets (microSD SPI, I2S, SAO) leave the QFN on
pins facing the WRONG side (SD on top, card slot below). Re-assigning GPIOs so each bus faces its
destination dissolves the crossings AT THE SOURCE. This is a **schematic edit** → needs explicit
user sign-off; quantify the crossing reduction first, don't take it on faith.

## Phases (each has a locked exit gate in HARNESS.md)
- **R0** Setup + bake in the pcbnew-binding disciplines (`pcb_runner`). Reuse the kept instrument.
- **R1** Stackup & netclass (kept from pass 1 — it worked).
- **R2** GPIO re-assignment eval (NEW, upstream, approval-gated, BEFORE any copper).
- **R3** QFN escape-fanout (NEW, the central fix — multi-layer so it's DRC-clean at 0.4mm pitch).
- **R4** Bus/topology planning (NEW, aesthetics enter HERE).
- **R5** Bulk singleton route + beautify.
- **R6** Plane fanout (LAST) + pour/stitch + verify-or-handoff.

## What "satisfied" means
All hard gates pass (100% routed OR clean hand-off, via_in_pad==0, 0 DRC, 0 shorts, USB correct,
aesthetic budget met, planes intact), determinism gate passes, incremental re-route demonstrated,
human render confirms hand-designed look. If the congested tail won't close, deliver the HAND-OFF
PACKAGE (best clean board + ranked unrouted list + corridor hints) — never grind, never lower a gate.

## Operating philosophy (non-negotiable, inherited)
Tools over edits. Plan before build. Measure everything. **Survey the engine's full toolbox before
building around it** (the #1 pass-1 lesson). Authoritative geometry + single writer. Placement +
schematic FROZEN (the R2 GPIO remap is the only allowed schematic change, with sign-off). The
quality bar is LOCKED — tighten only.
