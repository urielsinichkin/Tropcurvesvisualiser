import pytest

from tropcurves.curve import Curve
from tropcurves.geometry import Vec2
from tropcurves.balancing import resolve_slopes
from tropcurves.newton import newton_polygon
from tropcurves.subdivision import build_subdivision
from tropcurves.subdivision_import import import_subdivision
from tropcurves import builders


def _newton_set(c):
    return set((v.x, v.y) for v in newton_polygon(c))


def _ends(c):
    return sorted((e.vec.x, e.vec.y) for e in c.ends)


def test_import_two_triangle_square():
    cells = [[(0, 0), (1, 0), (0, 1)], [(1, 0), (1, 1), (0, 1)]]
    c = import_subdivision(cells)
    c.validate()
    assert len(c.vertices) == 2
    assert len(c.bounded) == 1
    assert len(c.ends) == 4
    assert c.is_tree() and c.is_balanced()
    assert _newton_set(c) == {(0, 0), (1, 0), (1, 1), (0, 1)}


def test_import_single_triangle_is_a_line():
    c = import_subdivision([[(0, 0), (1, 0), (0, 1)]])
    assert len(c.vertices) == 1
    assert len(c.ends) == 3
    assert c.is_balanced()
    assert _newton_set(c) == {(0, 0), (1, 0), (0, 1)}


def test_single_parallelogram_is_reducible():
    with pytest.raises(ValueError):
        import_subdivision([[(0, 0), (1, 0), (1, 1), (0, 1)]])


def test_edge_shared_by_three_cells_rejected():
    # three cells all claiming the segment (0,0)-(1,0)
    cells = [
        [(0, 0), (1, 0), (0, 1)],
        [(0, 0), (1, 0), (0, -1)],
        [(0, 0), (1, 0), (1, -1)],
    ]
    with pytest.raises(ValueError):
        import_subdivision(cells)


def _crossing_curve():
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


@pytest.mark.parametrize("factory", [
    builders.standard_line,
    builders.caterpillar_square,
    _crossing_curve,
])
def test_export_then_import_roundtrip(factory):
    c = factory()
    sub = build_subdivision(c)
    cells = [[(v.x, v.y) for v in cell.vertices] for cell in sub.cells]
    d = import_subdivision(cells)
    d.validate()
    assert d.is_tree() and d.is_balanced()
    assert _ends(d) == _ends(c)              # same ends recovered
    assert _newton_set(d) == _newton_set(c)  # same Newton polygon


def test_import_opens_parallelogram_crossing():
    c = _crossing_curve()
    sub = build_subdivision(c)
    cells = [[(v.x, v.y) for v in cell.vertices] for cell in sub.cells]
    n_par = sum(1 for cell in sub.cells if cell.is_parallelogram())
    d = import_subdivision(cells)
    # opening the parallelogram(s) drops that many cell-vertices
    assert n_par >= 1
    assert len(d.vertices) == len(cells) - n_par
