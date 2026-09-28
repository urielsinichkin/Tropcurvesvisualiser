import pytest

from tropcurves.api import Session
from tropcurves.curve import Curve
from tropcurves.evaluation import evaluation_matrix, setup, determinant
from tropcurves.geometry import Vec2


def _four_ended():
    """v0 --e--> v1 with e = (1, 1); ends a, b at v0 and c, d at v1;
    markings m1 at v0 and m2 at v1."""
    c = Curve()
    c.add_vertex("v0"); c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", Vec2(1, 1), name="e")
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    c.add_end("b", "v0", Vec2(0, -1), name="b")
    c.add_end("c", "v1", Vec2(1, 0), name="c")
    c.add_end("d", "v1", Vec2(0, 1), name="d")
    c.add_marking("m1", "v0", name="m1")
    c.add_marking("m2", "v1", name="m2")
    c.validate()
    return c


def test_marked_line_is_the_identity():
    c = Curve()
    c.add_vertex("v")
    c.add_end("a", "v", Vec2(-1, 0)); c.add_end("b", "v", Vec2(0, -1)); c.add_end("c", "v", Vec2(1, 1))
    c.add_marking("m", "v", name="m")
    out = evaluation_matrix(c, "v", [{"kind": "x", "marking": "m"}, {"kind": "y", "marking": "m"}])
    assert out["matrix"] == [[1, 0], [0, 1]]
    assert out["columns"] == ["x0", "y0"]
    assert out["rows"] == ["x(m)", "y(m)"]
    assert out["det"] == 1


def test_rows_follow_the_path_from_the_root():
    c = _four_ended()
    fs = [{"kind": "x", "marking": "m1"}, {"kind": "y", "marking": "m1"}, {"kind": "x", "marking": "m2"}]
    from_v0 = evaluation_matrix(c, "v0", fs)
    assert from_v0["matrix"] == [[1, 0, 0], [0, 1, 0], [1, 0, 1]]
    # from the other end the edge is walked backwards: -(1, 1)
    from_v1 = evaluation_matrix(c, "v1", fs)
    assert from_v1["matrix"] == [[1, 0, -1], [0, 1, -1], [1, 0, 0]]
    # changing the root is unimodular, so |det| does not depend on it
    assert abs(from_v0["det"]) == abs(from_v1["det"]) == 1


def test_cross_ratio_signs():
    c = _four_ended()
    cr = lambda *p: evaluation_matrix(c, "v0", [{"kind": "cross_ratio", "points": list(p)}],
                                      require_square=False)["matrix"][0]
    assert cr("a", "b", "c", "d") == [0, 0, 1]     # a->c and b->d both run along e
    assert cr("a", "d", "c", "b") == [0, 0, -1]    # d->b runs against a->c
    assert cr("a", "c", "b", "d") == [0, 0, 0]     # a->b stays at v0
    assert cr("m1", "b", "m2", "d") == [0, 0, 1]   # markings count as legs
    with pytest.raises(ValueError):
        cr("a", "a", "c", "d")


def test_weighted_vertex_gives_its_multiplicity():
    # a trivalent vertex with directions (-1, 0), (-1, -2), (2, 2): multiplicity 2;
    # markings on the first two legs, so each leg is a bounded edge + end
    c = Curve()
    for v in ("v", "w1", "w2"):
        c.add_vertex(v)
    c.add_bounded("e1", "v", "w1", Vec2(-1, 0), name="e1")
    c.add_bounded("e2", "v", "w2", Vec2(-1, -2), name="e2")
    c.add_end("a", "w1", Vec2(-1, 0)); c.add_end("b", "w2", Vec2(-1, -2)); c.add_end("c", "v", Vec2(2, 2))
    c.add_marking("m1", "w1", name="m1"); c.add_marking("m2", "w2", name="m2")
    c.validate()
    fs = [{"kind": k, "marking": m} for m in ("m1", "m2") for k in ("x", "y")]
    dets = {abs(evaluation_matrix(c, r, fs)["det"]) for r in c.vertices}
    assert dets == {2}


