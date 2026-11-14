"""The map ev x ft to (R^2)^k x M_0,5: cones, preimages, regions, walls."""

import random
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
WEIGHTED = {"a": [-1, 0], "b": [0, -1], "c": [-1, -1], "d": [2, 2]}


@pytest.fixture(scope="module")
def line4():
    s = _library(LINE, ["x1", "x2", "x3", "x4"])
    cfg = {"group": s.moduli_groups()[0]["key"], "evaluated": ["x1", "x2"],
           "legs": ["a", "b", "d", "x3", "x4"]}
    return s, cfg


@pytest.fixture(scope="module")
def weighted():
    s = _library(WEIGHTED, ["x1", "x2", "x3"])
    cfg = {"group": s.moduli_groups()[0]["key"], "evaluated": ["x1", "x2"],
           "legs": ["a", "b", "c", "d", "x3"]}
    return s, cfg


def _random_points(rng, names):
    return {m: [str(Fraction(rng.randint(-60, 60), rng.choice([7, 11, 13]))),
                str(Fraction(rng.randint(-60, 60), rng.choice([3, 5, 17])))] for m in names}


def _generic(s, cfg, m):
    """No full-dimensional type has a zero length over the point."""
    st = s._moduli_setup(cfg)
    cone, L = moduli.parse_point(m)
    for t in st.maps:
        if t.cone == cone and t.full:
            status, z = t.solve_at(st.p, L)
            if status == "unique" and any(v == 0 for v in z[2:]):
                return False
    return True


def test_groups_and_the_dimension_check():
    s = _library(LINE, ["x1", "x2"])
    s.add_preset("line")                             # another moduli space: no markings
    groups = s.moduli_groups()
    assert len(groups) == 2
    g = next(g for g in groups if g["markings"] == ["x1", "x2"])
    assert g["dim"] == 4 and len(g["types"]) == 12   # 15 trees, 3 with x1, x2 together
    ok = s.moduli_check({"group": g["key"], "evaluated": ["x1"], "legs": ["a", "b", "d", "x1", "x2"]})
    assert ok["ok"] and ok["target_dim"] == 4
    bad = s.moduli_check({"group": g["key"], "evaluated": ["x1", "x2"], "legs": ["a", "b", "d", "x1", "x2"]})
    assert not bad["ok"] and "fewer" in bad["message"]
    with pytest.raises(ValueError):
        s.moduli_check({"group": g["key"], "evaluated": ["x1"], "legs": ["a", "b", "d", "x1"]})


def test_the_cone_of_a_type_and_its_lengths():
    s = _library(LINE, ["x1", "x2"])
    g = s.moduli_groups()[0]
    legs = ["a", "b", "d", "x1", "x2"]
    out = s.moduli_check({"group": g["key"], "evaluated": ["x1"], "legs": legs})
    for t in out["types"]:
        # a five-leg caterpillar: the two vertices with two legs are its splits
        c = s.ws.nodes[t["id"]].curve
        cherries = [[legs.index(e.name) for e in c.incident(v) if e.name in legs] for v in c.vertices]
        want = sorted(sorted(ch) for ch in cherries if len(ch) == 2)
        assert t["cone"] == want and t["full"] and t["multiplicity"] == 1


def test_preimages_have_positive_lengths_and_pass_through_the_points(line4):
    s, cfg = line4
    rng = random.Random(7)
    seen = 0
    for _ in range(40):
        cfg = dict(cfg, points=_random_points(rng, ["x1", "x2"]))
        cone = rng.choice([c for c in moduli.CONES if (3, 4) not in c])
        m = moduli.point_json(cone, [Fraction(rng.randint(1, 90), 7), Fraction(rng.randint(1, 90), 11)])
        r = s.moduli_preimage(cfg, m)
        for p in r["preimages"]:
            assert all(Fraction(l["value"]) > 0 for l in p["lengths"])
            at = {mk["name"]: mk["at"] for mk in p["picture"]["markings"]}
            for name in ("x1", "x2"):
                want = [float(Fraction(v)) for v in cfg["points"][name]]
                assert at[name] == pytest.approx(want)
            seen += 1
    assert seen > 20


def test_the_weighted_count_is_the_same_at_generic_points(line4, weighted):
    rng = random.Random(11)
    for (s, cfg), degree, skip in [(line4, 1, (3, 4)), (weighted, 3, None)]:
        checked = 0
        for cone in moduli.CONES:
            if skip in cone:              # needs x3, x4 on a contracted edge: not in the library
                continue
            for _ in range(4):
                c = dict(cfg, points=_random_points(rng, cfg["evaluated"]))
                m = moduli.point_json(cone, [Fraction(rng.randint(1, 90), 13), Fraction(rng.randint(1, 90), 17)])
                if not _generic(s, c, m):
                    continue
                assert s.moduli_preimage(c, m)["count"] == degree
                checked += 1
        assert checked > 30


