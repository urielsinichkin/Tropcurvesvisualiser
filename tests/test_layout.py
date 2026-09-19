"""Layout: the drawn picture must not invent incidences the type does not have."""

import random
from fractions import Fraction

import pytest

from tropcurves import builders
from tropcurves.curve import Curve
from tropcurves.geometry import Vec2
from tropcurves.layout import (
    embed, end_ray_length, min_clearance, readable_lengths, vertex_span,
)
from tropcurves.operations import add_marking_on_edge
from tropcurves.subdivision import build_subdivision, SubdivisionError

TARGET = 0.06          # the default readable_lengths aims for
TOUCHING = 1e-9        # clearances are floats; this is "on top of each other"


def _unit(curve):
    return {e.id: Fraction(1) for e in curve.bounded}


def _reported_curve():
    """The type from the bug report: a resolved 4-valent vertex, end l2 marked.

    With unit lengths the marked vertex lands exactly on the end (2, 1).
    """
    c = Curve()
    c.add_vertex("c0")
    for eid, vec, name in [("e0", (-3, -2), "l1"), ("e1", (1, 0), "l2"),
                           ("e2", (2, 1), "l3"), ("e3", (0, 1), "l4")]:
        c.add_end(eid, "c0", Vec2(*vec), name=name)
    from tropcurves.operations import resolutions, apply_resolution
    res = next(r for r in resolutions(c, "c0") if set(r.side_a) == {"e0", "e2"})
    c = apply_resolution(c, res).curve
    add_marking_on_edge(c, "e1", name="x1")
    c.validate()
    return c


def test_unit_lengths_can_put_a_vertex_on_an_unrelated_end():
    c = _reported_curve()
    assert min_clearance(c, embed(c, _unit(c))) < TOUCHING


def test_readable_lengths_separate_them():
    c = _reported_curve()
    assert min_clearance(c, embed(c, readable_lengths(c))) >= TARGET


def test_readable_lengths_keep_unit_when_unit_is_already_clear():
    c = builders.caterpillar_square()
    assert min_clearance(c, embed(c, _unit(c))) >= TARGET
    assert readable_lengths(c) == _unit(c)


def test_readable_lengths_are_deterministic():
    c = _reported_curve()
    assert readable_lengths(c) == readable_lengths(c)


def test_clearance_is_scale_invariant():
    c = _reported_curve()
    L = readable_lengths(c)
    doubled = {k: v * 2 for k, v in L.items()}
    a = min_clearance(c, embed(c, L))
    b = min_clearance(c, embed(c, doubled))
    assert a == pytest.approx(b)


def test_clearance_ignores_where_an_end_is_cut_off():
    # a vertex on the *continuation* of an end still reads as lying on it, so
    # it must count even though the ray is drawn shorter than that
    c = _reported_curve()
    pos = embed(c, _unit(c))
    far = max(abs(float(x)) + abs(float(y)) for x, y in pos.values())
    assert end_ray_length(pos) < far            # the drawn ray stops short
    assert min_clearance(c, pos) < TOUCHING     # and it is still reported


def test_a_degenerate_type_cannot_be_separated():
    # an end leaving v0 along the edge v0 -> v1 runs through v1 whatever the
    # lengths; the layout reports that (0) instead of pretending otherwise
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", Vec2(1, 0))
    c.add_end("a", "v0", Vec2(1, 0))
    c.add_end("b", "v0", Vec2(-2, 0))
    c.add_end("d", "v1", Vec2(0, 1))
    c.add_end("f", "v1", Vec2(1, -1))
    c.validate()
    assert min_clearance(c, embed(c, readable_lengths(c))) < TOUCHING


def test_random_curves_get_a_clear_picture_unless_degenerate():
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from test_subdivision import _random_valid_curve

    rng = random.Random(7)
    tight = 0
    for _ in range(60):
        c = _random_valid_curve(rng)
        score = min_clearance(c, embed(c, readable_lengths(c)))
        if score > TOUCHING:
            continue
        # zero clearance is only allowed for a type with no generic embedding
        with pytest.raises(SubdivisionError):
            build_subdivision(c)
        tight += 1
    assert tight < 30          # and that is the minority


def test_vertex_span_of_a_single_vertex_is_not_zero():
    c = builders.standard_line()
    pos = embed(c, {})
    assert vertex_span(pos) == 1.0 and end_ray_length(pos) > 0
