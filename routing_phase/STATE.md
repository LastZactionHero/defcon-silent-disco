# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **D3 — Bus + bulk route** (D0+D1 done; D2 plane fanout + signals-first re-order done → 73%)
Current approach: build the routing system ON KiCadRoutingTools (KRT), Freerouting REJECTED.
Engine: KRT at `~/.local/share/defcon-badge-krt/KiCadRoutingTools` (pinned commit in
  `KRT_PINNED_COMMIT.txt` = ce5cb2d, v0.15.13), run via `~/.local/share/defcon-badge-krt/venv/bin/python`.
  Env is INSTALLED + smoke-tested (grid_router rust kernel + numpy/scipy/shapely OK). `setup.sh` reproduces it.

Last completed: **D0(2)** — `routing_phase/tools/route_db.py` (incremental engine: net_sig =
  sha1(sorted "REFDES-PADNUM"), live_nets/diff/stable_order/record_routes/replay/fingerprint) +
  `geom_route.safe_board` (/tmp-copy read context so any read-only tool avoids the .kicad_pro flush).
  Self-test: 64 routable nets (62 signal + planes GND/+3V3), all NEW vs empty db, stable order
  front-loads USB diff (rank0) then XIN/QSPI (rank1), signatures reproducible, frozen files clean.
  **D0 EXIT GATE MET** (measure_route + geom_route + route_db + KRT all verified) → now D1.
Earlier — **D0(1)** — instrument built. `routing_phase/tools/geom_route.py` (track/via
  read + add_track/add_via/delete_routing/refill_zones, writer-lock-guarded) and
  `routing_phase/tools/measure_route.py` (full routing metric schema, DRC/ERC on a /tmp project
  copy so the FROZEN .kicad_sch/.kicad_pro are never mutated — verified clean). Baseline row in
  metrics.jsonl: completion 0%, unconnected 218 (divergence 0), 0 tracks/vias, usb_diff_paired
  FALSE (netclass bug → D1), zones_filled_ok FALSE (artifact zones → D1), erc 0. KRT confirmed
  runnable against THIS board (list_nets: 84 nets / 83 comps, reads GND/+3V3/USB correctly).
  GOTCHA SOLVED: pcbnew's settings-manager flushes BOM field-defs into the real .kicad_pro on
  process exit after reading project state → measure now operates entirely on a /tmp copy.

D1 progress: **D1(1) DONE** — rework_stackup.py applied: thickness 1.0→1.6mm, deleted the 3 crude
  artifact rectangles, recreated 4 outline-following zones (In1 solid GND, In2 +3V3, F.Cu GND, B.Cu
  GND, inset 0.3mm), In2→mixed, filled. measure: zones_filled_ok TRUE, unconnected 218→147, drc 0,
  erc 0. baseline.json frozen at unconnected_baseline=147. Frozen-file discipline held (only
  .kicad_pcb changed; .kicad_pro/.kicad_sch clean). Render d1_top.png reviewed — placement intact.
  pcbnew swig GOTCHA: LoadBoard→mutate→Fill→Save→re-read in ONE process corrupts the swig wrapper
  registry (Zones()/GetDesignSettings() return raw pointers) → one LoadBoard+SaveBoard per process,
  verify via a fresh measure_route SUBPROCESS.

D1(2) DONE: USB_DIFF_90 netclass fixed (patterns → real nets /MCU_Core/USB_DP|DM + connector-side
  Net-(U3-USB_DP|DM); diff_pair_width 0.8→0.17, gap 0.15→0.13). measure usb_diff_paired→TRUE. Minimal
  .kicad_pro diff (12+/4−), .kicad_sch/.kicad_pcb untouched, DRC 0. **D1 EXIT GATE MET.**

D2(1) DONE — KRT INTEGRATION RESOLVED via a bridge. FINDING: KRT's board WRITER emits `(net "GND")`
  (net NAME) in segments/vias but KiCad 10 needs `(net <int>)` → KRT output does NOT load in pcbnew/
  kicad-cli ("Failed to load board"). KRT is a SOLVER ONLY. Built routing_phase/tools/krt_bridge.py:
  extract_routing (parse KRT output tracks/vias by net name) + apply_routing (re-apply via pcbnew/
  geom_route — the authoritative single writer). VALIDATED on /tmp: KRT route_planes → bridge → pcbnew
  board LOADS in kicad-cli ✓, footprints byte-frozen (fp hash matches) ✓, +3V3 47/47 + GND 89/89 to
  planes, unconnected 147→98, ZERO new routing-type DRC errors. Pre-existing placement DRC (NOT routing):
  28 solder_mask_bridge (different-net fine-pitch pads, scoped out of ROUTING_TYPES) + 7 starved_thermal
  (investigate — may be from the D1 zone thermal-relief; could need solid pad-connection on plane pads).