def test_needs_exactly_n_functions():
    c = _four_ended()
    with pytest.raises(ValueError):
        evaluation_matrix(c, "v0", [{"kind": "x", "marking": "m1"}])


def test_setup_orders_roots_and_defaults():
    c = _four_ended()
    s = setup(c)
    assert [r["label"] for r in s["roots"]] == ["m1", "m2"]      # both vertices are marked
    assert s["n"] == 3
    assert s["default_functions"] == [
        {"kind": "x", "marking": "m1"}, {"kind": "y", "marking": "m1"},
        {"kind": "x", "marking": "m2"}, {"kind": "y", "marking": "m2"}]
    assert [l["name"] for l in s["legs"]] == ["m1", "m2", "a", "b", "c", "d"]


def test_setup_lists_unmarked_vertices_after_markings_naturally_sorted():
    c = Curve()
    for v in ("p", "q", "r"):
        c.add_vertex(v)
    c.add_bounded("e10", "p", "q", Vec2(1, 0), name="e10")
    c.add_bounded("e2", "p", "r", Vec2(0, 1), name="e2")
    c.add_end("l1", "p", Vec2(-1, -1), name="l1")
    c.add_end("l2", "q", Vec2(1, 0), name="l2"); c.add_end("l3", "q", Vec2(-1, 0), name="l3")
    c.add_end("l4", "r", Vec2(0, 1), name="l4"); c.add_end("l5", "r", Vec2(0, -1), name="l5")
    c.add_marking("x10", "q", name="x10"); c.add_marking("x2", "r", name="x2")
    s = setup(c)
    assert [r["label"] for r in s["roots"]] == ["x2", "x10", "vertex e2, e10, l1"]
    assert s["roots"][0]["vertex"] == "r"


def test_session_api_round_trip():
    s = Session()
    root = s.add_preset("caterpillar_square")
    edge = next(e for e in s.render(root["id"])["curve"]["edges"] if e["kind"] == "end")
    s.add_marking_on_edge(root["id"], edge["id"])
    setup_ = s.evaluation_setup(root["id"])
    assert setup_["roots"][0]["kind"] == "marking"         # the marking is offered first
    fs = setup_["default_functions"][:setup_["n"]]
    while len(fs) < setup_["n"]:
        legs = [l["id"] for l in setup_["legs"]][:4]
        fs.append({"kind": "cross_ratio", "points": legs})
    out = s.evaluation_matrix(root["id"], setup_["roots"][0]["vertex"], fs)
    assert len(out["matrix"]) == setup_["n"] and all(len(r) == setup_["n"] for r in out["matrix"])
    assert isinstance(out["det"], int)


def test_determinant_exact():
    assert determinant([[2, 1], [1, 1]]) == 1
    assert determinant([[0, 1], [1, 0]]) == -1
    assert determinant([[1, 2], [2, 4]]) == 0


def test_columns_are_sorted_by_edge_name():
    c = Curve()
    for v in ("p", "q", "r"):
        c.add_vertex(v)
    c.add_bounded("zz", "p", "q", Vec2(1, 0), name="e10")
    c.add_bounded("aa", "p", "r", Vec2(0, 1), name="e2")
    c.add_end("l1", "p", Vec2(-1, -1))
    c.add_end("l2", "q", Vec2(1, 0)); c.add_end("l3", "q", Vec2(-1, 0))
    c.add_end("l4", "r", Vec2(0, 1)); c.add_end("l5", "r", Vec2(0, -1))
    c.add_marking("m", "q", name="m")
    out = evaluation_matrix(c, "p", [{"kind": "x", "marking": "m"}], require_square=False)
    assert out["columns"] == ["x0", "y0", "e2", "e10"]
    assert out["matrix"] == [[1, 0, 0, 1]]
