# Next-Pass Routing Plan

What I'd change for a clean-slate re-run, given the retrospective + a focused research pass.
This is a plan, not a build. It assumes the same starting point (placed board + schematic) but
treats the schematic pin-map as fair game ("blow it away").

---

## The one-sentence reframe

Last pass **routed reactively and never planned**; the next pass **plans first** — fix the
congestion at the source (pin assignment), escape the QFN deliberately *before* bulk routing,
plan buses as a phase, and only then route — with machine-enforced brakes so it can't grind on a
dead end, and a defined point where it hands the hard tail to a human.

---

## The biggest (and most humbling) finding

The two capabilities I concluded "we never built" — a **QFN escape planner** and a **bus/topology
planner** — **already exist inside KiCadRoutingTools and were never invoked.**

- **`qfn_fanout/`** lays two-segment 45° escape stubs on the component's *own* layer and returns
  **zero vias** (its docstring literally says "vias is empty"). That is *exactly* the route-time,
  via-in-pad-free escape tool I spent two iterations failing to build post-hoc. It shipped with the
  engine I adopted.
- **`chip_boundary.py` / `bus_detection.py`** + the `--bus` / `--guide-corridor` / `--keepout` /
  `--swappable-nets` flags are the topology/aesthetic layer I said was "ours to build."
- The "KRT rip-up is too slow" pain was its *Python* orchestration; the actual pathfinder is a
  compiled Rust A* (`grid_router.so`) with **turn-cost and cross-layer-attraction knobs** — the
  "hand-designed, not-Freerouting" levers — which we ran at defaults.

**So the engine choice was right; the miss was integration.** We used `route.py`/`route_planes.py`
with default flags and built workarounds (the bridge, the via-fixer) around capabilities the tool
already had. The real process lesson: *survey the full toolbox of an engine you adopt before
building around it.* That one habit would have changed the whole back half.

---

## The plan, in five moves

### 1. Fix it at the source — GPIO re-assignment (upstream, approval-gated)
Every unrouted net (microSD SPI, I2S, SAO, QSPI...) fails for one reason: it leaves the RP2040 on a
pin that faces the **wrong side** of the chip. SD sits on the top of the QFN but the card slot is
below; I2S sits on top but the DAC is to the right; SAO is split but its header is to the left.

The RP2040's IO is **firmware-flexible** — SPI/I2C have multiple pin instances, and **PIO can drive
any GPIO** (the SD bus and LED clock are PIO-capable → near-total freedom). Re-assigning each bus to
a pin that already faces its destination **dissolves the crossings before any router runs.** The
research estimates ~half the cross-side escapes become trivial same-side ones, likely closing most
of the 36 unrouted nets. (QSPI flash is the one fixed bank and is already correct — leave it.)

This is a **schematic edit** (firmware follows), so it needs your sign-off. My judgment: it may be
the single cheapest, highest-leverage change — but I'd *quantify* the crossing reduction first
(a planning artifact) before committing, rather than take the estimate on faith.

### 2. Escape-first — the QFN escape planner (the central route-time fix)
Before *any* bulk routing or plane fanout, escape every QFN signal pin to open space: a stub on the
pad's own layer, then a via in the clean ~4 mm escape ring around the chip (which is currently
empty). Built on KRT's `qfn_fanout`. This:
- makes **via-in-pad impossible by construction** (the via is never on a pad — retires the 11 errors
  and makes the dead-end via-fixer unnecessary),
- hands the bulk router a **relieved ring of well-spaced escape points** instead of a jammed pin
  field — so KRT then routes ring-to-ring across open mid-board (its *easy* case), and
- the staggered radial pattern **reads as hand-designed** (the aesthetic win, for free).

### 3. Plane-fanout LAST, not first
Last pass poured the GND/+3V3 plane vias *first*, which fenced the QFN's signal pins — the root of
the plateau, fixed reactively as "signals-first." Next pass **encodes that as structure**: signals
escape and route first; plane fanout fills in *around* them last, with a keepout ring so it can
never re-fence an escape.

### 4. Aesthetics as a phase, not a final polish
The "looks hand-designed" goal was lumped into "bulk route" and deferred to a cleanup pass that
never happened. Next pass makes **bus planning its own phase that runs before bulk** — the SD/I2S/
QSPI/SAO buses are laid as constant-pitch bundles via `--guide-corridor` *first*, so the backbone is
tidy by construction and singletons fill in around it. Aesthetic metrics (bus-pitch variance,
acute-angle/off-axis counts) become the **primary tracked objective** of that phase + a hard
render-and-look gate at every phase exit — not an unmeasured aspiration.

### 5. Plan deterministically, execute adaptively
The retrospective's shape — front-loaded value, back-loaded thrash — maps onto
**planning suits a Workflow, execution suits a loop**. So: the **planning** (GPIO eval, escape
geometry, bus corridors) becomes a deterministic **Workflow fan-out** that runs once, produces a
frozen plan artifact, and *must complete before routing starts* — which is precisely why escape/bus
planning never happened last time (in a pure loop it was always "next iteration"). The **execution**
(bulk singleton routing, beautify, verify) stays a bounded self-scheduling loop — the genuinely
adaptive part.

---

## Engine decision: keep KRT, but use *all* of it

