"""Assign residential buildings to social classes and generate agent-to-home mappings.

This script reads building function assignments, social class definitions, and 
residential building type mappings to assign residential functions to buildings
and create agent-to-home mappings based on historical Roman housing patterns.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BUILDING_ASSIGNMENTS = BASE_DIR / "output" / "building_function_assignments.csv"
DEFAULT_SOCIAL_CLASSES = BASE_DIR / "ext_data" / "roman_social_classes.csv"
DEFAULT_RESIDENTIAL_MAPPING = BASE_DIR / "ext_data" / "building_types_residential_mapping.csv"
DEFAULT_PROFESSIONS = BASE_DIR / "output" / "building_function_workers.csv"
DEFAULT_RESIDENTIAL_ASSIGNMENTS_OUTPUT = BASE_DIR / "output" / "residential_building_assignments.csv"
DEFAULT_AGENT_HOME_MAPPING_OUTPUT = BASE_DIR / "output" / "agent_home_assignments.csv"

# District affinity weights for residential types
DISTRICT_RESIDENTIAL_WEIGHTS = {
    "FORUM": {"RES-01": 0.05, "RES-02": 0.60, "RES-03": 0.20, "RES-04": 0.10, "RES-05": 0.02},
    "ELITE": {"RES-01": 0.10, "RES-02": 0.70, "RES-03": 0.15, "RES-04": 0.03, "RES-05": 0.01},
    "MARKET": {"RES-01": 0.50, "RES-02": 0.20, "RES-03": 0.02, "RES-04": 0.15, "RES-05": 0.05},
    "COMMERCIAL": {"RES-01": 0.45, "RES-02": 0.25, "RES-03": 0.02, "RES-04": 0.15, "RES-05": 0.05},
    "HOUSING": {"RES-01": 0.70, "RES-02": 0.05, "RES-03": 0.01, "RES-04": 0.10, "RES-05": 0.08},
    "WAREHOUSE": {"RES-01": 0.30, "RES-02": 0.02, "RES-03": 0.01, "RES-04": 0.25, "RES-05": 0.20},
    "INDUSTRIAL": {"RES-01": 0.25, "RES-02": 0.01, "RES-03": 0.01, "RES-04": 0.30, "RES-05": 0.25},
}

# Social class to residential type preferences (weights)
CLASS_RESIDENTIAL_PREFERENCE = {
    1: {"RES-02": 0.60, "RES-03": 0.35, "RES-01": 0.03, "RES-04": 0.02},  # Imperial
    2: {"RES-02": 0.55, "RES-03": 0.30, "RES-01": 0.10, "RES-04": 0.05},  # Senatorial
    3: {"RES-02": 0.50, "RES-03": 0.25, "RES-01": 0.15, "RES-04": 0.10},  # Equestrian
    4: {"RES-02": 0.60, "RES-01": 0.25, "RES-03": 0.10, "RES-04": 0.05},  # Decurial
    5: {"RES-01": 0.55, "RES-02": 0.25, "RES-04": 0.10, "RES-05": 0.05, "RES-03": 0.05},  # Citizens optimo iure
    6: {"RES-01": 0.60, "RES-02": 0.15, "RES-04": 0.10, "RES-05": 0.10, "RES-03": 0.05},  # Citizens sine suffragio
    7: {"RES-01": 0.65, "RES-02": 0.15, "RES-04": 0.10, "RES-05": 0.10},  # Latini
    8: {"RES-01": 0.70, "RES-04": 0.15, "RES-05": 0.10, "RES-02": 0.05},  # Freedmen
    9: {"RES-01": 0.75, "RES-04": 0.10, "RES-05": 0.15},  # Junian Latins
    10: {"RES-01": 0.40, "RES-05": 0.40, "RES-04": 0.20},  # Peregrini dediticii
    11: {"RES-01": 0.65, "RES-05": 0.25, "RES-04": 0.10},  # Peregrini liberi
    12: {"RES-04": 0.70, "RES-01": 0.30},  # Urban slaves
    13: {"RES-04": 0.85, "RES-05": 0.15},  # Industrial slaves
    14: {"RES-04": 0.60, "RES-05": 0.40},  # Rural slaves
}


@dataclass(frozen=True)
class SocialClass:
    class_id: int
    name: str
    description: str
    legal_status: str
    wealth_threshold: int
    typical_residence: str
    population_percent: float


@dataclass(frozen=True)
class ResidentialMapping:
    building_type_id: str
    building_type_name: str
    social_class_id: int
    min_occupants: int
    max_occupants: int
    building_area_sqm: int
    district_affinity: str
    description: str


@dataclass(frozen=True)
class BuildingRecord:
    building_id: int
    entrance_x: float
    entrance_y: float
    entrance_edge_id: int | None
    square: float
    on_main_road: bool
    district: str
    assigned_function: str
    building_type_id: int | None
    building_type_name: str
    landmark: str
    economic_cluster: str
    forum_distance: float
    distance_to_main_corridor: float
    road_centrality: float
    local_density: int
    worker_capacity: int
    assigned_workers: int


@dataclass
class ResidentialAssignment:
    building: BuildingRecord
    residential_type_id: str
    residential_type_name: str
    social_class_id: int
    social_class_name: str
    capacity: int
    current_occupants: int = 0


@dataclass
class AgentHomeAssignment:
    agent_id: str
    profession_id: str
    workplace_building_id: int
    home_building_id: int
    social_class_id: int
    social_class_name: str


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


def load_social_classes(input_path: Path) -> dict[int, SocialClass]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, {"ClassID", "ClassName", "PopulationPercent"}, input_path)

        classes: dict[int, SocialClass] = {}
        for row in reader:
            class_id_text = (row.get("ClassID") or "").strip()
            if not class_id_text:
                continue
            class_id = _parse_int(class_id_text, column="ClassID", path=input_path)

            name = (row.get("ClassName") or "").strip()
            description = (row.get("Description") or "").strip()
            legal_status = (row.get("LegalStatus") or "").strip()
            wealth_text = (row.get("WealthThresholdHS") or "0").strip()
            typical_residence = (row.get("TypicalResidence") or "").strip()
            pop_text = (row.get("PopulationPercent") or "0").strip()

            classes[class_id] = SocialClass(
                class_id=class_id,
                name=name,
                description=description,
                legal_status=legal_status,
                wealth_threshold=_parse_int(wealth_text, column="WealthThresholdHS", path=input_path),
                typical_residence=typical_residence,
                population_percent=float(pop_text),
            )

    if not classes:
        raise ValueError(f"No social class rows found in {input_path}")
    return classes


def load_residential_mappings(input_path: Path) -> list[ResidentialMapping]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(
            reader.fieldnames,
            {"BuildingTypeID", "BuildingTypeName", "SocialClassID", "MinOccupants", "MaxOccupants",
             "BuildingAreaSqM", "DistrictAffinity", "Description"},
            input_path,
        )

        mappings: list[ResidentialMapping] = []
        for row in reader:
            type_id = (row.get("BuildingTypeID") or "").strip()
            if not type_id:
                continue
            social_class_text = (row.get("SocialClassID") or "").strip()
            if not social_class_text:
                continue

            mappings.append(ResidentialMapping(
                building_type_id=type_id,
                building_type_name=(row.get("BuildingTypeName") or "").strip(),
                social_class_id=_parse_int(social_class_text, column="SocialClassID", path=input_path),
                min_occupants=_parse_int((row.get("MinOccupants") or "0").strip(), column="MinOccupants", path=input_path),
                max_occupants=_parse_int((row.get("MaxOccupants") or "0").strip(), column="MaxOccupants", path=input_path),
                building_area_sqm=_parse_int((row.get("BuildingAreaSqM") or "0").strip(), column="BuildingAreaSqM", path=input_path),
                district_affinity=(row.get("DistrictAffinity") or "").strip(),
                description=(row.get("Description") or "").strip(),
            ))

    if not mappings:
        raise ValueError(f"No residential mapping rows found in {input_path}")
    return mappings


def load_building_assignments(input_path: Path) -> list[BuildingRecord]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(
            reader.fieldnames,
            {"ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road",
             "district", "assigned_function", "building_type_id", "building_type_name",
             "landmark", "economic_cluster", "forum_distance", "distance_to_main_corridor",
             "road_centrality", "local_density", "worker_capacity", "assigned_workers"},
            input_path,
        )

        buildings: list[BuildingRecord] = []
        for row in reader:
            bid_text = (row.get("ID") or "").strip()
            if not bid_text:
                continue

            edge_text = (row.get("entranceEdgeID") or "").strip()
            btype_text = (row.get("building_type_id") or "").strip()

            buildings.append(BuildingRecord(
                building_id=_parse_int(bid_text, column="ID", path=input_path),
                entrance_x=_parse_float((row.get("entranceX") or "0").strip(), column="entranceX", path=input_path),
                entrance_y=_parse_float((row.get("entranceY") or "0").strip(), column="entranceY", path=input_path),
                entrance_edge_id=int(edge_text) if edge_text else None,
                square=_parse_float((row.get("square") or "0").strip(), column="square", path=input_path),
                on_main_road=((row.get("on_main_road") or "0").strip() == "1"),
                district=(row.get("district") or "").strip(),
                assigned_function=(row.get("assigned_function") or "").strip(),
                building_type_id=int(btype_text) if btype_text else None,
                building_type_name=(row.get("building_type_name") or "").strip(),
                landmark=(row.get("landmark") or "").strip(),
                economic_cluster=(row.get("economic_cluster") or "").strip(),
                forum_distance=_parse_float((row.get("forum_distance") or "0").strip(), column="forum_distance", path=input_path),
                distance_to_main_corridor=(
                    math.inf if (row.get("distance_to_main_corridor") or "").strip().lower() == "inf"
                    else _parse_float((row.get("distance_to_main_corridor") or "0").strip(), column="distance_to_main_corridor", path=input_path)
                ),
                road_centrality=_parse_float((row.get("road_centrality") or "0").strip(), column="road_centrality", path=input_path),
                local_density=_parse_int((row.get("local_density") or "0").strip(), column="local_density", path=input_path),
                worker_capacity=_parse_int((row.get("worker_capacity") or "0").strip(), column="worker_capacity", path=input_path),
                assigned_workers=_parse_int((row.get("assigned_workers") or "0").strip(), column="assigned_workers", path=input_path),
            ))

    if not buildings:
        raise ValueError(f"No building rows found in {input_path}")
    return buildings


def load_workplace_assignments(input_path: Path) -> dict[int, list[tuple[str, int]]]:
    """Load profession assignments per building from building_function_workers.csv.
    Returns mapping: building_id -> list of (profession_id, count)"""
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, {"buildingID", "professionID", "numberOfPeople"}, input_path)

        workplace: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for row in reader:
            bid_text = (row.get("buildingID") or "").strip()
            if not bid_text:
                continue
            building_id = _parse_int(bid_text, column="buildingID", path=input_path)
            profession_id = (row.get("professionID") or "").strip()
            count_text = (row.get("numberOfPeople") or "0").strip()
            count = _parse_int(count_text, column="numberOfPeople", path=input_path)
            if count > 0:
                workplace[building_id].append((profession_id, count))

    return workplace


def _calculate_residential_score(
    building: BuildingRecord,
    residential_type: ResidentialMapping,
    social_class: SocialClass,
) -> float:
    """Calculate how well a residential type fits a building for a given social class."""
    # Base score from district affinity weights
    district_weights = DISTRICT_RESIDENTIAL_WEIGHTS.get(building.district, {})
    district_score = district_weights.get(residential_type.building_type_id, 0.01)

    # Class preference score
    class_prefs = CLASS_RESIDENTIAL_PREFERENCE.get(social_class.class_id, {})
    class_score = class_prefs.get(residential_type.building_type_id, 0.01)

    # Size compatibility (building area vs residential type typical area)
    building_area = building.square
    type_area = residential_type.building_area_sqm
    if building_area > 0 and type_area > 0:
        size_ratio = min(building_area, type_area) / max(building_area, type_area)
        size_score = size_ratio
    else:
        size_score = 0.5

    # Forum distance preference
    # Elite classes prefer closer to forum (lower distance)
    # Lower classes prefer further from forum
    forum_pref = 0.5
    if social_class.class_id <= 4:  # Elite classes
        forum_pref = max(0.0, 1.0 - (building.forum_distance / 1000.0))
    elif social_class.class_id >= 10:  # Lowest classes
        forum_pref = min(1.0, building.forum_distance / 1000.0)
    else:
        forum_pref = 0.5

    # Main road access - commercial/shop classes prefer main road
    road_score = 1.0 if building.on_main_road else 0.5
    if social_class.class_id in {5, 6, 7, 8, 9, 11}:  # Merchant/citizen classes
        road_score = 1.0 if building.on_main_road else 0.7

    # Combine scores with weights
    total_score = (
        0.35 * district_score +
        0.30 * class_score +
        0.15 * size_score +
        0.10 * forum_pref +
        0.10 * road_score
    )

    return total_score


def assign_residential_buildings(
    buildings: list[BuildingRecord],
    social_classes: dict[int, SocialClass],
    residential_mappings: list[ResidentialMapping],
    *,
    seed: int = 42,
) -> list[ResidentialAssignment]:
    """Assign residential functions to buildings based on district and social class needs."""
    rng = random.Random(seed)

    # Filter buildings that can be residential (not already assigned as workplace landmarks, etc.)
    # We'll use buildings with assigned_workers == 0 or assigned_function in residential categories
    candidate_buildings = [
        b for b in buildings
        if b.assigned_workers == 0
        or b.assigned_function in {"dense_housing", "elite_residence", "street_front_residence", "peripheral_housing_or_yard", "storage_courtyard"}
    ]

    # Group residential mappings by social class
    mappings_by_class: dict[int, list[ResidentialMapping]] = defaultdict(list)
    for mapping in residential_mappings:
        mappings_by_class[mapping.social_class_id].append(mapping)

    # Calculate target population per social class (based on total building capacity)
    total_building_area = sum(b.square for b in candidate_buildings)
    avg_area_per_person = 25.0  # rough estimate sqm per person
    estimated_total_population = int(total_building_area / avg_area_per_person)

    # Target population per class
    total_percent = sum(c.population_percent for c in social_classes.values())
    target_population = {
        class_id: int(estimated_total_population * c.population_percent / total_percent)
        for class_id, c in social_classes.items()
    }

    # Sort buildings by district priority and size
    district_priority = {"FORUM": 0, "ELITE": 1, "MARKET": 2, "COMMERCIAL": 3, "HOUSING": 4, "WAREHOUSE": 5, "INDUSTRIAL": 6}
    candidate_buildings.sort(key=lambda b: (district_priority.get(b.district, 99), -b.square, b.building_id))

    assignments: list[ResidentialAssignment] = []
    remaining_population = dict(target_population)

    for building in candidate_buildings:
        # Find best residential type for this building
        best_mapping = None
        best_score = -1.0
        best_class_id = None

        # Consider all social classes that still need population
        active_classes = [cid for cid, pop in remaining_population.items() if pop > 0]
        if not active_classes:
            # All population placed, assign remaining to lowest class
            active_classes = [max(social_classes.keys())]

        for class_id in active_classes:
            social_class = social_classes[class_id]
            for mapping in mappings_by_class.get(class_id, []):
                # Check district affinity
                affinity_districts = [d.strip() for d in mapping.district_affinity.split(",")]
                if building.district not in affinity_districts:
                    continue

                # Check size compatibility - building should be reasonably sized for this type
                if building.square < mapping.building_area_sqm * 0.3:
                    continue

                score = _calculate_residential_score(building, mapping, social_class)
                if score > best_score:
                    best_score = score
                    best_mapping = mapping
                    best_class_id = class_id

        if best_mapping and best_class_id:
            # Calculate capacity based on building size and mapping
            capacity = int(building.square / max(1, best_mapping.building_area_sqm / best_mapping.max_occupants))
            capacity = max(best_mapping.min_occupants, min(capacity, best_mapping.max_occupants))

            # Limit by remaining population
            capacity = min(capacity, remaining_population.get(best_class_id, capacity))
            if capacity <= 0:
                capacity = best_mapping.min_occupants

            remaining_population[best_class_id] = max(0, remaining_population.get(best_class_id, 0) - capacity)

            assignments.append(ResidentialAssignment(
                building=building,
                residential_type_id=best_mapping.building_type_id,
                residential_type_name=best_mapping.building_type_name,
                social_class_id=best_class_id,
                social_class_name=social_classes[best_class_id].name,
                capacity=capacity,
            ))
        else:
            # Fallback: assign basic insula
            fallback_mapping = next((m for m in residential_mappings if m.building_type_id == "RES-01"), None)
            if fallback_mapping:
                capacity = max(fallback_mapping.min_occupants, int(building.square / 50))
                assignments.append(ResidentialAssignment(
                    building=building,
                    residential_type_id=fallback_mapping.building_type_id,
                    residential_type_name=fallback_mapping.building_type_name,
                    social_class_id=10,
                    social_class_name=social_classes[10].name,
                    capacity=capacity,
                ))

    return assignments


def generate_agent_home_assignments(
    residential_assignments: list[ResidentialAssignment],
    workplace_assignments: dict[int, list[tuple[str, int]]],
    social_classes: dict[int, SocialClass],
    *,
    seed: int = 42,
) -> list[AgentHomeAssignment]:
    """Generate agent-to-home mappings based on workplace and social class."""
    rng = random.Random(seed)

    # Build list of all workers with their profession and workplace
    workers: list[tuple[str, int, int]] = []  # (profession_id, workplace_building_id, social_class_id)
    for workplace_bid, professions in workplace_assignments.items():
        for profession_id, count in professions:
            # Map profession to social class (simplified mapping)
            group_id = int(profession_id.split("-")[0]) if "-" in profession_id else 0
            social_class_id = _profession_group_to_social_class(group_id)
            for _ in range(count):
                workers.append((profession_id, workplace_bid, social_class_id))

    # Group residential assignments by social class
    homes_by_class: dict[int, list[ResidentialAssignment]] = defaultdict(list)
    for assignment in residential_assignments:
        homes_by_class[assignment.social_class_id].append(assignment)

    # For each class, create a list of available home slots
    home_slots_by_class: dict[int, list[tuple[int, int]]] = {}  # class_id -> list of (home_building_id, slot_index)
    for class_id, homes in homes_by_class.items():
        slots = []
        for home in homes:
            for slot in range(home.capacity):
                slots.append((home.building.building_id, slot))
        rng.shuffle(slots)
        home_slots_by_class[class_id] = slots

    # Assign each worker to a home
    agent_assignments: list[AgentHomeAssignment] = []
    for idx, (profession_id, workplace_bid, social_class_id) in enumerate(workers):
        # Try to find home in same social class
        slots = home_slots_by_class.get(social_class_id, [])
        home_bid = None
        if slots:
            home_bid, _ = slots.pop()
        else:
            # Fallback: find any available slot
            for cid in sorted(home_slots_by_class.keys(), key=lambda c: abs(c - social_class_id)):
                if home_slots_by_class[cid]:
                    home_bid, _ = home_slots_by_class[cid].pop()
                    social_class_id = cid  # Reassign to this class
                    break

        if home_bid is None:
            # Last resort: pick any residential building
            all_slots = []
            for cid, slots_list in home_slots_by_class.items():
                all_slots.extend([(cid, bid, slot) for bid, slot in slots_list])
            if all_slots:
                cid, home_bid, _ = rng.choice(all_slots)
                social_class_id = cid

        if home_bid is not None:
            agent_assignments.append(AgentHomeAssignment(
                agent_id=f"citizen-{idx}",
                profession_id=profession_id,
                workplace_building_id=workplace_bid,
                home_building_id=home_bid,
                social_class_id=social_class_id,
                social_class_name=social_classes[social_class_id].name,
            ))

    return agent_assignments


def _profession_group_to_social_class(group_id: int) -> int:
    """Map profession group to social class based on historical status."""
    mapping = {
        0: 8,   # Agriculture & Food -> Freedmen/Citizens
        1: 8,   # Textile -> Freedmen/Citizens
        2: 8,   # Leather -> Freedmen/Citizens
        3: 8,   # Pottery -> Freedmen/Citizens
        4: 8,   # Glass -> Freedmen/Citizens
        5: 5,   # Metal -> Citizens (skilled)
        6: 5,   # Construction -> Citizens
        7: 8,   # Woodworking -> Freedmen/Citizens
        8: 8,   # Household goods -> Freedmen/Citizens
        9: 5,   # Trade -> Citizens
        10: 3,  # Finance -> Equestrian
        11: 8,  # Transport -> Freedmen/Citizens
        12: 8,  # Hospitality -> Freedmen/Citizens
        13: 8,  # Personal services -> Freedmen/Citizens
        14: 4,  # Education -> Decurial/Equestrian
        15: 4,  # Medicine -> Decurial/Equestrian
        16: 4,  # Religion -> Decurial
        17: 2,  # Government -> Senatorial/Equestrian
        18: 5,  # Military -> Citizens
        19: 8,  # Entertainment -> Freedmen/Citizens
        20: 12, # Domestic servants -> Urban slaves
        21: 8,  # Informal economy -> Freedmen/Citizens
        22: 8,  # Vice economy -> Freedmen/Citizens
        23: 10, # Criminal -> Peregrini/Low
        24: 10, # Organized crime -> Peregrini/Low
        25: 10, # Marginal -> Peregrini
        26: 13, # Mining -> Industrial slaves
        27: 5,  # Water management -> Citizens
        28: 13, # Sanitation -> Industrial slaves
        29: 5,  # Urban maintenance -> Citizens
        30: 4,  # Law -> Decurial
        31: 12, # Slave trade -> Urban slaves (managers)
    }
    return mapping.get(group_id, 8)


def write_residential_assignments_csv(
    assignments: list[ResidentialAssignment],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road",
                "district", "original_function", "residential_type_id", "residential_type_name",
                "social_class_id", "social_class_name", "capacity", "current_occupants",
                "forum_distance", "distance_to_main_corridor", "road_centrality", "local_density",
            ],
        )
        writer.writeheader()
        for assignment in assignments:
            b = assignment.building
            writer.writerow({
                "ID": b.building_id,
                "entranceX": int(round(b.entrance_x)),
                "entranceY": int(round(b.entrance_y)),
                "entranceEdgeID": "" if b.entrance_edge_id is None else b.entrance_edge_id,
                "square": int(round(b.square)),
                "on_main_road": 1 if b.on_main_road else 0,
                "district": b.district,
                "original_function": b.assigned_function,
                "residential_type_id": assignment.residential_type_id,
                "residential_type_name": assignment.residential_type_name,
                "social_class_id": assignment.social_class_id,
                "social_class_name": assignment.social_class_name,
                "capacity": assignment.capacity,
                "current_occupants": assignment.current_occupants,
                "forum_distance": f"{b.forum_distance:.2f}",
                "distance_to_main_corridor": (
                    "inf" if math.isinf(b.distance_to_main_corridor)
                    else f"{b.distance_to_main_corridor:.2f}"
                ),
                "road_centrality": f"{b.road_centrality:.4f}",
                "local_density": b.local_density,
            })
    return output_path


def write_agent_home_assignments_csv(
    assignments: list[AgentHomeAssignment],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "agent_id", "profession_id", "workplace_building_id",
                "home_building_id", "social_class_id", "social_class_name",
            ],
        )
        writer.writeheader()
        for assignment in assignments:
            writer.writerow({
                "agent_id": assignment.agent_id,
                "profession_id": assignment.profession_id,
                "workplace_building_id": assignment.workplace_building_id,
                "home_building_id": assignment.home_building_id,
                "social_class_id": assignment.social_class_id,
                "social_class_name": assignment.social_class_name,
            })
    return output_path


def generate_residential_assignments(
    *,
    building_assignments_path: Path = DEFAULT_BUILDING_ASSIGNMENTS,
    social_classes_path: Path = DEFAULT_SOCIAL_CLASSES,
    residential_mapping_path: Path = DEFAULT_RESIDENTIAL_MAPPING,
    workplace_assignments_path: Path = DEFAULT_PROFESSIONS,
    residential_output_path: Path = DEFAULT_RESIDENTIAL_ASSIGNMENTS_OUTPUT,
    agent_home_output_path: Path = DEFAULT_AGENT_HOME_MAPPING_OUTPUT,
    seed: int = 42,
) -> dict[str, Path]:
    social_classes = load_social_classes(social_classes_path)
    residential_mappings = load_residential_mappings(residential_mapping_path)
    buildings = load_building_assignments(building_assignments_path)
    workplace_assignments = load_workplace_assignments(workplace_assignments_path)

    residential_assignments = assign_residential_buildings(
        buildings, social_classes, residential_mappings, seed=seed
    )

    agent_home_assignments = generate_agent_home_assignments(
        residential_assignments, workplace_assignments, social_classes, seed=seed
    )

    residential_path = write_residential_assignments_csv(residential_assignments, residential_output_path)
    agent_home_path = write_agent_home_assignments_csv(agent_home_assignments, agent_home_output_path)

    print(f"Assigned {len(residential_assignments)} residential buildings")
    print(f"Created {len(agent_home_assignments)} agent-home mappings")
    print(f"Wrote residential assignments to {residential_path}")
    print(f"Wrote agent-home mappings to {agent_home_path}")

    return {
        "residential_assignments": residential_path,
        "agent_home_assignments": agent_home_path,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assign residential buildings to social classes and generate agent-to-home mappings."
        )
    )
    parser.add_argument("--buildings", type=Path, default=DEFAULT_BUILDING_ASSIGNMENTS,
                        help=f"Path to building_function_assignments.csv. Defaults to {DEFAULT_BUILDING_ASSIGNMENTS}.")
    parser.add_argument("--social-classes", type=Path, default=DEFAULT_SOCIAL_CLASSES,
                        help=f"Path to roman_social_classes.csv. Defaults to {DEFAULT_SOCIAL_CLASSES}.")
    parser.add_argument("--residential-mapping", type=Path, default=DEFAULT_RESIDENTIAL_MAPPING,
                        help=f"Path to building_types_residential_mapping.csv. Defaults to {DEFAULT_RESIDENTIAL_MAPPING}.")
    parser.add_argument("--workplace", type=Path, default=DEFAULT_PROFESSIONS,
                        help=f"Path to building_function_workers.csv. Defaults to {DEFAULT_PROFESSIONS}.")
    parser.add_argument("--residential-output", type=Path, default=DEFAULT_RESIDENTIAL_ASSIGNMENTS_OUTPUT,
                        help=f"Path for residential building assignments CSV. Defaults to {DEFAULT_RESIDENTIAL_ASSIGNMENTS_OUTPUT}.")
    parser.add_argument("--agent-home-output", type=Path, default=DEFAULT_AGENT_HOME_MAPPING_OUTPUT,
                        help=f"Path for agent-home assignments CSV. Defaults to {DEFAULT_AGENT_HOME_MAPPING_OUTPUT}.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic assignment.")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    generate_residential_assignments(
        building_assignments_path=args.buildings,
        social_classes_path=args.social_classes,
        residential_mapping_path=args.residential_mapping,
        workplace_assignments_path=args.workplace,
        residential_output_path=args.residential_output,
        agent_home_output_path=args.agent_home_output,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