def test_multiplicity_is_the_determinant_of_ev_and_ft(weighted):
    s, cfg = weighted
    st = s._moduli_setup(dict(cfg, points={"x1": [0, 0], "x2": [0, 0]}))
    mults = {int(t.det) for t in st.maps if t.full}
    assert mults == {1, 2}
    for t in st.maps:
        if t.full:
            assert len(t.matrix) == t.n == 6     # 2 points and 2 lengths; 4 bounded edges + 2
            assert abs(moduli.determinant(t.matrix)) == t.det


def test_regions_are_where_the_type_has_a_preimage(weighted):
    s, cfg = weighted
    rng = random.Random(3)
    cfg = dict(cfg, points=_random_points(rng, cfg["evaluated"]))
    st = s._moduli_setup(cfg)
    cone = ((0, 1), (2, 3))
    regs = s.moduli_regions(cfg, [[[0, 1], [2, 3]]], 40)[0]["regions"]
    assert regs
    by_type = {r["type"]: r for r in regs}
    for _ in range(200):
        a = Fraction(rng.randint(1, 390), 10)
        b = Fraction(rng.randint(1, 399 - int(a * 10)), 10)      # a + b < 40
        pre = s.moduli_preimage(cfg, moduli.point_json(cone, [a, b]))
        have = {p["type"] for p in pre["preimages"] if p["full"]}
        for t in st.full_maps(cone):
            poly, _ = moduli.region(t, st.p, Fraction(40))
            inside = poly is not None and _strictly_inside((a, b), [q for q, _ in poly])
            on_edge = poly is not None and _on_boundary((a, b), [q for q, _ in poly])
            if on_edge:
                continue
            assert (t.id in have) == inside
            assert (t.id in by_type) == (poly is not None)


def _strictly_inside(q, poly):
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (x2 - x1) * (q[1] - y1) - (y2 - y1) * (q[0] - x1) <= 0:
            return False
    return True


def _on_boundary(q, poly):
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (x2 - x1) * (q[1] - y1) - (y2 - y1) * (q[0] - x1) == 0:
            return True
    return False


def test_overview_counts_match_preimages(weighted):
    s, cfg = weighted
    rng = random.Random(5)
    cfg = dict(cfg, points=_random_points(rng, cfg["evaluated"]))
    size = Fraction(9)
    for row in s.moduli_overview(cfg, size):
        cone = tuple(tuple(c) for c in row["cone"])
        br = row["breaks"]
        for (u, v), n in zip(zip(br, br[1:]), row["counts"]):
            t = Fraction((u + v) / 2).limit_denominator(10 ** 6)
            m = moduli.point_json(cone, [size * (1 - t), size * t])
            assert s.moduli_preimage(cfg, m)["count"] == n


def test_a_contracted_type_appears_only_on_its_wall(line4):
    s, cfg = line4
    rng = random.Random(2)
    cfg = dict(cfg, points=_random_points(rng, cfg["evaluated"]))
    found = [(c["cone"], r) for c in s.moduli_regions(cfg, [[list(a), list(b)] for a, b in moduli.CONES], 60)
             for r in c["regions"] if r["walls"]]
    cone, reg = found[0]
    wall = reg["walls"][0]
    contracted = s.contract(reg["type"], wall["edge"], name="on the wall")
    mid = [(wall["from"][i] + wall["to"][i]) / 2 for i in range(2)]
    m = s.moduli_on_wall(cfg, cone, reg["type"], wall["edge"], mid[0], mid[1])
    pre = s.moduli_preimage(cfg, m)
    names = {p["name"]: p for p in pre["preimages"]}
    assert "on the wall" in names and names["on the wall"]["on_wall"]
    assert reg["name"] not in names          # its length l_e is 0 there, not positive
    # off the wall, the contracted type is never in the preimage
    off = moduli.point_json(tuple(tuple(c) for c in cone), [Fraction(mid[0]).limit_denominator(97) + Fraction(1, 101),
                                               Fraction(mid[1]).limit_denominator(89)])
    assert "on the wall" not in {p["name"] for p in s.moduli_preimage(cfg, off)["preimages"]}
    s.delete(contracted["id"])


