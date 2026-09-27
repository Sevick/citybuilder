import json
from pathlib import Path


def test_city_json_v2_roads_have_segments_and_building_access_has_segment():
    # Uses committed example output as a smoke test.
    p = Path(__file__).resolve().parents[1] / "procedural_city_generation" / "outputs" / "mycity_city.json"
    data = json.loads(p.read_text(encoding="utf-8"))

    assert data.get("schemaVersion") == 2
    assert isinstance(data.get("junctions"), list) and data["junctions"]
    assert isinstance(data.get("roads"), list)

    # Ensure each road has segments and each segment connects nodes.
    junction_ids = {j["id"] for j in data["junctions"]}
    for r in data["roads"][:100]:
        assert r.get("road_type") in (0, 1)
        assert "segments" in r and isinstance(r["segments"], list) and r["segments"]
        for s in r["segments"]:
            assert s["from"] in junction_ids
            assert s["to"] in junction_ids
            assert isinstance(s.get("shape"), list) and len(s["shape"]) >= 2

    # Buildings should include access and new building geometry when present
    for b in data.get("buildings", [])[:100]:
        access = b.get("access", {})
        assert "road" in access
        assert "offset" in access
        # segment may be missing if road is None
        if access.get("road") is not None:
            assert "segment" in access

        building = b.get("building")
        assert isinstance(building, dict)
        assert isinstance(building.get("polygon"), list) and len(building["polygon"]) >= 3
        assert "entrancePointX" in building
        assert "entrancePointY" in building


def test_export_merge_option_produces_multi_segment_roads():
    # Construct a tiny graph: 4 nodes in a line. Should merge into 1 road with 3 segments.
    from procedural_city_generation.export.city_json import export_city_json

    class V:
        def __init__(self, idx: int, x: float, y: float, minor_road: bool = False):
            self.selfindex = idx
            self.coords = (x, y)
            self.neighbours = []
            self.minor_road = minor_road

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 1, 0), V(2, 2, 0), V(3, 3, 0)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2]

    out = Path(__file__).with_suffix(".tmp.json")
    try:
        export_city_json([v0, v1, v2, v3], [], out, base_junction_id=0, base_road_id=0, merge_roads=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["roads"]) == 1
        assert data["roads"][0]["road_type"] == 0
        assert len(data["roads"][0]["segments"]) == 3
    finally:
        if out.exists():
            out.unlink()


def test_export_buildings_toggle_omits_buildings_and_keeps_roads():
    from procedural_city_generation.export.city_json import export_city_json

    class V:
        def __init__(self, idx: int, x: float, y: float):
            self.selfindex = idx
            self.coords = (x, y)
            self.neighbours = []

    class P:
        def __init__(self, vertices):
            self.vertices = vertices

    v0, v1 = V(0, 0, 0), V(1, 10, 0)
    v0.neighbours = [v1]
    v1.neighbours = [v0]

    poly = P([(5, 5), (6, 5), (6, 6), (5, 6)])

    out = Path(__file__).with_suffix(".tmp2.json")
    try:
        export_city_json([v0, v1], [poly], out, base_junction_id=0, base_road_id=0, base_building_id=0, export_buildings=False)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data.get("roads"), list) and data["roads"]
        assert data.get("buildings") == []
    finally:
        if out.exists():
            out.unlink()


def test_export_merge_option_handles_turns_and_assigns_all_edges_once():
    from procedural_city_generation.export.city_json import export_city_json

    class V:
        def __init__(self, idx: int, x: float, y: float, minor_road: bool = False):
            self.selfindex = idx
            self.coords = (x, y)
            self.neighbours = []
            self.minor_road = minor_road

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 1, 0), V(2, 2, 0), V(3, 2, 1)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2]

    out = Path(__file__).with_suffix(".turn.tmp.json")
    try:
        export_city_json([v0, v1, v2, v3], [], out, base_junction_id=0, base_road_id=0, merge_roads=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["roads"]) == 1
        road = data["roads"][0]
        assert road["road_type"] == 0
        assert len(road["segments"]) == 3
        used = {tuple(sorted((s["from"], s["to"]))) for s in road["segments"]}
        assert used == {(0, 1), (1, 2), (2, 3)}
    finally:
        if out.exists():
            out.unlink()


def test_export_merge_option_major_road_can_absorb_minor_dead_end_tails():
    from procedural_city_generation.export.city_json import export_city_json

    class V:
        def __init__(self, idx: int, x: float, y: float, minor_road: bool = False):
            self.selfindex = idx
            self.coords = (x, y)
            self.neighbours = []
            self.minor_road = minor_road

    v0 = V(0, -1, 0, minor_road=True)
    v1 = V(1, 0, 0)
    v2 = V(2, 1, 0)
    v3 = V(3, 2, 0)
    v4 = V(4, 3, 0, minor_road=True)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2, v4]
    v4.neighbours = [v3]

    out = Path(__file__).with_suffix(".tails.tmp.json")
    try:
        export_city_json([v0, v1, v2, v3, v4], [], out, base_junction_id=0, base_road_id=0, merge_roads=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["roads"]) == 1
        road = data["roads"][0]
        assert road["road_type"] == 0
        assert len(road["segments"]) == 4
        used = {tuple(sorted((s["from"], s["to"]))) for s in road["segments"]}
        assert used == {(0, 1), (1, 2), (2, 3), (3, 4)}
    finally:
        if out.exists():
            out.unlink()


def test_export_merge_option_leaves_minor_branch_as_separate_connected_road():
    from procedural_city_generation.export.city_json import export_city_json

    class V:
        def __init__(self, idx: int, x: float, y: float, minor_road: bool = False):
            self.selfindex = idx
            self.coords = (x, y)
            self.neighbours = []
            self.minor_road = minor_road

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 1, 0), V(2, 2, 0), V(3, 1, 1, minor_road=True)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2, v3]
    v2.neighbours = [v1]
    v3.neighbours = [v1]

    out = Path(__file__).with_suffix(".branch.tmp.json")
    try:
        export_city_json([v0, v1, v2, v3], [], out, base_junction_id=0, base_road_id=0, merge_roads=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["roads"]) == 2
        segment_sets = [
            {tuple(sorted((s["from"], s["to"]))) for s in road["segments"]}
            for road in data["roads"]
        ]
        assert {(0, 1), (1, 2)} in segment_sets
        assert {(1, 3)} in segment_sets
        assert sum(len(s) for s in segment_sets) == 3
    finally:
        if out.exists():
            out.unlink()
