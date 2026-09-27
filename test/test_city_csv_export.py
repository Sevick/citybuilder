import csv
from pathlib import Path


class V:
    def __init__(self, idx: int, x: float, y: float, minor_road: bool = False):
        self.selfindex = idx
        self.coords = (x, y)
        self.neighbours = []
        self.minor_road = minor_road


class P:
    def __init__(self, vertices, name=None, poly_type=None):
        self.vertices = vertices
        self.name = name
        self.poly_type = poly_type


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_header(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def test_export_city_csv_writes_requested_files_and_schema(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0, v1, v2 = V(0, 0, 0), V(1, 10, 0), V(2, 20, 0, minor_road=True)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1]
    poly = P([(12, 5), (16, 5), (16, 9), (12, 9)], name="House A")

    written = export_city_csv(
        [v0, v1, v2],
        [poly],
        tmp_path,
        base_junction_id=0,
        base_road_id=100,
        base_building_id=200,
        merge_roads=False,
        export_buildings=True,
    )

    assert set(written.keys()) == {"nodes", "edges", "roads", "buildings", "buildings_shape"}
    for path in written.values():
        assert path.exists()

    nodes = _read_rows(written["nodes"])
    assert nodes == [
        {"ID": "0", "positionX": "0", "positionY": "0"},
        {"ID": "1", "positionX": "10", "positionY": "0"},
        {"ID": "2", "positionX": "20", "positionY": "0"},
    ]

    edges = _read_rows(written["edges"])
    assert len(edges) == 2
    assert edges[0] == {"ID": "0", "source": "0", "target": "1", "length": "10", "type": "0"}
    assert edges[1] == {"ID": "1", "source": "1", "target": "2", "length": "10", "type": "1"}

    roads = _read_rows(written["roads"])
    assert roads[0]["ID"] == "100"
    assert roads[0]["edges"] == "0"
    assert roads[1]["ID"] == "101"
    assert roads[1]["edges"] == "1"
    assert roads[1]["type"] == "1"

    buildings = _read_rows(written["buildings"])
    assert _read_header(written["buildings"]) == ["ID", "entranceX", "entranceY", "entranceEdgeID", "square", "on_main_road"]
    assert buildings == [
        {"ID": "200", "entranceX": "14", "entranceY": "5", "entranceEdgeID": "1", "square": "16", "on_main_road": "0"}
    ]

    building_shape = _read_rows(written["buildings_shape"])
    assert building_shape == [
        {"buildingID": "200", "shape": "12;5;16;5;16;9;12;9"},
    ]


def test_export_city_csv_merge_roads_uses_existing_merge_logic(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 1, 0), V(2, 2, 0), V(3, 3, 0)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2]

    written = export_city_csv([v0, v1, v2, v3], [], tmp_path, base_junction_id=0, base_road_id=10, merge_roads=True)

    roads = _read_rows(written["roads"])
    edges = _read_rows(written["edges"])
    buildings = _read_rows(written["buildings"])
    building_shapes = _read_rows(written["buildings_shape"])

    assert len(roads) == 1
    assert roads[0]["ID"] == "10"
    assert roads[0]["type"] == "0"
    assert roads[0]["edges"] == "0;1;2"
    assert len(edges) == 3
    assert buildings == []
    assert building_shapes == []


def test_export_city_csv_merge_roads_keeps_turns_in_one_road(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 1, 0), V(2, 2, 0), V(3, 2, 1)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2]

    written = export_city_csv([v0, v1, v2, v3], [], tmp_path, base_junction_id=0, base_road_id=10, merge_roads=True)

    roads = _read_rows(written["roads"])
    edges = _read_rows(written["edges"])

    assert len(roads) == 1
    assert roads[0]["type"] == "0"
    assert roads[0]["edges"] == "0;1;2"
    assert [(row["source"], row["target"]) for row in edges] == [("0", "1"), ("1", "2"), ("2", "3")]


