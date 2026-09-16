import random

import pytest

from tropcurves.curve import Curve
from tropcurves.geometry import Vec2, polygon_area2
from tropcurves.balancing import resolve_slopes
from tropcurves.newton import newton_polygon
from tropcurves.subdivision import build_subdivision, SubdivisionError
from tropcurves import builders


def _cell_set(sub):
    return sorted(tuple(sorted((v.x, v.y) for v in c.vertices)) for c in sub.cells)


def test_line_single_triangle():
    c = builders.standard_line()
    sub = build_subdivision(c)
    assert sub.num_cells == 1
    assert sub.cell_side_counts() == [3]
    assert set((v.x, v.y) for v in sub.cells[0].vertices) == {(0, 0), (1, 0), (0, 1)}


def test_caterpillar_two_triangles_along_antidiagonal():
    c = builders.caterpillar_square()
    sub = build_subdivision(c)
    assert sub.cell_side_counts() == [3, 3]
    assert _cell_set(sub) == [
        ((0, 0), (0, 1), (1, 0)),
        ((0, 1), (1, 0), (1, 1)),
    ]


def test_four_valent_vertex_is_a_parallelogram():
    c = Curve()
    c.add_vertex("v0")
    for nm, v in [("a", Vec2(-1, 0)), ("b", Vec2(0, -1)), ("c", Vec2(1, 0)), ("d", Vec2(0, 1))]:
        c.add_end(nm, "v0", v)
    sub = build_subdivision(c)
    assert sub.num_cells == 1
    cell = sub.cells[0]
    assert cell.num_sides == 4
    assert cell.is_parallelogram()
    assert set((v.x, v.y) for v in cell.vertices) == {(0, 0), (1, 0), (1, 1), (0, 1)}


def _crossing_caterpillar():
    c = Curve()
    for v in ["v0", "v1", "v2"]:
        c.add_vertex(v)
    c.add_bounded("e1", "v0", "v1")
    c.add_bounded("e2", "v1", "v2")
    c.add_end("A", "v0", Vec2(-3, -1))
    c.add_end("B", "v0", Vec2(2, 0))
    c.add_end("C", "v1", Vec2(-2, 3))
    c.add_end("D", "v2", Vec2(2, -1))
    c.add_end("E", "v2", Vec2(1, -1))
    resolve_slopes(c)
    return c


def test_crossing_curve_has_parallelogram_and_tiles():
    c = _crossing_caterpillar()
    c.validate()
    sub = build_subdivision(c)
    # this chamber has a transverse self-crossing -> a parallelogram cell
    assert any(cell.is_parallelogram() for cell in sub.cells)
    # cells tile the Newton polygon
    total = sum(polygon_area2(cell.vertices) for cell in sub.cells)
    assert total == polygon_area2(newton_polygon(c))


def test_parallel_edges_at_vertex_rejected():
    # e2 and end D both leave v2 in direction (1,-1): a forced overlap.
    c = Curve()
    for v in ["v0", "v1", "v2"]:
        c.add_vertex(v)
    c.add_bounded("e1", "v0", "v1")
    c.add_bounded("e2", "v1", "v2")
    c.add_end("A", "v0", Vec2(1, 2))
    c.add_end("B", "v0", Vec2(3, 0))
    c.add_end("C", "v1", Vec2(-3, -3))
    c.add_end("D", "v2", Vec2(2, -2))
    c.add_end("E", "v2", Vec2(-3, 3))
    resolve_slopes(c)
    with pytest.raises(SubdivisionError):
        build_subdivision(c)


def _random_valid_curve(rng):
    dirs = [Vec2(x, y) for x in range(-3, 4) for y in range(-3, 4) if not (x == 0 and y == 0)]
    while True:
        ends = [rng.choice(dirs) for _ in range(5)]
        if not sum((e for e in ends), Vec2(0, 0)).is_zero():
            continue
        c = Curve()
        for v in ["v0", "v1", "v2"]:
            c.add_vertex(v)
        c.add_bounded("e1", "v0", "v1")
        c.add_bounded("e2", "v1", "v2")
        c.add_end("A", "v0", ends[0])
        c.add_end("B", "v0", ends[1])
        c.add_end("C", "v1", ends[2])
        c.add_end("D", "v2", ends[3])
        c.add_end("E", "v2", ends[4])
        try:
            resolve_slopes(c)
            c.validate()
        except Exception:
            continue
        return c


def test_random_curves_tile_newton_polygon():
    rng = random.Random(12345)
    checked = 0
    for _ in range(120):
        c = _random_valid_curve(rng)
        try:
            sub = build_subdivision(c)
        except SubdivisionError:
            # a degenerate type (e.g. two incident edges share a direction) has
            # no generic chamber; skip it
            continue
        total = sum(polygon_area2(cell.vertices) for cell in sub.cells)
        assert total == polygon_area2(newton_polygon(c)), f"tiling failed for {c!r}"
        for cell in sub.cells:
            for v in cell.vertices:
                assert isinstance(v.x, int) and isinstance(v.y, int)
        checked += 1
    assert checked >= 40  # plenty of non-degenerate curves were verified
