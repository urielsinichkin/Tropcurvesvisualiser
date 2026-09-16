import math

import pytest

from tropcurves.geometry import (
    Vec2,
    ZERO,
    dot,
    cross,
    rot90,
    primitive,
    weight,
    sort_by_angle,
    polygon_from_edge_vectors,
    convex_hull,
)


def test_vec2_arithmetic():
    a, b = Vec2(1, 2), Vec2(3, -1)
    assert a + b == Vec2(4, 1)
    assert a - b == Vec2(-2, 3)
    assert -a == Vec2(-1, -2)
    assert a * 3 == Vec2(3, 6)
    assert 3 * a == Vec2(3, 6)
    assert list(a) == [1, 2]
    assert a.to_list() == [1, 2]
    assert Vec2.from_iterable([5, 6]) == Vec2(5, 6)


def test_vec2_requires_int():
    with pytest.raises(TypeError):
        Vec2(1.5, 2)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Vec2(1, 2) * 2.0  # type: ignore[arg-type]


def test_dot_cross_rot():
    assert dot(Vec2(1, 2), Vec2(3, 4)) == 11
    assert cross(Vec2(1, 0), Vec2(0, 1)) == 1
    assert cross(Vec2(0, 1), Vec2(1, 0)) == -1
    assert rot90(Vec2(1, 0)) == Vec2(0, 1)
    assert rot90(Vec2(0, 1)) == Vec2(-1, 0)


def test_primitive_and_weight():
    assert primitive(Vec2(2, 4)) == (Vec2(1, 2), 2)
    assert primitive(Vec2(-2, 0)) == (Vec2(-1, 0), 2)
    assert primitive(Vec2(0, 0)) == (ZERO, 0)
    assert primitive(Vec2(-3, 6)) == (Vec2(-1, 2), 3)
    assert weight(Vec2(2, 4)) == 2
    assert weight(Vec2(0, 0)) == 0


def test_sort_by_angle_full_circle():
    vs = [Vec2(0, -1), Vec2(1, 1), Vec2(-1, 0), Vec2(1, 0), Vec2(0, 1)]
    ordered = sort_by_angle(vs)
    # angles: (1,0)=0, (1,1)=45, (0,1)=90, (-1,0)=180, (0,-1)=270
    assert ordered == [Vec2(1, 0), Vec2(1, 1), Vec2(0, 1), Vec2(-1, 0), Vec2(0, -1)]


def test_polygon_from_edge_vectors_square():
    edges = [Vec2(1, 0), Vec2(0, 1), Vec2(-1, 0), Vec2(0, -1)]
    verts = polygon_from_edge_vectors(edges)
    assert verts == [Vec2(0, 0), Vec2(1, 0), Vec2(1, 1), Vec2(0, 1)]


def test_polygon_from_edge_vectors_must_close():
    with pytest.raises(ValueError):
        polygon_from_edge_vectors([Vec2(1, 0), Vec2(0, 1)])


def test_convex_hull_square_with_interior():
    pts = [Vec2(0, 0), Vec2(2, 0), Vec2(2, 2), Vec2(0, 2), Vec2(1, 1), Vec2(1, 0)]
    hull = set((v.x, v.y) for v in convex_hull(pts))
    assert hull == {(0, 0), (2, 0), (2, 2), (0, 2)}


def test_convex_hull_small():
    assert convex_hull([Vec2(3, 3)]) == [Vec2(3, 3)]
    assert set((v.x, v.y) for v in convex_hull([Vec2(0, 0), Vec2(1, 1)])) == {(0, 0), (1, 1)}
