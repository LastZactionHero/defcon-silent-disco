# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **D0 — Setup & instrument** (just authored; no tools built yet)
Current approach: build the routing system ON KiCadRoutingTools (KRT), Freerouting REJECTED.
Engine: KRT at `~/.local/share/defcon-badge-krt/KiCadRoutingTools` (pinned commit in
  `KRT_PINNED_COMMIT.txt` = ce5cb2d, v0.15.13), run via `~/.local/share/defcon-badge-krt/venv/bin/python`.
  Env is INSTALLED + smoke-tested (grid_router rust kernel + numpy/scipy/shapely OK). `setup.sh` reproduces it.

Last completed: mission-control authored (MISSION/HARNESS/PROMPT/ROUTING_SPEC/STACKUP_SPEC/
  routing_rules) + KRT env stood up. Board still 0 tracks / 0 vias (unrouted), 4-copper PORTING-
  ARTIFACT stackup (thickness 1.0mm, no dielectric block, In1 full-GND + In2 full-+3V3, 3 unfilled zones).

Next intended action (D0):
  1. Build `routing_phase/tools/measure_route.py` (per ROUTING_SPEC METRIC ENGINE). Reuse
     placement_phase_2/tools/measure.py DRC plumbing + geom. Emit the full schema; --append a
     baseline row to metrics.jsonl (completion≈0 on the unrouted board). Building it IS the D0 work.
  2. Extend geom for tracks/vias: `load_tracks/load_vias/add_track/add_via/delete_routing`
     (writer-lock-guarded) — put in `routing_phase/tools/geom_route.py` importing placement geom.
  3. Build `routing_phase/tools/route_db.py` skeleton (net_sig = sorted pin-set hash; load/save;
     diff NEW/CHANGED/DELETED/UNCHANGED). Verified determinism gate harness (route-twice compare).
  4. Confirm KRT runs against this board (a trivial `--nets`/list invocation); then advance to D1.

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
