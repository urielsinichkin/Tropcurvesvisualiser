"""The walk through a type's moduli space: cells, walls, regenerations."""

from fractions import Fraction

import pytest

from tropcurves import moduli
from tropcurves.api import Session


def _trees(leaves):
    """All trivalent trees on the labelled leaves (internal nodes are ints)."""
    out = []

    def rec(edges, nxt, rest):
        if not rest:
            out.append(edges)
            return
        for i, (u, v) in enumerate(edges):
            rec(edges[:i] + edges[i + 1:] + [(u, nxt), (nxt, v), (nxt, rest[0])], nxt + 1, rest[1:])

    rec([(0, leaves[0]), (0, leaves[1]), (0, leaves[2])], 1, list(leaves[3:]))
    return out


def _library(ends, marks):
    """Every trivalent type of this degree whose edges all move (a type with
    a contracted edge is not a type of the library, so it is left out)."""
    s = Session()
    for k, edges in enumerate(_trees(list(ends) + list(marks))):
        nodes = sorted({x for e in edges for x in e if isinstance(x, int)})
        spec = {"vertices": [f"v{n}" for n in nodes], "bounded": [], "ends": [], "markings": []}
        for u, v in edges:
            if isinstance(v, int):
                spec["bounded"].append({"id": f"e{len(spec['bounded']) + 1}",
                                        "tail": f"v{u}", "head": f"v{v}"})
            elif v in ends:
                spec["ends"].append({"id": v, "tail": f"v{u}", "vec": ends[v], "name": v})
            else:
                spec["markings"].append({"id": v, "tail": f"v{u}", "name": v})
        try:
            s.add_curve(spec, name=f"T{k}")
        except Exception:
            pass
    return s


LINE = {"a": [-1, 0], "b": [0, -1], "d": [1, 1]}
EV, LEGS = ["x1", "x2"], ["a", "b", "d", "x3", "x4"]


def _walkable():
    """A library of one full-dimensional type (lines with four markings) whose
    region, at its starting point, has walls; and its starting data."""
    lib = _library(LINE, ["x1", "x2", "x3", "x4"])
    for nid in list(lib.ws.nodes):
        if not lib.moduli_check(nid, EV, LEGS)["full"]:
            continue
        st = lib.moduli_start(nid, EV, LEGS)
        view = lib.moduli_view(nid, EV, LEGS, st["points"], st["m"], 40)
        if view["region"] and view["region"]["walls"]:
            s = Session()
            s.load(lib.export_subset([nid]))
            return s, next(iter(s.ws.nodes)), st
    raise AssertionError("no type with walls")


def test_setup_check_and_start():
    s, nid, st = _walkable()
    out = s.moduli_check(nid, EV, LEGS)
    assert out["ok"] and out["full"] and out["multiplicity"] == 1 and out["why"] is None
    assert len(out["cone"]) == 2
    bad = s.moduli_check(nid, ["x1"], LEGS)
    assert not bad["ok"] and "more markings" in bad["message"]
    with pytest.raises(ValueError):
        s.moduli_check(nid, EV, LEGS[:4])


def test_the_view_places_the_curve_and_colours_its_skeleton():
    s, nid, st = _walkable()
    v = s.moduli_view(nid, EV, LEGS, st["points"], st["m"], 40)
    at = {m["name"]: m["at"] for m in v["picture"]["markings"]}
    for name, (x, y) in st["points"].items():
        assert at[name] == pytest.approx([float(Fraction(x)), float(Fraction(y))])
    # the two coloured paths: their lengths are the coordinates of the point
    c = s.ws.nodes[nid].curve
    ln = {e.id: Fraction(v["lengths"][e.name]) for e in c.bounded}
    for i, coord in enumerate(v["coords"]):
        assert sum(ln[e] for e, k in v["skeleton"].items() if k == i) == Fraction(coord)


def _to_a_wall(s, nid, st):
    v = s.moduli_view(nid, EV, LEGS, st["points"], st["m"], 40)
    w = v["region"]["walls"][0]
    inside = [sum(q[i] for q in v["region"]["polygon"]) / len(v["region"]["polygon"]) for i in range(2)]
    mid = [(w["from"][i] + w["to"][i]) / 2 for i in range(2)]
    far = [mid[i] + (mid[i] - inside[i]) for i in range(2)]
    y0 = v["coords"]
    out = s.moduli_move(nid, EV, LEGS, st["points"], y0, [str(Fraction(x).limit_denominator(10 ** 6)) for x in far])
    return v, out


