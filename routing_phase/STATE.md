# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **D2 — Plane fanout + critical pre-route** (D0 + D1 COMPLETE)
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

Next intended action:
  1. **D2(2) (NOW) — finalize + apply plane fanout:** resolve starved_thermal (check if from D1 zone
     thermal relief; if so set plane-pad connection appropriately or accept-with-REVIEW), then run KRT
     route_planes → krt_bridge → APPLY to the REAL board; verify unconnected drops (147→~98), 0 new
     routing-type DRC, shorts 0, footprints frozen, frozen-file discipline, DETERMINISM (run twice →
     identical via fingerprint), render. Record the vias/tracks in route_db (record_routes/save_db).
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
