"""Export utilities for interoperability with MASON (Multi-Agent Simulator Of Neighborhoods).

This repo doesn't ship with MASON itself. The goal here is to export a road network
from the roadmap vertex graph in a *simple, MASON-friendly* way.

We export two CSV files:
- <basename>_nodes.csv : node_id,x,y,minor_road,seed
- <basename>_edges.csv : source,target (undirected, de-duplicated)

This format is easy to ingest into MASON's `sim.field.network.Network` by creating
nodes and edges programmatically.

Python: 3.10+
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple, Any


@dataclass(frozen=True)
class MasonExportPaths:
    nodes_csv: Path
    edges_csv: Path


def export_road_network_csv(vertex_list: Sequence[Any], out_dir: str | Path, basename: str) -> MasonExportPaths:
    """Export the roadmap vertex graph to two CSV files.

    Parameters
    ----------
    vertex_list:
        Sequence of roadmap Vertex objects. Each vertex must have:
        - coords: array-like with [x, y]
        - neighbours: iterable of other Vertex objects
        - minor_road: bool
        - seed: bool
        - selfindex: int (if missing we fall back to list index)
    out_dir:
        Directory to write CSVs into.
    basename:
        Base name for outputs.

    Returns
    -------
    MasonExportPaths
        Paths to the written nodes and edges CSV files.
    """

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_path = out_dir / f"{basename}_nodes.csv"
    edges_path = out_dir / f"{basename}_edges.csv"

    # assign stable ids
    id_by_obj: dict[int, int] = {}
    for i, v in enumerate(vertex_list):
        vid = getattr(v, "selfindex", i)
        id_by_obj[id(v)] = int(vid)

    # Write nodes
    with nodes_path.open("w", encoding="utf-8", newline="") as f:
        f.write("node_id,x,y,minor_road,seed\n")
        for i, v in enumerate(vertex_list):
            vid = getattr(v, "selfindex", i)
            x = float(v.coords[0])
            y = float(v.coords[1])
            minor = 1 if bool(getattr(v, "minor_road", False)) else 0
            seed = 1 if bool(getattr(v, "seed", False)) else 0
            f.write(f"{int(vid)},{x},{y},{minor},{seed}\n")

    # Write edges (undirected; de-duplicate)
    seen: set[Tuple[int, int]] = set()
    with edges_path.open("w", encoding="utf-8", newline="") as f:
        f.write("source,target\n")
        for i, v in enumerate(vertex_list):
            a = int(getattr(v, "selfindex", i))
            for n in getattr(v, "neighbours", []):
                b = id_by_obj.get(id(n))
                if b is None:
                    # neighbour not in vertex_list; skip rather than crash
                    continue
                a2, b2 = (a, b) if a <= b else (b, a)
                if a2 == b2:
                    continue
                key = (a2, b2)
                if key in seen:
                    continue
                seen.add(key)
                f.write(f"{a2},{b2}\n")

    return MasonExportPaths(nodes_csv=nodes_path, edges_csv=edges_path)