def test_moving_stops_exactly_at_the_first_wall():
    s, nid, st = _walkable()
    v, out = _to_a_wall(s, nid, st)
    assert out["wall"] is not None
    view = s.moduli_view(nid, EV, LEGS, st["points"], out["m"], 40)
    lengths = {k: Fraction(x) for k, x in view["lengths"].items()}
    assert lengths[out["wall"]["name"]] == 0
    assert all(x >= 0 for x in lengths.values())
    # a move that stays inside reaches its target
    y0 = v["coords"]
    near = [str(Fraction(y0[0]) * Fraction(101, 100)), y0[1]]
    inside = s.moduli_move(nid, EV, LEGS, st["points"], y0, near)
    if inside["wall"] is None:
        assert inside["coords"] == near


def test_at_a_wall_the_regenerations_lead_back_or_on():
    s, nid, st = _walkable()
    _v, out = _to_a_wall(s, nid, st)
    edge = next(e.id for e in s.ws.nodes[nid].curve.bounded if e.name == out["wall"]["name"])
    wall = s.moduli_wall(nid, edge, EV, LEGS)
    wcurve = s.ws.nodes[wall["wall_id"]].curve
    assert max(wcurve.valence(v) for v in wcurve.vertices) >= 4
    regs = wall["regenerations"]
    assert sum(r["back"] for r in regs) == 1 and len(regs) >= 2
    # the wall's curve passes through the points too
    wv = s.moduli_view(wall["wall_id"], EV, LEGS, st["points"], out["m"], 40)
    assert wv["picture"] is not None and not wv["full"]
    for r in regs:
        res = s.moduli_regenerate(wall["wall_id"], wall["vertex"], r["index"], EV, LEGS,
                                  st["points"], out["m"], 10)
        if r["back"]:
            assert res["id"] == nid
        if res["m"] is None:
            assert res["why"]
            continue
        nv = s.moduli_view(res["id"], EV, LEGS, st["points"], res["m"], 40)
        ls = {k: Fraction(x) for k, x in nv["lengths"].items()}
        assert all(x > 0 for x in ls.values())            # a little inside its region
        at = {m["name"]: m["at"] for m in nv["picture"]["markings"]}
        for name, (x, y) in st["points"].items():           # through the same points
            assert at[name] == pytest.approx([float(Fraction(x)), float(Fraction(y))])
        assert min(ls.values()) < Fraction(1)               # the new edge: short
    # going on twice reuses the same type
    on = next(r for r in regs if not r["back"])
    a = s.moduli_regenerate(wall["wall_id"], wall["vertex"], on["index"], EV, LEGS, st["points"], out["m"], 10)
    b = s.moduli_regenerate(wall["wall_id"], wall["vertex"], on["index"], EV, LEGS, st["points"], out["m"], 10)
    assert a["id"] == b["id"]


# A type whose cell is 12-dimensional, as is the target, but on which the
# points fix the length of {x1,x2}: c0 is pinned by x1 and x2, the height of
# c2 by x3, and e1, e2 both drop by one per unit length between them.
WALLED = {
    "vertices": ["c0", "c1", "c2", "c3", "c4", "c5", "c0_1", "c0_2", "c2_1", "c5_1", "c5_2"],
    "bounded": [
        {"id": "e0", "tail": "c0", "head": "c1", "vec": [0, -1], "name": "e1"},
        {"id": "e3", "tail": "c1", "head": "c2", "vec": [1, -1], "name": "e2"},
        {"id": "e5", "tail": "c2", "head": "c3", "vec": [2, -1], "name": "e3"},
        {"id": "e8", "tail": "c3", "head": "c4", "vec": [2, 0], "name": "e4"},
        {"id": "e9", "tail": "c4", "head": "c5", "vec": [1, -1], "name": "e5"},
        {"id": "b1", "tail": "c0", "head": "c0_1", "vec": [-1, 0], "name": "e6"},
        {"id": "b2", "tail": "c0", "head": "c0_2", "vec": [1, 1], "name": "e7"},
        {"id": "b3", "tail": "c2", "head": "c2_1", "vec": [-1, 0], "name": "e8"},
        {"id": "b4", "tail": "c5", "head": "c5_1", "vec": [0, -1], "name": "e9"},
        {"id": "b5", "tail": "c5", "head": "c5_2", "vec": [1, 0], "name": "e10"},
    ],
    "ends": [
        {"id": "l1", "tail": "c0_2", "vec": [1, 1], "name": "l1"},
        {"id": "l2", "tail": "c0_1", "vec": [-1, 0], "name": "l2"},
        {"id": "l3", "tail": "c1", "vec": [-1, 0], "name": "l3"},
        {"id": "l4", "tail": "c2_1", "vec": [-1, 0], "name": "l4"},
        {"id": "l5", "tail": "c3", "vec": [0, -1], "name": "l5"},
        {"id": "l6", "tail": "c4", "vec": [1, 1], "name": "l6"},
        {"id": "l7", "tail": "c5_1", "vec": [0, -1], "name": "l7"},
        {"id": "l8", "tail": "c5_2", "vec": [1, 0], "name": "l8"},
    ],
    "markings": [{"id": f"m{i}", "tail": v, "name": f"x{i}"}
                 for i, v in enumerate(["c0_1", "c0_2", "c2_1", "c5_1", "c5_2"], 1)],
}


