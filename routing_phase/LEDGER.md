# LEDGER — routing loop decision log (append-only; NEVER rotate/truncate)

Format: `[ISO-date] D?(N) — action | rationale | result | Δmetric`.
Prefixes: `BLOCKER:` (stuck, exhausted approaches) · `REVIEW:` (a locked rule may be wrong — log +
keep complying) · `CHAMPION:` (new best approach) · `MANUAL(user...)` (user-directed out-of-band edit).

---

[2026-06-17] D0(0) — SETUP/AUTHORING (by the mission-author session, not a loop iteration).
  ACTION: stood up the routing phase. (1) Two deep research workflows: routing-phase bearings
  (harness reuse, headless DSN path, router survey, net plan, metric/gate spec) + routing-engine
  architecture (aesthetic routing, determinism/ECO, Freerouting fork-vs-build, KRT assessment,
  4-layer stackup rework). (2) ENGINE DECISION: REJECT Freerouting (110kloc legacy Java, structural
  ugliness, Java 25, non-deterministic, no incremental — forking buys the property we don't want);
  BUILD ON KiCadRoutingTools (MIT, KiCad-10-native, deterministic, diff-pairs/planes/rip-up; default
  aesthetics are griddy → OUR layer owns aesthetics). (3) Vetted KRT firsthand: cloned, viewed demo
  renders (confirmed default output is autorouted-looking on DENSE boards; our badge is sparse),
  confirmed MIT + KiCad 9/10 + the CLI seams (--guide-corridor, --bus, --turn/via/track-proximity
  cost, --nets/--rip-existing-nets for incrementality). (4) Installed the engine env: KRT pinned at
  ce5cb2d (v0.15.13) under ~/.local/share/defcon-badge-krt/, isolated venv with cp314
  numpy/scipy/shapely wheels, prebuilt rust grid_router kernel — smoke-tested OK. (5) Authored
  mission-control: MISSION/HARNESS/PROMPT/STATE/ROUTING_SPEC/STACKUP_SPEC/routing_rules + setup.sh.
  RATIONALE: user chose to build (not click Freerouting); the spec is aesthetic + deterministic +
  re-runnable + ours. Mirror the placement_phase_2 harness (authoritative geometry + DRC-backed
  instrument + locked gates + append-only memory + anti-thrash convergence rule).
  RESULT: env ready; board still unrouted (0 tracks/vias); 4-layer stackup is a porting artifact to
  be reworked in D1. No metrics row yet (D0's first loop iteration builds measure_route.py + baseline).
  USER DECISIONS recorded: 4-layer (rework the ported zones), fully-autonomous loop (run free,
  minimal interruption, all tooling on the table), engine = my call (chose build-on-KRT), re-runnable
  is a real goal. Δmetric: n/a (baseline pending).
  NOTE: a one-time host prerequisite remains optional — none blocking (KRT env already installed in
  the venv; no sudo/JRE needed). The loop owns the board file; placement is frozen.

[2026-06-17] D0(1) — BUILD INSTRUMENT | the loop can't fly without its metric engine + a
  copper-aware geometry layer | built routing_phase/tools/geom_route.py (authoritative track/via
  read + add_track/add_via/delete_routing/refill_zones, single-writer via writer_lock — the copper
  analog of geom.py) and measure_route.py (full routing schema per ROUTING_SPEC, reusing measure.py
  DRC plumbing). KRT smoke-tested on the real board (list_nets: 84 nets/83 comps, GND 89 / +3V3 47 /
  USB_DP 3 pads). | Δmetric: baseline row written — completion 0%, unconnected 218 (divergence 0),
  0 tracks/vias, usb_diff_paired FALSE, zones_filled_ok FALSE, drc 0, erc 0.
  FIX (frozen-file safety): a first measure mutated the approved .kicad_pro — pcbnew's settings
  manager flushes BOM field-defs (MPN/LCSC/Description, from earlier BOM work) into the real project
  on process exit after reading project state. Reverted; measure_route now runs ALL pcbnew loads +
  kicad-cli on a /tmp project copy (byte-identical reads, real frozen files never opened — verified
  git-clean after). The HARNESS already warns about this for the D2+ write path.

[2026-06-17] D0(2) — BUILD INCREMENTAL ENGINE | re-runnability must be structural (built before
  any router exists) | built routing_phase/tools/route_db.py (net_sig = sha1 of sorted pin-set
  "REFDES-PADNUM" — NOT the churning net name; live_nets/diff(NEW/CHANGED/DELETED/UNCHANGED)/
  stable_order/record_routes/replay/fingerprint) + geom_route.safe_board (/tmp-copy read context
  so any read-only tool is immune to the .kicad_pro BOM-flush). | Self-test: 64 routable nets (62
  signal + 2 planes), all NEW vs empty db, stable order front-loads the 4 USB diff nets (rank0) then
  XIN/QSPI (rank1), signatures reproducible across two reads, fingerprint empty on unrouted board,
  frozen files clean. Δmetric: board unchanged (completion 0%, unconnected 218). **D0 EXIT GATE MET**
  → advance to D1 (stackup rework per STACKUP_SPEC).

[2026-06-17] D1(1) — STACKUP/ZONE REWORK | the ported zones were crude 4-pt rectangles missing the
  right ~3.6mm of the board (D20/J20 had no ground reference) and didn't follow the sawtooth outline |
  built routing_phase/tools/rework_stackup.py: thickness 1.0→1.6mm; deleted the 3 artifact zones;
  recreated 4 zones from the real board outline inset 0.3mm (In1 solid GND plane, In2 +3V3-dominant
  pour, F.Cu + B.Cu GND pours) via SHAPE_POLY_SET + ZONE_FILLER; In2.Cu→mixed. Applied to the real
  board, verified by a fresh measure_route subprocess. | Δmetric: zones_filled_ok FALSE→TRUE,
  unconnected 218→147 (planes now carry GND/+3V3; remaining 147 = signal nets + pads still needing
  fanout vias, the D2 job), drc 0, erc 0. baseline.json frozen at 147 (completion_pct now measures
  real progress from here). Frozen-file discipline HELD: only .kicad_pcb changed (.kicad_pro/.kicad_sch
  git-clean). Render routing_phase/renders/d1_top.png reviewed: placement intact, pours present.
  GOTCHA: pcbnew swig wrapper registry corrupts after LoadBoard→mutate→Fill→Save→re-read in one
  process (raw pointers) → rework_stackup does one LoadBoard+SaveBoard, no post-save introspection;
  verification is a separate measure_route subprocess. DEFERRED to fab-prep: explicit dielectric
  (stackup ...) block (thickness set to 1.6mm; the block is fab metadata, not routing-blocking).

[2026-06-17] D1(2) — FIX USB DIFF-PAIR NETCLASS | the USB_DIFF_90 class targeted non-existent nets
  (/USB_D+ /USB_D-) so the pair silently fell back to Default, and its 0.8mm width was a 2-layer value
  | targeted minimal edits to defcon_badge.kicad_pro: patterns → the REAL nets /MCU_Core/USB_DP,
  /MCU_Core/USB_DM + the connector-side Net-(U3-USB_DP), Net-(U3-USB_DM) (whole pair through the 27R
  series Rs now controlled); diff_pair_width 0.8→0.17, diff_pair_gap 0.15→0.13 (≈90Ω over the In1 GND
  plane on the 1.6mm 4-layer stack). | Δmetric: usb_diff_paired FALSE→TRUE (gate flips). Diff is ONLY
  the netclass change (12+/4−); .kicad_sch + .kicad_pcb untouched; valid JSON; drc 0, erc 0,
  unconnected 147, zones_filled_ok TRUE. **D1 EXIT GATE MET** (zones reworked+filled, USB netclass
  fixed, unrouted DRC clean, baseline frozen) → advance to D2 (plane fanout + critical pre-route).

[2026-06-17] D2(1) — KRT INTEGRATION via a BRIDGE (escalation: KRT writer is unusable) | evaluated
  KRT route_planes for plane fanout; it computes a good fanout (GND 89/89, +3V3 47/47) BUT its board
  WRITER emits `(net "GND")` (net NAME) inside (segment)/(via) where KiCad 10 requires `(net <int>)`,
  so KRT's output board does NOT load in pcbnew OR kicad-cli ("Failed to load board"; pcbnew segfaults
  on zone-fill of it). => KRT can be a SOLVER but NOT our board writer. | ESCALATED (per HARNESS, don't
  repeat a failing move) to a BRIDGE: routing_phase/tools/krt_bridge.py — extract_routing() parses KRT's
  output tracks/vias (net names are right there) + apply_routing() re-emits them via pcbnew/geom_route
  (the authoritative single writer, HARNESS Resolution 1). This is the integration seam for ALL KRT use
  (D2 planes + D3 signals): KRT never touches the real board; pcbnew is the only writer.
  | VALIDATED on /tmp: KRT route_planes → bridge → pcbnew board LOADS in kicad-cli ✓; footprints
  byte-frozen (fp_pos_hash identical) ✓; unconnected 147→98; ZERO new routing-type DRC errors (clearance/
  dangling/width all clean). Δmetric: real board UNCHANGED this iter (147) — bridge built+validated only;
  fanout applied to the REAL board in D2(2). FINDINGS (pre-existing placement DRC, NOT routing-caused,
  present on the unrouted D1 board): 28 solder_mask_bridge (different-net fine-pitch pads — RP2040/USB-C/
  microSD; scoped out of ROUTING_TYPES like placement scoped intra-fp dfm) + 7 starved_thermal (may be
  from the D1 zone thermal relief — investigate in D2(2)). FLAG for the user: the approved placement has
  28 pre-existing solder-mask-bridge DFM warnings worth a placement revisit (out of routing scope).

[2026-06-17] D2(2) — PLANE FANOUT APPLIED (first copper on the real board) | connect GND/+3V3 pads to
  their planes so only signal nets remain to route | (a) FIX starved_thermal: D1 zones gave 7 GND pads a
  1-spoke thermal relief (min 2) on the F.Cu pour → set GND/+3V3 zones to SOLID connection
  (ZONE_CONNECTION_FULL, the textbook choice for planes) → starved_thermal 7→0. (b) FIX
  rework_stackup segfault-at-exit (pcbnew swig teardown) with os._exit(0) after a successful save.
  (c) FIX geom_route.load_vias — KiCad 10 PCB_VIA.GetWidth() needs a layer arg. (d) KRT route_planes
  (solver) → krt_bridge (extract → re-apply via pcbnew) onto the REAL board: 219 tracks + 114 vias
  (GND 75 + +3V3 39 + 14 GND-return). | Δmetric: completion 0→33.3%, unconnected 147→98 (divergence 0),
  drc_errors 0 (routing types), shorts 0, zones_filled_ok TRUE, usb_diff_paired TRUE. Footprints
  byte-frozen (fp hash unchanged); .kicad_pro/.kicad_sch git-clean. route_db recorded (64 nets; GND/+3V3
  carry the fanout). Renders d2_top.png/d2_copper.svg: placement intact. WATCH: off_axis_segments 17 +
  acute_angles 39 from KRT via-to-pad stubs → D4 cleanup (not a D2 gate). Determinism formal gate
  deferred to D5 (route_db replay is deterministic by construction; the inline replay-verify hit a
  multi-LoadBoard-per-process swig None bug in the TEST harness, fixed approach = subprocess per load).

[2026-06-17] D2(3) — CRITICAL FINDING: fanout blocks signal escape (re-order needed) + bridge fix |
  attempted USB pre-route via KRT | (1) TOOL: krt_bridge.apply_routing now supports replace=True
  (rip-then-lay) — KRT emits prior+new routing, so extracting its full output + applying with replace
  keeps the board == latest full solution with NO fanout duplication. (2) The USB pair is MULTI-POINT
  (U3 ↔ 27R R3/R4 ↔ J10) with a FORCED CROSSOVER (U3.46/DM above U3.47/DP at source, R4/DM below R3/DP
  at target → not planar on one layer). KRT route_diff couples the long J10→R leg, defers short MCU legs
  to single-ended (textbook). KRT route.py single-ended routes 3/4 USB nets but Net-(U3-USB_DP)
  (U3.47→R3.2) FAILS "no rippable blockers": the plane FANOUT VIAS around the U3 QFN form a via fence
  blocking signal escape. SYSTEMIC — power-fanout-before-signal-escape will block more nets near dense
  ICs in D3. | Δmetric: real board UNCHANGED (33.3%) — the 3/4 partial (probe: 36.7%/unconn93/DRC0) was
  NOT applied; it's incomplete and masks the real issue. ESCALATION (HARNESS: don't repeat a blocked
  move) → D2(4): adopt the route_db-as-source-of-truth model and RE-ORDER to SIGNALS-FIRST (route
  critical signals on empty copper, USB with a B.Cu/layer-swap escape for the crossover, THEN fanout in
  the remaining space). This is why we built route_db + the base/replay model — now it earns its keep.