D2(2) DONE — PLANE FANOUT APPLIED to the real board. (a) starved_thermal fixed: set the GND/+3V3
  zones to SOLID pad/via connection (ZONE_CONNECTION_FULL) — textbook for planes; starved_thermal 7→0.
  (b) fixed rework_stackup segfault-at-exit (os._exit(0) after save). (c) fixed geom_route.load_vias
  (KiCad 10 needs PCB_VIA.GetWidth(layer)). (d) KRT route_planes → krt_bridge → applied to REAL board:
  219 tracks + 114 vias (GND 75 + +3V3 39 + 14 GND-return). measure: completion 0→33.3%, unconnected
  147→98 (divergence 0), drc_errors 0 (routing types), shorts 0, zones_filled_ok TRUE, usb_diff_paired
  TRUE, footprints byte-frozen (fp hash unchanged), .kicad_pro/.kicad_sch clean. route_db recorded (64
  nets; GND/+3V3 carry the fanout copper, via widths 0.6). Renders d2_top.png/d2_copper.svg — placement
  intact. NOTE: off_axis_segments 17 + acute_angles 39 from KRT's via-to-pad stubs → D4 cleanup target
  (not a D2 gate). DETERMINISM formal gate deferred to D5 (structurally guaranteed by route_db replay;
  the D2 replay-verify hit a multi-LoadBoard-per-process swig bug in the TEST harness, not the pipeline).

