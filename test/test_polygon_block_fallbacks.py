import numpy as np


class Vertex:
    def __init__(self, x, y, minor_road=False):
        self.coords = np.array((x, y), dtype=float)
        self.minor_road = minor_road


class Wedge:
    def __init__(self, b, alpha=1.0):
        self.b = b
        self.alpha = alpha


def test_getblock_returns_fallback_polygon_for_invalid_vertex_index():
    from procedural_city_generation.polygons.getBlock import getBlock

    vertices = [Vertex(0, 0), Vertex(10, 0), Vertex(10, 10)]
    wedges = [Wedge(0), Wedge(1), Wedge(99)]

    result = getBlock(wedges, vertices)

    assert result == []


def test_getblock_returns_old_polygon_for_degenerate_edge_instead_of_crashing():
    from procedural_city_generation.polygons.getBlock import getBlock

    vertices = [Vertex(0, 0), Vertex(10, 0), Vertex(10, 0), Vertex(0, 10)]
    wedges = [Wedge(0), Wedge(1), Wedge(2), Wedge(3)]

    result = getBlock(wedges, vertices)

    assert len(result) == 1
    assert result[0].poly_type == "road"
    assert len(result[0].vertices) == 4


def test_polygon2d_zero_length_edge_does_not_divide_by_zero():
    from procedural_city_generation.polygons.Polygon2D import Polygon2D

    poly = Polygon2D([
        np.array((0.0, 0.0)),
        np.array((1.0, 0.0)),
        np.array((1.0, 0.0)),
    ])

    assert len(poly.edges) == 3
    assert poly.edges[1].length == 0
    assert tuple(poly.edges[1].n) == (0.0, 0.0)
    assert poly.area == 0
