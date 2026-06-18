# Routing Phase (Phase D) — Retrospective

A triage of the autonomous routing run: what we ended with, what went right, what went wrong,
and where the tooling fell short. No recommendations here — just hits, misses, and diagnosis.
Scope: the routing session (13 loop iterations, D0→D3). It built on an already-good schematic +
frozen, user-approved placement from prior sessions.

---

## Final state (the facts)

- **~75.5% routed.** 36 of ~147 connections remain (started 218 before the planes carried GND/+3V3).
- **Routed & correct:** USB D+/D− diff pair (4/4, in its netclass), the RP2040 core decoupling, the
  power chain, most of the audio chain, the LED chain, and the plane fanout (GND + +3V3 to their
  inner planes). Placement never moved a hair; the schematic stayed byte-identical the whole run.
- **Not routed (the QFN-escape casualties):** the **microSD bus** (SD_SCK/MOSI/MISO/CS + SD_CD —
  all 5), the **I2S audio bus** (DIN/BCK/LRCK), the **SAO header** (SDA + 2 GPIO), QSPI_SCLK/QSPI_SS,
  IR_TX, LED_SCK, VBAT_SENSE, AMP_OUTL, +1V1, BTN_SYNC. ~14 of the 36 are minor plane-stitch gaps.
- **Open DRC:** 2 via-to-via clearance + 11 "via-in-pad" (signal layer-change vias landing on
  passive pads). 0 shorts.
- **Stack:** reworked to a real 4-layer (In1 GND / In2 +3V3 planes intact, signals on F.Cu/B.Cu).
- **Via count ~169** — heavy, and mostly the plane fanout (a via per GND/+3V3 pad). Your instinct
  ("a lot of vias") is right: a human would lean on the F.Cu ground pour's pad connections and
  share/stitch fewer vias. The fanout was correct but generous.

The common thread on every unrouted net: they originate at the **RP2040 QFN-56** in the board
center and have to escape a congested pin field to reach the edges. That one geometric reality
is the whole story of the back half.

---

## What went well (the hits)

1. **The engine call held up.** Choosing KiCadRoutingTools over Freerouting, and building our own
   harness *on* it, was sound — KRT is deterministic, native-KiCad, and routed the bulk in seconds.
   The board you're looking at is largely its work, shaped by our layer. (You were right to trust it.)
2. **The placement & schematic were never harmed.** Every board write was verified footprint-frozen
   (a hash check) and the schematic/project diff stayed clean. The "frozen, authoritative-geometry,
   single-writer" discipline carried over from placement and did its job — zero corruption across 13
   iterations of heavy mutation.
3. **Measure-everything caught real defects before they shipped.** Three genuinely-bad things were
   found *by the metrics*, not by luck:
   - signals routed straight across the GND/+3V3 reference planes (a real signal-integrity flaw),
   - the USB diff-pair netclass pointing at net names that didn't exist (so the pair was silently
     un-classed),
   - via-in-pad being introduced by the fanout.
   A "looks done" autorouter run would have hidden all three.
4. **The KRT-as-solver bridge.** When KRT's *writer* turned out to be incompatible with KiCad 10
   (it writes net *names* where KiCad wants net *codes*), instead of abandoning it we made it a
   solver only — extract its geometry, re-emit through our own pcbnew writer. That single seam is
   what let us keep KRT's intelligence behind a board KiCad can actually open. Clean save.
5. **The "signals-first" reordering.** The biggest single jump (33%→73%) came from realizing the
   plane fanout was fencing the QFN's signal pins in, and re-ordering to route signals first. Good
   diagnosis, real payoff.
6. **Re-runnability was built in early.** The `route_db` (nets keyed by a stable pad-set signature,
   not the churning net name) means a future part swap re-routes only what changed. It's there and
   tested even though we never needed it yet.
7. **The instrument itself.** `measure_route.py` gives an honest, DRC-backed scorecard every
   iteration — completion %, via-in-pad, layer balance, diff-pair skew, etc. The whole run was
   legible because of it.

---

## What didn't go well (the misses)

1. **The 75% plateau — five iterations, ~no completion gain.** After the 33%→73% jump, iterations
   D3(1)–D3(5) moved completion 73→75.5% while burning a lot of effort. The back half was a grind,
   and several iterations produced *findings* (or dead-ends) rather than routed nets.
