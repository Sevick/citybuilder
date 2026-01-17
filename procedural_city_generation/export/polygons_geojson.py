"""Polygon export helpers.

This exporter targets a widely-supported format: GeoJSON.

We export a FeatureCollection where each feature is a polygon footprint.
The input comes from the polygons submodule output:
`procedural_city_generation/temp/<input_name>_polygons.txt`
which pickles a list of Polygon2D objects.

Python: 3.10+
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence


def _closed_ring(coords: Sequence[Sequence[float]]) -> list[list[float]]:
    ring = [[float(x), float(y)] for x, y in coords]
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def export_polygon2d_list_to_geojson(polygons: Iterable[Any], out_path: str | Path) -> Path:
    """Write a list of Polygon2D-like objects to GeoJSON.

    Each object is expected to have:
      - vertices: iterable of (x,y) (often numpy arrays)
      - poly_type: string (e.g. 'lot', 'road', 'vacant')

    Returns the written path.
    """

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    features = []
    for idx, poly in enumerate(polygons):
        verts = getattr(poly, "vertices", None)
        if verts is None:
            continue

        # Convert vertices to a single exterior ring
        ring = _closed_ring([(v[0], v[1]) for v in verts])
        if len(ring) < 4:
            # Not a valid polygon ring
            continue

        props = {
            "index": idx,
            "poly_type": getattr(poly, "poly_type", None),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": props,
            }
        )

    fc = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    return out_path

