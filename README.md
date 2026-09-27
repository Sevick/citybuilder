# Procedural City Generation

This is fork from [Procedural City Generation](https://github.com/josauder/procedural_city_generation). All credits go to by [josauder](https://github.com/josauder). Documentation can be found [here](http://josauder.github.io/procedural_city_generation).
Documentation can be found [here](http://josauder.github.io/procedural_city_generation)

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

Generate profession headcounts from `post_processing/input/professions_distribution.csv`:

> `python post_processing/population_professions.py 10000`

Optional arguments:

- `--input` to use a different profession distribution CSV
- `--output` to choose the generated `ProfessionID,NumberOfPeople` CSV path

Assign functions, landmarks, and workforce to exported buildings using
`buildings.csv`, `nodes.csv`, `edges.csv`, `roads.csv`,
`professions_absolute_count.csv`, and `building_types_profession_mapping.csv`:

> `python post_processing/buildings_assign_function.py`

Optional arguments:

- `--buildings`, `--nodes`, `--edges`, and `--roads` to point at a different city export
- `--professions` to use a different absolute profession-count CSV
- `--mapping` to use a different building-type/profession mapping CSV
- `--output` for the enriched building assignment CSV
- `--workers-output` for the per-building profession/workforce CSV

The script writes:

- `post_processing/output/building_function_assignments.csv`
- `post_processing/output/building_function_workers.csv`

![Demo](./doc/videos/procedural-city-generation.gif)

![roadnetwork](./doc/images/demo-1.png)

![polygons](./doc/images/demo-2.png)

![building](./doc/images/demo-3.png)

![blender](./doc/images/demo-4.png)