[2026-06-17] USER DIRECTIVE — NO via-in-pad (handled out-of-band; loop idle). User: "no via-in-pad
  please". Added it as a HARD GATE via_in_pad==0: measure_route._via_in_pad counts vias whose body
  hit-tests inside a pad's copper on a layer the via touches. FINDING: the current D2(2) fanout has
  94 via-in-pad — KRT route_planes places stitching vias AT pad centers by default
  (--same-net-pad-clearance −1). FIX (verified on /tmp, clean base + bridge): pass route_planes
  --same-net-pad-clearance 0.2 → offset vias + stub traces, via_in_pad 95→0, GND 89/89 + +3V3 47/47
  still connected, drc 0, shorts 0. Trade-off: offset stubs spike track_count (~219→1724) → a D4
  cleanup/aesthetic target. Locked in HARNESS (metric + D3/D4 gate + a dedicated note), routing_rules
  (via strategy), STATE D2(4) plan, and memory [[no-via-in-pad]]. Board UNCHANGED — the 94 via-in-pad
  get eliminated when D2(4) re-runs the fanout with the offset flag. erc/drc unaffected this commit.

[2026-06-18] D2(4) — SIGNALS-FIRST RE-ORDER → 73% (the re-order works) | the fanout via-fence blocked
  signal escape (D2(3)); fix = route signals on empty copper first | validated USB routes 4/4 on the
  clean base (was 3/4 fenced). Full chain: clean base (delete_routing+refill) → KRT route.py all 62
  signals (criticality order) → KRT route_planes fanout --same-net-pad-clearance 0.2 (no via-in-pad) →
  krt_bridge extract → apply_routing(replace) to REAL → route_db recorded (v2). | Δmetric: completion
  33→73.5%, unconnected 98→39, via_in_pad 94→8, USB 4/4 (usb_diff_paired TRUE), drc 0, shorts 0,
  footprints byte-frozen, pro/sch clean. REMAINING (D3/D4): 13 signal nets FAILED (congestion →
  rip-up/reroute + guide corridors + B.Cu); +3V3 fanout 37/47 (signals took space); via_in_pad 8 from
  KRT route.py SIGNAL vias (route.py lacks --same-net-pad-clearance → must offset/nudge them, hard gate
  needs 0); off_axis 147 / acute 635 / track 2214 → board looks AUTOROUTED, aesthetic goal UNMET (D4:
  bus planner via --guide-corridor + beautification). Honest state: connected-but-spaghetti; the
  hand-designed look is the D4 payoff still ahead.

