# HARNESS — Badge Routing Pass 2 (operational core)

You are the iteration engine. cwd is the repo root. Mission-control lives in `routing_phase/`;
the board is `defcon_badge/defcon_badge.kicad_pcb`. Read `MISSION.md` for the why.

## Structure: a Workflow plans, a Loop executes
- **PLANNING (R2 GPIO eval, R3 escape, R4 bus/topology) is a deterministic WORKFLOW**, run once,
  order-dependent, producing a frozen plan artifact (`escape_plan.json`, `bus_plan.json`,
  `gpio_remap.json`). It MUST complete before execution. These never belonged in a wake-up loop —
  that is why pass 1 never did escape/bus planning (always "next iteration").
- **EXECUTION (R5 bulk singleton route + beautify, R6 fanout/pour/verify) is the self-scheduling
  LOOP** with the anti-thrash brakes below. R0/R1 setup may be either.

## LOCKED resolutions (do not route around)
1. **Authoritative geometry + single writer.** All board reads/writes via `geom_route.py` (pcbnew),
   guarded by `writer_lock`. Every mutating tool calls the shared `pcb_runner.py` isolated
   load-mutate-save (see pcbnew checklist). KRT solves; pcbnew writes (the `krt_bridge` seam — KRT
   writes net NAMES, KiCad 10 wants CODES). Never text-edit s-exprs for geometry.
2. **via_in_pad == 0 is solved at ROUTE TIME, by construction.** Escape every pad on its own layer;
   place any via in OPEN space, never on a pad. Post-hoc via-moving is a CONFIRMED DEAD END (pass 1,
   4 variants — moving a via drags its route → needs re-routing → clearance/shorts). `fix_signal_vias.py`
   is DELETED; do not resurrect the approach.
3. **Plane fanout is LAST (R6), with a keepout ring** around escaped QFN pins. Signals escape +
   route first. This encodes pass 1's signals-first lesson as structure.
4. **Completion truth = DRC + a divergence guard** (`measure_route`: pcbnew unconnected vs
   kicad-cli `unconnected_items`; if they disagree, trust DRC).
5. **Determinism is un-loosenable** (route-twice → identical, gated where copper exists).
6. **Aesthetic render-gate every phase exit** — metrics (bus_pitch_var≈0, off_axis==0, acute low,
   via_count budget) AND render F.Cu/B.Cu/3D and LOOK. A phase cannot exit reading machine-generated.
7. **Locked gates/definitions — tighten only.** A definition change or capability deletion to pass
   is a `REVIEW:` + human sign-off.