`krt-escape-first`. The validated substrate (the `krt_bridge` solver→pcbnew-writer seam, `route_db`,
`measure_route`, `geom_route`) stays. The change is to invoke the parts we ignored: `qfn_fanout` for
escapes, `--bus`/`--guide-corridor` for buses, and the Rust router's turn-cost + cross-layer-
attraction for aesthetics. **Building our own router is rejected** — it would re-implement
`grid_router.so` + `qfn_fanout`, and a from-scratch DRC-correct router is exactly the deep,
congestion-hard work the autonomous loop is *worst* at. **KiCad's push-and-shove (PNS) is confirmed
un-scriptable** (GUI-bound C++, not in the SWIG bindings or the IPC API) — so it's reserved as the
*human* finishing tool for the last congested nets, which is its right role.

---

## Anti-thrash: make the ESCALATE rule code, not prose

My single worst operator failure last pass was chasing the post-hoc via-fixer through four variants
of a dead approach — violating my own "don't repeat a stalled move" rule. Next pass makes it
**machine-enforced**:
- A **dead-end detector** reads `metrics.jsonl` each iteration; 3 same-approach iterations with
  <2% gain on the phase's primary metric → the approach **family** is **banned** (a hard preflight
  that refuses to schedule another iteration under it).
- A **tried-approaches ledger** (`approaches.json`) keyed on a coarse *family* tag, so cosmetic
  re-skins of a dead approach (the four via-fixer variants were one family) are caught.
- **Per-approach budget** (≤3 iterations) and a **pre-declared escalation ladder** per phase, so
  when an approach is banned the loop takes the *next rung* automatically instead of improvising
  another variant of the banned one.
- **"Finding-only" iterations don't reset the counter** — a refactor or a diagnosis can't mask a
  stalled metric.

---

## Human hand-off gate

Define an explicit stop: when completion stalls (<2% over N iters) **and** every escalation rung is
banned **and** the remaining nets are flagged as intrinsic QFN-congestion casualties, the loop
**stops and packages a hand-off** instead of grinding — the best clean board (escapes + buses done,
DRC-clean on the routed subset, determinism verified) + a ranked list of unrouted nets with their
escape endpoints + corridor hints, with a note that KiCad's interactive push-and-shove is the right
tool for the last few. The loop's job is the 75–90% that decomposes into measurable steps; the last
congested handful is a human's. Last run had *no* defined stop short of 100%, so it ground.

---

## Tool audit: keep / rebuild / drop (~1300 lines)

**Keep ~as-is (~740 lines, the genuinely-good substrate):**
- `geom_route.py` — authoritative copper read/write + `safe_board` (the pattern that gave 13
  corruption-free iterations). Most reusable piece we built.
- `route_db.py` — incremental engine: stable pad-set signatures, NEW/CHANGED/UNCHANGED diff,
  determinism fingerprint. Serves the re-runnability requirement directly.
- `measure_route.py` — the DRC-backed instrument; it caught all three real defects. (Minor: fold its
  3 board-loads into one.)
- `writer_lock.py` (from placement) — single-writer discipline.

**Rebuild but salvage the core (~360 lines):**
- `route_pipeline.py` → a real **phase DAG** (escape → bus → bulk → fanout-last → beautify → pour),
  keeping its subprocess-isolation substrate.
- `krt_bridge.py` → keep the solver→writer seam; **replace the hand-rolled regex extractor with
  KRT's own `kicad_parser.py`** (parse with the producer's grammar, not a private regex).
- `rework_stackup.py` → keep the inset-zone logic; parameterize and run once at setup.

**Drop (~210 lines):** `fix_signal_vias.py` — the confirmed dead end. Post-hoc via-moving is
mini-routing and can't be done blindly; escape-first makes it unnecessary. Keep only its clearance
helpers as a reference.

**Add (the new tools):**
- **`escape_planner.py`** — *the highest-leverage new tool* (built on KRT `qfn_fanout`). Every
  unrouted net and every via-in-pad traces to QFN escape; this is both the biggest unblock and the
  cheapest to build.
- **`bus_topology_planner.py`** — buses as constant-pitch bundles via `--guide-corridor` (the
  aesthetic backbone). Built on KRT `chip_boundary.py` + `bus_detection.py`.
- **`gpio_reassigner.py`** — the upstream pin-map optimizer (approval-gated schematic edit).
- **`beautifier.py`** — pull-tight / 45°-quantize / teardrops on routed copper (NOT a via-mover).
- **`dead_end_detector.py`** + **`pcb_runner.py`** — the anti-thrash guard and a shared isolated
  load-mutate-save helper so the pcbnew-binding workarounds (one-load-one-save, `os._exit` after
  save, `safe_board`, frozen-file git guard, swig-noise suppression) are structural from iteration 0.

---

## New phase order

`R0` setup + bake-in pcbnew disciplines → `R1` stackup/netclass (kept) → **`R2` GPIO re-assignment
(new, approval-gated)** → **`R3` QFN escape-fanout (new, the central fix)** → **`R4` bus/topology
planning (new, aesthetics enter here)** → `R5` bulk singleton route + beautify → `R6` pour/stitch/
verify-or-handoff. The two structural changes that matter most: **escape becomes a phase**, and
**plane fanout moves to last**.

---

## Honest operator lessons (the meta)

1. **Survey the engine's full toolbox before building around it.** I built a bridge and a failed
   via-fixer around capabilities (`qfn_fanout`, `--guide-corridor`) KRT already shipped. The single
   biggest efficiency loss of the whole run.
2. **Plan the hard part first; don't discover the plan reactively.** Signals-first, layer-costs,
   planes-clean were all corrections to problems an upfront escape/topology plan would have avoided.
3. **Enforce the escalate rule in code.** I knew the rule and violated it on the via-fixer. Prose
   discipline failed; a preflight that *refuses* the stalled move would not have.
4. **Know when it's a human's job.** The congested QFN tail is where an autonomous loop is weakest
   and an interactive router is strongest — recognizing that earlier saves the grind.