def _walled():
    s = Session()
    s.add_curve(WALLED, name="walled")
    marks = ["x1", "x2", "x3", "x4", "x5"]
    return s, {"group": s.moduli_groups()[0]["key"], "evaluated": marks, "legs": marks}


def test_why_a_type_is_not_full_dimensional():
    s = Session()
    nid = s.add_curve(WALLED, name="walled")["id"]
    marks = ["x1", "x2", "x3", "x4", "x5"]
    out = s.moduli_check(nid, marks, marks)
    assert out["ok"] and not out["full"] and out["multiplicity"] == 0
    assert out["why"]["relation"] == "{x1,x2} = y(x1) − y(x3)"


def _walled():
    s = Session()
    s.add_curve(WALLED, name="walled")
    return s, None


def test_moving_a_marking_between_edges_and_vertices():
    s, _cfg = _walled()
    nid = next(iter(s.ws.nodes))
    c = s.ws.nodes[nid].curve
    n_vertices, n_bounded = len(c.vertices), len(c.bounded)
    x3 = next(e for e in c.markings if e.name == "x3")
    old_vertex = x3.tail                       # c2_1, inside the edge e8 + the end l4
    # into the end l7: c2_1 is merged away (e8 and l4 are one end again), and
    # l7 is cut in two
    s.move_marking(nid, x3.id, "edge", "l7")
    c = s.ws.nodes[nid].curve
    assert old_vertex not in c.vertices
    assert len(c.vertices) == n_vertices and len(c.bounded) == n_bounded
    x3 = c.edges[x3.id]
    assert x3.name == "x3" and x3.kind.value == "marking"
    assert {e.id for e in c.incident(x3.tail)} >= {"l7", x3.id}
    l4 = c.edges["l4"]
    assert l4.tail == "c2" and l4.vec.to_list() == [-1, 0]
    c.validate()
    # onto a vertex: c3 (where l5 leaves)
    s.move_marking(nid, x3.id, "vertex", "c3")
    c = s.ws.nodes[nid].curve
    assert c.edges[x3.id].tail == "c3"
    assert len(c.vertices) == n_vertices - 1
    c.validate()
    # back into a bounded edge, e3 (id e5): split in two with the same direction
    s.move_marking(nid, x3.id, "edge", "e5")
    c = s.ws.nodes[nid].curve
    v = c.edges[x3.id].tail
    vecs = sorted(tuple(e.outgoing(v).to_list()) for e in c.incident(v) if e.kind.value == "bounded")
    assert vecs == [(-2, 1), (2, -1)]
    c.validate()
    # the moduli map sees the moved marking (same group: same names)
    marks = ["x1", "x2", "x3", "x4", "x5"]
    out = s.moduli_check(nid, marks, marks)
    assert out["ok"]
    # a move that would merge the target into another edge goes to the merged one
    x1 = next(e for e in c.markings if e.name == "x1")
    s.move_marking(nid, x1.id, "edge", "b1")   # b1 (e6) holds x1's own point: it merges into l2
    c = s.ws.nodes[nid].curve
    c.validate()
    assert c.edges[x1.id].name == "x1"


def test_moving_markings_is_refused_on_derived_types():
    s, _cfg = _walled()
    nid = next(iter(s.ws.nodes))
    child = s.contract(nid, "e8")["id"]
    m = next(e.id for e in s.ws.nodes[nid].curve.markings)
    with pytest.raises(ValueError, match="derived types"):
        s.move_marking(nid, m, "edge", "l7")
    with pytest.raises(ValueError, match="derived from another"):
        s.move_marking(child, m, "edge", "l7")




def test_removing_a_marking_merges_its_point_back_into_the_edge():
    s = Session()
    nid = s.add_preset("caterpillar_square")["id"]
    before = len(s.ws.nodes[nid].curve.vertices)
    mid = s.add_marking_on_edge(nid, "a")["marking_id"]
    assert len(s.ws.nodes[nid].curve.vertices) == before + 1
    s.moduli_remove_marking(nid, mid)
    c = s.ws.nodes[nid].curve
    assert len(c.vertices) == before and not c.markings
    c.validate()


