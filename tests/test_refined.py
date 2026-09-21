"""Refined (Goettsche-Schroeter) multiplicity."""

from fractions import Fraction

import pytest

from tropcurves import builders
from tropcurves.curve import Curve
from tropcurves.geometry import Vec2
from tropcurves.operations import add_marking_on_edge, contract_edge
from tropcurves.refined import (
    Laurent, MultiplicityError, RefinedValue, balanced_split, q_integer_minus,
    q_integer_plus, refined_multiplicity, vertex_multiplicity,
)


def _star(*vecs, marked=False):
    """A single vertex with the given ends (which must sum to zero)."""
    c = Curve()
    c.add_vertex("v")
    for i, vec in enumerate(vecs):
        c.add_end(f"e{i}", "v", Vec2(*vec), name=f"l{i}")
    if marked:
        c.add_marking("m1", "v", name="p")
    c.validate()
    return c


# --- the q-integers --------------------------------------------------------
@pytest.mark.parametrize("q", [Fraction(4), Fraction(9), Fraction(1, 4), Fraction(25)])
@pytest.mark.parametrize("a", [1, 2, 3, 4, 5, 6, 7])
def test_q_integers_match_their_definition(a, q):
    t = Fraction(q).numerator ** 0 * _sqrt(q)
    assert q_integer_minus(a).at_q(q) == (t ** a - t ** -a) / (t - t ** -1)
    assert q_integer_plus(a).at_q(q) == (t ** a + t ** -a) / (t + t ** -1)


def _sqrt(q: Fraction) -> Fraction:
    import math
    return Fraction(math.isqrt(q.numerator), math.isqrt(q.denominator))


def test_the_minus_integers_are_polynomials_and_the_plus_ones_only_for_odd_a():
    for a in range(1, 8):
        assert q_integer_minus(a).is_polynomial
        assert q_integer_plus(a).is_polynomial is bool(a % 2)


def test_q_integers_read_as_expected():
    assert q_integer_minus(1).text() == "1"
    assert q_integer_minus(2).text() == "q^(1/2) + q^(-1/2)"
    assert q_integer_minus(3).text() == "q + 1 + q^-1"
    assert q_integer_plus(3).text() == "q - 1 + q^-1"
    assert q_integer_plus(5).text() == "q^2 - q + 1 - q^-1 + q^-2"
    assert q_integer_plus(2).text() == "(q + q^-1) / (q^(1/2) + q^(-1/2))"


def test_at_q_one_counts_the_unrefined_multiplicity():
    for a in range(1, 8):
        assert q_integer_minus(a).at_q(Fraction(1)) == a
        assert q_integer_plus(a).at_q(Fraction(1)) == 1


def test_a_leftover_denominator_cancels_when_it_can():
    # [2]^- [2]^+ = (t + 1/t)(t^2 + 1/t^2)/(t + 1/t) = q + q^-1
    v = q_integer_minus(2) * q_integer_plus(2)
    assert v.is_polynomial and v.text() == "q + q^-1"


def test_values_add_across_different_denominators():
    a, b = q_integer_plus(2), q_integer_minus(3)          # one fraction, one not
    s = a + b
    for q in (Fraction(4), Fraction(9)):
        assert s.at_q(q) == a.at_q(q) + b.at_q(q)


def test_laurent_halving_needs_even_coefficients():
    assert Laurent.of(0, [2, 4]).halve() == Laurent.of(0, [1, 2])
    assert Laurent.of(0, [2, 3]).halve() is None


# --- vertices --------------------------------------------------------------
def test_a_plain_trivalent_vertex():
    vm = vertex_multiplicity(builders.standard_line(), "v0")
    assert (vm.mu, vm.marked) == (1, False)


def test_a_weighted_vertex_has_the_lattice_area_of_its_dual_triangle():
    vm = vertex_multiplicity(_star((2, 0), (-1, 1), (-1, -1)), "v")
    assert (vm.mu, vm.marked) == (2, False)


def test_a_marking_makes_the_vertex_marked_without_changing_mu():
    vm = vertex_multiplicity(_star((2, 0), (-1, 1), (-1, -1), marked=True), "v")
    assert (vm.mu, vm.marked) == (2, True)


