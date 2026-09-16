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
