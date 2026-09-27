"""Export a combined city JSON with junctions, roads, and buildings.

This format is intended for simple downstream consumption.

Schema v2:
{ "schemaVersion": 2, "junctions": [...], "roads": [...], "buildings": [...] }

- roads[].segments is a list of segments connecting junction node ids.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence


def _vertex_id(v: Any, idx: int, base_id: int) -> int:
    return int(getattr(v, "selfindex", idx)) + base_id


def _iter_edges(vertex_list: Sequence[Any], base_junction_id: int) -> list[dict[str, Any]]:
    id_by_obj: dict[int, int] = {}
    for i, v in enumerate(vertex_list):
        id_by_obj[id(v)] = _vertex_id(v, i, base_junction_id)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for i, v in enumerate(vertex_list):
        a_id = _vertex_id(v, i, base_junction_id)
        for n in getattr(v, "neighbours", []):
            b_id = id_by_obj.get(id(n))
            if b_id is None:
                continue
            a2, b2 = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
            if a2 == b2:
                continue
            key = (a2, b2)
            if key in seen:
                continue
            seen.add(key)

            x1 = float(v.coords[0])
            y1 = float(v.coords[1])
            x2 = float(n.coords[0])
            y2 = float(n.coords[1])
            edges.append(
                {
                    "from": a_id,
                    "to": b_id,
                    "shape": [[x1, y1], [x2, y2]],
                }
            )
    return edges


def _centroid(points: Sequence[Sequence[float]]) -> tuple[float, float] | None:
    if not points:
        return None
    sx = 0.0
    sy = 0.0
    for x, y in points:
        sx += float(x)
        sy += float(y)
    n = float(len(points))
    return (sx / n, sy / n)


def _closest_point_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float]:
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return ax, ay, 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return cx, cy, t


def _nearest_road_access(
    px: float,
    py: float,
    road_segments: Sequence[tuple[int, int, float, float, float, float]],
) -> tuple[int | None, int | None, float]:
    """Return (road_id, segment_index, offset_along_segment)."""
    best_road: int | None = None
    best_seg: int | None = None
    best_offset = 0.0
    best_dist2: float | None = None

    for road_id, seg_idx, ax, ay, bx, by in road_segments:
        cx, cy, t = _closest_point_on_segment(px, py, ax, ay, bx, by)
        dist2 = (px - cx) ** 2 + (py - cy) ** 2
        if best_dist2 is None or dist2 < best_dist2:
            best_dist2 = dist2
            best_road = road_id
            best_seg = seg_idx
            best_offset = math.hypot(bx - ax, by - ay) * t

    return best_road, best_seg, best_offset


def _point_segment_distance2(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    cx, cy, _t = _closest_point_on_segment(px, py, ax, ay, bx, by)
    return (px - cx) ** 2 + (py - cy) ** 2


def _entrance_point_for_building(
    polygon: Sequence[tuple[float, float]],
    road_segments: Sequence[tuple[int, int, float, float, float, float]],
) -> tuple[float, float] | None:
    """Compute entrance point as midpoint of the façade (polygon edge) closest to any road.

    We approximate façade selection by choosing the polygon edge with the smallest distance
    to the road network (min over road segments).
    """
    if not polygon or len(polygon) < 2 or not road_segments:
        return None

    best_edge_mid: tuple[float, float] | None = None
    best_dist2: float | None = None

    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        # skip degenerate edges
        if ax == bx and ay == by:
            continue

        # Edge midpoint
        mx = (ax + bx) / 2.0
        my = (ay + by) / 2.0

        # Distance from this edge to the road network: approximate by taking min distance
        # from the edge midpoint to each road segment.
        edge_best = None
        for _road_id, _seg_idx, rx1, ry1, rx2, ry2 in road_segments:
            d2 = _point_segment_distance2(mx, my, rx1, ry1, rx2, ry2)
            if edge_best is None or d2 < edge_best:
                edge_best = d2

        if edge_best is None:
            continue
        if best_dist2 is None or edge_best < best_dist2:
            best_dist2 = edge_best
            best_edge_mid = (mx, my)

    return best_edge_mid


def _is_minor(v: Any) -> bool:
    return bool(getattr(v, "minor_road", False))


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _edge_length(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))


def _edge_direction(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx = float(b[0]) - float(a[0])
    dy = float(b[1]) - float(a[1])
    length = math.hypot(dx, dy)
    if length == 0.0:
        return 0.0, 0.0
    return dx / length, dy / length


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _build_merge_roads(
    vertex_list: Sequence[Any],
    base_junction_id: int,
    *,
    prefer_major: bool = True,
) -> list[dict[str, Any]]:
    """Build merged roads as connected chains of unique segments.

    Rules enforced:
    - every undirected edge is assigned exactly once,
    - roads are contiguous (each consecutive segment shares a node),
    - major roads are built first when requested,
    - a major road may absorb minor dead-end tails at its two ends,
    - roads may turn; collinearity is preferred but not required.
    """

    id_by_obj: dict[int, int] = {id(v): _vertex_id(v, i, base_junction_id) for i, v in enumerate(vertex_list)}
    coord_by_id: dict[int, tuple[float, float]] = {
        _vertex_id(v, i, base_junction_id): (float(v.coords[0]), float(v.coords[1])) for i, v in enumerate(vertex_list)
    }

    edges: dict[tuple[int, int], bool] = {}
    adjacency_all: dict[int, set[int]] = {}
    adjacency_major: dict[int, set[int]] = {}
    adjacency_minor: dict[int, set[int]] = {}
    for i, v in enumerate(vertex_list):
        a_id = _vertex_id(v, i, base_junction_id)
        a_minor = _is_minor(v)
        for n in getattr(v, "neighbours", []) or []:
            b_id = id_by_obj.get(id(n))
            if b_id is None or b_id == a_id:
                continue
            key = _edge_key(a_id, b_id)
            if key in edges:
                continue
            is_minor = a_minor or _is_minor(n)
            edges[key] = is_minor
            adjacency_all.setdefault(a_id, set()).add(b_id)
            adjacency_all.setdefault(b_id, set()).add(a_id)
            target_adj = adjacency_minor if is_minor else adjacency_major
            target_adj.setdefault(a_id, set()).add(b_id)
            target_adj.setdefault(b_id, set()).add(a_id)

    assigned: set[tuple[int, int]] = set()

    def available_neighbors(node: int, edge_is_minor: bool, include_assigned: bool = False) -> list[int]:
        adj = adjacency_minor if edge_is_minor else adjacency_major
        out = []
        for nxt in adj.get(node, set()):
            key = _edge_key(node, nxt)
            if edges.get(key) != edge_is_minor:
                continue
            if not include_assigned and key in assigned:
                continue
            out.append(nxt)
        out.sort()
        return out

    def score_candidate(prev: int | None, current: int, nxt: int) -> tuple[float, float, int]:
        cur_pt = coord_by_id[current]
        next_pt = coord_by_id[nxt]
        if prev is None:
            return 0.0, -_edge_length(cur_pt, next_pt), nxt
        prev_pt = coord_by_id[prev]
        incoming = _edge_direction(prev_pt, cur_pt)
        outgoing = _edge_direction(cur_pt, next_pt)
        # prefer straight continuation; on ties, prefer longer segment, then deterministic id
        return _dot(incoming, outgoing), -_edge_length(cur_pt, next_pt), nxt

    def count_unassigned(node: int, edge_is_minor: bool) -> int:
        return len(available_neighbors(node, edge_is_minor, include_assigned=False))

    def choose_next(prev: int | None, current: int, edge_is_minor: bool) -> int | None:
        candidates = available_neighbors(current, edge_is_minor, include_assigned=False)
        if prev is not None:
            candidates = [n for n in candidates if n != prev]
        if not candidates:
            return None

        preferred = [n for n in candidates if count_unassigned(n, edge_is_minor) <= 2]
        pool = preferred or candidates
        return max(pool, key=lambda n: score_candidate(prev, current, n))

    def build_chain(start_a: int, start_b: int, edge_is_minor: bool) -> list[int]:
        key = _edge_key(start_a, start_b)
        if key in assigned:
            return []
        assigned.add(key)
        path = [start_a, start_b]

        while True:
            nxt = choose_next(path[-2], path[-1], edge_is_minor)
            if nxt is None:
                break
            assigned.add(_edge_key(path[-1], nxt))
            path.append(nxt)

        while True:
            nxt = choose_next(path[1] if len(path) > 1 else None, path[0], edge_is_minor)
            if nxt is None:
                break
            assigned.add(_edge_key(path[0], nxt))
            path.insert(0, nxt)

        return path

    def maybe_attach_minor_tail(path: list[int], at_front: bool) -> list[int]:
        endpoint = path[0] if at_front else path[-1]
        prev = path[1] if at_front and len(path) > 1 else (path[-2] if len(path) > 1 else None)
        extension: list[int] = []
        current = endpoint
        current_prev = prev
        while True:
            candidates = available_neighbors(current, True, include_assigned=False)
            if current_prev is not None:
                candidates = [n for n in candidates if n != current_prev]
            if not candidates:
                break
            dead_end_candidates = [n for n in candidates if count_unassigned(n, True) <= 1]
            if not dead_end_candidates:
                break
            nxt = max(dead_end_candidates, key=lambda n: score_candidate(current_prev, current, n))
            assigned.add(_edge_key(current, nxt))
            extension.append(nxt)
            current_prev, current = current, nxt
        if at_front:
            return list(reversed(extension)) + path
        return path + extension

    def road_from_path(path: list[int], edge_is_minor: bool) -> dict[str, Any]:
        segments = []
        for u, v in zip(path, path[1:]):
            ax, ay = coord_by_id[u]
            bx, by = coord_by_id[v]
            segments.append({"from": u, "to": v, "shape": [[ax, ay], [bx, by]]})
        return {"minor_road": bool(edge_is_minor), "segments": segments}

    def emit_roads_for_class(edge_is_minor: bool, allow_minor_tails: bool = False) -> list[dict[str, Any]]:
        class_edges = sorted(k for k, is_minor in edges.items() if is_minor == edge_is_minor and k not in assigned)
        roads: list[dict[str, Any]] = []

        def node_degree(node: int) -> int:
            adj = adjacency_minor if edge_is_minor else adjacency_major
            return len(adj.get(node, set()))

        seeded: list[tuple[int, int]] = []
        fallback: list[tuple[int, int]] = []
        for a, b in class_edges:
            if _edge_key(a, b) in assigned:
                continue
            deg_a = node_degree(a)
            deg_b = node_degree(b)
            item = (a, b)
            if deg_a != 2 or deg_b != 2:
                seeded.append(item)
            else:
                fallback.append(item)

        for a, b in seeded + fallback:
            if _edge_key(a, b) in assigned:
                continue
            path = build_chain(a, b, edge_is_minor)
            if len(path) < 2:
                continue
            if allow_minor_tails and not edge_is_minor:
                path = maybe_attach_minor_tail(path, at_front=True)
                path = maybe_attach_minor_tail(path, at_front=False)
            roads.append(road_from_path(path, edge_is_minor))
        return roads

    order = [False, True] if prefer_major else [True, False]
    roads: list[dict[str, Any]] = []
    for cls in order:
        roads.extend(emit_roads_for_class(cls, allow_minor_tails=prefer_major and not cls))

    # Safety net: if anything slipped through, emit singleton roads so every edge is exported exactly once.
    for (a, b), is_minor in sorted(edges.items()):
        key = _edge_key(a, b)
        if key in assigned:
            continue
        assigned.add(key)
        roads.append(road_from_path([a, b], is_minor))

    return roads


def export_city_json(
    vertex_list: Sequence[Any],
    polygons: Iterable[Any],
    out_path: str | Path,
    *,
    base_junction_id: int = 100,
    base_road_id: int = 200,
    base_building_id: int = 300,
    default_surface: str = "asphalt",
    default_lanes: int = 2,
    default_speed_limit: int = 50,
    merge_roads: bool = False,
    export_buildings: bool = True,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    junctions = []
    for i, v in enumerate(vertex_list):
        junctions.append(
            {
                "id": _vertex_id(v, i, base_junction_id),
                "x": float(v.coords[0]),
                "y": float(v.coords[1]),
            }
        )

    raw_edges = _iter_edges(vertex_list, base_junction_id)

    roads: list[dict[str, Any]] = []
    road_segments: list[tuple[int, int, float, float, float, float]] = []

    if merge_roads:
        merged = _build_merge_roads(vertex_list, base_junction_id, prefer_major=True)
        for i, r in enumerate(merged):
            road_id = base_road_id + i
            segments = r["segments"]
            road_type = 1 if bool(r.get("minor_road", False)) else 0
            roads.append(
                {
                    "id": road_id,
                    "name": f"Road {road_id}",
                    "surface": default_surface,
                    "lanes": int(default_lanes),
                    "speedLimit": int(default_speed_limit),
                    "road_type": int(road_type),
                    "segments": segments,
                }
            )
            for seg_idx, s in enumerate(segments):
                x1, y1 = s["shape"][0]
                x2, y2 = s["shape"][1]
                road_segments.append((road_id, seg_idx, float(x1), float(y1), float(x2), float(y2)))
    else:
        for i, e in enumerate(raw_edges):
            road_id = base_road_id + i
            x1, y1 = e["shape"][0]
            x2, y2 = e["shape"][1]

            segment = {"from": e["from"], "to": e["to"], "shape": e["shape"]}
            roads.append(
                {
                    "id": road_id,
                    "name": f"Road {road_id}",
                    "surface": default_surface,
                    "lanes": int(default_lanes),
                    "speedLimit": int(default_speed_limit),
                    "road_type": 0,
                    "segments": [segment],
                }
            )
            road_segments.append((road_id, 0, float(x1), float(y1), float(x2), float(y2)))

    buildings = []
    if export_buildings:
        for i, poly in enumerate(polygons or []):
            verts = getattr(poly, "vertices", None)
            if not verts:
                continue
            points = [(float(v[0]), float(v[1])) for v in verts]
            # drop duplicate last point if polygon is closed
            if len(points) >= 2 and points[0] == points[-1]:
                points = points[:-1]
            if len(points) < 3:
                continue

            center = _centroid(points)
            if center is None:
                continue
            cx, cy = center
            road_id, seg_idx, offset = _nearest_road_access(cx, cy, road_segments)

            b_id = base_building_id + i
            poly_type = getattr(poly, "poly_type", None)
            name = getattr(poly, "name", None) or (f"{poly_type} {b_id}" if poly_type else f"Building {b_id}")
            floors = getattr(poly, "floors", None)
            if floors is None:
                floors = 1

            entrance = _entrance_point_for_building(points, road_segments)

            b: dict[str, Any] = {
                "id": b_id,
                "name": str(name),
                "floors": int(floors),
                "building": {
                    "polygon": [[float(x), float(y)] for x, y in points],
                    "entrancePointX": float(entrance[0]) if entrance is not None else None,
                    "entrancePointY": float(entrance[1]) if entrance is not None else None,
                },
            }

            # keep access metadata for backwards compatibility with existing consumers/tests
            access: dict[str, Any] = {"road": road_id, "offset": float(offset)}
            if seg_idx is not None:
                access["segment"] = int(seg_idx)
            b["access"] = access

            buildings.append(b)

    payload = {"schemaVersion": 2, "junctions": junctions, "roads": roads, "buildings": buildings}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
