#!/usr/bin/env python3
"""Generate topological sort of profession supply chain dependencies.

Reads professions_supply_chain_dependencies.csv and writes
profession_supply_chain_topo.csv with columns:
  ProfessionID,TopoOrder,Tier

Tier 0 = root producers (no dependencies).
"""

from __future__ import annotations

import csv
from collections import defaultdict, deque
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "input" / "professions_supply_chain_dependencies.csv"
OUTPUT_PATH = BASE_DIR / "output" / "profession_supply_chain_topo.csv"


def load_dependencies(path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """Load dependency graph.
    Returns (dependents_of, dependencies_of, all_professions).
    dependents_of[prof] = set of professions that depend on prof (reverse edges).
    dependencies_of[prof] = set of professions that prof depends on (forward edges).
    """
    dependents_of = defaultdict(set)
    dependencies_of = defaultdict(set)
    all_professions = set()

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dep = row["Dependent"].strip()
            d = row["Dependency"].strip()
            if not dep or not d:
                continue
            dependents_of[d].add(dep)
            dependencies_of[dep].add(d)
            all_professions.add(dep)
            all_professions.add(d)

    return dependents_of, dependencies_of, all_professions


def topological_sort_with_tiers(
    dependents_of: dict[str, set[str]],
    dependencies_of: dict[str, set[str]],
    all_professions: set[str]
) -> list[tuple[str, int, int]]:
    """Kahn's algorithm with tier (longest path from roots).
    Returns list of (profession_id, topo_order, tier).
    """
    # In-degree = number of dependencies
    in_degree = {prof: len(dependencies_of.get(prof, set())) for prof in all_professions}

    # Queue of nodes with in-degree 0
    queue = deque([prof for prof in all_professions if in_degree[prof] == 0])

    topo_order = 0
    tier = {prof: 0 for prof in all_professions}
    result = []

    while queue:
        # Process all nodes at current tier level
        level_size = len(queue)
        for _ in range(level_size):
            prof = queue.popleft()
            result.append((prof, topo_order, tier[prof]))
            topo_order += 1

            for dependent in dependents_of.get(prof, set()):
                in_degree[dependent] -= 1
                # Tier of dependent = max(tier[dependent], tier[prof] + 1)
                tier[dependent] = max(tier[dependent], tier[prof] + 1)
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    if len(result) != len(all_professions):
        # Cycle detected - fall back to tier 0 for remaining
        remaining = all_professions - {r[0] for r in result}
        for prof in sorted(remaining):
            result.append((prof, topo_order, 0))
            topo_order += 1

    return result


def main() -> int:
    dependents_of, dependencies_of, all_professions = load_dependencies(INPUT_PATH)
    sorted_professions = topological_sort_with_tiers(dependents_of, dependencies_of, all_professions)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ProfessionID", "TopoOrder", "Tier"])
        for prof_id, topo_order, tier in sorted_professions:
            writer.writerow([prof_id, topo_order, tier])

    print(f"Wrote {len(sorted_professions)} professions to {OUTPUT_PATH}")
    # Summary
    tiers = defaultdict(int)
    for _, _, t in sorted_professions:
        tiers[t] += 1
    for t in sorted(tiers):
        print(f"  Tier {t}: {tiers[t]} professions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())