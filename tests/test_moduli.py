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
