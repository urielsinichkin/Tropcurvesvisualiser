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


def test_a_vertex_carries_fewer_markings_than_other_edges():
    s = Session()
    nid = s.add_from_subdivision(SQUARE, "drawn")["id"]
    c = s.ws.nodes[nid].curve
    v = next(v for v in c.vertices if c.valence(v) >= 3)
    s.moduli_add_marking(nid, v)
    s.moduli_add_marking(nid, v)
    with pytest.raises(ValueError, match="at most 2"):
        s.moduli_add_marking(nid, v)                 # 3 other edges: two markings at most


def test_positive_kernel_point():
    # l1 = l2 and l2 + l3 = 2 l4, all positive
    E = [[1, -1, 0, 0], [0, 1, 1, -2]]
    l = moduli.positive_kernel_point(E, 4)
    assert all(x > 0 for x in l)
    assert all(sum(Fraction(a) * x for a, x in zip(r, l)) == 0 for r in E)
    # l1 = -l2 has no positive solution
    assert moduli.positive_kernel_point([[1, 1, 0]], 3) is None
    assert moduli.positive_kernel_point([[1, 0, -1], [0, 0, 1]], 3) is None


# The 2x2 square cut by an inner parallelogram: a rational curve with 8 ends
# whose image crosses itself where e1 meets the end l3.
CROSS = [[[0, 0], [1, 0], [0, 1]], [[1, 0], [2, 0], [1, 1], [0, 1]], [[2, 0], [2, 1], [1, 1]],
         [[1, 1], [2, 1], [1, 2]], [[2, 1], [2, 2], [1, 2]], [[0, 1], [1, 1], [0, 2]],
         [[1, 1], [1, 2], [0, 2]]]
MARKS5 = ["x1", "x2", "x3", "x4", "x5"]
LEGS5 = ["l1", "l2", "l3", "l4", "l5"]
ONE = [["x1", "x2"]]


def _crossing(on=("e1", "l3", "e4", "e7", "l5")):
    s = Session()
    nid = s.add_from_subdivision(CROSS, "drawn")["id"]
    for name in on:
        c = s.ws.nodes[nid].curve
        s.add_marking_on_edge(nid, next(e.id for e in c.edges.values() if e.name == name), "", "")
    return s, nid


def _at(view, name):
    return next(m["at"] for m in view["picture"]["markings"] if m["name"] == name)


def test_points_required_to_be_one_cut_both_sides_by_two():
    s, nid = _crossing()
    out = s.moduli_check(nid, MARKS5, LEGS5, ONE)
    # 8 ends, 5 markings: 12 = 2*5 + 2; on the cycle x1 = x2, 10 = 2*4 + 2
    assert out["ok"] and out["dim"] == 12 and out["target"] == 12
    assert out["cycle_dim"] == 10 and out["cycle_target"] == 10
    assert out["full"] and out["multiplicity"] == 1
    st = s.moduli_start(nid, MARKS5, LEGS5, ONE)
    assert st["points"]["x1"] == st["points"]["x2"]
    v = s.moduli_view(nid, MARKS5, LEGS5, st["points"], st["m"], 30, ONE)
    assert v["full"] and all(Fraction(x) > 0 for x in v["lengths"].values())
    # x1 and x2 lie on different edges of the abstract curve, at one point of the plane
    assert _at(v, "x1") == pytest.approx(_at(v, "x2"))
    assert v["region"]["walls"]


def test_markings_whose_images_never_meet():
    # x1 inside l1 and x2 inside l2: two ends leaving one vertex never meet again
    s, nid = _crossing(("l1", "l2", "e4", "e7", "l5"))
    t = moduli.TypeMap(nid, "", s.ws.nodes[nid].curve, MARKS5, LEGS5, ONE)
    assert not t.meets and not t.full
    why = s.moduli_check(nid, MARKS5, LEGS5, ONE)["why"]
    assert why["kind"] == "apart" and "never one point" in why["reason"]
    # the same markings, not linked, are fine
    assert moduli.TypeMap(nid, "", s.ws.nodes[nid].curve, MARKS5, LEGS5).meets