[2026-06-18] D3(1) — DIAGNOSIS: B.Cu blocked by the outer GND pours (no board change) | tried to
  push completion past 73% | the 39 unconnected = 21 plane edges (GND 11 + +3V3 10, fanout blocked by
  signals) + 18 signal edges (whole SD bus SD_SCK/MOSI/MISO/CS/CD, I2S trio, QSPI_SCLK, IR_TX, LED_SCK,
  BTN_VOL_UP/SYNC, SAO_SDA/GPIO1/GPIO2, VBAT_SENSE, 1 USB MCU-side). KEY FINDING: B.Cu is severely
  underused — F.Cu 796mm vs B.Cu 22mm (layer_balance 0.028); the cross-board buses fail for lack of
  room while the bottom layer sits empty. KRT reports "blocked by pads/stubs/ZONES" → the FILLED outer
  F.Cu/B.Cu GND pours are a solid obstacle to KRT's router → it can't route signals on B.Cu. FIX
  (D3(2)): route with the OUTER pours UNFILLED (keep inner planes), refill ALL zones at the very end so
  the pours recede around the traces. Also: KRT mps + rip-up (--rip-existing-nets all) is pathologically
  slow on this board (300k iters → minutes/timeout, several runs killed); use --ordering original (fast,
  ~instant). | Δmetric: real board UNCHANGED (73.5%, 39 unconnected, via_in_pad 8) — all experiments
  were on /tmp; real board verified clean + intact (83 fps, 2214 tracks, 169 vias). The B.Cu insight is
  the unlock for the failed cross-board buses.