def test_initial_point_has_a_preimage(weighted):
    s, cfg = weighted
    ini = s.moduli_initial(cfg)
    pre = s.moduli_preimage(dict(cfg, points=ini["points"]), ini["m"])
    assert pre["count"] >= 1


def test_points_of_m05_are_parsed_strictly():
    assert moduli.parse_point({"splits": [[1, 0], [3, 2]], "lengths": ["2", "1/2"]}) == \
        (((0, 1), (2, 3)), [Fraction(2), Fraction(1, 2)])
    # a zero length is the ray of the other split
    assert moduli.parse_point({"splits": [[0, 1], [2, 3]], "lengths": ["0", "1"]}) == (((2, 3),), [1])
    with pytest.raises(ValueError):
        moduli.parse_point({"splits": [[0, 1], [1, 2]], "lengths": ["1", "1"]})
    assert len(moduli.CONES) == 15 and len(moduli.RAYS) == 10


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
    s, cfg = _walled()
    t = s.moduli_check(cfg)["types"][0]
    assert t["cell_dim"] == 12 and not t["full"] and t["multiplicity"] == 0
    assert t["why"]["kind"] == "fixed"
    assert t["why"]["relation"] == "{x1,x2} = y(x1) − y(x3)"
    # other reasons, in words
    s2 = _library(LINE, ["x1", "x2"])
    cfg2 = {"group": s2.moduli_groups()[0]["key"], "evaluated": ["x1"], "legs": ["a", "b", "d", "x1", "x2"]}
    assert all(t["why"] is None for t in s2.moduli_check(cfg2)["types"])
    contracted = s2.contract(s2.moduli_check(cfg2)["types"][0]["id"], "e1")
    why = next(t["why"] for t in s2.moduli_check(cfg2)["types"] if t["id"] == contracted["id"])
    assert why["kind"] == "lower"


def test_the_image_of_a_type_whose_lengths_the_points_fix():
    s, cfg = _walled()
    ini = s.moduli_initial(cfg)                       # no full type: starts on the image
    assert ini["m"] and ini["points"]
    cfg = dict(cfg, points=ini["points"])
    imgs = s.moduli_images(cfg, 40)
    assert len(imgs) == 1 and imgs[0]["kind"] == "segment"
    (a1, b1), (a2, b2) = [[Fraction(x) for x in q] for q in imgs[0]["exact"]]
    y = {m: Fraction(v[1]) for m, v in cfg["points"].items()}
    assert a1 == a2 == y["x1"] - y["x3"]              # the {x1,x2} length, fixed
    assert b1 != b2
    # a point on it has a whole family of curves over it: one is shown
    for frac in (Fraction(1, 10), Fraction(1, 2), Fraction(9, 10)):
        m = s.moduli_on_image(cfg, imgs[0]["type"], 40, str(frac))
        pre = s.moduli_preimage(cfg, m)
        assert [p["fibre"] for p in pre["preimages"]] == [1]
        p = pre["preimages"][0]
        assert all(Fraction(l["value"]) > 0 for l in p["lengths"])
        at = {mk["name"]: mk["at"] for mk in p["picture"]["markings"]}
        for name, (x, yy) in cfg["points"].items():
            assert at[name] == pytest.approx([float(Fraction(x)), float(Fraction(yy))])
        assert pre["count"] == 0                      # not counted: not a finite fibre
    # beyond the segment's ends, and off its line, there is nothing
    off = moduli.point_json(((0, 1), (3, 4)), [a1 + Fraction(1, 7), (b1 + b2) / 2])
    assert s.moduli_preimage(cfg, off)["preimages"] == []
    past = moduli.point_json(((0, 1), (3, 4)), [a1, max(b1, b2) + 1])
    assert s.moduli_preimage(cfg, past)["preimages"] == []


def test_full_dimensional_types_have_no_image_entry(weighted):
    s, cfg = weighted
    rng = random.Random(9)
    cfg = dict(cfg, points=_random_points(rng, cfg["evaluated"]))
    ids = {t["id"] for t in s.moduli_check(cfg)["types"] if t["full"]}
    assert not ids & {i["type"] for i in s.moduli_images(cfg, 30)}


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
    out = s.moduli_check({"group": s.moduli_groups()[0]["key"], "evaluated": marks, "legs": marks})
    assert out["ok"] and len(out["types"]) == 1
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