def test_the_walk_stays_on_the_cycle():
    s, nid = _crossing()
    st = s.moduli_start(nid, MARKS5, LEGS5, ONE)
    v = s.moduli_view(nid, MARKS5, LEGS5, st["points"], st["m"], 30, ONE)
    w = v["region"]["walls"][0]
    target = [str((Fraction(a) + Fraction(b)) / 2 * 2 - Fraction(c))
              for a, b, c in zip(w["from"], w["to"], v["coords"])]       # across the wall's middle
    out = s.moduli_move(nid, MARKS5, LEGS5, st["points"], v["coords"], target, ONE)
    assert out["wall"]
    wall = s.moduli_wall(nid, out["wall"]["edge"], MARKS5, LEGS5, ONE)
    entered = 0
    for r in wall["regenerations"]:
        if not r["full"]:
            assert r["why"]
            continue
        res = s.moduli_regenerate(wall["wall_id"], wall["vertex"], r["index"], MARKS5, LEGS5,
                                  st["points"], out["m"], 10, ONE)
        if not res.get("m"):
            continue
        entered += 1
        nv = s.moduli_view(res["id"], MARKS5, LEGS5, st["points"], res["m"], 30, ONE)
        assert all(Fraction(x) > 0 for x in nv["lengths"].values())
        assert _at(nv, "x1") == pytest.approx(_at(nv, "x2"))
    assert entered >= 1


def _one_vertex():
    """The square's curve with x1 and x2 on one vertex, x3 inside the end l1."""
    s = Session()
    nid = s.add_from_subdivision(SQUARE, "drawn")["id"]
    c = s.ws.nodes[nid].curve
    v = next(v for v in c.vertices if c.valence(v) >= 3)
    s.moduli_add_marking(nid, v)                                              # x1 on a vertex
    for name in ("l3", "l1"):                                                 # x2, x3 inside ends
        c = s.ws.nodes[nid].curve
        s.add_marking_on_edge(nid, next(e.id for e in c.ends if e.name == name), "", "")
    by = lambda: {e.name: e for e in s.ws.nodes[nid].curve.markings}
    s.moduli_move_marking(nid, "x2", vertex=by()["x1"].tail)
    assert by()["x1"].tail == by()["x2"].tail
    s.ws.nodes[nid].curve.validate()
    return s, nid


def test_moving_a_marking_onto_another_markings_vertex():
    s, nid = _one_vertex()
    by = lambda: {e.name: e for e in s.ws.nodes[nid].curve.markings}
    assert by()["x1"].tail == by()["x2"].tail
    # a third does not fit (3 other edges), nor a second on a point inside an edge
    with pytest.raises(ValueError, match="can carry no more"):
        s.moduli_move_marking(nid, "x3", vertex=by()["x1"].tail)
    with pytest.raises(ValueError, match="room for one marking only"):
        s.moduli_move_marking(nid, "x1", vertex=by()["x3"].tail)


def test_markings_on_one_vertex_required_to_be_one_point():
    s, nid = _one_vertex()
    legs = ["l1", "l2", "l3", "l4", "x3"]
    out = s.moduli_check(nid, ["x1", "x2"], legs, ONE)
    # 4 ends, 3 markings: 6 = 2*2 + 2; the cycle x1 = x2: 4 = 2*1 + 2, and this
    # cell (two markings on one vertex) lies in it whole
    assert out["ok"] and out["cycle_dim"] == 4 and out["full"] and out["multiplicity"] == 1
    st = s.moduli_start(nid, ["x1", "x2"], legs, ONE)
    assert st["points"]["x1"] == st["points"]["x2"]
    v = s.moduli_view(nid, ["x1", "x2"], legs, st["points"], st["m"], 20, ONE)
    assert v["full"] and _at(v, "x1") == pytest.approx(_at(v, "x2"))
    # not required to be one point, the two evaluations are tied, and it says so
    why = s.moduli_check(nid, ["x1", "x2"], legs)["why"]
    assert why["kind"] == "lower" and "x1 and x2 sit on one vertex" in why["reason"]