SQUARE = [[[0, 0], [1, 0], [0, 1]], [[1, 0], [1, 1], [0, 1]]]
ONE = [["x1", "x2"]]


def _linked():
    """The square's curve with x1 and x2 together at a vertex (one point) and
    x3 inside the end l1."""
    s = Session()
    nid = s.add_from_subdivision(SQUARE, "drawn")["id"]
    c = s.ws.nodes[nid].curve
    v = next(v for v in c.vertices if c.valence(v) >= 3)
    s.moduli_add_marking(nid, v)
    s.moduli_add_marking(nid, v)
    s.add_marking_on_edge(nid, "l1" if "l1" in c.edges else next(e.id for e in c.ends if e.name == "l1"), "", "")
    return s, nid


def test_a_vertex_carries_fewer_markings_than_other_edges():
    s, nid = _linked()
    c = s.ws.nodes[nid].curve
    v = c.edges[next(e.id for e in c.markings if e.name == "x1")].tail
    with pytest.raises(ValueError, match="at most 2"):
        s.moduli_add_marking(nid, v)                 # 3 other edges: two markings at most
    # x3 sits inside an end: 2 other edges, room for no second marking
    with pytest.raises(ValueError, match="room for one marking only"):
        s.moduli_link(nid, "x3", "x1")
    with pytest.raises(ValueError, match="3 other edges and already 2 markings"):
        s.moduli_link(nid, "x1", "x3")
    assert moduli.crowded_vertices(c) == []


def test_markings_that_are_one_point_are_evaluated_once():
    s, nid = _linked()
    legs = ["l1", "l2", "l3", "l4", "x3"]
    out = s.moduli_check(nid, ["x1", "x2"], legs, ONE)
    # |Delta| + n - 1 - |group| = 4 + 3 - 1 - 2 = 4 = 2 * 1 + 2: one point
    assert out["ok"] and out["dim"] == 4 and out["target"] == 4 and out["full"]
    # without the declaration the two rows coincide: the points are tied
    tied = s.moduli_check(nid, ["x1", "x2"], legs)
    assert not tied["full"] and tied["why"]["kind"] in ("points", "lower")
    st = s.moduli_start(nid, ["x1", "x2"], legs, ONE)
    assert st["points"]["x1"] == st["points"]["x2"]
    v = s.moduli_view(nid, ["x1", "x2"], legs, st["points"], st["m"], 20, ONE)
    at = {m["name"]: m["at"] for m in v["picture"]["markings"]}
    assert at["x1"] == pytest.approx(at["x2"])
    assert at["x1"] == pytest.approx([float(Fraction(x)) for x in st["points"]["x1"]])


def test_one_point_must_be_one_vertex():
    s, nid = _linked()
    legs = ["l1", "l2", "l3", "l4", "x1"]
    out = s.moduli_check(nid, ["x2", "x3"], legs, [["x2", "x3"]])
    assert not out["full"] and out["why"]["kind"] == "apart"
    # linking moves the second onto the first's vertex, when there is room
    s2 = Session()
    nid2 = s2.add_from_subdivision(SQUARE, "drawn")["id"]
    c = s2.ws.nodes[nid2].curve
    v = next(v for v in c.vertices if c.valence(v) >= 3)
    s2.moduli_add_marking(nid2, v)                                  # x1 at a vertex
    s2.add_marking_on_edge(nid2, next(e.id for e in c.ends if e.name == "l3"), "", "")   # x2 on l3
    s2.moduli_link(nid2, "x1", "x2")
    c = s2.ws.nodes[nid2].curve
    by = {e.name: e for e in c.markings}
    assert by["x1"].tail == by["x2"].tail == v
    assert moduli.crowded_vertices(c) == []
    c.validate()


def test_regenerations_keep_one_point_together():
    s, nid = _linked()
    legs = ["l1", "l2", "l3", "l4", "x3"]
    c = s.ws.nodes[nid].curve
    v = c.edges[next(e.id for e in c.markings if e.name == "x1")].tail
    e = next(e.id for e in c.incident(v) if e.kind.value == "bounded")
    wall = s.moduli_wall(nid, e, ["x1", "x2"], legs, ONE)
    regs = wall["regenerations"]
    assert sum(r["back"] for r in regs) == 1
    kinds = set()
    for r in regs:
        if not r["full"]:
            assert r["why"]
            kinds.add("apart" if "different vertices" in r["why"] else
                      "crowded" if "as many markings" in r["why"] else "other")
    assert "apart" in kinds          # the resolutions taking x1 and x2 apart cannot be entered
