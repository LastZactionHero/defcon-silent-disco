#!/usr/bin/env bash
# run_pipeline.sh — full reproducible placement pipeline for the badge.
# Deterministic (seeded). Produces the complete placement from a depopulated
# board using only the spec'd tools. Re-run any time to regenerate.
#
#   depopulate -> floorplan -> constructive place -> SA(+decouple,snap)
#     -> polish -> back-side decouple -> declutter (legalize) -> measure
set -e
cd "$(dirname "$0")/.."          # repo root
PCB=defcon_badge/defcon_badge.kicad_pcb
T=placement_phase_2/tools
Q() { python3 "$@" 2>/dev/null; }   # silence pcbnew enum asserts

echo "== depopulate =="
Q $T/depopulate.py $PCB
echo "== floorplan (champion A) =="
Q $T/floorplan.py $PCB --approach A --out placement_phase_2/floorplan.json | tail -1
echo "== constructive place (fixed orientations + uniform rows) =="
Q $T/place.py $PCB --plan placement_phase_2/floorplan.json | tail -1
echo "== SA optimize (passives; decoupling term + snap) =="
Q $T/anneal.py $PCB --plan placement_phase_2/floorplan.json --iters 120000 --seed 1 \
   --w-dec 8 --w-ov 250 --deco-target 1.0 --snap | grep -i ratsnest || true
echo "== polish (overlap priority) =="
Q $T/anneal.py $PCB --plan placement_phase_2/floorplan.json --iters 60000 --seed 7 \
   --w-dec 6 --w-ov 500 --deco-target 1.2 --t0 1.0 --t1 0.003 | grep -i ratsnest || true
echo "== back-side decouple stragglers =="
Q $T/backside_decouple.py $PCB --auto 2.0 | tail -1
echo "== declutter (legalize) =="
Q $T/declutter.py $PCB --clear 0.1 --pad-clear 0.3 | grep -i nudged || true
echo "== final measure =="
Q $T/measure.py $PCB --json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  {k:22} {d[k]}') for k in ['overlaps','offboard','unplaced','fp_unresolved','ratsnest_mm','decoupling_max_mm','dfm_spacing_violations','fixed_ok','erc_errors']]"