## Per-iteration procedure (execution loop)
0. **Preflight:** `pcb_runner` writer-lock check; if KiCad holds the board open, read-only iteration.
1. **Read:** MISSION, this file, `routing_rules.md`, `badge_hw_design.md`, the relevant SPEC.
2. **Load memory:** tail of `LEDGER.md` + ALL of `metrics.jsonl` + `approaches.json` (the
   tried-approaches ledger) + `STATE.md` (phase pointer, this phase's PRIMARY metric + escalation ladder).
3. **Dead-end preflight (ANTI-THRASH, HARD):** run `dead_end_detector.py`. It reads `metrics.jsonl`
   + `approaches.json`. If the action you intend uses an approach FAMILY that is `status:banned`, the
   iteration is REFUSED — take the next rung of the phase's pre-declared escalation ladder instead.
   (See "Anti-thrash" — this is code, not advice.)
4. **Measure:** `measure_route.py … --append metrics.jsonl`; check `unconnected_divergence==0`.
5. **Convergence check** over the last K=3 rows tagged with the SAME approach family, judged ONLY
   against the phase's declared PRIMARY metric: <2% gain for 3 rows of one family → that family is
   auto-BANNED in `approaches.json`; you MUST switch to the next ladder rung. A "finding-only" or
   "refactor" iteration is allowed but does NOT reset the dead-end counter and does NOT count as
   progress.
6. **One highest-leverage action**, declaring its approach `family` tag up front.
7. **Execute via tools** (pcb_runner-isolated writes; update `route_db`).
7b. **Phase-exit gate:** aesthetic metrics + determinism (where copper exists) + render-and-look.
8. **Commit + log:** `R?(N): summary`; one `LEDGER.md` line; update `approaches.json`; confirm the
   `metrics.jsonl` row.
9. **Schedule next** (`ScheduleWakeup` with `PROMPT.md`), OR if the HAND-OFF gate fired, STOP +
   produce the hand-off package.

## Anti-thrash (machine-enforced — this is the #1 process fix)
- **`approaches.json`** — one record per (phase, family): {first_iter, last_iter, best_primary,
  status: active|banned|champion, reason}. Keyed on a COARSE family tag the agent declares (e.g.
  `posthoc-via-move`, `krt-default-route`, `escape-multilayer`), so cosmetic re-skins of a dead
  approach are caught (the 4 via-fixer variants were ONE family).
- **Ban rule:** 3 same-family iterations with <2% primary-metric gain → banned; preflight refuses it.
- **Budget:** ≤3 iterations per family before it must show >2% gain or auto-ban.
- **Escalation ladder, pre-declared per phase in STATE.md** — when a family is banned, take the NEXT
  rung automatically (don't invent a new variant of the banned rung). E.g. R3 ladder: KRT qfn_fanout
  multi-layer → manual escape-corridor seeding → GPIO remap (R2) → hand-off.
- **Root-cause gate:** retrying a family already in the ledger requires writing a one-line
  falsifiable hypothesis ("differs by X, predicted to move M by N"); two misses → ban.

## pcbnew binding checklist (BAKE IN from R0 — pass 1 rediscovered these the hard way)
- ONE LoadBoard + ONE SaveBoard per process; a 2nd in-process load corrupts the swig registry. Every
  mutation goes through `pcb_runner.py` (run-snippet-isolated).
- `os._exit(0)` immediately after SaveBoard (heavy mutate-then-save segfaults during teardown AFTER
  the file is written). Do NOT gate success on the exit code — check the file/metrics.
- `safe_board` (read from a /tmp project copy) for ALL read-only analysis — pcbnew flushes BOM field
  defs into the frozen .kicad_pro on exit otherwise.
- Frozen-file git guard after every iteration: assert `.kicad_sch`/`.kicad_pro` git-clean + footprint
  hash unchanged; auto-revert stray rewrites. Run ERC/DRC only on /tmp project copies (with the .kicad_pro).
- Suppress swig assert noise (grep -vE 'PROPERTY_ENUM|memory leak') so real output isn't buried.
- Refill zones in the SAME isolated save process as the copper edit.
- KRT rip-up is pathologically slow on this board — prefer escape+bus planning; if rip-up is needed,
  scope it to a SMALL net set (`--rip-existing-nets PATTERN`), never all-nets.

## Phase exit gates
- **R0 Setup:** `measure_route` emits full schema + baseline row; `pcb_runner` used by geom/bridge;
  KRT `qfn_fanout.py` + a `--guide-corridor` invocation verified runnable on /tmp; divergence==0.
- **R1 Stackup/netclass:** real 4-layer (In1 GND/In2 +3V3, F/B GND pours), USB_DIFF_90 pattern+width
  fixed; zones fill; unrouted DRC clean of NEW stackup errors; baseline frozen.
- **R2 GPIO eval:** `gpio_reassigner` reports current-vs-best QFN-escape crossing count + a ranked
  remap proposal with the reduction quantified; USER adjudication recorded (apply+re-sync OR proceed)
  BEFORE any escape copper. If applied: schematic re-synced, footprints byte-frozen.
- **R3 QFN escape:** every QFN signal pin escaped to open space; **via_in_pad==0** on the escaped set
  (vias in open space, not on pads); escapes DRC-clean (multi-layer so 0.4mm-pitch stubs clear the
  0.15mm rule); no signal on an inner plane; determinism passes; render = clean radial pattern.
- **R4 Bus planning:** named buses (SD/I2S/QSPI/SAO) routed as constant-pitch bundles in corridors;
  `bus_pitch_var`≈0; acute/off-axis low on bused copper; determinism; render = hand-drawn bundles.
- **R5 Bulk + beautify:** completion==100 OR a documented BLOCKER + hand-off package; via_in_pad==0;
  shorts==0; routing drc_errors==0; off_axis==0; acute→0; via_count in budget; determinism_ok.
- **R6 Fanout/pour/verify:** plane fanout placed (keepout ring honored, NO via-in-pad, no fenced
  escape); zones filled + GND-stitched; ALL hard gates pass after fill; incremental 1-net re-route
  demonstrated; human render confirms hand-designed — OR the hand-off package is delivered.

## Hand-off gate (define the stop — pass 1 had none short of 100%)
Trigger: completion <2% gain over the last 6 iterations AND every R5-ladder family is `banned` AND
the unrouted nets are flagged intrinsic-QFN-congestion (not capacity/ordering). On trigger: STOP
scheduling; produce the HAND-OFF PACKAGE — (a) the board at its best clean state (escapes+buses done,
planes intact, DRC-clean on the routed subset, determinism verified); (b) ranked unrouted nets with
escape endpoints + destination zones; (c) per-net corridor hints; (d) the note that KiCad interactive
push-and-shove is the right tool for the last few. The loop does the decomposable 75–90%; the
congested handful is a human's.

## Tools (keep / rebuild / drop)
- KEEP: `geom_route.py`, `route_db.py`, `measure_route.py`, `writer_lock.py`.
- REBUILD: `route_pipeline.py` (phase DAG), `krt_bridge.py` (extractor via KRT `kicad_parser`),
  `rework_stackup.py` (parameterized, once at R1).
- DROP: `fix_signal_vias.py` (dead end — deleted).
- ADD: `pcb_runner.py`, `dead_end_detector.py`, `escape_planner.py` (the linchpin), `bus_topology_planner.py`,
  `gpio_reassigner.py`, `beautifier.py`.
