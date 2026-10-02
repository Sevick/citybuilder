# Procedural City Generation

This is fork from [Procedural City Generation](https://github.com/josauder/procedural_city_generation). All credits go to by [josauder](https://github.com/josauder). Documentation can be found [here](http://josauder.github.io/procedural_city_generation)

#### Kindly open issues if you encounter bugs / need fixes.

---

## Dependencies

- pyqt5
- numpy
- matplotlib
- json
- pickle
- PIL
- scipy
- importlib
- pkgutil


## Running the program

> `python3 GUI.py`

## Post-processing utilities

The `post_processing/` directory contains two Python scripts that enrich the generated city with demographic and economic data for simulation.

---

### 1. `population_professions.py` — Generate profession headcounts

**Purpose:** Converts a percentage-based profession distribution into absolute headcounts for a target population size.

**Algorithm:**
- Reads `professions_distribution.csv` containing columns `Synthetic ID` and `Population %`
- Uses the **largest remainder method** (Hamilton method) to allocate integer counts deterministically
- Guarantees the sum of allocated people exactly equals the target population
- Uses `Decimal` arithmetic for precision

**Input (`post_processing/input/professions_distribution.csv`):**
```
GroupID,Synthetic ID,Name,Population %
0,0-0,grain_merchant,1.09
0,0-1,grain_measurer,0.73
...
```

**Output (`post_processing/output/population_professions.csv`):**
```
ProfessionID,NumberOfPeople
0-0,109
0-1,73
...
```

**Usage:**
```bash
python post_processing/population_professions.py 10000
```

**Optional arguments:**
| Argument | Description |
|----------|-------------|
| `total_population` | Target city population (default: 10000) |
| `--input` | Path to profession distribution CSV |
| `--output` | Path for generated profession population CSV |

---

### 2. `buildings_assign_function.py` — Assign functions, landmarks, and workforce to buildings

**Purpose:** Takes exported city geometry (buildings, road network) and profession targets, then assigns each building a district, function, landmark status, and specific workforce composition.

#### Core functionality

**A. Graph analysis & district classification**
- Computes **betweenness centrality**, **closeness centrality**, and **degree** for all road nodes (Brandes algorithm)
- Calculates a composite **forum score** = 0.5×betweenness + 0.3×closeness + 0.2×degree
- Identifies the **forum center** (highest-scoring node cluster, up to 3 nodes within 150m)
- Detects **major corridors** (top 15% edges by normalized betweenness)
- Classifies each building into a **district** using spatial rules:
  - `FORUM` — within 200m of forum center
  - `MARKET` — within 400m of forum AND within 50m of major corridor
  - `ELITE` — within 500m of forum AND below median road centrality
  - `COMMERCIAL` — within 40m of major corridor
  - `HOUSING` — within 900m of forum
  - `WAREHOUSE` — near boundary (<120m) AND near corridor (<80m)
  - `INDUSTRIAL` — everything else (peripheral)

**B. Landmark placement**
- Places 5 landmark types in sequence at optimal locations:
  - `FORUM` (type 34) — target 80m from forum center
  - `TEMPLE` (type 33) — target 140m
  - `MARKET` (type 25) — target 220m
  - `COURTHOUSE` (type 45) — target 180m
  - `BATHHOUSE` (type 30) — target 260m
- Scoring combines distance-to-target, road access, forum proximity, and building size

**C. Building function assignment**
- Loads `building_types_profession_mapping.csv` defining 46 building types, each with:
  - `BuildingTypeID`, `BuildingTypeName`
  - Multiple `ProfessionID` roles with `MinNumberOfPeople` / `MaxNumberOfPeople`
- Infers **category** for each type (public, shop, workshop, industrial, warehouse, elite, housing, tavern, service, entertainment, infrastructure, shady)
- For each non-landmark building (processed by district priority, then size):
  1. Scores all building types using weighted formula:
     - 3.5×district-category weight
     - 4.0×capacity coverage (how well it fills remaining profession deficits)
     - 1.5×size fit (building area vs type capacity percentile)
     - Location bonuses (forum proximity, corridor access, boundary distance, road centrality)
     - 0.35×minimum-fit count
  2. If best score > 0.9 and workers available → assign that type, allocate workers
  3. Otherwise → assign **pseudo-function** based on district (e.g., `dense_housing`, `street_front_residence`, `storage_courtyard`)

**D. Worker allocation**
- For assigned building types, allocates workers per profession role:
  - First satisfies `MinNumberOfPeople` per role (if available)
  - Then distributes remaining capacity up to `MaxNumberOfPeople` prioritizing professions with largest remaining deficits
- Tracks remaining profession counts; re-passes unassigned buildings if deficits remain

**E. Economic clusters**
- Seeds 3–8 trade clusters (food, textiles, ceramics, metalworking, logistics, general)
- Assigns nearby compatible buildings (shops/workshops/industrial/warehouse) within 120–200m radius

#### Input files (all in `post_processing/input/`)

| File | Required columns | Description |
|------|------------------|-------------|
| `buildings.csv` | `ID,entranceX,entranceY,entranceEdgeID,square,on_main_road` | Exported building geometry |
| `nodes.csv` | `ID,positionX,positionY` | Road network nodes (MASON format) |
| `edges.csv` | `ID,source,target,length,type` | Road network edges (MASON format) |
| `roads.csv` | `ID,type,edges` | Road segments (semicolon-separated edge IDs) |
| `professions_absolute_count.csv` | `Synthetic ID,Count,Name` | Output from `population_professions.py` |
| `building_types_profession_mapping.csv` | `BuildingTypeID,BuildingTypeName,ProfessionID,MinNumberOfPeople,MaxNumberOfPeople` | Building type ↔ profession roles |

#### Output files (written to `post_processing/output/`)

**`building_function_assignments.csv`** — One row per building:
```
ID,entranceX,entranceY,entranceEdgeID,square,on_main_road,
district,assigned_function,building_type_id,building_type_name,landmark,
economic_cluster,forum_distance,distance_to_main_corridor,
road_centrality,local_density,worker_capacity,assigned_workers
```

**`building_function_workers.csv`** — One row per building-profession assignment:
```
buildingID,buildingTypeID,buildingTypeName,professionID,professionName,numberOfPeople
```

#### Usage
```bash
python post_processing/buildings_assign_function.py
```

**Optional arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `--buildings` | `input/buildings.csv` | Building geometry CSV |
| `--nodes` | `input/nodes.csv` | Road nodes CSV |
| `--edges` | `input/edges.csv` | Road edges CSV |
| `--roads` | `input/roads.csv` | Road segments CSV |
| `--professions` | `input/professions_absolute_count.csv` | Profession headcounts CSV |
| `--mapping` | `input/building_types_profession_mapping.csv` | Building type ↔ profession mapping |
| `--output` | `output/building_function_assignments.csv` | Enriched building assignments |
| `--workers-output` | `output/building_function_workers.csv` | Per-building workforce detail |
| `--seed` | `42` | Random seed for deterministic economic clusters |

---

## Typical workflow

```bash
# 1. Generate city in GUI or via API, export CSVs to post_processing/input/
# 2. Generate profession headcounts for 10,000 population
python post_processing/population_professions.py 10000

# 3. Assign functions and workers to buildings
python post_processing/buildings_assign_function.py

# 4. Outputs in post_processing/output/ ready for sim module consumption
```