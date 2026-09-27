from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from .city_json import (
    _build_merge_roads,
    _centroid,
    _entrance_point_for_building,
    _iter_edges,
    _nearest_road_access,
    _vertex_id,
)


def _edge_type_from_segment(segment: dict[str, Any], minor_lookup: dict[tuple[int, int], bool]) -> int:
    a = int(segment["from"])
    b = int(segment["to"])
    key = (a, b) if a <= b else (b, a)
    return 1 if minor_lookup.get(key, False) else 0


def _build_minor_edge_lookup(vertex_list: Sequence[Any], base_junction_id: int) -> dict[tuple[int, int], bool]:
    id_by_obj = {id(v): _vertex_id(v, i, base_junction_id) for i, v in enumerate(vertex_list)}
    minor_lookup: dict[tuple[int, int], bool] = {}
    for i, v in enumerate(vertex_list):
        a_id = _vertex_id(v, i, base_junction_id)
        a_minor = bool(getattr(v, "minor_road", False))
        for n in getattr(v, "neighbours", []) or []:
            b_id = id_by_obj.get(id(n))
            if b_id is None or a_id == b_id:
                continue
            key = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
            if key not in minor_lookup:
                minor_lookup[key] = a_minor or bool(getattr(n, "minor_road", False))
    return minor_lookup


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _as_int(value: float) -> int:
    return int(round(float(value)))


def _serialize_array(values: Sequence[Any]) -> str:
    return ";".join(str(value) for value in values)


def _serialize_polygon(points: Sequence[tuple[float, float]]) -> str:
    flat: list[int] = []
    for x, y in points:
        flat.extend((_as_int(x), _as_int(y)))
    return _serialize_array(flat)


def export_city_csv(
    vertex_list: Sequence[Any],
    polygons: Iterable[Any],
    out_dir: str | Path,
    *,
    base_junction_id: int = 100,
    base_road_id: int = 200,
    base_building_id: int = 300,
    merge_roads: bool = False,
    export_buildings: bool = True,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_path = out_dir / "nodes.csv"
    edges_path = out_dir / "edges.csv"
    roads_path = out_dir / "roads.csv"
    buildings_path = out_dir / "buildings.csv"
    buildings_shape_path = out_dir / "buildings_shape.csv"

    minor_lookup = _build_minor_edge_lookup(vertex_list, base_junction_id)

    nodes = [
        {
            "ID": _vertex_id(v, i, base_junction_id),
            "positionX": _as_int(v.coords[0]),
            "positionY": _as_int(v.coords[1]),
        }
        for i, v in enumerate(vertex_list)
    ]

    road_segments: list[tuple[int, int, float, float, float, float]] = []
    edge_id_by_road_segment: dict[tuple[int, int], int] = {}
    road_is_main: dict[int, bool] = {}
    edges: list[dict[str, Any]] = []
    roads: list[dict[str, Any]] = []

    if merge_roads:
        merged_roads = _build_merge_roads(vertex_list, base_junction_id, prefer_major=True)
        edge_id = 0
        for road_offset, road in enumerate(merged_roads):
            road_id = base_road_id + road_offset
            segment_ids = []
            road_type = 1 if bool(road.get("minor_road", False)) else 0
            road_is_main[road_id] = road_type == 0
            for segment in road.get("segments", []):
                x1, y1 = segment["shape"][0]
                x2, y2 = segment["shape"][1]
                length = _as_int(math.hypot(float(x2) - float(x1), float(y2) - float(y1)))
                edges.append(
                    {
                        "ID": edge_id,
                        "source": int(segment["from"]),
                        "target": int(segment["to"]),
                        "length": length,
                        "type": str(road_type),
                    }
                )
                segment_ids.append(edge_id)
                segment_index = len(segment_ids) - 1
                road_segments.append((road_id, segment_index, float(x1), float(y1), float(x2), float(y2)))
                edge_id_by_road_segment[(road_id, segment_index)] = edge_id
                edge_id += 1
            roads.append(
                {
                    "ID": road_id,
                    "name": f"Road {road_id}",
                    "type": str(road_type),
                    "edges": _serialize_array(segment_ids),
                }
            )
    else:
        raw_edges = _iter_edges(vertex_list, base_junction_id)
        for edge_id, edge in enumerate(raw_edges):
            x1, y1 = edge["shape"][0]
            x2, y2 = edge["shape"][1]
            edge_type = _edge_type_from_segment(edge, minor_lookup)
            length = _as_int(math.hypot(float(x2) - float(x1), float(y2) - float(y1)))
            edges.append(
                {
                    "ID": edge_id,
                    "source": int(edge["from"]),
                    "target": int(edge["to"]),
                    "length": length,
                    "type": str(edge_type),
                }
            )
            road_id = base_road_id + edge_id
            road_is_main[road_id] = edge_type == 0
            roads.append(
                {
                    "ID": road_id,
                    "name": f"Road {road_id}",
                    "type": str(edge_type),
                    "edges": _serialize_array([edge_id]),
                }
            )
            road_segments.append((road_id, 0, float(x1), float(y1), float(x2), float(y2)))
            edge_id_by_road_segment[(road_id, 0)] = edge_id

    buildings: list[dict[str, Any]] = []
    building_shapes: list[dict[str, Any]] = []
    if export_buildings:
        for i, poly in enumerate(polygons or []):
            verts = getattr(poly, "vertices", None)
            if not verts:
                continue
            points = [(float(v[0]), float(v[1])) for v in verts]
            if len(points) >= 2 and points[0] == points[-1]:
                points = points[:-1]
            if len(points) < 3:
                continue

            center = _centroid(points)
            if center is None:
                continue

            building_id = base_building_id + i
            poly_type = getattr(poly, "poly_type", None)
            entrance = _entrance_point_for_building(points, road_segments)
            if entrance is None:
                entrance = center
            road_id, seg_idx, _offset = _nearest_road_access(float(entrance[0]), float(entrance[1]), road_segments)
            entrance_edge_id = edge_id_by_road_segment.get((int(road_id), int(seg_idx))) if road_id is not None and seg_idx is not None else None
            on_main_road = 1 if road_id is not None and road_is_main.get(int(road_id), False) else 0

            buildings.append(
                {
                    "ID": building_id,
                    "entranceX": _as_int(entrance[0]),
                    "entranceY": _as_int(entrance[1]),
                    "entranceEdgeID": "" if entrance_edge_id is None else int(entrance_edge_id),
                    "square": _as_int(_polygon_area(points)),
                    "on_main_road": on_main_road,
                }
            )
            building_shapes.append(
                {
                    "buildingID": building_id,
                    "shape": _serialize_polygon(points),
                }
            )

    def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    _write_csv(nodes_path, ["ID", "positionX", "positionY"], nodes)
    _write_csv(edges_path, ["ID", "source", "target", "length", "type"], edges)
    _write_csv(roads_path, ["ID", "name", "type", "edges"], roads)
    _write_csv(buildings_path, ["ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road"], buildings)
    _write_csv(buildings_shape_path, ["buildingID", "shape"], building_shapes)

    return {
        "nodes": nodes_path,
        "edges": edges_path,
        "roads": roads_path,
        "buildings": buildings_path,
        "buildings_shape": buildings_shape_path,
    }
