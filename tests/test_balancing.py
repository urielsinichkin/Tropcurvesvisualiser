import pytest

from tropcurves.curve import Curve
from tropcurves.geometry import Vec2, ZERO
from tropcurves.balancing import (
    SlopeSolveError,
    solve_bounded,
    resolve_slopes,
    apply_two_ends_edit,
    ends_sum,
)
from tropcurves import builders


def _fresh_caterpillar_unsolved() -> Curve:
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", name="e")
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    c.add_end("b", "v0", Vec2(0, -1), name="b")
    c.add_end("c", "v1", Vec2(1, 0), name="c")
    c.add_end("d", "v1", Vec2(0, 1), name="d")
    return c


def test_resolve_slopes_solves_bounded_edge():
    c = _fresh_caterpillar_unsolved()
    assert c.edges["e"].vec == ZERO
    resolve_slopes(c)
    assert c.edges["e"].vec == Vec2(1, 1)
    assert c.is_balanced()


def test_solve_inconsistent_ends_raise():
    # A single vertex with three ends that do not sum to zero.
    c = Curve()
    c.add_vertex("v0")
    c.add_end("a", "v0", Vec2(-1, 0))
    c.add_end("b", "v0", Vec2(0, -1))
    c.add_end("d", "v0", Vec2(1, 0))  # sum = (0,-1) != 0
    with pytest.raises(SlopeSolveError):
        resolve_slopes(c)


def test_ends_sum_helper():
    c = builders.caterpillar_square()
    assert ends_sum(c) == ZERO
    assert ends_sum(c, exclude="c") == -Vec2(1, 0)


def test_two_ends_edit_rebalances():
    c = builders.caterpillar_square()
    apply_two_ends_edit(c, "a", Vec2(-2, -1), dependent_end_id="c")
    assert c.edges["a"].vec == Vec2(-2, -1)
    assert c.edges["c"].vec == Vec2(2, 1)  # -(a+b+d) = -((-2,-1)+(0,-1)+(0,1))
    assert c.edges["e"].vec == Vec2(2, 2)  # -(a+b) at v0
    assert c.is_balanced()
    assert ends_sum(c) == ZERO


def test_two_ends_edit_rejects_zero_new_vec():
    c = builders.caterpillar_square()
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "a", ZERO, dependent_end_id="c")
    assert c.edges["a"].vec == Vec2(-1, 0)  # unchanged


def test_two_ends_edit_same_end_rejected():
    c = builders.caterpillar_square()
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "a", Vec2(-2, -1), dependent_end_id="a")


def test_two_ends_edit_rejects_degenerate_bounded_edge():
    # Editing a to (0,1) makes a+b = 0, collapsing the bounded edge e to zero.
    c = builders.caterpillar_square()
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "a", Vec2(0, 1), dependent_end_id="c")
    # rollback: original values intact
    assert c.edges["a"].vec == Vec2(-1, 0)
    assert c.edges["e"].vec == Vec2(1, 1)
    assert c.is_balanced()


def test_two_ends_edit_rejects_zero_dependent():
    # Choosing dependent d and editing a to (-1,1) makes a+b+c = 0, so d -> 0.
    c = builders.caterpillar_square()
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "a", Vec2(-1, 1), dependent_end_id="d")
    assert c.edges["a"].vec == Vec2(-1, 0)  # rolled back


def test_two_ends_edit_rejects_non_end():
    c = builders.caterpillar_square()
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "e", Vec2(1, 0), dependent_end_id="c")  # e is bounded
    with pytest.raises(SlopeSolveError):
        apply_two_ends_edit(c, "a", Vec2(1, 0), dependent_end_id="e")


def test_solve_underdetermined_detected():
    # A 2-cycle of unknown bounded edges (positive genus): every vertex keeps two
    # unknown incident edges, so leaf-pruning can never peel one off.
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e1", "v0", "v1", name="e1")
    c.add_bounded("e2", "v0", "v1", name="e2")
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    c.add_end("b", "v1", Vec2(1, 0), name="b")
    with pytest.raises(SlopeSolveError):
        solve_bounded(c)