def test_export_city_csv_merge_roads_major_road_absorbs_minor_end_segments(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

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

    written = export_city_csv([v0, v1, v2, v3, v4], [], tmp_path, base_junction_id=0, base_road_id=20, merge_roads=True)

    roads = _read_rows(written["roads"])
    edges = _read_rows(written["edges"])

    assert len(roads) == 1
    assert roads[0]["ID"] == "20"
    assert roads[0]["type"] == "0"
    assert roads[0]["edges"] == "0;1;2;3"
    assert [row["type"] for row in edges] == ["0", "0", "0", "0"]
    assert {(row["source"], row["target"]) for row in edges} == {("0", "1"), ("1", "2"), ("2", "3"), ("3", "4")}


def test_export_city_csv_merge_roads_building_uses_segment_edge_id_for_entrance(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 10, 0), V(2, 20, 0), V(3, 30, 0)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2]
    poly = P([(18, 5), (22, 5), (22, 9), (18, 9)])

    written = export_city_csv(
        [v0, v1, v2, v3],
        [poly],
        tmp_path,
        base_junction_id=0,
        base_road_id=10,
        base_building_id=20,
        merge_roads=True,
        export_buildings=True,
    )

    roads = _read_rows(written["roads"])
    edges = _read_rows(written["edges"])
    buildings = _read_rows(written["buildings"])

    assert len(roads) == 1
    assert roads[0]["edges"] == "0;1;2"
    assert [(row["ID"], row["source"], row["target"]) for row in edges] == [
        ("0", "0", "1"),
        ("1", "1", "2"),
        ("2", "2", "3"),
    ]
    assert buildings == [
        {"ID": "20", "entranceX": "20", "entranceY": "5", "entranceEdgeID": "1", "square": "16", "on_main_road": "1"}
    ]


def test_export_city_csv_merge_roads_building_on_minor_branch_is_not_on_main_road(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0, v1, v2, v3 = V(0, 0, 0), V(1, 10, 0), V(2, 20, 0), V(3, 10, 10, minor_road=True)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2, v3]
    v2.neighbours = [v1]
    v3.neighbours = [v1]
    poly = P([(12, 12), (16, 12), (16, 16), (12, 16)])

    written = export_city_csv(
        [v0, v1, v2, v3],
        [poly],
        tmp_path,
        base_junction_id=0,
        base_road_id=10,
        base_building_id=20,
        merge_roads=True,
        export_buildings=True,
    )

    roads = _read_rows(written["roads"])
    buildings = _read_rows(written["buildings"])

    assert len(roads) == 2
    assert {row["type"] for row in roads} == {"0", "1"}
    assert buildings == [
        {"ID": "20", "entranceX": "14", "entranceY": "12", "entranceEdgeID": "2", "square": "16", "on_main_road": "0"}
    ]


def test_export_city_csv_merge_roads_minor_tail_on_major_road_counts_as_main(tmp_path):
    from procedural_city_generation.export.city_csv import export_city_csv

    v0 = V(0, -10, 0, minor_road=True)
    v1 = V(1, 0, 0)
    v2 = V(2, 10, 0)
    v3 = V(3, 20, 0)
    v4 = V(4, 30, 0, minor_road=True)
    v0.neighbours = [v1]
    v1.neighbours = [v0, v2]
    v2.neighbours = [v1, v3]
    v3.neighbours = [v2, v4]
    v4.neighbours = [v3]
    poly = P([(26, 5), (30, 5), (30, 9), (26, 9)])

    written = export_city_csv(
        [v0, v1, v2, v3, v4],
        [poly],
        tmp_path,
        base_junction_id=0,
        base_road_id=20,
        base_building_id=30,
        merge_roads=True,
        export_buildings=True,
    )

    roads = _read_rows(written["roads"])
    buildings = _read_rows(written["buildings"])

    assert roads == [{"ID": "20", "name": "Road 20", "type": "0", "edges": "0;1;2;3"}]
    assert buildings == [
        {"ID": "30", "entranceX": "28", "entranceY": "5", "entranceEdgeID": "3", "square": "16", "on_main_road": "1"}
    ]

