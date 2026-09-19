import pytest

from tropcurves.curve import Curve, EdgeKind
from tropcurves.geometry import Vec2
from tropcurves.newton import newton_polygon
from tropcurves.operations import (
    contract_edge,
    resolutions,
    apply_resolution,
)
from tropcurves import builders


def _newton_set(c):
    return set((v.x, v.y) for v in newton_polygon(c))


def test_contract_caterpillar_to_four_valent():
    c = builders.caterpillar_square()
    before = _newton_set(c)
    res = contract_edge(c, "e")
    d = res.curve
    d.validate()
    assert len(d.vertices) == 1
    assert d.valence(d.vertices[0]) == 4
    assert d.is_balanced()
    assert "e" not in d.edges
    assert _newton_set(d) == before  # ends unchanged
    assert res.vertex_map["v1"] == res.merged_vertex


def test_contract_rejects_non_bounded():
    c = builders.caterpillar_square()
    with pytest.raises(ValueError):
        contract_edge(c, "a")  # an end


def test_resolutions_of_square_four_valent():
    c = contract_edge(builders.caterpillar_square(), "e").curve
    v = c.vertices[0]
    res = resolutions(c, v)  # trivalent resolutions only
    vecs = sorted((r.new_edge_vec.x, r.new_edge_vec.y) for r in res)
    # two triangulations: inserted edges (1,1) and (1,-1) (up to sign)
    assert len(res) == 2
    assert vecs == [(-1, 1), (1, 1)] or vecs == [(1, -1), (1, 1)] or vecs == [(-1, -1), (1, 1)] \
        or vecs == [(1, 1), (1, -1)]
    # with crossings included there is a third (zero) pairing
    allres = resolutions(c, v, include_crossings=True)
    assert len(allres) == 3
    assert sum(1 for r in allres if r.is_crossing) == 1


def test_apply_resolution_roundtrips_to_caterpillar():
    c4 = contract_edge(builders.caterpillar_square(), "e").curve
    v = c4.vertices[0]
    before = _newton_set(c4)
    res = [r for r in resolutions(c4, v) if (r.new_edge_vec.x, r.new_edge_vec.y) == (1, 1)][0]
    out = apply_resolution(c4, res)
    d = out.curve
    d.validate()
    assert len(d.vertices) == 2
    assert d.valence(out.vertex_a) == 3 and d.valence(out.vertex_b) == 3
    assert d.edges[out.new_edge].vec == Vec2(1, 1)
    assert d.is_balanced()
    assert _newton_set(d) == before


def test_resolutions_require_four_valent():
    c = builders.caterpillar_square()  # trivalent vertices
    with pytest.raises(ValueError):
        resolutions(c, "v0")


def test_resolution_crossing_pairing_flagged():
    c4 = contract_edge(builders.caterpillar_square(), "e").curve
    v = c4.vertices[0]
    allres = resolutions(c4, v, include_crossings=True)
    crossing = [r for r in allres if r.is_crossing][0]
    assert crossing.new_edge_vec == Vec2(0, 0)
    with pytest.raises(ValueError):
        apply_resolution(c4, crossing)


def test_marking_on_bounded_edge_subdivides_it():
    c = builders.caterpillar_square()
    before_newton = _newton_set(c)
    from tropcurves.operations import add_marking_on_edge
    r = add_marking_on_edge(c, "e", name="p")
    w, new_edge, mid = r.vertex, r.new_edge, r.marking
    c.validate()  # connected genus-0 tree, balanced, no degenerate edges

    assert len(c.vertices) == 3          # one new vertex on the edge
    assert len(c.bounded) == 2           # the edge became two pieces
    assert len(c.markings) == 1
    # both pieces keep the edge's direction, so they leave w oppositely
    assert c.edges["e"].vec == c.edges[new_edge].vec
    assert c.edges["e"].outgoing(w) == -c.edges[new_edge].outgoing(w)
    assert c.is_balanced() and c.is_tree()
    assert c.edges[mid].tail == w
    assert _newton_set(c) == before_newton   # markings are invisible in Delta


def test_marking_on_end_keeps_the_end_identity():
    c = builders.caterpillar_square()
    before_newton = _newton_set(c)
    before_vec = c.edges["a"].vec
    from tropcurves.operations import add_marking_on_edge
    r = add_marking_on_edge(c, "a")
    w, new_edge, mid = r.vertex, r.new_edge, r.marking
    c.validate()

    # 'a' is still an end, with the same direction, now leaving the new vertex
    assert c.edges["a"].kind is EdgeKind.END
    assert c.edges["a"].vec == before_vec
    assert c.edges["a"].tail == w
    # the piece towards the original vertex is a new bounded edge
    assert c.edges[new_edge].kind is EdgeKind.BOUNDED
    assert c.edges[new_edge].head == w
    # the flag at the original vertex is now the stub, not the end
    assert r.moved_flag_vertex == "v0" and r.split_edge == "a"
    assert {f.id for f in c.incident("v0")} >= {new_edge} and "a" not in {f.id for f in c.incident("v0")}
    assert len(c.ends) == 4              # still four ends
    assert _newton_set(c) == before_newton
    assert c.is_balanced() and c.is_tree()


def test_marking_on_marking_rejected():
    from tropcurves.operations import add_marking_on_edge
    c = builders.caterpillar_square()
    c.add_marking("m1", "v0")
    with pytest.raises(ValueError):
        add_marking_on_edge(c, "m1")


