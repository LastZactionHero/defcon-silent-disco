.PHONY: help render render-quick sync zones fab clean drc erc all

PCB := defcon_badge/defcon_badge.kicad_pcb
SCH := defcon_badge/defcon_badge.kicad_sch
TOOLS := defcon_badge/tools

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "} {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

render: ## Render full board views (top/bottom/all + PNGs) to renders/
	$(TOOLS)/render_pcb.sh

render-quick: ## Render just the assembly view to renders/assembly.png
	$(TOOLS)/render_pcb.sh --quick

sync: ## Sync nets from the schematic into the PCB
	python3 $(TOOLS)/sync_nets.py

drc: ## Run DRC + refill zones + save board (strips nets — run sync after)
	kicad-cli pcb drc --refill-zones --save-board --format report \
	  -o /tmp/drc.rpt $(PCB) && tail -3 /tmp/drc.rpt

erc: ## Run ERC and summarize
	kicad-cli sch erc --format json -o /tmp/erc.json $(SCH) > /dev/null
	@python3 -c "import json; d=json.load(open('/tmp/erc.json')); \
	  print(f'ERC: {sum(len(s.get(\"violations\",[])) for s in d.get(\"sheets\",[]))} violations')"

# The full fab build: refill zones (strips nets) → re-sync nets → patch
# J10 → export gerbers/drill/pos. Run this when you want to ship.
fab: ## Refill zones, re-sync nets, patch J10, export gerbers + drill + pos + BOM
	@echo ">>> Step 1: refill zones (this strips top-level net decls)"
	@kicad-cli pcb drc --refill-zones --save-board --format report \
	  -o /tmp/drc.rpt $(PCB) | tail -2
	@echo ">>> Step 2: re-sync nets from schematic"
	@python3 $(TOOLS)/sync_nets.py
	@echo ">>> Step 3: re-patch J10 USB-C pads (UFP mapping)"
	@python3 $(TOOLS)/patch_j10_nets.py
	@echo ">>> Step 4: export gerbers + drill + pos + BOM to fab/"
	@rm -rf fab/gerbers && mkdir -p fab/gerbers
	@kicad-cli pcb export gerbers --output fab/gerbers/ $(PCB) | tail -1
	@kicad-cli pcb export drill --output fab/gerbers/ --format excellon $(PCB) | tail -1
	@kicad-cli pcb export pos --output fab/defcon_badge-pos.csv --format csv --units mm $(PCB) | tail -1
	@kicad-cli sch export bom --output fab/defcon_badge-bom.csv \
	  --fields 'Reference,Value,Footprint,MPN,LCSC' --group-by 'Value,Footprint' $(SCH) | tail -1
	@echo ">>> Done. fab/ contents:"
	@ls -lh fab/

clean: ## Remove generated artifacts (renders, fab/gerbers, /tmp reports)
	rm -rf renders/ fab/gerbers/ /tmp/erc.json /tmp/drc.rpt /tmp/defcon_netlist.net

all: sync fab render ## Run full pipeline (sync, fab, render)
