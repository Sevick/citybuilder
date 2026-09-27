import csv
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from post_processing.population_professions import (
    ProfessionDistribution,
    allocate_population,
    generate_population_csv,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "post_processing" / "population_professions.py"
INPUT_PATH = ROOT_DIR / "post_processing" / "input" / "professions_distribution.csv"


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generate_population_csv_writes_expected_schema_and_totals(tmp_path):
    output_path = tmp_path / "population_professions.csv"

    written_path = generate_population_csv(10_000, INPUT_PATH, output_path)

    assert written_path == output_path
    assert written_path.exists()

    rows = _read_rows(written_path)
    assert len(rows) == 235
    assert rows[0] == {"ProfessionID": "0-0", "NumberOfPeople": "109"}
    assert rows[4] == {"ProfessionID": "0-4", "NumberOfPeople": "100"}
    assert rows[-1] == {"ProfessionID": "31-4", "NumberOfPeople": "10"}
    assert sum(int(row["NumberOfPeople"]) for row in rows) == 10_000


def test_allocate_population_uses_deterministic_largest_remainder_ordering():
    distribution = [
        ProfessionDistribution("b", Decimal("25")),
        ProfessionDistribution("a", Decimal("25")),
        ProfessionDistribution("d", Decimal("25")),
        ProfessionDistribution("c", Decimal("25")),
    ]

    allocated = allocate_population(distribution, 2)

    assert allocated == [("b", 1), ("a", 1), ("d", 0), ("c", 0)]
    assert sum(count for _, count in allocated) == 2


def test_population_professions_script_runs_as_standalone_cli(tmp_path):
    output_path = tmp_path / "cli_population_professions.csv"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "100", "--input", str(INPUT_PATH), "--output", str(output_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT_DIR,
    )

    assert output_path.exists()
    assert "Wrote profession population CSV" in completed.stdout

    rows = _read_rows(output_path)
    assert rows[0]["ProfessionID"] == "0-0"
    assert sum(int(row["NumberOfPeople"]) for row in rows) == 100