def test_a_new_slope_moves_the_type_to_another_group_and_can_free_it():
    s, cfg = _walled()
    nid = next(iter(s.ws.nodes))
    s.edit_slopes(nid, "l2", [-1, 1], "l3")       # x1's horizontal end now goes up-left
    groups = s.moduli_groups()
    assert len(groups) == 1 and groups[0]["key"] != cfg["group"]
    out = s.moduli_check(dict(cfg, group=groups[0]["key"]))
    t = out["types"][0]
    # c0 is no longer pinned at the height of x1, so nothing fixes {x1,x2}
    assert out["ok"] and t["full"] and t["multiplicity"] > 0 and t["why"] is None


_BIG = {}


def _one_type(s, with_walls=False):
    """A library holding one full-dimensional type of the weighted degree
    (whose region at its starting point has walls, if asked)."""
    if "lib" not in _BIG:
        _BIG["lib"] = _library(WEIGHTED, ["x1", "x2", "x3"])
    big = _BIG["lib"]
    cfg = {"group": big.moduli_groups()[0]["key"], "evaluated": ["x1", "x2"], "legs": ["a", "b", "c", "d", "x3"]}
    for t in big.moduli_check(cfg)["types"]:
        if not t["full"]:
            continue
        s.load(big.export_subset([t["id"]]))
        nid = next(iter(s.ws.nodes))
        one = dict(cfg, types=[nid])
        if not with_walls:
            return nid, one
        ini = s.moduli_initial(one)
        regs = s.moduli_regions(dict(one, points=ini["points"]), [ini["m"]["splits"]], 200)[0]["regions"]
        if regs and regs[0]["walls"]:
            return nid, one
    raise AssertionError("no type with walls")


def test_crossing_a_wall_adds_the_types_on_the_other_side():
    s = Session()
    nid, cfg = _one_type(s, with_walls=True)
    ini = s.moduli_initial(cfg)
    cfg = dict(cfg, points=ini["points"])
    cone = tuple(tuple(x) for x in ini["m"]["splits"])
    reg = s.moduli_regions(cfg, [list(map(list, cone))], 200)[0]["regions"][0]
    wall = reg["walls"][0]
    # from inside the region straight across that wall
    inside = [sum(q[i] for q in reg["polygon"]) / len(reg["polygon"]) for i in range(2)]
    mid = [(wall["from"][i] + wall["to"][i]) / 2 for i in range(2)]
    out = [mid[i] + (mid[i] - inside[i]) * 0.05 for i in range(2)]
    q = lambda v: moduli.point_json(cone, [Fraction(x).limit_denominator(10 ** 6) for x in v])
    m0, m1 = q(inside), q(out)
    assert [p["type"] for p in s.moduli_preimage(cfg, m0)["preimages"]] == [nid]
    assert s.moduli_preimage(cfg, m1)["preimages"] == []          # only the one type so far
    res = s.moduli_cross(cfg, nid, cfg["points"], m0, m1)
    assert res["edge"] == wall["edge_name"]
    assert len(s.ws.nodes) == 1 + len(res["added"]) and len(res["types"]) >= 2
    # the type on the wall has a vertex of valence 4, the others are full and new
    keys = {moduli.type_key(s.ws.nodes[i].curve) for i in res["types"]}
    assert moduli.type_key(s.ws.nodes[nid].curve) not in keys and len(keys) == len(res["types"])
    wall_type = s.ws.nodes[res["wall"]].curve
    assert max(wall_type.valence(v) for v in wall_type.vertices) == 4
    # with them, the other side has curves again, with the same weighted count
    cfg2 = dict(cfg, types=[nid] + res["types"])
    assert s.moduli_preimage(cfg2, m1)["count"] == s.moduli_preimage(cfg2, m0)["count"]
    assert s.moduli_preimage(cfg2, m1)["count"] > 0
    # crossing again reuses them
    again = s.moduli_cross(cfg, nid, cfg["points"], m0, m1)
    assert again["added"] == [] and sorted(again["types"]) == sorted(res["types"])
    # staying inside crosses nothing
    assert s.moduli_cross(cfg, nid, cfg["points"], m0, q([inside[0] * 1.01, inside[1]]))["edge"] is None


def test_points_through_a_type_over_a_given_point():
    s = Session()
    nid, cfg = _one_type(s)
    ini = s.moduli_initial(cfg)
    pts = s.moduli_points_through(cfg, nid, ini["m"])["points"]
    assert pts and set(pts) == {"x1", "x2"}
    pre = s.moduli_preimage(dict(cfg, points=pts), ini["m"])
    assert [p["type"] for p in pre["preimages"]] == [nid]
    # over a point of another cone the type has no curve
    other = next(c for c in moduli.CONES if c != tuple(tuple(x) for x in ini["m"]["splits"]))
    assert s.moduli_points_through(cfg, nid, moduli.point_json(other, [1, 1]))["points"] is None