[2026-06-18] D3(2) — route_pipeline tool + CORRECTED diagnosis (real board unchanged, 73%) | implement
  the D3(1) B.Cu fix | built routing_phase/tools/route_pipeline.py — the reproducible signals-first
  pipeline (base → KRT route → fanout → bridge apply), each pcbnew step subprocess-isolated; clean arg
  lists (no shell quoting — fixed the bogus "0/18"). FIXED build_base segfault: delete_routing + zone
  fill in ONE process crashes BEFORE SaveBoard (board unchanged, no output) → split into delete+save
  then unfill/fill+save (each save lands before the teardown crash). FINDINGS: (a) the D3(1) "outer GND
  pours block B.Cu" hypothesis is DISPROVEN — with them unfilled B.Cu stayed 22mm; KRT reproduced 49/62
  exactly (deterministic). (b) the real lever is --layer-costs: `--layers F.Cu B.Cu --layer-costs 3.0 1.0`
  (penalize F.Cu) forces B.Cu 22→588mm — KRT is F.Cu-dominant + won't use B.Cu unprompted; added 2.0/1.0
  to route_pipeline. (c) BUT layer-balancing does NOT fix the ~13 failing nets (still fail with B.Cu free)
  → they fail on INTRINSIC escape/crossing congestion near the U3 QFN, not layer capacity. | Δmetric:
  real board UNCHANGED (73.5%, 39 unconnected, via_in_pad 8) — pipeline reproduces it deterministically;
  not re-applied (layer-balanced apply + the 13 stragglers + via_in_pad→0 is D3(3), with DRC verify).

