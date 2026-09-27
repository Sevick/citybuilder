"""
High-level API for procedural city generation.

Provides simple functions that correspond to the GUI actions:
- generate_all(): run roadmap -> polygons -> building_generation
- export_csv(): export CSV files compatible with the MASON sim module
- export_roads(): export combined city JSON (roads + optional buildings)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Sequence, Optional

# Ensure the package root is on sys.path when used as a script
try:
    import procedural_city_generation  # noqa: F401
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from procedural_city_generation.roadmap import main as roadmap_main
from procedural_city_generation.polygons import main as polygons_main
from procedural_city_generation.building_generation import main as building_generation_main
from procedural_city_generation.additional_stuff.Singleton import Singleton
from procedural_city_generation.additional_stuff import pickletools
from procedural_city_generation.export.city_csv import export_city_csv
from procedural_city_generation.export.city_json import export_city_json


def generate_all() -> None:
    """
    Run the full generation pipeline:
    1. Roadmap generation
    2. Polygon (lot/block) extraction
    3. Building generation

    Equivalent to pressing "Run" in the Roadmap, Polygons, and Building Generation tabs.
    """
    # 1. Roadmap
    Singleton("roadmap").kill()
    roadmap_main.submain()
    Singleton("roadmap").kill()

    # 2. Polygons
    Singleton("polygons").kill()
    polygons_main.submain()
    Singleton("polygons").kill()

    # 3. Building generation
    Singleton("building_generation").kill()
    building_generation_main.submain()
    Singleton("building_generation").kill()


def _load_generated_data() -> tuple[list[Any], list[Any], str]:
    """
    Load the latest generated vertex list and polygons from the temp directory.

    Returns
    -------
    vertex_list : list
        Roadmap vertices.
    polygons : list
        Building lots / block polygons.
    base_name : str
        Base name used for output files (from roadmap config).
    """
    roadmap_singleton = Singleton("roadmap")
    base_name = getattr(roadmap_singleton, "output_name", "mycity")

    vertex_list = pickletools.reconstruct(base_name)

    # Try building_generation output first, then polygons output
    polygons = []
    bgen_singleton = Singleton("building_generation")
    bgen_name = getattr(bgen_singleton, "output_name", None)
    if bgen_name:
        bgen_path = os.path.join(
            os.path.dirname(procedural_city_generation.__file__), "temp", f"{bgen_name}_polygons.txt"
        )
        if os.path.exists(bgen_path):
            import pickle
            with open(bgen_path, "rb") as f:
                polygons = pickle.loads(f.read())

    if not polygons:
        polys_singleton = Singleton("polygons")
        polys_name = getattr(polys_singleton, "input_name", None)
        if polys_name:
            poly_path = os.path.join(
                os.path.dirname(procedural_city_generation.__file__), "temp", f"{polys_name}_polygons.txt"
            )
            if os.path.exists(poly_path):
                import pickle
                with open(poly_path, "rb") as f:
                    polygons = pickle.loads(f.read())

    return vertex_list, polygons, base_name


def _prepare_export_data(
    vertex_list: Sequence[Any],
    polygons: Iterable[Any],
    *,
    scale_x: Optional[float] = None,
    scale_y: Optional[float] = None,
    merge_roads: bool = False,
    export_buildings: bool = True,
) -> dict[str, Any]:
    """
    Normalize coordinates (optional) and build lookup structures used by exporters.
    Mirrors the logic in GUI._prepare_export_data but without UI widgets.
    """
    import math

    def _collect_points(verts, polys):
        points = []
        for v in verts or []:
            try:
                points.append((float(v.coords[0]), float(v.coords[1])))
            except Exception:
                continue
        for poly in polys or []:
            verts_list = getattr(poly, "vertices", None) or []
            for vx, vy in verts_list:
                points.append((float(vx), float(vy)))
        return points

    def _normalize(value, min_v, max_v, scale):
        if scale is None:
            return value
        if max_v <= min_v:
            return 0.0
        return (value - min_v) / (max_v - min_v) * scale

    points = _collect_points(vertex_list, polygons)
    if points and (scale_x is not None or scale_y is not None):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        class _VertexProxy:
            def __init__(self, src, coords):
                self.coords = coords
                if hasattr(src, "selfindex"):
                    self.selfindex = src.selfindex
                if hasattr(src, "minor_road"):
                    self.minor_road = src.minor_road
                self.neighbours = []

        proxy_by_id = {}
        normalized_vertices = []
        for v in vertex_list or []:
            nx = _normalize(float(v.coords[0]), min_x, max_x, scale_x)
            ny = _normalize(float(v.coords[1]), min_y, max_y, scale_y)
            proxy = _VertexProxy(v, [nx, ny])
            proxy_by_id[id(v)] = proxy
            normalized_vertices.append(proxy)

        for v in vertex_list or []:
            proxy = proxy_by_id.get(id(v))
            if proxy is None:
                continue
            neighbours = []
            for n in getattr(v, "neighbours", []) or []:
                p = proxy_by_id.get(id(n))
                if p is not None:
                    neighbours.append(p)
            proxy.neighbours = neighbours

        class _PolyProxy:
            def __init__(self, src, vertices):
                self.vertices = vertices
                if hasattr(src, "poly_type"):
                    self.poly_type = src.poly_type
                if hasattr(src, "name"):
                    self.name = src.name
                if hasattr(src, "floors"):
                    self.floors = src.floors

        normalized_polygons = []
        for poly in polygons or []:
            verts_list = getattr(poly, "vertices", None) or []
            scaled = []
            for vx, vy in verts_list:
                nx = _normalize(float(vx), min_x, max_x, scale_x)
                ny = _normalize(float(vy), min_y, max_y, scale_y)
                scaled.append((nx, ny))
            normalized_polygons.append(_PolyProxy(poly, scaled))

        vertex_list = normalized_vertices
        polygons = normalized_polygons

    return {
        "vertex_list": vertex_list,
        "polygons": polygons,
        "merge_roads": merge_roads,
        "export_buildings": export_buildings,
    }


def export_csv(
    out_dir: Optional[str | Path] = None,
    *,
    merge_roads: bool = False,
    export_buildings: bool = True,
    scale_x: Optional[float] = 1000.0,
    scale_y: Optional[float] = 1000.0,
    base_junction_id: int = 100,
    base_road_id: int = 200,
    base_building_id: int = 300,
) -> dict[str, Path]:
    """
    Export the current city data to CSV files (nodes.csv, edges.csv, roads.csv,
    buildings.csv, buildings_shape.csv) in a directory compatible with the MASON
    simulation (`sim/src/main/resources/data/`).

    Parameters
    ----------
    out_dir : str | Path, optional
        Destination directory. Defaults to `procedural_city_generation/outputs/<name>_csv`.
    merge_roads : bool
        If True, merge colinear road segments into longer roads.
    export_buildings : bool
        Include building footprints and metadata.
    scale_x, scale_y : float, optional
        Optional scaling to normalize coordinates into a [0, scale] range.
    base_junction_id, base_road_id, base_building_id : int
        Starting IDs for generated objects.

    Returns
    -------
    dict mapping file role to Path.
    """
    vertex_list, polygons, base_name = _load_generated_data()
    prepared = _prepare_export_data(
        vertex_list,
        polygons,
        scale_x=scale_x,
        scale_y=scale_y,
        merge_roads=merge_roads,
        export_buildings=export_buildings,
    )

    if out_dir is None:
        out_dir = Path(
            os.path.dirname(procedural_city_generation.__file__),
            "outputs",
            f"{base_name}_csv",
        )
    else:
        out_dir = Path(out_dir)

    written = export_city_csv(
        prepared["vertex_list"],
        prepared["polygons"],
        out_dir,
        base_junction_id=base_junction_id,
        base_road_id=base_road_id,
        base_building_id=base_building_id,
        merge_roads=prepared["merge_roads"],
        export_buildings=prepared["export_buildings"],
    )
    return written


def export_roads(
    out_path: Optional[str | Path] = None,
    *,
    merge_roads: bool = False,
    export_buildings: bool = True,
    scale_x: Optional[float] = 1000.0,
    scale_y: Optional[float] = 1000.0,
) -> Path:
    """
    Export the current city data to a single JSON file containing roads and
    (optionally) building footprints. This mirrors the "Export Roads" button
    in the GUI.

    Parameters
    ----------
    out_path : str | Path, optional
        Output file path. Defaults to `procedural_city_generation/outputs/<name>_city.json`.
    merge_roads : bool
        Merge colinear road segments.
    export_buildings : bool
        Include buildings in the JSON.
    scale_x, scale_y : float, optional
        Optional coordinate scaling.

    Returns
    -------
    Path to the written JSON file.
    """
    vertex_list, polygons, base_name = _load_generated_data()
    prepared = _prepare_export_data(
        vertex_list,
        polygons,
        scale_x=scale_x,
        scale_y=scale_y,
        merge_roads=merge_roads,
        export_buildings=export_buildings,
    )

    if out_path is None:
        out_dir = Path(
            os.path.dirname(procedural_city_generation.__file__), "outputs"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{base_name}_city.json"
    else:
        out_path = Path(out_path)

    export_city_json(
        prepared["vertex_list"],
        prepared["polygons"],
        out_path,
        merge_roads=prepared["merge_roads"],
        export_buildings=prepared["export_buildings"],
    )
    return out_path


# Convenience: run everything in one call
def generate_and_export_csv(**kwargs) -> dict[str, Path]:
    """
    Run the full generation pipeline and immediately export CSV.
    Extra kwargs are forwarded to export_csv().
    """
    generate_all()
    return export_csv(**kwargs)


def generate_and_export_roads(**kwargs) -> Path:
    """
    Run the full generation pipeline and immediately export the combined JSON.
    Extra kwargs are forwarded to export_roads().
    """
    generate_all()
    return export_roads(**kwargs)