D2(3) — KEY FINDING + tool fix (no board change). Added krt_bridge.apply_routing(replace=True): KRT
  routes on a board holding ALL prior routing and emits prior+new, so the bridge extracts the FULL
  output and applies with REPLACE (rip-then-lay) → board == latest full KRT solution, no fanout
  duplication. FINDING (the routing problem to solve): the USB pair is a MULTI-POINT pair (U3 ↔ 27R
  R3/R4 ↔ J10) with a FORCED CROSSOVER (U3.46/DM is above U3.47/DP at the source but R4/DM ends below
  R3/DP → can't route planar on one layer). KRT route_diff couples the long J10→R leg but defers the
  short MCU legs to single-ended; KRT route.py single-ended then routes 3/4 USB nets but Net-(U3-USB_DP)
  (U3.47→R3.2) FAILS — "no rippable blockers": the **plane fanout vias around the U3 QFN form a via
  fence that blocks signal escape**. This is SYSTEMIC: power fanout-before-signal-escape will block more
  nets near dense ICs in D3. (On a /tmp verify the 3/4 partial reached completion 36.7%/unconn 93, DRC 0
  — but it's incomplete + masks the real issue, so NOT applied to the real board.)

D2(4) DONE — SIGNALS-FIRST RE-ORDER applied to the real board. Validated USB routes 4/4 on empty
  copper (was 3/4 fenced by fanout). Full chain (clean base → KRT route.py all 62 signals → KRT
  route_planes fanout with --same-net-pad-clearance 0.2 → bridge replace → real). RESULT: completion
  33→**73.5%**, unconnected 98→39, via_in_pad **94→8**, USB 4/4 (usb_diff_paired TRUE), drc_errors 0,
  shorts 0, footprints byte-frozen, .kicad_pro/.kicad_sch clean. route_db recorded (router_version 2).
  REMAINING GAPS (the D3/D4 work): (a) 13 signal nets FAILED (in the 39 unconnected) — congestion,
  need rip-up/reroute + guide corridors + B.Cu; (b) +3V3 fanout only 37/47 (signals took the space) —
  re-fanout or rip-blocker; (c) via_in_pad 8 (from KRT route.py SIGNAL layer-change vias — route.py
  lacks --same-net-pad-clearance; must offset/nudge them) — HARD GATE needs 0 before D3 exit;
  (d) off_axis_segments 147, acute_angles 635, track_count 2214 — board looks AUTOROUTED (the
  aesthetic goal is unmet): D4 needs the bus planner (--guide-corridor) + beautification (pull-tight,
  push-to-grid/45-quantize, via-min). Render shows spaghetti — not hand-designed yet.

D3(1) DIAGNOSIS (no board change; real board stays at 73%, clean). The 39 unconnected =
  **21 plane edges** (GND 11 + +3V3 10 — fanout blocked by signals) + **18 signal edges**: the whole
  SD bus (SD_SCK/MOSI/MISO/CS + SD_CD), the I2S trio (DIN/BCK/LRCK), QSPI_SCLK, IR_TX, LED_SCK,
  BTN_VOL_UP, BTN_SYNC, SAO_SDA/GPIO1/GPIO2, VBAT_SENSE, Net-(U3-USB_DM). KEY FINDING: **B.Cu is
  severely underused — F.Cu 796mm vs B.Cu 22mm (layer_balance 0.028).** The cross-board buses (SD→J31,
  I2S→U20) fail for lack of room while B.Cu sits empty. KRT reports the failures as "blocked by
  pads/stubs/ZONES" → the **outer F.Cu/B.Cu GND pours block B.Cu signal routing** (filled pours = solid
  obstacle to KRT). Also: KRT mps + rip-up (--rip-existing-nets all) is PATHOLOGICALLY SLOW on this
  board (300k iters = minutes, times out) and not clearly better → use **--ordering original (fast)**.

D3(2) — CORRECTED DIAGNOSIS + route_pipeline tool (real board unchanged, 73%). Built
  routing_phase/tools/route_pipeline.py (reproducible: base → KRT route → fanout → bridge apply,
  each pcbnew step subprocess-isolated; FIXED a build_base segfault — delete_routing + fill in ONE
  process crashes before SaveBoard, so split into delete+save then unfill/fill+save). FINDINGS:
  (a) the D3(1) "outer pours block B.Cu" hypothesis is **DISPROVEN** — unfilling them left B.Cu at
  22mm (KRT reproduced the exact same 49/62 deterministically). (b) The real lever is **--layer-costs**:
  `--layers F.Cu B.Cu --layer-costs 2.0/3.0 1.0` (penalize F.Cu) FORCES B.Cu usage (22→588mm) — KRT is
  F.Cu-dominant and won't use B.Cu unprompted. Added to route_pipeline (2.0/1.0). (c) BUT layer-balancing
  does NOT fix the ~13 failing nets — they still fail with B.Cu available, so they fail on **intrinsic
  escape/crossing congestion near the U3 QFN** (SD bus→J31, I2S→U20, QSPI_SCLK, IR_TX, LED_SCK, buttons,
  SAO), not layer capacity. via_in_pad 8 (signal vias) still to drive to 0.

D3(3) DONE — MAJOR FIX: signals were ON THE PLANES. Found the current board had ~60 signal-track
  segments routed on the In1 GND / In2 +3V3 PLANES (carving up the reference planes — a serious SI
  flaw) because earlier routes didn't restrict layers. route_pipeline now passes --layers F.Cu B.Cu
  (added D3(2)), so re-applying it gives: **0 signal tracks on inner planes** (planes intact), both
  outer layers used (F.Cu 736 / B.Cu 372, balance 0.028→0.505), completion 73.5→75.5%, footprints
  frozen, pro/sch clean, route_db v3. COST (the next cleanup): drc_errors 0→2 (via-to-via clearance:
  USB DP/DM vias 0.128mm; BTN_VOL_UP/BTN_CH vias 0.128mm) + via_in_pad 8→11 — BOTH are KRT route.py
  SIGNAL-via placement defects (route.py has no --same-net-pad-clearance / via-spacing like route_planes).
  This planes-clean board is the CORRECT foundation; the via issues are fixable cleanup.

D3(4) — VIA-FIXER built but post-hoc via-moving DOESN'T WORK on this congested board (real board
  unchanged, 75.5%/via_in_pad 11). Built routing_phase/tools/fix_signal_vias.py (move via off pad along
  its escape dir + relink tracks + add pad→via stub; fixed a state-staleness bug by re-querying the
  board per via — now deterministic). It reduces via_in_pad 11→1 BUT creates 124 DRC + **8 SHORTS**:
  the via-in-pad vias sit in genuinely congested spots (next to other pads/tracks), so the moved
  vias + their stubs collide with other nets. CONCLUSION: via-in-pad CANNOT be cleanly post-fixed here
  — it must be solved at ROUTING time (route the net so it doesn't change layers AT the pad). KRT
  route.py has no via-in-pad-avoidance flag, so the fix lives in the bus planner / guided re-route
  (control each net's pad escape: route a short stub on the pad's own layer, THEN via in open space).

Next intended action:
  1. **D3(5) — solve via-in-pad + the ~12 stragglers TOGETHER at routing time via guided escape /
     bus planner.** For the via-in-pad nets AND the failed nets, route them with controlled escapes:
     a short trace on the pad's layer out to open space, then the via / B.Cu run there (--guide-corridor
     draws the channel; or hand-script the escape stub + via via geom_route, then KRT routes the rest).
     This is the start of the bus planner. Goal: via_in_pad 0 (HARD GATE) + completion up, drc 0, shorts 0.
     fix_signal_vias.py stays as a reference (the tiny-move + relink mechanics are reusable; the missing
     piece is DRC-checking/routing the stub instead of drawing it blindly).
  2. **D4 — bus planner (constant-pitch bundles) + beautification.**
  OLD plan (reference):
  1. **D3(4) — build the VIA-FIXER (routing_phase/tools/fix_signal_vias.py).** Post-process: (a)
     via_in_pad 11→0 — for each via on a pad, move it off along its escape direction into clear space,
     extend the pad→via stub, and move the connected track endpoints to the new via position (geom_route);
     (b) the 2 via-to-via clearance — nudge one via of each too-close pair apart (≥0.75mm center-to-center
     for 0.6mm vias @ 0.15mm clearance) + fix its track endpoints. Verify via_in_pad 0, drc 0, shorts 0,
     connectivity preserved (unconnected unchanged), frozen. HARD GATE via_in_pad==0.
  2. **D3(5) — the ~12 stragglers**: targeted small-set rip-up / per-net --guide-corridor on B.Cu (SD
     bus→J31, I2S→U20, etc.) → completion toward 100.
  3. **D4 — bus planner + beautification** (aesthetic payoff).
  OLD plan (reference):
  1. **D3(3) — apply layer-balanced route + attack the 13 stragglers.** (a) Run route_pipeline
     --target on the REAL board (layer-balanced, both layers used) and DRC-verify (full measure_route,
     not --no-drc): completion ~same but B.Cu now used, drc 0, shorts 0, frozen. (b) For the ~13
     intrinsic failures: targeted KRT rip-up on JUST those nets (--rip-existing-nets the blockers,
     small set = fast, unlike all-nets rip-up), and/or per-net --guide-corridor to route each failed
     bus on B.Cu in its own channel. Identify blockers from KRT JSON_SUMMARY. (c) drive via_in_pad 8→0
     (offset/nudge signal vias). Gate: completion 100, via_in_pad 0, drc 0, shorts 0.
  2. **D4 — bus planner + beautification** (the aesthetic payoff): the --guide-corridor work from (b)
     IS the start of the bus planner; extend it to route QSPI/SPI/I2S/SD as constant-pitch bundles,
     then pull-tight/45-quantize/via-min. off_axis→0, acute→0; render must look hand-designed.
  OLD plan (reference):
  1. **D3(2) — route with OUTER POURS UNFILLED (the B.Cu fix).** Implement cleanly + fast: base =
     delete_routing + fill ONLY inner planes (In1.Cu/In2.Cu), leave F.Cu/B.Cu GND pours UNFILLED →
     KRT route.py all 62 signals --ordering original (FAST, no rip-up/mps) → KRT route_planes fanout
     --same-net-pad-clearance 0.2 → krt_bridge extract → apply_routing(replace, refill=True) refills
     ALL zones (outer pours recede around the signals). Verify B.Cu usage jumps + completion rises +
     via_in_pad 0 + drc 0. If still failing nets, THEN add targeted rip-up on just those nets.
     (Tip: KRT runs slow under high --max-iterations; do NOT raise it. Suppress swig "memory leak"
     stderr noise — it floods logs. Verify each step with a fresh measure_route subprocess.)
  2. Then drive via_in_pad 8→0 (offset signal vias) and finish remaining nets → D3 gate (100%, 0 via-in-pad).
  OLD plan (reference):
  1. **D3 — finish routing to 100% + drive via_in_pad to 0.** (a) Re-route the 13 failed signals:
     KRT route.py with rip-up enabled (--rip-existing-nets) + allow more vias/B.Cu, or per-net guide
     corridors; (b) complete +3V3 fanout (re-run route_planes after signals, or --rip-blocker-nets);
     (c) eliminate the 8 via_in_pad — nudge signal layer-change vias off pads (post-process via
     geom_route, or constrain KRT). Gate: completion 100, unconnected 0, via_in_pad 0, shorts 0, drc 0.
  2. **D4 — aesthetic cleanup** (the "not-Freerouting" payoff): build the bus planner (route QSPI/
     SPI/I2S/SD as constant-pitch bundles via --guide-corridor) + beautification (pull-tight, 45-quantize,
     via-min, bus-pitch-normalize). Drive off_axis→0, acute→0, via_count down; render must look hand-designed.
  OLD plan (reference):
  1. **D2(4) — fix fanout-vs-escape ordering.** Adopt the route_db-centric model: base board (D1 solid
     zones, no routing) + route_db = the source of truth; regenerate the board = base + replay. Re-order
     so SIGNALS route before dense-IC power fanout (signals naturally leave the board; fanout fills the
     rest). Concretely: (a) rip routing back to the D1 solid-zone base; (b) route the critical nets first
     on EMPTY copper — USB (allow B.Cu escape / layer swap for the crossover), crystal, QSPI, I2S — via
     the bridge; (c) THEN run plane fanout in the remaining space (KRT route_planes already avoids
     existing tracks). **NO via-in-pad (USER DIRECTIVE, hard gate via_in_pad==0): pass
     `--same-net-pad-clearance 0.2` to route_planes → offset vias + stubs, via_in_pad 0 (verified;
     default −1 gives 95). NOTE: offset stubs spike track_count (~1724) → a D4 cleanup target.**
     Record everything in route_db. Verify USB now routes 4/4, drc 0, completion rises, via_in_pad 0.
     ALTERNATIVE if re-order is heavy: make the fanout escape-aware (skip/relocate fanout vias within
     ~1mm of a signal pin's escape on dense ICs). Prefer signal-first; it's cleaner and more general.
  2. **D3 — bus + bulk route** remaining signals to 100% (bus planner via --guide-corridor + KRT
     single-ended through the bridge, criticality order from route_db.stable_order), fanout last.
  OLD D2 plan (reference): via-stitch every GND (89) and +3V3 (47) pad to its inner plane +
     pour-to-pour stitching, dropping unconnected well below 147. Try KRT first:
     `~/.local/share/defcon-badge-krt/venv/bin/python ~/.local/share/defcon-badge-krt/KiCadRoutingTools/route_planes.py
     defcon_badge/defcon_badge.kicad_pcb` (read its --help; single-threaded/deterministic). If KRT's
     plane tool doesn't fit our zone setup cleanly, build routing_phase/tools/plane_fanout.py
     (deterministic: for each GND/+3V3 pad not already on its plane, drop a via at/near the pad via
     geom_route.add_via; add a structured GND stitching-via grid tying F.Cu/B.Cu pours to In1). Record
     vias in route_db (record_routes). Verify: unconnected drops, drc 0, shorts 0, frozen-file clean,
     determinism (run twice → identical via set). One LoadBoard+SaveBoard per process.
  2. **D2 critical pre-route:** bus-route + LOCK the USB diff pair (route_diff.py), crystal XIN/XOUT,
     QSPI, I2S — clean structured copper, recorded+frozen in route_db. Then D3 bus/bulk route to 100%.
  DEFERRED to fab-prep: explicit dielectric (stackup ...) block (thickness 1.6mm is set; fab metadata).
  NOTE: when the loop WRITES routing to the real board (D2+), pcbnew SaveBoard may also flush BOM
  field-defs into .kicad_pro — after any board write, assert `git diff --quiet defcon_badge/
  defcon_badge.kicad_pro defcon_badge/*.kicad_sch` and revert stray BOM-only churn (keep only the
  .kicad_pcb routing changes + intended D1 .kicad_pro netclass edit).

Then D1 (stackup rework per STACKUP_SPEC) → D2 (plane fanout + critical pre-route) → D3 (bus+bulk
route to 100%) → D4 (cleanup/DRC) → D5 (pour/stitch + determinism + render).

LOCKED Phase-D exit gates (ALL must hold; tighten only) — see HARNESS:
  completion_pct==100 (unconnected==0, divergence==0); shorts==0; drc_errors==0 (routing types);
  usb_diff_paired & skew<=2.5mm; power_min_width_ok (≥0.30mm); acute_angles==0; off_axis_segments==0;
  via_count<=budget; bus_pitch_var≈0; zones_filled_ok + GND stitching; determinism_ok==true;
  incremental 1-net re-route demonstrated; erc not worse than baseline; human-eyes render = hand-designed.
  Produced BY TOOLS (single writer); placement FROZEN (footprints never move; D1 stackup/zones excepted).

Board: 88.1×54.1mm, outline x[100,188] y[80,134]. ~62 signal nets; GND=89 pads, +3V3=47 pads on planes.
USB nets = /MCU_Core/USB_DP, /MCU_Core/USB_DM (+ connector-side Net-(U3-USB_DP/DM)). unconnected
baseline (zones unfilled) = 218; RE-BASELINE after D1 zone-fill (planes absorb GND/+3V3 → ~real signal count).
