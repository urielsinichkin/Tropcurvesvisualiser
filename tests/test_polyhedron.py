"""The polyhedron of curves of one type through point and line constraints."""

from fractions import Fraction

import pytest

from tropcurves import polyhedron
from tropcurves.api import Session

CONIC = [[[0, 0], [1, 0], [0, 1]], [[1, 0], [2, 0], [1, 1]], [[0, 1], [1, 1], [0, 2]],
         [[1, 0], [1, 1], [0, 1]]]


def _conic():
    """A conic with markings x1, x2, x3 inside the ends l1, l3, l5."""
    s = Session()
    nid = s.add_from_subdivision(CONIC, "conic")["id"]
    for name in ("l1", "l3", "l5"):
        c = s.ws.nodes[nid].curve
        s.add_marking_on_edge(nid, next(e.id for e in c.edges.values() if e.name == name), "", "")
    z = s.poly_start(nid)["z"]
    return s, nid, z, s.poly_values(nid, z)


def _two_dim():
    s, nid, z, vals = _conic()
    pts = {"x1": vals["points"]["x1"], "x2": vals["points"]["x2"]}
    lines = {"l2": vals["lines"]["l2"], "l4": vals["lines"]["l4"]}
    return s, nid, pts, lines, s.poly_fit(nid, pts, lines, z)["z"]


def test_linear_programs():
    assert polyhedron.lp_min([1, 1], [[1, 1]], [2])[0] == "optimal"
    assert polyhedron.lp_min([-1, 0], [[1, -1]], [0])[0] == "unbounded"
    assert polyhedron.lp_min([0, 0], [[1, 1]], [-1])[0] == "infeasible"
    st, x = polyhedron.lp_min([1, 2, 0], [[1, 1, -1], [0, 1, 1]], [1, 3])
    assert st == "optimal" and x[0] + x[1] - x[2] == 1 and x[1] + x[2] == 3 and min(x) >= 0


def test_each_point_cuts_two_and_each_line_one():
    s, nid, z, vals = _conic()
    # 6 ends, 3 markings: 6 bounded edges, a cell of dimension 8
    assert s.poly_fit(nid, {}, {}, z)["dim"] == 8
    out = s.poly_fit(nid, {"x1": vals["points"]["x1"]}, {"l2": vals["lines"]["l2"]}, z)
    assert out["feasible"] and out["precise"] and out["dim"] == 5
    # the curve found passes through the constraints
    cell = polyhedron.Cell(s.ws.nodes[nid].curve, {"x1": vals["points"]["x1"]}, {"l2": vals["lines"]["l2"]})
    zz = [Fraction(x) for x in out["z"]]
    assert cell.satisfies(zz) and all(x > 0 for x in cell.lengths(zz).values())


def test_constraints_no_curve_of_the_type_meets():
    s, nid, z, vals = _conic()
    x, y = (Fraction(a) for a in vals["points"]["x1"])
    # x1 sits on the end l1, pointing down from its vertex: put it far above
    pts = {"x1": vals["points"]["x1"], "x2": vals["points"]["x2"], "x3": vals["points"]["x3"]}
    pts["x1"] = [str(x), str(y + 100)]
    out = s.poly_fit(nid, pts, {}, z)
    assert not out["precise"]


def test_a_two_dimensional_polyhedron_is_charted_by_lengths():
    s, nid, pts, lines, z = _two_dim()
    v = s.poly_view(nid, pts, lines, z)
    assert v["dim"] == 2 and v["satisfied"]
    ch = v["chart"]
    assert all(a["length"] for a in ch["axes"])
    assert ch["region"]["walls"]
    # the point lies in the box shown
    for (lo, hi), w in zip(ch["box"], ch["coords"]):
        assert Fraction(lo) <= Fraction(w) <= Fraction(hi)


def test_moving_stops_at_a_degeneration_and_goes_on():
    s, nid, pts, lines, z = _two_dim()
    ch = s.poly_view(nid, pts, lines, z)["chart"]
    w = ch["region"]["walls"][0]
    mid = [Fraction((w["from"][i] + w["to"][i]) / 2).limit_denominator(1000) for i in range(2)]
    far = [str(2 * mid[i] - Fraction(ch["coords"][i])) for i in range(2)]
    mv = s.poly_move(nid, pts, lines, z, far)
    assert mv["wall"]
    cell = polyhedron.Cell(s.ws.nodes[nid].curve, pts, lines)
    zz = [Fraction(x) for x in mv["z"]]
    assert cell.satisfies(zz) and cell.lengths(zz)[mv["wall"]["edge"]] == 0
    wall = s.poly_wall(nid, mv["wall"]["edge"], pts, lines, mv["z"])
    regs = wall["regenerations"]
    assert sum(r["back"] for r in regs) == 1
    went = 0
    for r in regs:
        if not r["enter"]:
            assert r["why"]
            continue
        g = s.poly_regenerate(wall["wall_id"], wall["vertex"], r["index"], pts, lines, wall["z"])
        nv = s.poly_view(g["id"], pts, lines, g["z"])
        assert nv["satisfied"] and all(Fraction(x) > 0 for x in nv["lengths"].values())
        went += 1
    assert went >= 2


def test_a_direction_is_projected_to_the_polyhedron():
    s, nid, z, vals = _conic()
    pts = {"x1": vals["points"]["x1"], "x2": vals["points"]["x2"]}
    z = s.poly_fit(nid, pts, {}, z)["z"]
    c = s.ws.nodes[nid].curve
    e = c.bounded[0].id
    d = s.poly_direction(nid, pts, {}, z, {e: 1})
    assert d["moves"]
    cell = polyhedron.Cell(c, pts, {})
    v = [Fraction(x) for x in d["v"]]
    assert all(cell.dot(r, v) == 0 for r in cell.C)               # along the polyhedron
    assert v[cell.index[e]] > 0                                  # still lengthens the edge
    if d["t_max"] is not None:
        out = s.poly_at(nid, pts, {}, z, d["v"], d["t_max"])
        assert out["wall"] and cell.satisfies([Fraction(x) for x in out["z"]])
    half = s.poly_at(nid, pts, {}, z, d["v"], "1/100")
    assert half["wall"] is None


def test_values_give_the_constraints_the_curve_satisfies():
    s, nid, z, vals = _conic()
    cell = polyhedron.Cell(s.ws.nodes[nid].curve, vals["points"], vals["lines"])
    assert cell.satisfies([Fraction(x) for x in z])