def test_a_degenerate_vertex_is_refused():
    with pytest.raises(MultiplicityError):
        vertex_multiplicity(_star((2, 0), (-1, 0), (-1, 0)), "v")


def test_a_four_valent_vertex_is_refused():
    four = contract_edge(builders.caterpillar_square(), "e").curve
    with pytest.raises(MultiplicityError):
        refined_multiplicity(four)


def test_two_markings_at_one_vertex_are_refused():
    c = _star((2, 0), (-1, 1), (-1, -1), marked=True)
    c.add_marking("m2", "v", name="p2")
    with pytest.raises(MultiplicityError):
        refined_multiplicity(c)


def test_a_marking_in_the_interior_of_an_edge_is_refused():
    # that vertex is trivalent counting the marking, so the curve under it is
    # not trivalent -- the definition does not cover it
    c = builders.caterpillar_square()
    add_marking_on_edge(c, "e", name="mid")
    with pytest.raises(MultiplicityError):
        refined_multiplicity(c)


# --- whole curves ----------------------------------------------------------
def test_a_line_and_the_square_caterpillar_have_multiplicity_one():
    assert refined_multiplicity(builders.standard_line()).text() == "1"
    assert refined_multiplicity(builders.caterpillar_square()).text() == "1"


def test_a_curve_is_the_product_over_its_vertices():
    # two vertices, of multiplicity 2 and 1
    c = Curve()
    c.add_vertex("v0"); c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", Vec2(1, 1), name="e")
    c.add_end("a", "v0", Vec2(-2, 0), name="a")
    c.add_end("b", "v0", Vec2(1, -1), name="b")
    c.add_end("c", "v1", Vec2(2, 1), name="c")
    c.add_end("d", "v1", Vec2(-1, 0), name="d")
    c.validate()
    assert vertex_multiplicity(c, "v0").mu == 2
    assert vertex_multiplicity(c, "v1").mu == 1
    assert refined_multiplicity(c) == q_integer_minus(2) * q_integer_minus(1)


def test_marking_a_vertex_switches_which_q_integer_it_contributes():
    plain = _star((3, 0), (-1, 1), (-2, -1))
    mu = vertex_multiplicity(plain, "v").mu
    marked = _star((3, 0), (-1, 1), (-2, -1), marked=True)
    assert refined_multiplicity(plain) == q_integer_minus(mu)
    assert refined_multiplicity(marked) == q_integer_plus(mu)


def test_at_q_one_a_curve_counts_only_its_unmarked_vertices():
    c = _star((3, 0), (-1, 1), (-2, -1))
    assert refined_multiplicity(c).at_q(Fraction(1)) == vertex_multiplicity(c, "v").mu
    marked = _star((3, 0), (-1, 1), (-2, -1), marked=True)
    assert refined_multiplicity(marked).at_q(Fraction(1)) == 1


# --- balanced splits -------------------------------------------------------
def test_two_equal_values_split():
    a = q_integer_minus(3)
    chosen = balanced_split([a, a])
    assert chosen is not None and len(chosen) == 1


def test_a_split_that_needs_both_sides_to_pair_up():
    a, b = q_integer_minus(2), q_integer_minus(3)
    chosen = balanced_split([a, b, a, b])
    assert chosen is not None
    picked = sorted(chosen)
    rest = [i for i in range(4) if i not in set(chosen)]
    assert _total([a, b, a, b], picked) == _total([a, b, a, b], rest)


def _total(values, idx):
    out = values[idx[0]]
    for i in idx[1:]:
        out = out + values[i]
    return out


def test_no_split_when_the_total_cannot_be_halved():
    assert balanced_split([q_integer_minus(1)]) is None
    assert balanced_split([q_integer_minus(2), q_integer_minus(3)]) is None


def test_a_split_across_values_with_leftover_denominators():
    a, b = q_integer_plus(2), q_integer_plus(4)      # neither is a polynomial
    chosen = balanced_split([a, b, b, a])
    assert chosen is not None
    rest = [i for i in range(4) if i not in set(chosen)]
    assert _total([a, b, b, a], sorted(chosen)) == _total([a, b, b, a], rest)


def test_an_empty_set_splits_trivially():
    assert balanced_split([]) == []


def test_too_many_curves_is_refused_rather_than_hung_on():
    with pytest.raises(ValueError):
        balanced_split([q_integer_minus(1)] * 40)
