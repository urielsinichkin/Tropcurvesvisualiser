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

from tropcurves.layout import CLEARANCE_GOAL as TARGET   # what readable_lengths aims for
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


def test_readable_lengths_keep_the_targets_when_already_clear():
    # the target is a drawn (Euclidean) length of 1, so the diagonal edge of the
    # caterpillar is 1/sqrt(2) in lattice units
    c = builders.caterpillar_square()
    L = readable_lengths(c)
    assert abs(float(L["e"]) - 2 ** -0.5) < 1e-6
    assert min_clearance(c, embed(c, L)) >= TARGET


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


# --- drawn lengths and resemblance to the parent ---------------------------
from tropcurves.layout import display_lengths, layout_reference, target_drawn_lengths, _unit_len


def _drawn(curve, L):
    return {e.id: float(L[e.id]) * _unit_len(e) for e in curve.bounded}


def test_edges_are_evened_out_in_drawn_length_not_lattice_length():
    # direction (3, 4) is five lattice units long per step; it must not be drawn 5x
    c = Curve()
    c.add_vertex("u"); c.add_vertex("v")
    c.add_bounded("e", "u", "v", Vec2(3, 4))
    c.add_end("a", "u", Vec2(-1, 0)); c.add_end("b", "u", Vec2(-2, -4))
    c.add_end("c", "v", Vec2(0, 1)); c.add_end("d", "v", Vec2(3, 3))
    c.validate()
    assert abs(_drawn(c, readable_lengths(c))["e"] - 1.0) < 1e-3


def test_an_edge_cut_by_interior_markings_keeps_its_length():
    c = builders.caterpillar_square()
    add_marking_on_edge(c, "e", name="p")
    t = target_drawn_lengths(c)
    assert sorted(t.values()) == [0.5, 0.5]           # two halves of one edge


def _derived_by_two_steps():
    """A type that differs from its parent by nothing but a marking.

    root -> contract e -> resolve the same pairing back (a new edge id), with a
    marking at a vertex, and the middle type deleted so the child is derived
    from the root in one go -- the shape of the case that prompted this.
    """
    from tropcurves.workspace import Workspace
    from tropcurves.operations import resolution_for_subset
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    mid = ws.contract(root.id, "e")
    v = mid.curve.vertices[0]
    child = ws.resolve(mid.id, resolution_for_subset(mid.curve, v, ["a", "b"]))
    ws.add_marking(child.id, v, name="x")
    ws.delete(mid.id)
    return ws, root, child


def test_a_child_differing_only_by_a_marking_is_drawn_identically():
    from tropcurves.api import Session
    ws, root, child = _derived_by_two_steps()
    s = Session(); s.ws = ws
    Lp, _ = s._node_layout(root.id)
    Lc, _ = s._node_layout(child.id)
    pp = {v: (float(x), float(y)) for v, (x, y) in embed(root.curve, Lp).items()}
    pc = {v: (float(x), float(y)) for v, (x, y) in embed(child.curve, Lc).items()}
    shared = set(pp) & set(pc)
    assert len(shared) >= 1
    (ax, ay), (bx, by) = next(iter((pp[v], pc[v]) for v in shared))
    for v in shared:
        assert abs((pc[v][0] - bx) - (pp[v][0] - ax)) < 1e-3
        assert abs((pc[v][1] - by) - (pp[v][1] - ay)) < 1e-3
    # and the recreated edge (a fresh id) is drawn as long as the one it replaces
    new_edge = [e for e in child.curve.bounded if e.id not in root.curve.edges][0]
    assert abs(_drawn(child.curve, Lc)[new_edge.id] - _drawn(root.curve, Lp)["e"]) < 1e-3


def test_a_child_is_not_held_to_more_clearance_than_its_parent_had():
    # the parent's own clearance is part of the reference, and an exact copy of
    # a parent that is only just clear must stay an exact copy
    c = builders.caterpillar_square()
    L = readable_lengths(c)
    ref = layout_reference(c, L)
    assert "clearance" in ref and ref["clearance"] > 0
    assert display_lengths(c, ref) == L


def test_the_subdivision_is_built_in_the_chamber_that_is_drawn():
    from tropcurves.api import Session
    s = Session()
    node = s.add_preset("caterpillar_square")["id"]
    lengths, _ = s._node_layout(node)
    drawn = build_subdivision(s.ws.nodes[node].curve, lengths=lengths)
    norm = lambda cells: sorted(tuple(sorted(map(tuple, c))) for c in cells)
    assert norm(s.render(node)["subdivision"]["cells"]) == \
           norm([[v.to_list() for v in cell.vertices] for cell in drawn.cells])
