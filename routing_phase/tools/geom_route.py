#!/usr/bin/env python3
"""geom_route.py — AUTHORITATIVE copper (track/via) geometry via the pcbnew API.

The routing-phase extension of placement_phase_2/tools/geom.py. geom.py only reads/
writes FOOTPRINTS (load_pcb / apply move); a router must also read and WRITE tracks
and vias. This module adds that, obeying the same single-writer discipline:
every write asserts the board is not held open by KiCad (writer_lock) before saving,
and all geometry goes through the pcbnew API — NEVER by text-editing (segment ...)/
(via ...) s-expressions (the placement loop's hard-won lesson, now for copper).

Read helpers take a PATH (read-only LoadBoard, no mutation):
  load_tracks(path)  -> [ {kind, net, layer, layer_name, x0,y0,x1,y1, width, length_mm} ]
  load_vias(path)    -> [ {net, x, y, drill, width, top, bottom} ]
  count_unconnected(path) -> int    (pcbnew connectivity; the completion truth)

Write helpers operate on a loaded BOARD object so many edits batch into one save;
call save(path, board) to persist (asserts writable first):
  add_track(board, x0,y0,x1,y1, layer, net, width_mm) -> PCB_TRACK
  add_via(board, x,y, net, drill_mm, width_mm, top='F.Cu', bottom='B.Cu') -> PCB_VIA
  delete_routing(board) -> n_removed   (rips every track/arc/via; leaves fp+zones)
  refill_zones(board)   -> n_zones     (ZONE_FILLER over all zones)
  save(path, board)     -> writes the board (single-writer guarded)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "placement_phase_2" / "tools"))
from writer_lock import assert_writable   # noqa: E402  single-writer discipline

NM = 1e6


# --------------------------------------------------------------------------- #
# read helpers (path -> data; read-only)
# --------------------------------------------------------------------------- #
def _load(path):
    return pcbnew.LoadBoard(str(path))


def load_tracks(path) -> list[dict]:
    b = _load(path)
    out = []
    for t in b.GetTracks():
        cls = t.GetClass()
        if cls not in ("PCB_TRACK", "PCB_ARC"):
            continue
        s, e = t.GetStart(), t.GetEnd()
        out.append({
            "kind": "arc" if cls == "PCB_ARC" else "track",
            "net": t.GetNetname() or None,
            "layer": t.GetLayer(),
            "layer_name": b.GetLayerName(t.GetLayer()),
            "x0": s.x / NM, "y0": s.y / NM, "x1": e.x / NM, "y1": e.y / NM,
            "width": t.GetWidth() / NM,
            "length_mm": t.GetLength() / NM,
        })
    return out


def load_vias(path) -> list[dict]:
    b = _load(path)
    out = []
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        p = t.GetPosition()
        out.append({
            "net": t.GetNetname() or None,
            "x": p.x / NM, "y": p.y / NM,
            "drill": t.GetDrill() / NM,
            "width": t.GetWidth() / NM,
            "top": b.GetLayerName(t.TopLayer()),
            "bottom": b.GetLayerName(t.BottomLayer()),
        })
    return out


def count_unconnected(path) -> int:
    """The completion truth: pcbnew ratsnest unconnected count (visible_only=False)."""
    b = _load(path)
    b.BuildConnectivity()
    return b.GetConnectivity().GetUnconnectedCount(False)


# --------------------------------------------------------------------------- #
# write helpers (operate on a loaded board; save() persists, guarded)
# --------------------------------------------------------------------------- #
def _vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(int(round(x_mm * NM)), int(round(y_mm * NM)))


def add_track(board, x0, y0, x1, y1, layer, net, width_mm) -> "pcbnew.PCB_TRACK":
    """Create a straight copper segment. `layer` is a name ('F.Cu') or id; `net` is a
    net name (linked via FindNet so the segment carries the right netcode — what DRC's
    unconnected_items reads) or None."""
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(_vec(x0, y0))
    t.SetEnd(_vec(x1, y1))
    t.SetWidth(int(round(width_mm * NM)))
    t.SetLayer(layer if isinstance(layer, int) else board.GetLayerID(layer))
    if net is not None:
        n = board.FindNet(net)
        if n is not None:
            t.SetNet(n)
    board.Add(t)
    return t


def add_via(board, x, y, net, drill_mm, width_mm, top="F.Cu", bottom="B.Cu") -> "pcbnew.PCB_VIA":
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(_vec(x, y))
    v.SetDrill(int(round(drill_mm * NM)))
    v.SetWidth(int(round(width_mm * NM)))
    v.SetLayerPair(board.GetLayerID(top) if isinstance(top, str) else top,
                   board.GetLayerID(bottom) if isinstance(bottom, str) else bottom)
    if net is not None:
        n = board.FindNet(net)
        if n is not None:
            v.SetNet(n)
    board.Add(v)
    return v


def delete_routing(board) -> int:
    """Rip up ALL tracks/arcs/vias (the routing reset). Footprints + zones untouched."""
    victims = [t for t in board.GetTracks()
               if t.GetClass() in ("PCB_TRACK", "PCB_ARC", "PCB_VIA")]
    for t in victims:
        board.Remove(t)
    return len(victims)


def refill_zones(board) -> int:
    zones = board.Zones()
    pcbnew.ZONE_FILLER(board).Fill(zones)
    return len(zones)


def save(path, board) -> None:
    """Single writer (Resolution 1): refuse to write while KiCad holds the board open."""
    assert_writable(str(path))
    pcbnew.SaveBoard(str(path), board)


def load_board(path):
    """Expose a loaded board for batched edits; pair with save(path, board)."""
    return _load(path)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    print(f"{p}: tracks={len(load_tracks(p))} vias={len(load_vias(p))} "
          f"unconnected={count_unconnected(p)}")