2. **A wrong hypothesis cost two iterations.** D3(1) diagnosed the B.Cu-underuse as "the outer
   ground pours block the bottom layer" — confidently, and **wrong**. D3(2) disproved it (the real
   lever was a layer-cost penalty) and corrected course. The metrics caught the error, but only
   after a full iteration spent acting on it.
3. **The signals-on-planes flaw lived for several iterations.** It was introduced back at D2(4)
   (the router defaulted to using all 4 copper layers) and wasn't noticed until D3(3). For a few
   commits the "73% clean" board was quietly carving up its own reference planes.
4. **The via-in-pad post-fixer was a ~2-iteration dead end.** I built a tool to nudge vias off pads,
   then chased it through four variants (tiny moves, track-aware, full-clearance, DRC-gated) — each
   either left vias on pads or created clearance/short violations. The honest conclusion ("you
   can't patch this after the fact; it's a routing-time problem") was reachable earlier than I
   reached it. I over-invested in a losing approach before calling it.
5. **The QFN escape was never solved.** The microSD/I2S/SAO/QSPI failures are all the same problem,
   and we never built the thing that would address it (a route-time escape/bus planner). It stayed
   on the "next iteration" list the entire run and never got built.
6. **The via budget is high and was never optimized.** 169 vias, fanout-dominated, with no pass to
   reduce them. We measured it but never acted on it.
7. **The aesthetic goal — the whole "not-Freerouting" premise — was never reached.** The board is
   *connected* where it's routed, but it still reads as autorouted (high acute-angle count, no clean
   bundles). The bus planner that was supposed to deliver "hand-designed" was deferred to the end
   and never started.

---

## Tooling gaps (what I needed and didn't have)

- **An escape-aware / bus router (ours).** The single biggest missing piece. KRT has no via-in-pad
  avoidance and no way to say "escape this pad on its own layer, then via in open space." That one
  capability is what the unrouted nets and the via-in-pad both needed, and it never existed.
- **A DRC-aware geometry editor.** The via-fixer kept failing because moving a via in a congested
  area is really mini-routing — you can't legally place copper without pathfinding around obstacles.
  I had a blind placer; I needed a tiny router. (KiCad's interactive push-and-shove *is* exactly
  this tool, and it's a human-driven one.)
- **A faster/controllable KRT.** Its rip-up/reroute mode is pathologically slow on this board
  (minutes, frequent timeouts), so we couldn't lean on the one feature that resolves congestion.
  Several iterations lost time to runs that had to be killed.
- **A clean pcbnew scripting substrate.** A surprising amount of friction came from the KiCad Python
  binding: it segfaults on heavy mutate-then-save in one process, corrupts its object registry on a
  second board-load, flushes BOM fields into the project file on exit, and floods logs with
  harmless asserts. Each was diagnosed and worked around, but collectively they were a tax on every
  board-writing tool.

---

## Timeline read: where the effort actually went

- **D0–D1 (5 commits): foundation — efficient and clean.** Instrument, incremental engine, stackup
  rework, USB netclass fix. Steady, no wasted motion. Completion still 0% (correctly — no routing yet).
- **D2 (4 commits + the via-in-pad gate): the productive middle.** The KRT bridge, the plane fanout
  (→33%), and the signals-first reorder (→73%). This is where most of the actual routing happened
  and where the run looked healthy.
- **D3 (5 commits): the grind.** 73→75.5%. Diagnosis, one wrong turn, the signals-on-planes fix
  (real and important, but a *correction*, not forward progress), and the via-fixer dead end. This
  is where the autonomous loop hit the wall and kept circling it.

The shape of it: **front-loaded value, back-loaded thrash.** The loop excelled at the parts that
decompose into clear measurable steps (build instrument, fix a netclass, apply a fanout) and
struggled exactly where PCB routing is hard for *everyone* — congested escape — which doesn't yield
to "measure → one move → repeat."

---

## The one-line diagnosis

We built a strong, honest, reusable routing *system* and got the board to a clean, structurally-correct
75% — then spent the back third grinding on the QFN-escape congestion, which is precisely the kind of
problem an autorouter (and an autonomous loop) is worst at and a human with an interactive router is
best at. The biggest *miss* and the biggest *gap* are the same thing: the route-time escape planner that
would have unblocked the last 25%, and the aesthetic pass, were always "next" and never got built.