def test_marking_on_edge_leaves_the_dual_subdivision_unchanged():
    # a marking is invisible in the Newton polygon, and subdividing an edge
    # into two collinear pieces must not change the dual subdivision either
    from tropcurves.operations import add_marking_on_edge
    from tropcurves.subdivision import build_subdivision
    c = builders.caterpillar_square()
    before = sorted(tuple(sorted((v.x, v.y) for v in cell.vertices))
                    for cell in build_subdivision(c).cells)
    add_marking_on_edge(c, "e")
    after = sorted(tuple(sorted((v.x, v.y) for v in cell.vertices))
                   for cell in build_subdivision(c).cells)
    assert after == before


# --- resolving a vertex of valence 5 or more -------------------------------
def _star(*vecs):
    """One vertex with the given ends (they must sum to zero)."""
    c = Curve()
    c.add_vertex("v")
    for i, vec in enumerate(vecs):
        c.add_end(f"e{i}", "v", Vec2(*vec))
    c.validate()
    return c


def test_a_five_valent_vertex_splits_along_a_chosen_subset():
    from tropcurves.operations import resolution_for_subset, apply_resolution
    c = _star((1, 0), (0, 1), (-1, 0), (2, 1), (-2, -2))
    res = resolution_for_subset(c, "v", ["e0", "e1"])

    assert set(res.side_a) == {"e0", "e1"}
    assert set(res.side_b) == {"e2", "e3", "e4"}
    # balancing forces the new edge: it absorbs the chosen side's directions
    assert res.new_edge_vec == -(Vec2(1, 0) + Vec2(0, 1))
    out = apply_resolution(c, res)
    out.curve.validate()
    assert out.curve.valence(out.vertex_a) == 3
    assert out.curve.valence(out.vertex_b) == 4
    assert len(out.curve.bounded) == 1


def test_both_sides_need_at_least_two_flags():
    from tropcurves.operations import resolution_for_subset
    c = _star((1, 0), (0, 1), (-1, 0), (2, 1), (-2, -2))
    for bad in ([], ["e0"], ["e0", "e1", "e2", "e3"], ["e0", "e1", "e2", "e3", "e4"]):
        with pytest.raises(ValueError):
            resolution_for_subset(c, "v", bad)


def test_a_subset_must_be_flags_of_that_vertex():
    from tropcurves.operations import resolution_for_sides, resolution_for_subset
    c = _star((1, 0), (0, 1), (-1, 0), (2, 1), (-2, -2))
    with pytest.raises(ValueError):
        resolution_for_subset(c, "v", ["e0", "nope"])
    with pytest.raises(ValueError):       # sides must cover every flag
        resolution_for_sides(c, "v", ["e0", "e1"], ["e2", "e3"])


def test_a_subset_summing_to_zero_is_a_crossing():
    from tropcurves.operations import resolution_for_subset, apply_resolution
    c = _star((1, 0), (-1, 0), (0, 1), (0, -1), (2, 2), (-2, -2))
    res = resolution_for_subset(c, "v", ["e0", "e1"])   # (1,0) + (-1,0) = 0
    assert res.is_crossing
    with pytest.raises(ValueError):
        apply_resolution(c, res)


def test_every_split_is_listed_once():
    from tropcurves.operations import resolutions
    c = _star((1, 0), (0, 1), (-1, 0), (2, 1), (-2, -2))
    listed = resolutions(c, "v", include_crossings=True)
    assert len(listed) == 10                       # 2^5 / 2 - 5 - 1
    seen = {frozenset([frozenset(r.side_a), frozenset(r.side_b)]) for r in listed}
    assert len(seen) == len(listed)                # no split twice
    for r in listed:
        assert 2 <= len(r.side_a) and 2 <= len(r.side_b)
        assert set(r.side_a) | set(r.side_b) == {f"e{i}" for i in range(5)}


def test_valence_four_still_lists_the_three_pairings_in_order():
    from tropcurves.operations import resolutions
    c = builders.caterpillar_square()
    four = contract_edge(c, "e").curve
    listed = resolutions(four, four.vertices[0], include_crossings=True)
    assert [tuple(r.side_a) for r in listed] == [("a", "b"), ("a", "c"), ("a", "d")]


def test_resolving_below_valence_four_is_refused():
    from tropcurves.operations import resolutions
    c = _star((1, 0), (0, 1), (-1, -1))
    with pytest.raises(ValueError):
        resolutions(c, "v")


def test_splitting_a_six_valent_vertex_twice_reaches_trivalent():
    from tropcurves.operations import resolution_for_subset, apply_resolution
    c = _star((1, 0), (0, 1), (-1, 0), (0, -1), (2, 3), (-2, -3))
    out = apply_resolution(c, resolution_for_subset(c, "v", ["e0", "e1"]))
    curve = out.curve
    assert sorted(curve.valence(v) for v in curve.vertices) == [3, 5]
    big = max(curve.vertices, key=curve.valence)
    flags = [f.id for f in curve.incident(big)]
    out2 = apply_resolution(curve, resolution_for_subset(curve, big, flags[:2]))
    out2.curve.validate()
    assert sorted(out2.curve.valence(v) for v in out2.curve.vertices) == [3, 3, 4]
