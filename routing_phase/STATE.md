# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **D1 — Stackup & rules rework** (D0 COMPLETE — instrument + geom_route + route_db + KRT all verified)
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

Next intended action:
  1. **D1 (NOW):** execute STACKUP_SPEC (rework_stackup.py): real 1.6mm JLC stack, In1 solid GND / In2
     +3V3-mixed / F+B GND pours, delete+recreate zones, fix USB_DIFF_90 netclass (pattern + 0.8→
     0.17mm), refill, re-baseline completion (freeze unconnected_baseline post-fill in baseline.json).
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
