import csv
import subprocess
import sys
from pathlib import Path

import pytest

from post_processing.buildings_assign_function import (
    generate_building_function_csv,
    load_profession_counts,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "post_processing" / "buildings_assign_function.py"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_fixture(tmp_path: Path) -> dict[str, Path]:
    nodes_path = _write_csv(
        tmp_path / "nodes.csv",
        ["ID", "positionX", "positionY"],
        [
            {"ID": 0, "positionX": -100, "positionY": 0},
            {"ID": 1, "positionX": 0, "positionY": 0},
            {"ID": 2, "positionX": 100, "positionY": 0},
            {"ID": 3, "positionX": 0, "positionY": -100},
            {"ID": 4, "positionX": 0, "positionY": 100},
            {"ID": 5, "positionX": 200, "positionY": 0},
        ],
    )
    edges_path = _write_csv(
        tmp_path / "edges.csv",
        ["ID", "source", "target", "length", "type"],
        [
            {"ID": 0, "source": 0, "target": 1, "length": 100, "type": 0},
            {"ID": 1, "source": 1, "target": 2, "length": 100, "type": 0},
            {"ID": 2, "source": 1, "target": 3, "length": 100, "type": 0},
            {"ID": 3, "source": 1, "target": 4, "length": 100, "type": 0},
            {"ID": 4, "source": 2, "target": 5, "length": 100, "type": 0},
        ],
    )
    roads_path = _write_csv(
        tmp_path / "roads.csv",
        ["ID", "name", "type", "edges"],
        [
            {"ID": 200, "name": "Decumanus", "type": 0, "edges": "0;1;4"},
            {"ID": 201, "name": "Cardo", "type": 0, "edges": "2;3"},
        ],
    )
    buildings_path = _write_csv(
        tmp_path / "buildings.csv",
        ["ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road"],
        [
            {"ID": 10, "entranceX": 5, "entranceY": 5, "entranceEdgeID": 1, "square": 1500, "on_main_road": 1},
            {"ID": 11, "entranceX": 0, "entranceY": 120, "entranceEdgeID": 3, "square": 900, "on_main_road": 1},
            {"ID": 12, "entranceX": 170, "entranceY": 0, "entranceEdgeID": 4, "square": 1000, "on_main_road": 1},
            {"ID": 13, "entranceX": -40, "entranceY": 20, "entranceEdgeID": 0, "square": 400, "on_main_road": 1},
            {"ID": 14, "entranceX": 0, "entranceY": -120, "entranceEdgeID": 2, "square": 350, "on_main_road": 1},
        ],
    )
    professions_path = _write_csv(
        tmp_path / "professions_absolute_count.csv",
        ["GroupID", "Synthetic ID", "Name", "Population %", "Count"],
        [
            {"GroupID": 1, "Synthetic ID": "17-0", "Name": "magistrate_assistant", "Population %": "0.0", "Count": 3},
            {"GroupID": 2, "Synthetic ID": "16-0", "Name": "priest", "Population %": "0.0", "Count": 2},
            {"GroupID": 3, "Synthetic ID": "9-0", "Name": "merchant", "Population %": "0.0", "Count": 4},
        ],
    )
    mapping_path = _write_csv(
        tmp_path / "building_types_profession_mapping.csv",
        ["BuildingTypeID", "BuildingTypeName", "ProfessionID", "MinNumberOfPeople", "MaxNumberOfPeople"],
        [
            {
                "BuildingTypeID": 34,
                "BuildingTypeName": "Civic Office and Archive",
                "ProfessionID": "17-0",
                "MinNumberOfPeople": 1,
                "MaxNumberOfPeople": 3,
            },
            {
                "BuildingTypeID": 33,
                "BuildingTypeName": "Temple and Shrine",
                "ProfessionID": "16-0",
                "MinNumberOfPeople": 1,
                "MaxNumberOfPeople": 2,
            },
            {
                "BuildingTypeID": 25,
                "BuildingTypeName": "Market Hall and Shop Row",
                "ProfessionID": "9-0",
                "MinNumberOfPeople": 1,
                "MaxNumberOfPeople": 4,
            },
        ],
    )
    return {
        "nodes": nodes_path,
        "edges": edges_path,
        "roads": roads_path,
        "buildings": buildings_path,
        "professions": professions_path,
        "mapping": mapping_path,
    }


def test_load_profession_counts_reads_clean_csv(tmp_path):
    professions_path = _write_csv(
        tmp_path / "professions_absolute_count.csv",
        ["GroupID", "Synthetic ID", "Name", "Population %", "Count"],
        [
            {"GroupID": 1, "Synthetic ID": "0-0", "Name": "grain_merchant", "Population %": "0.1", "Count": 7},
            {"GroupID": 1, "Synthetic ID": "0-1", "Name": "grain_measurer", "Population %": "0.1", "Count": 5},
        ],
    )

    professions = load_profession_counts(professions_path)

    assert set(professions) == {"0-0", "0-1"}
    assert professions["0-0"].name == "grain_merchant"
    assert professions["0-0"].count == 7
    assert professions["0-1"].count == 5


def test_load_profession_counts_raises_for_incomplete_nonblank_row(tmp_path):
    professions_path = _write_csv(
        tmp_path / "professions_absolute_count.csv",
        ["GroupID", "Synthetic ID", "Name", "Population %", "Count"],
        [
            {"GroupID": 1, "Synthetic ID": "0-0", "Name": "grain_merchant", "Population %": "0.1", "Count": 7},
            {"GroupID": 1, "Synthetic ID": "0-1", "Name": "grain_measurer", "Population %": "0.1", "Count": ""},
        ],
    )

    with pytest.raises(ValueError, match="Missing Count"):
        load_profession_counts(professions_path)


def test_generate_building_function_csv_assigns_landmarks_and_exact_worker_totals(tmp_path):
    fixture = _build_fixture(tmp_path)
    assignments_output = tmp_path / "building_function_assignments.csv"
    workers_output = tmp_path / "building_function_workers.csv"

    result = generate_building_function_csv(
        buildings_path=fixture["buildings"],
        professions_path=fixture["professions"],
        mapping_path=fixture["mapping"],
        nodes_path=fixture["nodes"],
        edges_path=fixture["edges"],
        roads_path=fixture["roads"],
        assignments_output_path=assignments_output,
        workers_output_path=workers_output,
        seed=7,
    )

    assert result["assignments"] == assignments_output
    assert result["workers"] == workers_output
    assert result["remaining_professions"] == {}

    assignment_rows = _read_rows(assignments_output)
    worker_rows = _read_rows(workers_output)

    assert len(assignment_rows) == 5
    by_building = {row["ID"]: row for row in assignment_rows}
    assert by_building["10"]["landmark"] == "FORUM"
    assert by_building["10"]["building_type_id"] == "34"
    assert {row["landmark"] for row in assignment_rows} >= {"FORUM", "TEMPLE", "MARKET"}

    totals: dict[str, int] = {}
    for row in worker_rows:
        totals[row["professionID"]] = totals.get(row["professionID"], 0) + int(row["numberOfPeople"])

    assert totals == {"17-0": 3, "16-0": 2, "9-0": 4}


def test_buildings_assign_function_cli_runs_standalone(tmp_path):
    fixture = _build_fixture(tmp_path)
    assignments_output = tmp_path / "cli_building_function_assignments.csv"
    workers_output = tmp_path / "cli_building_function_workers.csv"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--buildings",
            str(fixture["buildings"]),
            "--professions",
            str(fixture["professions"]),
            "--mapping",
            str(fixture["mapping"]),
            "--nodes",
            str(fixture["nodes"]),
            "--edges",
            str(fixture["edges"]),
            "--roads",
            str(fixture["roads"]),
            "--output",
            str(assignments_output),
            "--workers-output",
            str(workers_output),
            "--seed",
            "7",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT_DIR,
    )

    assert assignments_output.exists()
    assert workers_output.exists()
    assert "Wrote building assignments CSV" in completed.stdout
    assert "Assigned all target professions to buildings" in completed.stdout