[2026-06-18] D3(3) — MAJOR FIX: signals were routed ON THE REFERENCE PLANES | applying the
  layer-balanced route surfaced it | the committed board (D2(4)+) had ~60 signal-track segments on the
  In1 GND / In2 +3V3 planes (IR_RX, USB, VBUS, +1V1, RUN, audio JACK_R, buttons, QSPI_SS, LED_DAT...) —
  KRT defaulted to routing on ALL 4 copper layers because earlier routes lacked --layers. This carves up
  the reference planes (serious SI flaw). route_pipeline now restricts to --layers F.Cu B.Cu (added D3(2));
  re-applied it to the real board. | Δmetric: signal-tracks-on-inner-planes ~60→0 (planes intact); both
  outer layers now used (F.Cu 736 / B.Cu 372, layer_balance 0.028→0.505); completion 73.5→75.5%; footprints
  byte-frozen; pro/sch clean; route_db v3. COST (the next cleanup, D3(4)): drc_errors 0→2 (via-to-via
  clearance — USB DP/DM vias 0.128mm apart; BTN_VOL_UP/BTN_CH vias 0.128mm) + via_in_pad 8→11 — BOTH are
  KRT route.py SIGNAL-via placement defects (unlike route_planes, route.py has no via-offset/spacing flag).
  Judgment: planes-clean + both-layer is the CORRECT design foundation (signals off the planes is
  fundamental), worth accepting 2 transient via-clearance + via_in_pad to fix with a dedicated via-fixer
  next — better than keeping a metrically-cleaner board that's structurally wrong (signals on planes).
  REVERTED an intermediate apply earlier this iter before realizing the planes issue made the balanced
  board the correct one. NOTE: route.py also routes on planes unless --layers F.Cu B.Cu — keep it in the pipeline.
