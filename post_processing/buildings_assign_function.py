"""Assign functions and workers to buildings from exported city CSV files.

The script combines building geometry, optional road-network topology, and a
building-type/profession mapping to place landmark buildings, derive urban
districts, and assign workplace functions while matching target profession
counts as closely as possible.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BUILDINGS_PATH = BASE_DIR / "input" / "buildings.csv"
DEFAULT_PROFESSIONS_PATH = BASE_DIR / "input" / "professions_absolute_count.csv"
DEFAULT_MAPPING_PATH = BASE_DIR / "input" / "building_types_profession_mapping.csv"
DEFAULT_NODES_PATH = BASE_DIR / "input" / "nodes.csv"
DEFAULT_EDGES_PATH = BASE_DIR / "input" / "edges.csv"
DEFAULT_ROADS_PATH = BASE_DIR / "input" / "roads.csv"
DEFAULT_ASSIGNMENTS_OUTPUT_PATH = BASE_DIR / "output" / "building_function_assignments.csv"
DEFAULT_WORKERS_OUTPUT_PATH = BASE_DIR / "output" / "building_function_workers.csv"

FORUM_DISTANCE_THRESHOLD = 200.0
MARKET_DISTANCE_THRESHOLD = 400.0
ELITE_DISTANCE_THRESHOLD = 500.0
HOUSING_DISTANCE_THRESHOLD = 900.0
COMMERCIAL_CORRIDOR_THRESHOLD = 40.0
MARKET_CORRIDOR_THRESHOLD = 50.0
LOCAL_DENSITY_RADIUS = 120.0

DISTRICT_PRIORITY = {
	"FORUM": 0,
	"MARKET": 1,
	"ELITE": 2,
	"COMMERCIAL": 3,
	"HOUSING": 4,
	"WAREHOUSE": 5,
	"INDUSTRIAL": 6,
}

DISTRICT_CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
	"FORUM": {
		"public": 1.00,
		"service": 0.90,
		"elite": 0.80,
		"shop": 0.55,
		"entertainment": 0.50,
		"tavern": 0.30,
		"workshop": 0.15,
		"industrial": 0.05,
		"warehouse": 0.10,
		"infrastructure": 0.20,
		"housing": 0.50,
		"shady": 0.05,
	},
	"MARKET": {
		"shop": 1.00,
		"tavern": 0.80,
		"warehouse": 0.55,
		"service": 0.45,
		"public": 0.30,
		"workshop": 0.35,
		"housing": 0.45,
		"elite": 0.20,
		"industrial": 0.15,
		"infrastructure": 0.10,
		"shady": 0.20,
		"entertainment": 0.25,
	},
	"ELITE": {
		"elite": 1.00,
		"public": 0.55,
		"service": 0.45,
		"shop": 0.35,
		"housing": 0.60,
		"tavern": 0.10,
		"workshop": 0.15,
		"industrial": 0.05,
		"warehouse": 0.05,
		"infrastructure": 0.15,
		"shady": 0.02,
		"entertainment": 0.30,
	},
	"COMMERCIAL": {
		"shop": 1.00,
		"tavern": 0.85,
		"service": 0.65,
		"warehouse": 0.50,
		"workshop": 0.40,
		"public": 0.25,
		"housing": 0.35,
		"industrial": 0.20,
		"infrastructure": 0.10,
		"elite": 0.15,
		"shady": 0.35,
		"entertainment": 0.25,
	},
	"HOUSING": {
		"housing": 1.00,
		"shop": 0.35,
		"tavern": 0.35,
		"service": 0.30,
		"workshop": 0.20,
		"public": 0.15,
		"warehouse": 0.10,
		"industrial": 0.10,
		"infrastructure": 0.15,
		"elite": 0.25,
		"shady": 0.15,
		"entertainment": 0.10,
	},
	"WAREHOUSE": {
		"warehouse": 1.00,
		"industrial": 0.60,
		"workshop": 0.45,
		"shop": 0.20,
		"tavern": 0.20,
		"housing": 0.25,
		"public": 0.10,
		"service": 0.15,
		"infrastructure": 0.45,
		"elite": 0.02,
		"shady": 0.20,
		"entertainment": 0.05,
	},
	"INDUSTRIAL": {
		"industrial": 1.00,
		"workshop": 0.80,
		"warehouse": 0.45,
		"infrastructure": 0.55,
		"housing": 0.30,
		"tavern": 0.20,
		"shop": 0.15,
		"public": 0.08,
		"service": 0.10,
		"elite": 0.02,
		"shady": 0.25,
		"entertainment": 0.05,
	},
}

PSEUDO_FUNCTIONS = {
	"FORUM": "forum_square_or_civic_court",
	"MARKET": "market_residential_mixed_use",
	"ELITE": "elite_residence",
	"COMMERCIAL": "street_front_residence",
	"HOUSING": "dense_housing",
	"WAREHOUSE": "storage_courtyard",
	"INDUSTRIAL": "peripheral_housing_or_yard",
}

TYPE_CATEGORY_OVERRIDES = {
	1: "warehouse",
	2: "workshop",
	3: "shop",
	4: "shop",
	5: "shop",
	6: "workshop",
	7: "shop",
	8: "shop",
	9: "workshop",
	10: "workshop",
	11: "shop",
	12: "industrial",
	13: "workshop",
	14: "industrial",
	15: "workshop",
	16: "workshop",
	17: "shop",
	18: "public",
	19: "industrial",
	20: "industrial",
	21: "workshop",
	22: "industrial",
	23: "workshop",
	24: "workshop",
	25: "shop",
	26: "service",
	27: "warehouse",
	28: "warehouse",
	29: "tavern",
	30: "service",
	31: "public",
	32: "service",
	33: "public",
	34: "public",
	35: "public",
	36: "entertainment",
	37: "elite",
	38: "shop",
	39: "shady",
	40: "shady",
	41: "industrial",
	42: "infrastructure",
	43: "infrastructure",
	44: "infrastructure",
	45: "public",
	46: "warehouse",
}

LANDMARK_TYPE_SEQUENCE = (
	("FORUM", 34),
	("TEMPLE", 33),
	("MARKET", 25),
	("COURTHOUSE", 45),
	("BATHHOUSE", 30),
)

LANDMARK_DISTANCE_TARGETS = {
	"FORUM": 80.0,
	"TEMPLE": 140.0,
	"MARKET": 220.0,
	"COURTHOUSE": 180.0,
	"BATHHOUSE": 260.0,
}


@dataclass(frozen=True)
class ProfessionTarget:
	profession_id: str
	name: str
	count: int


@dataclass(frozen=True)
class BuildingTypeRole:
	profession_id: str
	min_people: int
	max_people: int


@dataclass
class BuildingTypeDefinition:
	building_type_id: int
	name: str
	roles: list[BuildingTypeRole] = field(default_factory=list)
	category: str = "workshop"
	capacity_percentile: float = 0.0

	@property
	def min_workers(self) -> int:
		return sum(role.min_people for role in self.roles)

	@property
	def max_workers(self) -> int:
		return sum(role.max_people for role in self.roles)


@dataclass(frozen=True)
class NodeRecord:
	node_id: int
	x: float
	y: float


@dataclass(frozen=True)
class EdgeRecord:
	edge_id: int
	source: int
	target: int
	length: float
	edge_type: int
	road_id: int | None = None


@dataclass(frozen=True)
class RoadRecord:
	road_id: int
	road_type: int
	edge_ids: tuple[int, ...]


@dataclass(frozen=True)
class BuildingRecord:
	building_id: str
	x: float
	y: float
	entrance_edge_id: int | None
	square: float
	on_main_road: bool


@dataclass(frozen=True)
class BuildingContext:
	district: str
	forum_distance: float
	distance_to_main_corridor: float
	road_centrality: float
	local_density: int
	boundary_distance: float
	nearest_edge_id: int | None


@dataclass
class BuildingAssignment:
	building: BuildingRecord
	district: str
	assigned_function: str
	building_type_id: int | None = None
	building_type_name: str = ""
	landmark: str = ""
	economic_cluster: str = ""
	worker_capacity: int = 0
	workers: dict[str, int] = field(default_factory=dict)
	forum_distance: float = 0.0
	distance_to_main_corridor: float = math.inf
	road_centrality: float = 0.0
	local_density: int = 0

	@property
	def assigned_workers(self) -> int:
		return sum(self.workers.values())


@dataclass(frozen=True)
class GraphMetrics:
	forum_node_id: int | None
	forum_node_ids: tuple[int, ...]
	forum_center: tuple[float, float]
	node_betweenness: dict[int, float]
	node_closeness: dict[int, float]
	node_degree: dict[int, int]
	node_forum_score: dict[int, float]
	edge_betweenness: dict[int, float]
	normalized_edge_centrality: dict[int, float]
	major_edge_ids: set[int]
	forum_distances: dict[int, float]


def _require_columns(fieldnames: Iterable[str] | None, required: set[str], path: Path) -> None:
	missing_columns = required.difference(fieldnames or [])
	if missing_columns:
		missing_list = ", ".join(sorted(missing_columns))
		raise ValueError(f"Missing required columns in {path}: {missing_list}")


def _parse_int(value: str, *, column: str, path: Path) -> int:
	try:
		return int(value)
	except ValueError as exc:
		raise ValueError(f"Invalid integer {value!r} for column {column!r} in {path}") from exc


def _parse_float(value: str, *, column: str, path: Path) -> float:
	try:
		return float(value)
	except ValueError as exc:
		raise ValueError(f"Invalid number {value!r} for column {column!r} in {path}") from exc


def _normalize(values: dict[int, float] | dict[int, int]) -> dict[int, float]:
	if not values:
		return {}
	numeric_values = [float(value) for value in values.values()]
	minimum = min(numeric_values)
	maximum = max(numeric_values)
	if math.isclose(minimum, maximum):
		return {key: 1.0 for key in values}
	return {key: (float(value) - minimum) / (maximum - minimum) for key, value in values.items()}


def _quantile(values: Iterable[float], q: float) -> float:
	ordered = sorted(float(value) for value in values)
	if not ordered:
		return 0.0
	if len(ordered) == 1:
		return ordered[0]
	position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
	lower = math.floor(position)
	upper = math.ceil(position)
	if lower == upper:
		return ordered[lower]
	weight = position - lower
	return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _euclidean(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
	return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def _point_segment_distance(
	point: tuple[float, float],
	segment_start: tuple[float, float],
	segment_end: tuple[float, float],
) -> float:
	px, py = point
	x1, y1 = segment_start
	x2, y2 = segment_end
	dx = x2 - x1
	dy = y2 - y1
	if math.isclose(dx, 0.0) and math.isclose(dy, 0.0):
		return _euclidean(point, segment_start)
	t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
	t = max(0.0, min(1.0, t))
	projected = (x1 + t * dx, y1 + t * dy)
	return _euclidean(point, projected)


def _read_dict_rows(path: Path) -> list[dict[str, str]]:
	with path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		return list(reader)


def load_profession_counts(input_path: Path) -> dict[str, ProfessionTarget]:
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(reader.fieldnames, {"Synthetic ID", "Count"}, input_path)

		professions: dict[str, ProfessionTarget] = {}
		for row in reader:
			profession_id = (row.get("Synthetic ID") or "").strip()
			count_text = (row.get("Count") or "").strip()
			name = (row.get("Name") or profession_id).strip()

			if not profession_id:
				continue
			if not count_text:
				raise ValueError(f"Missing Count for profession {profession_id!r} in {input_path}")

			count = _parse_int(count_text, column="Count", path=input_path)
			if count < 0:
				raise ValueError(f"Negative Count for profession {profession_id!r} in {input_path}")
			if profession_id in professions:
				raise ValueError(f"Duplicate profession id {profession_id!r} in {input_path}")

			professions[profession_id] = ProfessionTarget(profession_id=profession_id, name=name, count=count)

	if not professions:
		raise ValueError(f"No profession rows found in {input_path}")

	return professions


def _infer_category(building_type_id: int, name: str) -> str:
	if building_type_id in TYPE_CATEGORY_OVERRIDES:
		return TYPE_CATEGORY_OVERRIDES[building_type_id]

	lowered = name.lower()
	if any(keyword in lowered for keyword in ("temple", "civic", "courthouse", "barracks")):
		return "public"
	if any(keyword in lowered for keyword in ("warehouse", "depot", "stable")):
		return "warehouse"
	if any(keyword in lowered for keyword in ("tavern", "inn", "brothel")):
		return "tavern"
	if any(keyword in lowered for keyword in ("market", "stall", "shop", "exchange")):
		return "shop"
	if any(keyword in lowered for keyword in ("quarry", "brick", "mine", "tannery", "shipyard")):
		return "industrial"
	if any(keyword in lowered for keyword in ("bathhouse", "clinic", "school", "library")):
		return "service"
	if any(keyword in lowered for keyword in ("domus", "villa")):
		return "elite"
	return "workshop"


def load_building_type_mappings(
	input_path: Path,
	professions: dict[str, ProfessionTarget] | None = None,
) -> dict[int, BuildingTypeDefinition]:
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(
			reader.fieldnames,
			{"BuildingTypeID", "BuildingTypeName", "ProfessionID", "MinNumberOfPeople", "MaxNumberOfPeople"},
			input_path,
		)

		mappings: dict[int, BuildingTypeDefinition] = {}
		for row in reader:
			type_id_text = (row.get("BuildingTypeID") or "").strip()
			profession_id = (row.get("ProfessionID") or "").strip()
			if not type_id_text or not profession_id:
				continue

			building_type_id = _parse_int(type_id_text, column="BuildingTypeID", path=input_path)
			building_type_name = (row.get("BuildingTypeName") or "").strip() or f"Building Type {building_type_id}"
			min_people = _parse_int((row.get("MinNumberOfPeople") or "").strip(), column="MinNumberOfPeople", path=input_path)
			max_people = _parse_int((row.get("MaxNumberOfPeople") or "").strip(), column="MaxNumberOfPeople", path=input_path)

			if min_people < 0 or max_people < 0:
				raise ValueError(f"Negative worker range for building type {building_type_id} in {input_path}")
			if min_people > max_people:
				raise ValueError(
					f"MinNumberOfPeople greater than MaxNumberOfPeople for building type {building_type_id} profession {profession_id!r}"
				)
			if professions is not None and profession_id not in professions:
				raise ValueError(
					f"Profession {profession_id!r} from {input_path} is not present in profession counts input"
				)

			definition = mappings.setdefault(
				building_type_id,
				BuildingTypeDefinition(
					building_type_id=building_type_id,
					name=building_type_name,
					category=_infer_category(building_type_id, building_type_name),
				),
			)
			definition.roles.append(
				BuildingTypeRole(
					profession_id=profession_id,
					min_people=min_people,
					max_people=max_people,
				)
			)

	if not mappings:
		raise ValueError(f"No building type mappings found in {input_path}")

	capacities = {type_id: definition.max_workers for type_id, definition in mappings.items()}
	normalized_capacities = _normalize(capacities)
	for type_id, definition in mappings.items():
		definition.capacity_percentile = normalized_capacities.get(type_id, 0.0)
	return mappings


def load_buildings(input_path: Path) -> list[BuildingRecord]:
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(
			reader.fieldnames,
			{"ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road"},
			input_path,
		)

		buildings: list[BuildingRecord] = []
		for row in reader:
			building_id = (row.get("ID") or "").strip()
			if not building_id:
				continue
			edge_text = (row.get("entranceEdgeID") or "").strip()
			buildings.append(
				BuildingRecord(
					building_id=building_id,
					x=_parse_float((row.get("entranceX") or "").strip(), column="entranceX", path=input_path),
					y=_parse_float((row.get("entranceY") or "").strip(), column="entranceY", path=input_path),
					entrance_edge_id=int(edge_text) if edge_text else None,
					square=_parse_float((row.get("square") or "").strip(), column="square", path=input_path),
					on_main_road=((row.get("on_main_road") or "0").strip() == "1"),
				)
			)

	if not buildings:
		raise ValueError(f"No building rows found in {input_path}")
	return buildings


def load_nodes(input_path: Path | None) -> dict[int, NodeRecord]:
	if input_path is None or not input_path.exists():
		return {}
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(reader.fieldnames, {"ID", "positionX", "positionY"}, input_path)
		nodes: dict[int, NodeRecord] = {}
		for row in reader:
			node_id_text = (row.get("ID") or "").strip()
			if not node_id_text:
				continue
			node_id = _parse_int(node_id_text, column="ID", path=input_path)
			nodes[node_id] = NodeRecord(
				node_id=node_id,
				x=_parse_float((row.get("positionX") or "").strip(), column="positionX", path=input_path),
				y=_parse_float((row.get("positionY") or "").strip(), column="positionY", path=input_path),
			)
		return nodes


def load_edges(input_path: Path | None) -> dict[int, EdgeRecord]:
	if input_path is None or not input_path.exists():
		return {}
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(reader.fieldnames, {"ID", "source", "target", "length", "type"}, input_path)
		edges: dict[int, EdgeRecord] = {}
		for row in reader:
			edge_id_text = (row.get("ID") or "").strip()
			if not edge_id_text:
				continue
			edge_id = _parse_int(edge_id_text, column="ID", path=input_path)
			edges[edge_id] = EdgeRecord(
				edge_id=edge_id,
				source=_parse_int((row.get("source") or "").strip(), column="source", path=input_path),
				target=_parse_int((row.get("target") or "").strip(), column="target", path=input_path),
				length=_parse_float((row.get("length") or "").strip(), column="length", path=input_path),
				edge_type=_parse_int((row.get("type") or "").strip(), column="type", path=input_path),
			)
		return edges


def load_roads(input_path: Path | None) -> dict[int, RoadRecord]:
	if input_path is None or not input_path.exists():
		return {}
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		_require_columns(reader.fieldnames, {"ID", "type", "edges"}, input_path)
		roads: dict[int, RoadRecord] = {}
		for row in reader:
			road_id_text = (row.get("ID") or "").strip()
			if not road_id_text:
				continue
			edge_ids = tuple(
				_parse_int(part.strip(), column="edges", path=input_path)
				for part in (row.get("edges") or "").split(";")
				if part.strip()
			)
			road_id = _parse_int(road_id_text, column="ID", path=input_path)
			roads[road_id] = RoadRecord(
				road_id=road_id,
				road_type=_parse_int((row.get("type") or "").strip(), column="type", path=input_path),
				edge_ids=edge_ids,
			)
		return roads


def _build_edge_road_lookup(roads: dict[int, RoadRecord]) -> dict[int, int]:
	lookup: dict[int, int] = {}
	for road_id, road in roads.items():
		for edge_id in road.edge_ids:
			lookup[edge_id] = road_id
	return lookup


def _build_adjacency(edges: dict[int, EdgeRecord]) -> dict[int, list[tuple[int, float, int]]]:
	adjacency: dict[int, list[tuple[int, float, int]]] = defaultdict(list)
	for edge in edges.values():
		adjacency[edge.source].append((edge.target, edge.length, edge.edge_id))
		adjacency[edge.target].append((edge.source, edge.length, edge.edge_id))
	return adjacency


def _single_source_shortest_paths(
	source: int,
	adjacency: dict[int, list[tuple[int, float, int]]],
) -> dict[int, float]:
	distances = {source: 0.0}
	heap: list[tuple[float, int]] = [(0.0, source)]
	while heap:
		current_distance, node_id = heapq.heappop(heap)
		if current_distance > distances.get(node_id, math.inf):
			continue
		for neighbour_id, length, _edge_id in adjacency.get(node_id, []):
			candidate = current_distance + length
			if candidate + 1e-9 < distances.get(neighbour_id, math.inf):
				distances[neighbour_id] = candidate
				heapq.heappush(heap, (candidate, neighbour_id))
	return distances


def compute_graph_metrics(
	nodes: dict[int, NodeRecord],
	edges: dict[int, EdgeRecord],
	roads: dict[int, RoadRecord],
) -> GraphMetrics:
	if not nodes or not edges:
		center = (0.0, 0.0)
		return GraphMetrics(
			forum_node_id=None,
			forum_node_ids=(),
			forum_center=center,
			node_betweenness={},
			node_closeness={},
			node_degree={},
			node_forum_score={},
			edge_betweenness={},
			normalized_edge_centrality={},
			major_edge_ids=set(),
			forum_distances={},
		)

	adjacency = _build_adjacency(edges)
	node_ids = list(nodes)
	node_betweenness = {node_id: 0.0 for node_id in node_ids}
	edge_betweenness = {edge_id: 0.0 for edge_id in edges}
	node_closeness: dict[int, float] = {}
	node_degree = {node_id: len(adjacency.get(node_id, [])) for node_id in node_ids}

	for source in node_ids:
		predecessors: dict[int, list[tuple[int, int]]] = defaultdict(list)
		sigma = {node_id: 0.0 for node_id in node_ids}
		sigma[source] = 1.0
		distances = {node_id: math.inf for node_id in node_ids}
		distances[source] = 0.0
		stack: list[int] = []
		heap: list[tuple[float, int]] = [(0.0, source)]

		while heap:
			current_distance, node_id = heapq.heappop(heap)
			if current_distance > distances[node_id] + 1e-9:
				continue
			stack.append(node_id)
			for neighbour_id, length, edge_id in adjacency.get(node_id, []):
				candidate = current_distance + length
				if candidate + 1e-9 < distances[neighbour_id]:
					distances[neighbour_id] = candidate
					heapq.heappush(heap, (candidate, neighbour_id))
					sigma[neighbour_id] = sigma[node_id]
					predecessors[neighbour_id] = [(node_id, edge_id)]
				elif math.isclose(candidate, distances[neighbour_id], rel_tol=1e-9, abs_tol=1e-9):
					sigma[neighbour_id] += sigma[node_id]
					predecessors[neighbour_id].append((node_id, edge_id))

		reachable = [distance for distance in distances.values() if distance < math.inf]
		if len(reachable) > 1:
			total_distance = sum(distance for distance in reachable if distance > 0)
			scale = (len(reachable) - 1) / max(1, len(node_ids) - 1)
			node_closeness[source] = ((len(reachable) - 1) / total_distance) * scale if total_distance > 0 else 0.0
		else:
			node_closeness[source] = 0.0

		dependency = {node_id: 0.0 for node_id in node_ids}
		while stack:
			node_id = stack.pop()
			if sigma[node_id] == 0:
				continue
			coefficient = (1.0 + dependency[node_id]) / sigma[node_id]
			for predecessor_id, edge_id in predecessors.get(node_id, []):
				contribution = sigma[predecessor_id] * coefficient
				dependency[predecessor_id] += contribution
				edge_betweenness[edge_id] += contribution
			if node_id != source:
				node_betweenness[node_id] += dependency[node_id]

	for node_id in node_betweenness:
		node_betweenness[node_id] /= 2.0
	for edge_id in edge_betweenness:
		edge_betweenness[edge_id] /= 2.0

	normalized_betweenness = _normalize(node_betweenness)
	normalized_closeness = _normalize(node_closeness)
	normalized_degree = _normalize(node_degree)
	forum_scores = {
		node_id: 0.5 * normalized_betweenness.get(node_id, 0.0)
		+ 0.3 * normalized_closeness.get(node_id, 0.0)
		+ 0.2 * normalized_degree.get(node_id, 0.0)
		for node_id in node_ids
	}

	forum_node_id = max(forum_scores, key=forum_scores.get)
	ranked_forum_nodes = sorted(forum_scores, key=lambda node_id: (-forum_scores[node_id], node_id))
	forum_cluster = [forum_node_id]
	top_score = forum_scores[forum_node_id]
	forum_point = (nodes[forum_node_id].x, nodes[forum_node_id].y)
	for node_id in ranked_forum_nodes[1:]:
		if len(forum_cluster) >= 3:
			break
		if forum_scores[node_id] < top_score * 0.9:
			continue
		candidate_point = (nodes[node_id].x, nodes[node_id].y)
		if _euclidean(forum_point, candidate_point) <= 150.0:
			forum_cluster.append(node_id)

	forum_center = (
		sum(nodes[node_id].x for node_id in forum_cluster) / len(forum_cluster),
		sum(nodes[node_id].y for node_id in forum_cluster) / len(forum_cluster),
	)
	normalized_edge_centrality = _normalize(edge_betweenness)
	threshold = _quantile(normalized_edge_centrality.values(), 0.85)
	major_edge_ids = {edge_id for edge_id, value in normalized_edge_centrality.items() if value >= threshold and value > 0}

	if not major_edge_ids:
		edge_lookup = _build_edge_road_lookup(roads)
		major_edge_ids = {
			edge_id
			for edge_id, edge in edges.items()
			if (edge.road_id is not None and roads.get(edge.road_id, RoadRecord(-1, 1, tuple())).road_type == 0)
			or edge.edge_type == 0
			or edge_lookup.get(edge_id) in {road_id for road_id, road in roads.items() if road.road_type == 0}
		}

	forum_distances = _single_source_shortest_paths(forum_node_id, adjacency)

	return GraphMetrics(
		forum_node_id=forum_node_id,
		forum_node_ids=tuple(forum_cluster),
		forum_center=forum_center,
		node_betweenness=node_betweenness,
		node_closeness=node_closeness,
		node_degree=node_degree,
		node_forum_score=forum_scores,
		edge_betweenness=edge_betweenness,
		normalized_edge_centrality=normalized_edge_centrality,
		major_edge_ids=major_edge_ids,
		forum_distances=forum_distances,
	)


def _augment_edges_with_road_ids(edges: dict[int, EdgeRecord], roads: dict[int, RoadRecord]) -> dict[int, EdgeRecord]:
	if not roads:
		return edges
	edge_to_road = _build_edge_road_lookup(roads)
	augmented: dict[int, EdgeRecord] = {}
	for edge_id, edge in edges.items():
		augmented[edge_id] = EdgeRecord(
			edge_id=edge.edge_id,
			source=edge.source,
			target=edge.target,
			length=edge.length,
			edge_type=edge.edge_type,
			road_id=edge_to_road.get(edge_id),
		)
	return augmented


def _edge_segments(edges: dict[int, EdgeRecord], nodes: dict[int, NodeRecord]) -> dict[int, tuple[tuple[float, float], tuple[float, float]]]:
	segments: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
	for edge_id, edge in edges.items():
		source = nodes.get(edge.source)
		target = nodes.get(edge.target)
		if source is None or target is None:
			continue
		segments[edge_id] = ((source.x, source.y), (target.x, target.y))
	return segments


def _nearest_node(building: BuildingRecord, nodes: dict[int, NodeRecord]) -> int | None:
	if not nodes:
		return None
	point = (building.x, building.y)
	return min(nodes, key=lambda node_id: _euclidean(point, (nodes[node_id].x, nodes[node_id].y)))


def _compute_local_density(buildings: list[BuildingRecord], radius: float) -> dict[str, int]:
	densities = {building.building_id: 0 for building in buildings}
	for index, building in enumerate(buildings):
		point_a = (building.x, building.y)
		for other in buildings[index + 1 :]:
			if _euclidean(point_a, (other.x, other.y)) <= radius:
				densities[building.building_id] += 1
				densities[other.building_id] += 1
	return densities


def build_building_contexts(
	buildings: list[BuildingRecord],
	nodes: dict[int, NodeRecord],
	edges: dict[int, EdgeRecord],
	graph_metrics: GraphMetrics,
) -> dict[str, BuildingContext]:
	if not buildings:
		return {}

	segments = _edge_segments(edges, nodes)
	main_corridor_segments = [segments[edge_id] for edge_id in graph_metrics.major_edge_ids if edge_id in segments]
	local_densities = _compute_local_density(buildings, LOCAL_DENSITY_RADIUS)
	road_centrality_values = list(graph_metrics.normalized_edge_centrality.values()) or [0.0]
	road_centrality_median = _quantile(road_centrality_values, 0.5)

	min_x = min(building.x for building in buildings)
	max_x = max(building.x for building in buildings)
	min_y = min(building.y for building in buildings)
	max_y = max(building.y for building in buildings)

	contexts: dict[str, BuildingContext] = {}
	for building in buildings:
		point = (building.x, building.y)
		nearest_edge_id = building.entrance_edge_id if building.entrance_edge_id in edges else None

		if nearest_edge_id is None and segments:
			nearest_edge_id = min(segments, key=lambda edge_id: _point_segment_distance(point, *segments[edge_id]))

		forum_distance = _euclidean(point, graph_metrics.forum_center)
		if graph_metrics.forum_node_id is not None and nearest_edge_id is not None and nearest_edge_id in edges:
			edge = edges[nearest_edge_id]
			source = nodes.get(edge.source)
			target = nodes.get(edge.target)
			if source is not None and target is not None:
				source_distance = graph_metrics.forum_distances.get(edge.source, math.inf) + _euclidean(point, (source.x, source.y))
				target_distance = graph_metrics.forum_distances.get(edge.target, math.inf) + _euclidean(point, (target.x, target.y))
				forum_distance = min(forum_distance, source_distance, target_distance)
		elif graph_metrics.forum_node_id is not None:
			nearest_node_id = _nearest_node(building, nodes)
			if nearest_node_id is not None:
				nearest_node_record = nodes[nearest_node_id]
				forum_distance = min(
					forum_distance,
					graph_metrics.forum_distances.get(nearest_node_id, math.inf)
					+ _euclidean(point, (nearest_node_record.x, nearest_node_record.y)),
				)

		if building.on_main_road and nearest_edge_id in graph_metrics.major_edge_ids:
			distance_to_main_corridor = 0.0
		elif main_corridor_segments:
			distance_to_main_corridor = min(
				_point_segment_distance(point, start, end) for start, end in main_corridor_segments
			)
		else:
			distance_to_main_corridor = 0.0 if building.on_main_road else math.inf

		road_centrality = graph_metrics.normalized_edge_centrality.get(nearest_edge_id, 1.0 if building.on_main_road else 0.0)
		boundary_distance = min(building.x - min_x, max_x - building.x, building.y - min_y, max_y - building.y)

		if forum_distance < FORUM_DISTANCE_THRESHOLD:
			district = "FORUM"
		elif forum_distance < MARKET_DISTANCE_THRESHOLD and distance_to_main_corridor < MARKET_CORRIDOR_THRESHOLD:
			district = "MARKET"
		elif forum_distance < ELITE_DISTANCE_THRESHOLD and road_centrality < road_centrality_median:
			district = "ELITE"
		elif distance_to_main_corridor < COMMERCIAL_CORRIDOR_THRESHOLD:
			district = "COMMERCIAL"
		elif forum_distance < HOUSING_DISTANCE_THRESHOLD:
			district = "HOUSING"
		elif boundary_distance < 120.0 and distance_to_main_corridor < 80.0:
			district = "WAREHOUSE"
		else:
			district = "INDUSTRIAL"

		contexts[building.building_id] = BuildingContext(
			district=district,
			forum_distance=forum_distance,
			distance_to_main_corridor=distance_to_main_corridor,
			road_centrality=road_centrality,
			local_density=local_densities.get(building.building_id, 0),
			boundary_distance=boundary_distance,
			nearest_edge_id=nearest_edge_id,
		)

	return contexts


def _building_area_percentiles(buildings: list[BuildingRecord]) -> dict[str, float]:
	areas = {building.building_id: building.square for building in buildings}
	if not areas:
		return {}
	numeric_values = [float(value) for value in areas.values()]
	minimum = min(numeric_values)
	maximum = max(numeric_values)
	if math.isclose(minimum, maximum):
		return {key: 1.0 for key in areas}
	return {
		key: (float(value) - minimum) / (maximum - minimum)
		for key, value in areas.items()
	}


def _profession_totals(professions: dict[str, ProfessionTarget]) -> dict[str, int]:
	return {profession_id: target.count for profession_id, target in professions.items()}


def _allocate_workers_for_type(
	building_type: BuildingTypeDefinition,
	remaining: dict[str, int],
	*,
	allow_partial_minimums: bool,
) -> dict[str, int]:
	allocated: dict[str, int] = {}
	for role in building_type.roles:
		available = remaining.get(role.profession_id, 0)
		if available <= 0:
			if not allow_partial_minimums and role.min_people > 0:
				return {}
			continue
		if available < role.min_people:
			if not allow_partial_minimums:
				return {}
			allocated[role.profession_id] = available
		else:
			allocated[role.profession_id] = role.min_people

	if not allocated:
		return {}

	for role in sorted(
		building_type.roles,
		key=lambda candidate: (-remaining.get(candidate.profession_id, 0), candidate.profession_id),
	):
		current = allocated.get(role.profession_id, 0)
		available = remaining.get(role.profession_id, 0)
		extra_capacity = max(0, role.max_people - current)
		if extra_capacity <= 0 or available <= current:
			continue
		allocated[role.profession_id] = current + min(extra_capacity, available - current)

	return {profession_id: count for profession_id, count in allocated.items() if count > 0}


def _type_fit_score(
	building: BuildingRecord,
	context: BuildingContext,
	building_type: BuildingTypeDefinition,
	remaining: dict[str, int],
	area_percentile: float,
	target_totals: dict[str, int],
) -> float:
	capacity_coverage = 0.0
	min_fit_count = 0
	for role in building_type.roles:
		deficit = remaining.get(role.profession_id, 0)
		if deficit <= 0:
			continue
		capacity_coverage += min(deficit, role.max_people) / max(1, target_totals.get(role.profession_id, role.max_people))
		if deficit >= role.min_people:
			min_fit_count += 1

	if capacity_coverage <= 0:
		return -1.0

	category_weight = DISTRICT_CATEGORY_WEIGHTS.get(context.district, {}).get(building_type.category, 0.05)
	size_score = 1.0 - abs(area_percentile - building_type.capacity_percentile)
	location_bonus = 0.0

	if building_type.category in {"public", "service", "elite"}:
		location_bonus += max(0.0, 1.0 - (context.forum_distance / 600.0))
	if building_type.category in {"shop", "tavern", "service"}:
		location_bonus += max(0.0, 1.0 - (context.distance_to_main_corridor / 120.0))
	if building_type.category in {"warehouse", "industrial", "infrastructure"}:
		location_bonus += max(0.0, 1.0 - (context.boundary_distance / 200.0))
	if building_type.category == "elite":
		location_bonus += max(0.0, 0.75 - context.road_centrality)
	if building.on_main_road and building_type.category in {"shop", "tavern", "service", "public"}:
		location_bonus += 0.25

	return (3.5 * category_weight) + (4.0 * capacity_coverage) + (1.5 * size_score) + location_bonus + (0.35 * min_fit_count)


def _landmark_candidate_score(
	building: BuildingRecord,
	context: BuildingContext,
	area_percentile: float,
	landmark_name: str,
) -> float:
	target_distance = LANDMARK_DISTANCE_TARGETS[landmark_name]
	distance_score = 1.0 / (1.0 + abs(context.forum_distance - target_distance) / 150.0)
	road_bonus = 1.0 / (1.0 + context.distance_to_main_corridor / 75.0)
	forum_bonus = 1.0 / (1.0 + context.forum_distance / 250.0)
	quiet_bonus = 1.0 - min(1.0, context.road_centrality)

	if landmark_name == "FORUM":
		return 3.0 * forum_bonus + 2.0 * road_bonus + 2.0 * area_percentile
	if landmark_name == "MARKET":
		return 2.5 * road_bonus + 1.8 * distance_score + 1.3 * area_percentile
	if landmark_name == "TEMPLE":
		return 2.1 * distance_score + 1.5 * quiet_bonus + 1.4 * area_percentile
	return 1.8 * distance_score + 1.4 * road_bonus + 1.2 * area_percentile


def place_landmarks(
	buildings: list[BuildingRecord],
	contexts: dict[str, BuildingContext],
	building_types: dict[int, BuildingTypeDefinition],
	area_percentiles: dict[str, float],
) -> dict[str, tuple[str, int]]:
	assignments: dict[str, tuple[str, int]] = {}
	used_buildings: set[str] = set()

	for landmark_name, building_type_id in LANDMARK_TYPE_SEQUENCE:
		if building_type_id not in building_types:
			continue
		candidates = sorted(
			(building for building in buildings if building.building_id not in used_buildings),
			key=lambda building: (
				-_landmark_candidate_score(
					building,
					contexts[building.building_id],
					area_percentiles.get(building.building_id, 0.0),
					landmark_name,
				),
				building.building_id,
			),
		)
		if not candidates:
			continue
		chosen = candidates[0]
		assignments[chosen.building_id] = (landmark_name, building_type_id)
		used_buildings.add(chosen.building_id)

	return assignments


def _commit_workers(remaining: dict[str, int], workers: dict[str, int]) -> None:
	for profession_id, count in workers.items():
		remaining[profession_id] = max(0, remaining.get(profession_id, 0) - count)


def _trade_family(building_type_name: str) -> str:
	lowered = building_type_name.lower()
	if any(keyword in lowered for keyword in ("grain", "bakery", "fish", "butcher", "oil", "produce", "dairy", "tavern")):
		return "food_trade"
	if any(keyword in lowered for keyword in ("textile", "dye", "tailor", "tannery", "leather")):
		return "textiles_and_leather"
	if any(keyword in lowered for keyword in ("pottery", "glass", "brick", "stone", "quarry")):
		return "ceramics_and_stone"
	if any(keyword in lowered for keyword in ("metal", "forge", "smithy", "jewelry", "armory")):
		return "metalworking"
	if any(keyword in lowered for keyword in ("warehouse", "stable", "shipyard", "port")):
		return "logistics"
	return "general_trade"


def assign_economic_clusters(
	assignments: list[BuildingAssignment],
	*,
	seed: int,
) -> None:
	candidates = [
		assignment
		for assignment in assignments
		if assignment.building_type_id is not None
		and assignment.building_type_name
		and TYPE_CATEGORY_OVERRIDES.get(assignment.building_type_id, "") in {"shop", "workshop", "industrial", "warehouse"}
	]
	if len(candidates) < 3:
		return

	rng = random.Random(seed)
	cluster_count = max(3, min(8, len(candidates) // 12 or 3))
	seed_assignments = rng.sample(candidates, k=min(cluster_count, len(candidates)))

	for index, seed_assignment in enumerate(seed_assignments, start=1):
		radius = rng.uniform(120.0, 200.0)
		family = _trade_family(seed_assignment.building_type_name)
		label = f"{family}_{index}"
		seed_point = (seed_assignment.building.x, seed_assignment.building.y)
		for assignment in candidates:
			if assignment.economic_cluster:
				continue
			if _euclidean(seed_point, (assignment.building.x, assignment.building.y)) <= radius:
				assignment.economic_cluster = label


def assign_building_functions(
	buildings: list[BuildingRecord],
	building_types: dict[int, BuildingTypeDefinition],
	professions: dict[str, ProfessionTarget],
	contexts: dict[str, BuildingContext],
	*,
	seed: int,
) -> tuple[list[BuildingAssignment], dict[str, int]]:
	area_percentiles = _building_area_percentiles(buildings)
	landmark_assignments = place_landmarks(buildings, contexts, building_types, area_percentiles)
	remaining = _profession_totals(professions)
	target_totals = dict(remaining)

	assignments_by_building: dict[str, BuildingAssignment] = {}
	unassigned_buildings = {building.building_id for building in buildings}

	def _make_assignment(
		building: BuildingRecord,
		context: BuildingContext,
		assigned_function: str,
		*,
		building_type: BuildingTypeDefinition | None,
		landmark: str = "",
	) -> BuildingAssignment:
		workers: dict[str, int] = {}
		if building_type is not None:
			workers = _allocate_workers_for_type(
				building_type,
				remaining,
				allow_partial_minimums=True,
			)
			if workers:
				_commit_workers(remaining, workers)

		return BuildingAssignment(
			building=building,
			district=context.district,
			assigned_function=assigned_function,
			building_type_id=None if building_type is None else building_type.building_type_id,
			building_type_name="" if building_type is None else building_type.name,
			landmark=landmark,
			worker_capacity=0 if building_type is None else building_type.max_workers,
			workers=workers,
			forum_distance=context.forum_distance,
			distance_to_main_corridor=context.distance_to_main_corridor,
			road_centrality=context.road_centrality,
			local_density=context.local_density,
		)

	for building in buildings:
		if building.building_id not in landmark_assignments:
			continue
		landmark_name, building_type_id = landmark_assignments[building.building_id]
		context = contexts[building.building_id]
		building_type = building_types[building_type_id]
		assignment = _make_assignment(
			building,
			context,
			building_type.name.lower().replace(" and ", "_").replace(" ", "_"),
			building_type=building_type,
			landmark=landmark_name,
		)
		assignments_by_building[building.building_id] = assignment
		unassigned_buildings.discard(building.building_id)

	ordered_buildings = sorted(
		(building for building in buildings if building.building_id in unassigned_buildings),
		key=lambda building: (
			DISTRICT_PRIORITY[contexts[building.building_id].district],
			-area_percentiles.get(building.building_id, 0.0),
			building.building_id,
		),
	)

	for building in ordered_buildings:
		context = contexts[building.building_id]
		area_percentile = area_percentiles.get(building.building_id, 0.0)
		best_type: BuildingTypeDefinition | None = None
		best_score = -1.0

		for building_type in building_types.values():
			score = _type_fit_score(building, context, building_type, remaining, area_percentile, target_totals)
			if score > best_score:
				best_score = score
				best_type = building_type

		if best_type is not None and best_score > 0.9:
			candidate_workers = _allocate_workers_for_type(best_type, remaining, allow_partial_minimums=True)
			if candidate_workers:
				_commit_workers(remaining, candidate_workers)
				assignments_by_building[building.building_id] = BuildingAssignment(
					building=building,
					district=context.district,
					assigned_function=best_type.category,
					building_type_id=best_type.building_type_id,
					building_type_name=best_type.name,
					worker_capacity=best_type.max_workers,
					workers=candidate_workers,
					forum_distance=context.forum_distance,
					distance_to_main_corridor=context.distance_to_main_corridor,
					road_centrality=context.road_centrality,
					local_density=context.local_density,
				)
				continue

		assignments_by_building[building.building_id] = BuildingAssignment(
			building=building,
			district=context.district,
			assigned_function=PSEUDO_FUNCTIONS[context.district],
			forum_distance=context.forum_distance,
			distance_to_main_corridor=context.distance_to_main_corridor,
			road_centrality=context.road_centrality,
			local_density=context.local_density,
		)

	remaining_positive = {profession_id: count for profession_id, count in remaining.items() if count > 0}
	if remaining_positive:
		spare_buildings = sorted(
			[assignment for assignment in assignments_by_building.values() if assignment.building_type_id is None],
			key=lambda assignment: (-assignment.road_centrality, assignment.building.building_id),
		)
		for assignment in spare_buildings:
			if not any(count > 0 for count in remaining.values()):
				break
			building = assignment.building
			context = contexts[building.building_id]
			area_percentile = area_percentiles.get(building.building_id, 0.0)
			best_type = None
			best_score = -1.0
			for building_type in building_types.values():
				score = _type_fit_score(building, context, building_type, remaining, area_percentile, target_totals)
				if score > best_score:
					best_score = score
					best_type = building_type
			if best_type is None or best_score <= 0:
				continue
			workers = _allocate_workers_for_type(best_type, remaining, allow_partial_minimums=True)
			if not workers:
				continue
			_commit_workers(remaining, workers)
			assignment.assigned_function = best_type.category
			assignment.building_type_id = best_type.building_type_id
			assignment.building_type_name = best_type.name
			assignment.worker_capacity = best_type.max_workers
			assignment.workers = workers

	assignments = sorted(assignments_by_building.values(), key=lambda assignment: int(assignment.building.building_id))
	assign_economic_clusters(assignments, seed=seed)
	return assignments, remaining


def write_building_assignments_csv(assignments: list[BuildingAssignment], output_path: Path) -> Path:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(
			handle,
			fieldnames=[
				"ID",
				"entranceX",
				"entranceY",
				"entranceEdgeID",
				"square",
				"on_main_road",
				"district",
				"assigned_function",
				"building_type_id",
				"building_type_name",
				"landmark",
				"economic_cluster",
				"forum_distance",
				"distance_to_main_corridor",
				"road_centrality",
				"local_density",
				"worker_capacity",
				"assigned_workers",
			],
		)
		writer.writeheader()
		for assignment in assignments:
			building = assignment.building
			writer.writerow(
				{
					"ID": building.building_id,
					"entranceX": int(round(building.x)),
					"entranceY": int(round(building.y)),
					"entranceEdgeID": "" if building.entrance_edge_id is None else building.entrance_edge_id,
					"square": int(round(building.square)),
					"on_main_road": 1 if building.on_main_road else 0,
					"district": assignment.district,
					"assigned_function": assignment.assigned_function,
					"building_type_id": "" if assignment.building_type_id is None else assignment.building_type_id,
					"building_type_name": assignment.building_type_name,
					"landmark": assignment.landmark,
					"economic_cluster": assignment.economic_cluster,
					"forum_distance": f"{assignment.forum_distance:.2f}",
					"distance_to_main_corridor": (
						"inf" if math.isinf(assignment.distance_to_main_corridor) else f"{assignment.distance_to_main_corridor:.2f}"
					),
					"road_centrality": f"{assignment.road_centrality:.4f}",
					"local_density": assignment.local_density,
					"worker_capacity": assignment.worker_capacity,
					"assigned_workers": assignment.assigned_workers,
				}
			)
	return output_path


def write_worker_assignments_csv(
	assignments: list[BuildingAssignment],
	professions: dict[str, ProfessionTarget],
	output_path: Path,
) -> Path:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(
			handle,
			fieldnames=["buildingID", "buildingTypeID", "buildingTypeName", "professionID", "professionName", "numberOfPeople"],
		)
		writer.writeheader()
		for assignment in assignments:
			if not assignment.workers:
				continue
			for profession_id, count in sorted(assignment.workers.items()):
				profession = professions[profession_id]
				writer.writerow(
					{
						"buildingID": assignment.building.building_id,
						"buildingTypeID": assignment.building_type_id,
						"buildingTypeName": assignment.building_type_name,
						"professionID": profession_id,
						"professionName": profession.name,
						"numberOfPeople": count,
					}
				)
	return output_path


def generate_building_function_csv(
	*,
	buildings_path: Path = DEFAULT_BUILDINGS_PATH,
	professions_path: Path = DEFAULT_PROFESSIONS_PATH,
	mapping_path: Path = DEFAULT_MAPPING_PATH,
	nodes_path: Path | None = DEFAULT_NODES_PATH,
	edges_path: Path | None = DEFAULT_EDGES_PATH,
	roads_path: Path | None = DEFAULT_ROADS_PATH,
	assignments_output_path: Path = DEFAULT_ASSIGNMENTS_OUTPUT_PATH,
	workers_output_path: Path = DEFAULT_WORKERS_OUTPUT_PATH,
	seed: int = 42,
) -> dict[str, Path | dict[str, int]]:
	professions = load_profession_counts(professions_path)
	building_types = load_building_type_mappings(mapping_path, professions)
	buildings = load_buildings(buildings_path)
	nodes = load_nodes(nodes_path)
	edges = _augment_edges_with_road_ids(load_edges(edges_path), load_roads(roads_path))
	roads = load_roads(roads_path)
	graph_metrics = compute_graph_metrics(nodes, edges, roads)
	contexts = build_building_contexts(buildings, nodes, edges, graph_metrics)
	assignments, remaining = assign_building_functions(
		buildings,
		building_types,
		professions,
		contexts,
		seed=seed,
	)

	assignments_path = write_building_assignments_csv(assignments, assignments_output_path)
	workers_path = write_worker_assignments_csv(assignments, professions, workers_output_path)
	return {
		"assignments": assignments_path,
		"workers": workers_path,
		"remaining_professions": {profession_id: count for profession_id, count in remaining.items() if count > 0},
	}


def build_argument_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description=(
			"Assign landmark, district, and workplace functions to buildings from city export CSV files."
		)
	)
	parser.add_argument("--buildings", type=Path, default=DEFAULT_BUILDINGS_PATH, help=f"Path to buildings.csv. Defaults to {DEFAULT_BUILDINGS_PATH}.")
	parser.add_argument("--professions", type=Path, default=DEFAULT_PROFESSIONS_PATH, help=f"Path to professions_absolute_count.csv. Defaults to {DEFAULT_PROFESSIONS_PATH}.")
	parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH, help=f"Path to building_types_profession_mapping.csv. Defaults to {DEFAULT_MAPPING_PATH}.")
	parser.add_argument("--nodes", type=Path, default=DEFAULT_NODES_PATH, help=f"Path to nodes.csv. Defaults to {DEFAULT_NODES_PATH}.")
	parser.add_argument("--edges", type=Path, default=DEFAULT_EDGES_PATH, help=f"Path to edges.csv. Defaults to {DEFAULT_EDGES_PATH}.")
	parser.add_argument("--roads", type=Path, default=DEFAULT_ROADS_PATH, help=f"Path to roads.csv. Defaults to {DEFAULT_ROADS_PATH}.")
	parser.add_argument("--output", type=Path, default=DEFAULT_ASSIGNMENTS_OUTPUT_PATH, help=f"Path for the enriched building assignments CSV. Defaults to {DEFAULT_ASSIGNMENTS_OUTPUT_PATH}.")
	parser.add_argument("--workers-output", type=Path, default=DEFAULT_WORKERS_OUTPUT_PATH, help=f"Path for the per-building workforce CSV. Defaults to {DEFAULT_WORKERS_OUTPUT_PATH}.")
	parser.add_argument("--seed", type=int, default=42, help="Random seed used for deterministic economic clusters.")
	return parser


def main() -> int:
	parser = build_argument_parser()
	args = parser.parse_args()

	result = generate_building_function_csv(
		buildings_path=args.buildings,
		professions_path=args.professions,
		mapping_path=args.mapping,
		nodes_path=args.nodes,
		edges_path=args.edges,
		roads_path=args.roads,
		assignments_output_path=args.output,
		workers_output_path=args.workers_output,
		seed=args.seed,
	)
	remaining = result["remaining_professions"]
	print(f"Wrote building assignments CSV to {result['assignments']}")
	print(f"Wrote building worker CSV to {result['workers']}")
	if remaining:
		total_remaining = sum(remaining.values())
		print(f"Unassigned workers remaining: {total_remaining} across {len(remaining)} professions")
	else:
		print("Assigned all target professions to buildings")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())




