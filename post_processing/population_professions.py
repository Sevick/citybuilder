"""Generate profession headcounts for a target population.

This script reads ``input/professions_distribution.csv`` and writes a CSV with
the columns ``ProfessionID`` and ``NumberOfPeople`` to ``output/``.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable


DEFAULT_TOTAL_POPULATION = 10_000
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = BASE_DIR / "input" / "professions_distribution.csv"
DEFAULT_OUTPUT_PATH = BASE_DIR / "output" / "population_professions.csv"
PERCENT_DENOMINATOR = Decimal("100")


@dataclass(frozen=True)
class ProfessionDistribution:
	profession_id: str
	percentage: Decimal


def _non_negative_int(value: str) -> int:
	parsed = int(value)
	if parsed < 0:
		raise argparse.ArgumentTypeError("TOTAL_POPULATION must be a non-negative integer")
	return parsed


def load_profession_distribution(input_path: Path) -> list[ProfessionDistribution]:
	"""Load profession percentages from the configured CSV file."""
	with input_path.open("r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		required_columns = {"Synthetic ID", "Population %"}
		missing_columns = required_columns.difference(reader.fieldnames or [])
		if missing_columns:
			missing_list = ", ".join(sorted(missing_columns))
			raise ValueError(f"Missing required columns in {input_path}: {missing_list}")

		distribution: list[ProfessionDistribution] = []
		for row in reader:
			profession_id = (row.get("Synthetic ID") or "").strip()
			percentage_text = (row.get("Population %") or "").strip()

			if not profession_id:
				continue
			if not percentage_text:
				raise ValueError(f"Missing population percentage for profession {profession_id!r}")

			percentage = Decimal(percentage_text)
			if percentage < 0:
				raise ValueError(f"Negative population percentage for profession {profession_id!r}")

			distribution.append(ProfessionDistribution(profession_id=profession_id, percentage=percentage))

	if not distribution:
		raise ValueError(f"No profession rows found in {input_path}")

	return distribution


def allocate_population(
	distribution: Iterable[ProfessionDistribution], total_population: int
) -> list[tuple[str, int]]:
	"""Convert percentage weights into integer population counts.

	The function uses the largest remainder method so the integer allocations are
	deterministic and always sum exactly to ``total_population``.
	"""
	distribution_list = list(distribution)
	total_percentage = sum(item.percentage for item in distribution_list)
	if total_percentage <= 0:
		raise ValueError("The sum of profession percentages must be greater than zero")

	allocations: list[dict[str, Decimal | int | str]] = []
	assigned_population = 0

	for item in distribution_list:
		exact_count = (Decimal(total_population) * item.percentage) / total_percentage
		base_count = int(exact_count)
		assigned_population += base_count
		allocations.append(
			{
				"profession_id": item.profession_id,
				"base_count": base_count,
				"remainder": exact_count - Decimal(base_count),
			}
		)

	remaining_people = total_population - assigned_population
	ranked_allocations = sorted(
		enumerate(allocations),
		key=lambda entry: (-entry[1]["remainder"], entry[1]["profession_id"]),
	)
	for index, _ in ranked_allocations[:remaining_people]:
		allocations[index]["base_count"] = int(allocations[index]["base_count"]) + 1

	return [
		(str(item["profession_id"]), int(item["base_count"]))
		for item in allocations
	]


def write_population_csv(rows: Iterable[tuple[str, int]], output_path: Path) -> Path:
	"""Write the allocated profession totals to disk."""
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(["ProfessionID", "NumberOfPeople"])
		writer.writerows(rows)
	return output_path


def generate_population_csv(
	total_population: int,
	input_path: Path = DEFAULT_INPUT_PATH,
	output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
	"""Generate the profession population CSV and return its path."""
	distribution = load_profession_distribution(input_path)
	allocated_rows = allocate_population(distribution, total_population)
	return write_population_csv(allocated_rows, output_path)


def build_argument_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description=(
			"Generate a ProfessionID/NumberOfPeople CSV from the profession "
			"distribution percentages."
		)
	)
	parser.add_argument(
		"total_population",
		nargs="?",
		type=_non_negative_int,
		default=DEFAULT_TOTAL_POPULATION,
		help=(
			"Target city population. Defaults to "
			f"{DEFAULT_TOTAL_POPULATION}."
		),
	)
	parser.add_argument(
		"--input",
		type=Path,
		default=DEFAULT_INPUT_PATH,
		help=f"Path to the professions distribution CSV. Defaults to {DEFAULT_INPUT_PATH}.",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=DEFAULT_OUTPUT_PATH,
		help=f"Path for the generated profession population CSV. Defaults to {DEFAULT_OUTPUT_PATH}.",
	)
	return parser


def main() -> int:
	parser = build_argument_parser()
	args = parser.parse_args()

	output_path = generate_population_csv(
		total_population=args.total_population,
		input_path=args.input,
		output_path=args.output,
	)
	print(f"Wrote profession population CSV to {output_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

