import pytest

from tropcurves.geometry import Vec2
from tropcurves.newton import newton_polygon, newton_edge_vectors
from tropcurves import builders
from tropcurves.curve import Curve


def test_newton_of_line_is_unit_triangle():
    c = builders.standard_line()
    verts = set((v.x, v.y) for v in newton_polygon(c))
    assert verts == {(0, 0), (1, 0), (0, 1)}


def test_newton_of_caterpillar_is_unit_square():
    c = builders.caterpillar_square()
    verts = set((v.x, v.y) for v in newton_polygon(c))
    assert verts == {(0, 0), (1, 0), (1, 1), (0, 1)}


def test_newton_edge_vectors_sum_to_zero():
    c = builders.caterpillar_square()
    evs = newton_edge_vectors(c)
    total = Vec2(sum(v.x for v in evs), sum(v.y for v in evs))
    assert total == Vec2(0, 0)


def test_newton_markings_do_not_affect_polygon():
    c = builders.standard_line()
    before = set((v.x, v.y) for v in newton_polygon(c))
    c.add_marking("m", "v0")
    after = set((v.x, v.y) for v in newton_polygon(c))
    assert before == after


def test_newton_weighted_end_lattice_length():
    # A weight-2 line: ends (-2,0), (0,-2), (2,2). Newton polygon is the size-2
    # triangle with vertices (0,0),(2,0),(0,2).
    c = Curve()
    c.add_vertex("v0")
    c.add_end("a", "v0", Vec2(-2, 0))
    c.add_end("b", "v0", Vec2(0, -2))
    c.add_end("d", "v0", Vec2(2, 2))
    verts = set((v.x, v.y) for v in newton_polygon(c))
    assert verts == {(0, 0), (2, 0), (0, 2)}


def test_newton_requires_ends():
    c = Curve()
    c.add_vertex("v0")
    with pytest.raises(ValueError):
        newton_polygon(c)
