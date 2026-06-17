#!/usr/bin/env python3
"""sch_health.py — AUTHORITATIVE schematic health metrics for the badge.

WHY THIS EXISTS (the same lesson as placement_phase_2/tools/geom.py):
the kicad-happy `analyze_schematic.py` OVER-MERGES hierarchical nets by base
name. It reports `+3V3` as ONE healthy 3.3 V rail (rail_voltages: {'+3V3': 3.3})
while KiCad's real netlist splits it into FIVE disconnected islands
(/Power/+3V3, /IO/+3V3, /Audio/+3V3, /LEDs_IR/+3V3, +3V3). That over-merge masks
the single biggest defect on the board. So — exactly like geom.py replaced the
regex courtyard parser with pcbnew truth — every metric here is derived from
KiCad's OWN engines:
    * `kicad-cli sch erc`              (authoritative DRC/ERC engine)
    * `kicad-cli sch export netlist`   (authoritative netlister)
which agree with what KiCad and the board itself see.

Metrics (JSON):
  erc_errors, erc_warnings              total counts by severity
  erc_by_type                           {violation_type: count} (errors only)
  erc_warn_by_type                      {violation_type: count} (warnings)
  power_pins_not_driven                 IC power-input pins with no power source on their net
  rail_fragmentation                    logical rail (base name) -> the N distinct electrical
                                        nets it was wrongly split into; is_power flag
  power_rails_fragmented                count of POWER rails split across >1 net (board-killers)
  single_pin_nets                       floating nets touching exactly one pin (excl. NC autopads)
  net_count, pin_count
  health_score / gate_*                 derived pass/fail gates (see HARNESS.md)

Usage:
  sch_health.py defcon_badge/defcon_badge.kicad_sch            # text summary
  sch_health.py defcon_badge/defcon_badge.kicad_sch --json     # full JSON
  sch_health.py ... --append schematic_phase/metrics.jsonl     # append a metrics row
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict, Counter

# A base net name is a POWER RAIL if it looks like a voltage rail or a known supply name.
_VOLT = re.compile(r'^[+-]?\d+V\d*$', re.I)            # +3V3, +1V1, +5V, 3V3, -12V
_SUPPLY = {"VBUS","VCC","VDD","VSYS","VBAT","VIN","VOUT","AVDD","DVDD","IOVDD",
           "VREG","VDDA","VDDIO","VPP","VAA","GND","AGND","DGND","VSS"}

def is_power_rail(base: str) -> bool:
    b = base.upper()
    return bool(_VOLT.match(base)) or b in _SUPPLY or base.startswith('+')

def base_name(net: str) -> str:
    """Logical rail/signal name = final path component (strips /sheet/ or /uuid/ prefix)."""
    return net.rsplit('/', 1)[-1]

def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def run_erc(sch: Path) -> dict:
    out = Path('/tmp/_schhealth_erc.json')
    _run(['kicad-cli','sch','erc','--severity-error','--severity-warning',
          '--format','json','-o',str(out),str(sch)])
    return json.loads(out.read_text())

def run_netlist(sch: Path):
    out = Path('/tmp/_schhealth_net.xml')
    _run(['kicad-cli','sch','export','netlist','--format','kicadxml',
          '-o',str(out),str(sch)])
    return ET.parse(out).getroot()

def analyze(sch: Path) -> dict:
    # ---- ERC (authoritative) ----
    erc = run_erc(sch)
    err_by_type, warn_by_type = Counter(), Counter()
    pnd = []                       # power_pin_not_driven items
    pin_conflicts = []             # pin_to_pin (e.g. two power outputs shorted)
    for s in erc.get('sheets', []):
        for v in s.get('violations', []):
            t, sev = v.get('type'), v.get('severity')
            (err_by_type if sev == 'error' else warn_by_type)[t] += 1
            if t == 'power_pin_not_driven':
                for it in v.get('items', []):
                    m = re.search(r'Symbol (\S+) Pin (\S+) \[([^,]+)', it.get('description',''))
                    if m:
                        pnd.append({'ref': m.group(1), 'pin': m.group(2), 'pin_name': m.group(3)})
            if t == 'pin_to_pin':
                pin_conflicts.append([it.get('description','') for it in v.get('items',[])])

    # ---- netlist (authoritative) ----
    root = run_netlist(sch)
    nets = {}
    for n in root.iter('net'):
        nets[n.get('name')] = [(x.get('ref'), x.get('pin')) for x in n.iter('node')]

    # rail fragmentation: a logical rail/signal split into >1 electrical net
    base_map = defaultdict(list)
    for name in nets:
        if name.startswith('unconnected-'):
            continue
        base_map[base_name(name)].append(name)
    fragmentation = {}
    for base, full in base_map.items():
        if len(full) > 1:
            fragmentation[base] = {
                'fragments': len(full),
                'is_power': is_power_rail(base),
                'nets': sorted(full),
                'pin_counts': {f: len(nets[f]) for f in sorted(full)},
            }
    power_frag = {b: v for b, v in fragmentation.items() if v['is_power']}

    # single-pin (floating) nets, excluding KiCad's auto unconnected-* nets
    single = [{'net': name, 'pin': nodes[0]}
              for name, nodes in nets.items()
              if len(nodes) == 1 and not name.startswith('unconnected-')]

    erc_errors = sum(err_by_type.values())
    erc_warnings = sum(warn_by_type.values())

    out = {
        'schematic': str(sch),
        'erc_errors': erc_errors,
        'erc_warnings': erc_warnings,
        'erc_by_type': dict(err_by_type),
        'erc_warn_by_type': dict(warn_by_type),
        'power_pins_not_driven': pnd,
        'power_pins_not_driven_count': len(pnd),
        'pin_conflicts': pin_conflicts,
        'rail_fragmentation': fragmentation,
        'power_rails_fragmented': len(power_frag),
        'power_rails_fragmented_detail': power_frag,
        'single_pin_nets': single,
        'single_pin_nets_count': len(single),
        'net_count': len(nets),
        'pin_count': sum(len(v) for v in nets.values()),
        # ---- LOCKED gates (tighten only; see schematic_phase/HARNESS.md) ----
        'gate_power_rails_unified': len(power_frag) == 0,
        'gate_power_pins_driven': len(pnd) == 0,
        'gate_no_pin_conflicts': len(pin_conflicts) == 0,
        'gate_no_floating_nets': len(single) == 0,
        'gate_erc_clean': erc_errors == 0,
    }
    return out

def text_summary(d: dict) -> str:
    L = []
    L.append(f"SCHEMATIC HEALTH — {d['schematic']}")
    L.append(f"  ERC: {d['erc_errors']} errors, {d['erc_warnings']} warnings")
    if d['erc_by_type']:
        L.append("       errors by type: " + ", ".join(f"{k}={v}" for k,v in sorted(d['erc_by_type'].items())))
    L.append(f"  POWER RAILS FRAGMENTED: {d['power_rails_fragmented']}  "
             f"{'<-- BOARD-KILLER' if d['power_rails_fragmented'] else 'OK'}")
    for b, v in d['power_rails_fragmented_detail'].items():
        L.append(f"     {b}: split into {v['fragments']} nets {v['nets']}")
    L.append(f"  POWER PINS NOT DRIVEN: {d['power_pins_not_driven_count']}")
    for p in d['power_pins_not_driven']:
        L.append(f"     {p['ref']}.{p['pin']} ({p['pin_name']})")
    L.append(f"  PIN CONFLICTS (pin_to_pin): {len(d['pin_conflicts'])}")
    L.append(f"  FLOATING (single-pin) NETS: {d['single_pin_nets_count']}")
    L.append(f"  nets={d['net_count']} pins={d['pin_count']}")
    gates = {k: v for k, v in d.items() if k.startswith('gate_')}
    L.append("  GATES: " + ", ".join(f"{k.replace('gate_','')}={'PASS' if v else 'FAIL'}" for k, v in gates.items()))
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('schematic')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--append', help='append a metrics row (jsonl) to this path')
    ap.add_argument('--iter', default='?', help='iteration tag for the metrics row')
    a = ap.parse_args()
    d = analyze(Path(a.schematic))
    if a.append:
        row = {'iter': a.iter, **{k: d[k] for k in
               ('erc_errors','erc_warnings','power_rails_fragmented',
                'power_pins_not_driven_count','single_pin_nets_count','net_count')},
               'gates': {k: d[k] for k in d if k.startswith('gate_')}}
        with open(a.append, 'a') as f:
            f.write(json.dumps(row) + '\n')
    if a.json:
        print(json.dumps(d, indent=2))
    else:
        print(text_summary(d))

if __name__ == '__main__':
    main()
