# ESCAPE_SPEC — QFN escape planner (R3, the central new tool)

`routing_phase/tools/escape_planner.py`. The phase that never existed in pass 1. Escapes every
QFN signal pin to OPEN space outside the pin field BEFORE bulk routing — so via_in_pad==0 by
construction and the bulk router starts from a relieved ring, not a jammed pad field.

## Proven foundation (de-risking result, 2026-06-18)
KRT's `qfn_fanout` (shipped, never used in pass 1) escaped all **43** U3 signal pads with **0 vias**
(escapes on the mounted F.Cu layer, two-segment 45° stubs, side-classified bottom 12/left 8/right 11/
top 12, "No endpoint collisions"). Applied via `krt_bridge` → **via_in_pad==0** confirmed.

**The residual it surfaced — and the reason escape_planner is more than a qfn_fanout wrapper:** at
0.40mm pitch the single-layer 45° fan stubs sit only ~0.283mm apart (pitch/√2) → with 0.15mm tracks
the gap is ~0.133mm < the 0.15mm clearance rule → **54 clearance DRC errors**. One layer cannot hold
43 escapes at this pitch. qfn_fanout's own note: "route.py --grid-step 0.05 --clearance 0.05 ... the
default will fail." So escape_planner must SPREAD ACROSS LAYERS.

## Design: multi-layer alternating escape (the fix)
Halve the per-layer escape density so adjacent same-layer stubs clear the 0.15mm rule.
- Per side, walk pads in index order and ALTERNATE escape layer: even pads escape on **F.Cu**
  (qfn_fanout direct stub, no via), odd pads escape via a **B.Cu dog-bone** (short F.Cu stub off the
  pad → off-pad via in the empty annulus → B.Cu stub outward). This doubles per-layer pitch to
  ~0.566mm → ~0.416mm gap > 0.15mm → DRC-clean.
- The off-pad via stays via_in_pad-free (via is in the open annulus, never on the pad). Placement is
  EASY because escape-first runs on EMPTY copper (the annulus is clear — pass 1's congestion was
  caused by routing INTO a filled field; here there's nothing to collide with).
- Power/GND QFN pads (+3V3/+1V1/GND) are NOT escaped here — they drop straight to their plane in R6
  fanout (excluded via `--nets "*" "!GND" "!+3V3" "!+1V1"`). The EP and its 9 GND vias are untouched.
- MONOTONE ordering per side (no two same-layer escapes cross; preserve pad order at the ring) — this
  is what makes it read hand-designed.

## Algorithm
1. Run KRT `qfn_fanout.py --component U3 --layer F.Cu --width 0.15 --clearance 0.15 --nets <F.Cu set>`
   for the EVEN pads → KRT-format board; `krt_bridge.extract_routing` → F.Cu escape tracks.
2. For the ODD pads, build B.Cu dog-bones directly on `geom_route`: F.Cu stub pad→via_pos (short,
   along the outward radial), `add_via` at via_pos (validated clear by the `_pt_clear`/`_seg_dist`
   geometry check — reused from the deleted fix_signal_vias as a reference helper), B.Cu stub
   via_pos→ring-exit. Sweep radius in the empty annulus until clear (nearly always first try).
3. Apply ALL escapes via `krt_bridge.apply_routing`/`geom_route` (pcbnew writer), one save.
4. Emit `escape_plan.json`: per pin {refdes_pin, net, native_side, escape_layer, mode: vialess|dogbone,
   via:[x,y]|null, escape_point:[x,y,layer]}. This is the HAND-OFF CONTRACT to R4/R5 — the bulk router
   uses `escape_point` as the net's effective source terminal and never touches the pad field again.
5. Reserve a KEEPOUT ring (a `(keepout (vias not_allowed))` rule area around U3 out to ~r_outer) so R6
   plane fanout can't re-fence the escapes.

## Inputs / guardrails
- Read via `geom_route.safe_board`; design rules from the netclass (don't hardcode); single-writer.
- Does NOT route to destinations (only to the ring). Does NOT touch the EP/planes' fill. Never places
  a via that HitTests a pad (the invariant). One LoadBoard+SaveBoard (pcb_runner).
- Also escape the microSD J31 and any other dense connector the same way if it blocks (start with U3).

## Exit gate (R3): every QFN signal pin escaped to open space; via_in_pad==0; escapes DRC-clean
(multi-layer); no signal on an inner plane; determinism passes; render shows a clean radial pattern.

## Tuning fallbacks (the R3 escalation ladder)
qfn_fanout-multilayer → manual escape-corridor seeding (hand-place a few hard stubs) → push to R2
GPIO remap (move the pin so it doesn't need a cross-side escape) → hand-off. Also: if 0.4mm pitch is
truly too tight even multi-layer, route the QFN-local nets with `route.py --grid-step 0.05
--clearance 0.05 --track-width 0.15` (qfn_fanout's own suggestion) scoped to just U3's nets.
