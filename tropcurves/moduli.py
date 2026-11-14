"""The map ev x ft : M_{0,n}(R^2, Delta) -> (R^2)^k x M_{0,5}, cell by cell.

A combinatorial type's cell has coordinates ``z = (x_0, y_0, l_e for every
bounded edge e)`` (see :mod:`evaluation`; ``l_e`` is the length of the
parametrizing edge, which the curve stretches by its direction vector, weight
included). On the cell both maps are linear:

* ``ev``: the images ``(x, y)`` of ``k`` chosen markings, rows as in
  :func:`evaluation.row_of`;
* ``ft``: the tree spanned by five chosen legs (ends or markings), stabilized.
  Every bounded edge splits the five legs in two; a split with two legs on one
  side and three on the other is one of the ten rays of M_{0,5}, named by its
  two-element side. The splits of one tree are pairwise compatible (their
  two-element sides are disjoint), so a tree lies in a cone spanned by at most
  two rays -- one of the fifteen two-dimensional cones, a ray, or the apex --
  and the length along each ray is the sum of the ``l_e`` inducing that split.

A type is *full-dimensional* when the map is square and invertible on its cell
(its two splits included). Then for fixed points ``p`` the preimage of
``(p, a, b)`` in the cone ``{S1, S2}`` is ``z = A^{-1} (p, a, b)``, affine in
``(a, b)``; the type has a preimage exactly where every ``l_e`` is positive --
a convex region of the cone, whose sides on the lines ``l_e = 0`` are the
*walls*. A type of lower dimension can only have a preimage on a wall.

Everything is exact (``Fraction``); floats only come out for drawing.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .curve import Curve, EdgeKind
from .evaluation import _bounded_by_name, natural_key, row_of
from .layout import embed
from .operations import contract_edge, resolutions, apply_resolution

Split = Tuple[int, int]           # the two-element side, as indices into the legs
Cone = Tuple[Split, ...]          # sorted; 0, 1 or 2 splits

RAYS: List[Split] = list(combinations(range(5), 2))
CONES: List[Tuple[Split, Split]] = [(s, t) for s, t in combinations(RAYS, 2) if not set(s) & set(t)]


def compatible(s: Split, t: Split) -> bool:
    return not set(s) & set(t)


# --- grouping types by their degree and markings --------------------------
def signature(curve: Curve) -> str:
    """Types sharing ends (by name and direction) and markings (by name) are
    points of the same moduli space."""
    ends = sorted(f"{e.name}:{e.vec.x},{e.vec.y}" for e in curve.ends)
    marks = sorted(m.name for m in curve.markings)
    return "ends " + " ".join(ends) + " | markings " + " ".join(marks)


def group_info(curve: Curve) -> Dict[str, Any]:
    ends = sorted(curve.ends, key=lambda e: natural_key(e.name))
    marks = sorted(curve.markings, key=lambda m: natural_key(m.name))
    return {
        "ends": [{"name": e.name, "vec": e.vec.to_list()} for e in ends],
        "markings": [m.name for m in marks],
        # dim M_{0,n}(R^2, Delta) = |Delta| + n - 3 + 2
        "dim": len(ends) + len(marks) - 1,
    }


# --- exact linear algebra ---------------------------------------------------
def _rref(rows: List[List[Fraction]], ncols: int):
    """Reduced row echelon form in place; returns the pivot columns."""
    pivots: List[int] = []
    r = 0
    for c in range(ncols):
        p = next((i for i in range(r, len(rows)) if rows[i][c] != 0), None)
        if p is None:
            continue
        rows[r], rows[p] = rows[p], rows[r]
        inv = 1 / rows[r][c]
        rows[r] = [x * inv for x in rows[r]]
        for i in range(len(rows)):
            if i != r and rows[i][c] != 0:
                f = rows[i][c]
                rows[i] = [x - f * y for x, y in zip(rows[i], rows[r])]
        pivots.append(c)
        r += 1
        if r == len(rows):
            break
    return pivots


def solve(A: List[List[int]], b: List[Fraction]):
    """``("unique", z)``, ``("none", None)`` or ``("free", None)``."""
    n = len(A[0]) if A else 0
    rows = [[Fraction(x) for x in row] + [Fraction(v)] for row, v in zip(A, b)]
    piv = _rref(rows, n + 1)
    if n in piv:
        return "none", None
    if len(piv) < n:
        return "free", None
    z = [Fraction(0)] * n
    for i, c in enumerate(piv):
        z[c] = rows[i][n]
    return "unique", z


def inverse(A: List[List[int]]) -> Optional[List[List[Fraction]]]:
    n = len(A)
    if any(len(r) != n for r in A):
        return None
    rows = [[Fraction(x) for x in row] + [Fraction(int(i == j)) for j in range(n)]
            for i, row in enumerate(A)]
    piv = _rref(rows, n)
    if piv != list(range(n)):
        return None
    return [row[n:] for row in rows]


def determinant(A: List[List[int]]) -> Fraction:
    n = len(A)
    m = [[Fraction(x) for x in row] for row in A]
    det = Fraction(1)
    for c in range(n):
        p = next((i for i in range(c, n) if m[i][c] != 0), None)
        if p is None:
            return Fraction(0)
        if p != c:
            m[c], m[p] = m[p], m[c]
            det = -det
        det *= m[c][c]
        for i in range(c + 1, n):
            f = m[i][c] / m[c][c]
            if f:
                m[i] = [x - f * y for x, y in zip(m[i], m[c])]
    return det


# --- one type under the map -------------------------------------------------
class TypeMap:
    """The map ev x ft on one type's cell."""

    def __init__(self, node_id: str, name: str, curve: Curve,
                 evaluated: Sequence[str], legs: Sequence[str]):
        self.id, self.name, self.curve = node_id, name, curve
        self.root = curve.vertices[0]
        self.bounded = _bounded_by_name(curve)
        self.index = {e.id: i + 2 for i, e in enumerate(self.bounded)}
        self.n = len(self.bounded) + 2
        by_name = {e.name: e for e in curve.edges.values() if e.kind is not EdgeKind.BOUNDED}
        rows: List[List[int]] = []
        for m in evaluated:
            e = by_name.get(m)
            if e is None or e.kind is not EdgeKind.MARKING:
                raise ValueError(f"{name}: no marking named {m!r}")
            for kind in ("x", "y"):
                rows.append(row_of(curve, self.root, self.index, {"kind": kind, "marking": e.id}))
        self.ev_rows = rows
        leg_edges = []
        for l in legs:
            if l not in by_name:
                raise ValueError(f"{name}: no end or marking named {l!r}")
            leg_edges.append(by_name[l])
        self.splits: Dict[Split, List[int]] = {}
        for e in self.bounded:
            side = self._tail_side(e)
            inside = tuple(i for i, le in enumerate(leg_edges) if le.tail in side)
            if len(inside) == 3:
                inside = tuple(i for i in range(5) if i not in inside)
            if len(inside) != 2:
                continue
            row = self.splits.setdefault(inside, [0] * self.n)
            row[self.index[e.id]] += 1
        self.cone: Cone = tuple(sorted(self.splits))
        self.matrix = self.ev_rows + [self.splits[s] for s in self.cone]
        square = len(self.matrix) == self.n
        self.det = abs(determinant(self.matrix)) if square else None
        self.full = bool(square and self.det and len(self.cone) == 2)
        self.inv = inverse(self.matrix) if self.full else None

    def _tail_side(self, e) -> set:
        """Vertices on the tail's side of the bounded edge ``e``."""
        seen = {e.tail}
        stack = [e.tail]
        while stack:
            v = stack.pop()
            for f in self.curve.incident(v):
                if f.kind is not EdgeKind.BOUNDED or f.id == e.id:
                    continue
                w = f.other(v)
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        return seen

    @property
    def cell_dim(self) -> int:
        return self.n

    # z = A^{-1} (p, a, b): each length as c + alpha a + beta b
    def length_forms(self, p: List[Fraction]) -> Dict[str, Tuple[Fraction, Fraction, Fraction]]:
        k2 = len(p)
        out = {}
        for e in self.bounded:
            row = self.inv[self.index[e.id]]
            c = sum((row[j] * p[j] for j in range(k2)), Fraction(0))
            out[e.id] = (c, row[k2], row[k2 + 1])
        return out

    def solve_at(self, p: List[Fraction], lengths: List[Fraction]):
        status, z = solve(self.matrix, list(p) + list(lengths))
        return status, z


# --- configuration ----------------------------------------------------------
class Setup:
    """The types of one group, k evaluated markings, five legs and the points."""

    def __init__(self, types: Sequence[Tuple[str, str, Curve]], evaluated: Sequence[str],
                 legs: Sequence[str], points: Dict[str, Sequence[Any]],
                 cache: Optional[dict] = None):
        if len(legs) != 5 or len(set(legs)) != 5:
            raise ValueError("choose exactly five different legs")
        if len(set(evaluated)) != len(evaluated):
            raise ValueError("an evaluated marking is listed twice")
        self.evaluated, self.legs = list(evaluated), list(legs)
        self.maps: List[TypeMap] = []
        for nid, name, curve in types:
            key = (nid, _curve_key(curve), tuple(evaluated), tuple(legs))
            tm = cache.get(key) if cache is not None else None
            if tm is None:
                tm = TypeMap(nid, name, curve, evaluated, legs)
                if cache is not None:
                    if len(cache) > 2000:
                        cache.clear()
                    cache[key] = tm
            tm.name = name
            self.maps.append(tm)
        self.p: List[Fraction] = []
        for m in self.evaluated:
            xy = points.get(m)
            if xy is None:
                raise ValueError(f"no point given for {m!r}")
            self.p += [Fraction(str(xy[0])), Fraction(str(xy[1]))]

    def full_maps(self, cone: Cone) -> List[TypeMap]:
        return [t for t in self.maps if t.full and t.cone == cone]


def _curve_key(c: Curve) -> tuple:
    return (tuple(c.vertices),
            tuple(sorted((e.id, e.kind.value, e.tail, e.head or "", e.vec.x, e.vec.y, e.name)
                         for e in c.edges.values())))


def check(curve_infos: Dict[str, Any], k: int) -> Dict[str, Any]:
    dim = curve_infos["dim"]
    target = 2 * k + 2
    ok = dim == target
    msg = ""
    if not ok:
        if dim > target:
            msg = (f"The moduli space has dimension {dim} but (R²)^{k} × M_0,5 has {target}: "
                   f"evaluate {(dim - target) / 2:g} more marking(s), or use types with fewer "
                   f"ends or markings.")
        else:
            msg = (f"The moduli space has dimension {dim} but (R²)^{k} × M_0,5 has {target}: "
                   f"evaluate fewer markings, or use types with more ends or markings.")
    return {"ok": ok, "dim": dim, "target_dim": target, "message": msg}


# --- points of M_{0,5} -----------------------------------------------------
def parse_point(m: Dict[str, Any]) -> Tuple[Cone, List[Fraction]]:
    pairs = []
    for s, l in zip(m.get("splits", []), m.get("lengths", [])):
        s = tuple(sorted(int(i) for i in s))
        L = Fraction(str(l))
        if L < 0:
            raise ValueError("lengths in M_0,5 are not negative")
        if L > 0:                      # a zero length puts the point on the other ray
            pairs.append((s, L))
    pairs.sort()
    if len(pairs) == 2 and not compatible(pairs[0][0], pairs[1][0]):
        raise ValueError("those two rays do not span a cone")
    return tuple(s for s, _ in pairs), [L for _, L in pairs]


def point_json(cone: Cone, lengths: Sequence[Fraction]) -> Dict[str, Any]:
    return {"splits": [list(s) for s in cone], "lengths": [str(x) for x in lengths]}


# --- preimages ---------------------------------------------------------------
def preimage(st: Setup, cone: Cone, lengths: List[Fraction], render) -> Dict[str, Any]:
    """The curves over ``(p, m)``: every type in the group whose cone is the
    cone of ``m`` and whose cell has a point with positive lengths over it."""
    found, notes = [], []
    for t in st.maps:
        if t.cone != cone:
            continue
        status, z = t.solve_at(st.p, lengths)
        if status == "none":
            continue
        fibre = 0
        if status == "free":
            # a whole family of curves over this point: show one of them
            rep_ = fibre_point(t, st.p, lengths)
            if rep_ is None:
                continue
            z, fibre = rep_
        ls = {e.id: z[t.index[e.id]] for e in t.bounded}
        if any(v <= 0 for v in ls.values()):
            continue
        found.append({
            "type": t.id, "name": t.name,
            "multiplicity": int(t.det) if t.full else None,
            "full": t.full,
            "on_wall": not t.full and t.n < len(t.ev_rows) + 2,
            "fibre": fibre,
            "lengths": [{"edge": e.id, "name": e.name, "value": str(ls[e.id]),
                         "float": float(ls[e.id])} for e in t.bounded],
            "picture": render(t, z),
        })
    found.sort(key=lambda f: natural_key(f["name"]))
    count = sum(f["multiplicity"] or 0 for f in found)
    return {"preimages": found, "count": count, "notes": notes,
            "on_wall": any(f["on_wall"] for f in found) or len(cone) < 2,
            "special": any(not f["full"] for f in found)}


def picture(st: Setup, t: TypeMap, z: List[Fraction], render_curve) -> Dict[str, Any]:
    """The curve at the coordinates z, placed in the plane (not just up to
    translation): drawn lengths are l_e times the weight."""
    lengths = {e.id: z[t.index[e.id]] * e.weight for e in t.bounded}
    data = render_curve(t.curve, lengths)
    pos = embed(t.curve, lengths)
    ox, oy = float(z[0] - pos[t.root][0]), float(z[1] - pos[t.root][1])
    for v in data["vertices"]:
        v["x"] += ox; v["y"] += oy
    for e in data["edges"]:
        e["from"] = [e["from"][0] + ox, e["from"][1] + oy]
        e["to"] = [e["to"][0] + ox, e["to"][1] + oy]
    for m in data["markings"]:
        m["at"] = [m["at"][0] + ox, m["at"][1] + oy]
    return data


# --- regions and walls in one cone ------------------------------------------
Pt = Tuple[Fraction, Fraction]


def _clip(poly: List[Tuple[Pt, str]], c: Fraction, al: Fraction, be: Fraction, label: str):
    """Keep the part of the polygon where c + al*a + be*b >= 0. Each vertex
    carries the label of the side leaving it."""
    if not poly:
        return poly
    f = lambda q: c + al * q[0] + be * q[1]
    out: List[Tuple[Pt, str]] = []
    n = len(poly)
    for i in range(n):
        (P, lab), (Q, _) = poly[i], poly[(i + 1) % n]
        fp, fq = f(P), f(Q)
        if fp >= 0:
            out.append((P, lab))
            if fq < 0:
                t = fp / (fp - fq)
                out.append(((P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])), label))
        elif fq >= 0:
            t = fp / (fp - fq)
            out.append(((P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])), lab))
    # drop repeated points
    clean: List[Tuple[Pt, str]] = []
    for q in out:
        if clean and clean[-1][0] == q[0]:
            clean[-1] = (clean[-1][0], q[1])
            continue
        clean.append(q)
    if len(clean) > 1 and clean[0][0] == clean[-1][0]:
        clean.pop()
    return clean


def _area2(poly) -> Fraction:
    s = Fraction(0)
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i][0], poly[(i + 1) % len(poly)][0]
        s += x1 * y2 - x2 * y1
    return s


def region(t: TypeMap, p: List[Fraction], R: Fraction):
    """The part of the cone up to size R (a + b <= R) where the type has a
    preimage, with the label of each side: an edge id (a wall), "a0" / "b0"
    (the cone's rays: a = 0 lies on the ray of the second split), or "box"."""
    forms = t.length_forms(p)
    Z = Fraction(0)
    poly = [((Z, Z), "b0"), ((R, Z), "box"), ((Z, R), "a0")]
    for eid, (c, al, be) in forms.items():
        poly = _clip(poly, c, al, be, eid)
        if len(poly) < 3:
            return None, forms
    if _area2(poly) <= 0:
        return None, forms
    return poly, forms


def regions(st: Setup, cone: Cone, R: Fraction) -> List[Dict[str, Any]]:
    out = []
    for t in st.full_maps(cone):
        poly, forms = region(t, st.p, R)
        if poly is None:
            continue
        names = {e.id: e.name for e in t.bounded}
        n = len(poly)
        walls = []
        for i, (P, lab) in enumerate(poly):
            if lab in names:
                Q = poly[(i + 1) % n][0]
                c, al, be = forms[lab]
                walls.append({"from": [float(P[0]), float(P[1])], "to": [float(Q[0]), float(Q[1])],
                              "edge": lab, "edge_name": names[lab],
                              "line": [str(c), str(al), str(be)]})
        out.append({
            "type": t.id, "name": t.name, "multiplicity": int(t.det),
            "polygon": [[float(P[0]), float(P[1])] for P, _ in poly],
            "sides": [lab for _, lab in poly],
            "unbounded": any(lab == "box" for _, lab in poly),
            "walls": walls,
        })
    return out


def overview(st: Setup, s: Fraction) -> List[Dict[str, Any]]:
    """For every cone, the weighted count along the segment a + b = s, as
    breakpoints t (a = s(1 - t), b = s t) and the count on each piece."""
    res = []
    for cone in CONES:
        spans = []
        for t in st.full_maps(cone):
            lo, hi = Fraction(0), Fraction(1)
            ok = True
            for c, al, be in t.length_forms(st.p).values():
                c0, c1 = c + al * s, s * (be - al)      # c0 + c1 t > 0
                if c1 == 0:
                    if c0 <= 0:
                        ok = False
                        break
                elif c1 > 0:
                    lo = max(lo, -c0 / c1)
                else:
                    hi = min(hi, -c0 / c1)
            if ok and lo < hi:
                spans.append((lo, hi, int(t.det), t.name))
        cuts = sorted({Fraction(0), Fraction(1)} | {x for sp in spans for x in sp[:2]})
        counts = []
        for u, v in zip(cuts, cuts[1:]):
            mid = (u + v) / 2
            counts.append(sum(w for lo, hi, w, _ in spans if lo < mid < hi))
        res.append({"cone": [list(cone[0]), list(cone[1])],
                    "breaks": [float(x) for x in cuts], "counts": counts})
    return res


def on_wall(st: Setup, cone: Cone, type_id: str, edge_id: str, a: Fraction, b: Fraction):
    """The point of the wall l_e = 0 of a type nearest to (a, b), exactly:
    one coordinate kept (to six decimals), the other solved for."""
    t = next((x for x in st.full_maps(cone) if x.id == type_id), None)
    if t is None:
        raise ValueError("no such region in this cone")
    c, al, be = t.length_forms(st.p)[edge_id]
    # orthogonal projection, then back onto the line exactly
    n2 = al * al + be * be
    d = (c + al * a + be * b) / n2
    a, b = a - d * al, b - d * be
    if abs(be) >= abs(al):
        a = Fraction(round(float(a), 6)).limit_denominator(10 ** 6)
        b = -(c + al * a) / be
    else:
        b = Fraction(round(float(b), 6)).limit_denominator(10 ** 6)
        a = -(c + be * b) / al
    return parse_point(point_json(cone, [max(a, Fraction(0)), max(b, Fraction(0))]))


def initial_point(st: Setup):
    """A point with a preimage: the image of a full-dimensional type at
    generic lengths, root at the origin."""
    for t in sorted(st.maps, key=lambda t: natural_key(t.name)):
        if not t.full:
            continue
        z = [Fraction(0), Fraction(0)] + [Fraction(1) + Fraction(i + 1, 7 + i) for i in range(t.n - 2)]
        img = [sum((Fraction(r[j]) * z[j] for j in range(t.n)), Fraction(0)) for r in t.matrix]
        k2 = len(t.ev_rows)
        points = {m: [str(img[2 * i]), str(img[2 * i + 1])] for i, m in enumerate(st.evaluated)}
        return points, point_json(t.cone, img[k2:])
    # none: start on the image of a type that is not full-dimensional, so
    # there is something to look at (that image is drawn on the chart)
    for t in sorted(st.maps, key=lambda t: natural_key(t.name)):
        if t.n < len(t.ev_rows) + 2:
            continue
        z = [Fraction(0), Fraction(0)] + [Fraction(1) + Fraction(i + 1, 7 + i) for i in range(t.n - 2)]
        img = [sum((Fraction(r[j]) * z[j] for j in range(t.n)), Fraction(0)) for r in t.matrix]
        k2 = len(t.ev_rows)
        points = {m: [str(img[2 * i]), str(img[2 * i + 1])] for i, m in enumerate(st.evaluated)}
        return points, point_json(t.cone, img[k2:])
    return None, None


# --- types that are not full-dimensional --------------------------------------
# Such a type has curves over a point only where its cell's image is; that
# image is lower-dimensional when the points tie its lengths in M_0,5 (or tie
# each other) on the cell. Here: why (a relation, in words) and where (the
# image of the fibre over the points, by exact Fourier-Motzkin elimination).

def _nullspace(A: List[List[Any]], ncols: int) -> List[List[Fraction]]:
    """A basis of {v : A v = 0}."""
    rows = [[Fraction(x) for x in r] for r in A]
    piv = _rref(rows, ncols) if rows else []
    out = []
    for f in (c for c in range(ncols) if c not in piv):
        v = [Fraction(0)] * ncols
        v[f] = Fraction(1)
        for i, c in enumerate(piv):
            v[c] = -rows[i][f]
        out.append(v)
    return out


def _transpose(A, nrows, ncols):
    return [[A[i][j] for i in range(nrows)] for j in range(ncols)]


def _affine_solutions(A: List[List[int]], b: List[Fraction], n: int):
    """All z with A z = b, as (z0, N): z = z0 + N w; None when there is none."""
    rows = [[Fraction(x) for x in r] + [Fraction(v)] for r, v in zip(A, b)]
    piv = _rref(rows, n + 1) if rows else []
    if n in piv:
        return None
    z0 = [Fraction(0)] * n
    for i, c in enumerate(piv):
        z0[c] = rows[i][n]
    N = []
    for f in (c for c in range(n) if c not in piv):
        v = [Fraction(0)] * n
        v[f] = Fraction(1)
        for i, c in enumerate(piv):
            v[c] = -rows[i][f]
        N.append(v)
    return z0, N


def _fmt(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _linear_text(terms: List[Tuple[Fraction, str]]) -> str:
    out = ""
    for c, name in terms:
        if c == 0:
            continue
        sign = "−" if c < 0 else "+"
        a = abs(c)
        body = name if a == 1 else f"{_fmt(a)}·{name}"
        out += (("−" if sign == "−" else "") + body) if not out else f" {sign} {body}"
    return out or "0"


def explain(t: TypeMap, evaluated: Sequence[str], legs: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Why a type is not full-dimensional, in words, with the relation that
    holds on its cell when there is one."""
    if t.full:
        return None
    k2 = len(t.ev_rows)
    target = k2 + 2
    pnames = [f"{c}({m})" for m in evaluated for c in "xy"]
    ray = lambda sp: "{" + legs[sp[0]] + "," + legs[sp[1]] + "}"
    if t.n < target:
        return {"kind": "lower",
                "reason": f"its cell has dimension {t.n}, less than {target}: it is a type of lower "
                          f"dimension, which only appears on walls (where an edge of a full-dimensional "
                          f"type shrinks to 0)"}
    # the points tied together: lambda . ev = 0
    if k2:
        lk = _nullspace(_transpose(t.ev_rows, k2, t.n), k2)
        if lk:
            lam = lk[0]
            rel = _linear_text([(lam[j], pnames[j]) for j in range(k2)])
            return {"kind": "points", "relation": rel + " = 0",
                    "reason": f"on this type the points are tied: {rel} = 0, so points in general "
                              f"position have no curve of this type"}
    if len(t.cone) < 2:
        return {"kind": "ray",
                "reason": "the five legs span a tree with " + ("one inner edge" if t.cone else "no inner edge")
                          + " on this type, so it maps to " + ("the ray " + ray(t.cone[0]) if t.cone else "the apex")
                          + " of M₀,₅, not to an open cone"}
    # the lengths in M_0,5 tied to the points: mu . ft = -lambda . ev
    S = t.ev_rows + [t.splits[sp] for sp in t.cone]
    for v in _nullspace(_transpose(S, len(S), t.n), len(S)):
        mu = v[k2:]
        if any(mu):
            lam = v[:k2]
            lead = next(x for x in mu if x)
            mu = [x / lead for x in mu]
            lam = [-x / lead for x in lam]
            lhs = _linear_text([(mu[i], ray(sp)) for i, sp in enumerate(t.cone)])
            rhs = _linear_text([(lam[j], pnames[j]) for j in range(k2)])
            return {"kind": "fixed", "relation": f"{lhs} = {rhs}",
                    "reason": f"the points fix {lhs} on this type: {lhs} = {rhs}, so it maps onto a line "
                              f"of M₀,₅ (the orange segment in the chart), not onto an open set"}
    return {"kind": "other", "reason": "the map is not invertible on its cell"}


# Fourier-Motzkin on constraints  const + coefs . v  (> 0 if strict, >= 0 if not)
Con = Tuple[Tuple[Fraction, ...], Fraction, bool]


def _norm(c: Con) -> Con:
    coefs, const, strict = c
    m = max([abs(x) for x in coefs] + [abs(const)])
    if m == 0:
        return c
    return tuple(x / m for x in coefs), const / m, strict


def _eliminate(cons: List[Con], v: int) -> Optional[List[Con]]:
    """Drop variable v; None when the system has no solution."""
    keep, pos, neg = [], [], []
    for c in cons:
        a = c[0][v]
        (pos if a > 0 else neg if a < 0 else keep).append(c)
    for P in pos:
        for Nn in neg:
            a, b = P[0][v], -Nn[0][v]
            coefs = tuple(b * x + a * y for x, y in zip(P[0], Nn[0]))
            keep.append((coefs, b * P[1] + a * Nn[1], P[2] or Nn[2]))
    out, seen = [], set()
    for c in keep:
        if not any(c[0]):
            if c[1] < 0 or (c[1] == 0 and c[2]):
                return None
            continue
        c = _norm(c)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _interior_point(cons: List[Con], nvars: int) -> Optional[List[Fraction]]:
    """A point satisfying all constraints, or None (eliminate, then choose
    each variable inside its bounds, last eliminated first)."""
    stages = [cons]
    cur = cons
    for v in range(nvars - 1, -1, -1):
        cur = _eliminate(cur, v)
        if cur is None:
            return None
        stages.append(cur)
    vals: List[Fraction] = []
    for v in range(nvars):
        lo = hi = None
        lo_s = hi_s = False
        for coefs, const, strict in stages[nvars - 1 - v]:
            a = coefs[v]
            if a == 0:
                continue
            rest = const + sum((coefs[u] * vals[u] for u in range(v)), Fraction(0))
            bound = -rest / a
            if a > 0 and (lo is None or bound > lo):
                lo = bound
            elif a < 0 and (hi is None or bound < hi):
                hi = bound
        if lo is not None and hi is not None:
            x = (lo + hi) / 2
        elif lo is not None:
            x = lo + 1
        elif hi is not None:
            x = hi - 1
        else:
            x = Fraction(0)
        vals.append(x)
    return vals


def _length_cons(t: TypeMap, z0, N) -> List[Con]:
    """l_e > 0 for every bounded edge, in the coordinates w of z = z0 + N w."""
    out = []
    for e in t.bounded:
        i = t.index[e.id]
        out.append((tuple(v[i] for v in N), z0[i], True))
    return out


def fibre_point(t: TypeMap, p: List[Fraction], lengths: List[Fraction]):
    """A curve of the type over (p, m) when the fibre is positive-dimensional:
    (z, dimension of the fibre), or None."""
    sol = _affine_solutions(t.matrix, list(p) + list(lengths), t.n)
    if sol is None:
        return None
    z0, N = sol
    w = _interior_point(_length_cons(t, z0, N), len(N))
    if w is None:
        return None
    z = [z0[i] + sum((N[j][i] * w[j] for j in range(len(N))), Fraction(0)) for i in range(t.n)]
    return z, len(N)


def image(t: TypeMap, p: List[Fraction], R: Fraction) -> Optional[Dict[str, Any]]:
    """The image in M_0,5 of the type's curves over the points: a point, a
    segment or a region of its cone (cut at a + b <= R), exactly; None if no
    curve of the type passes through the points."""
    sol = _affine_solutions(t.ev_rows, p, t.n) if t.ev_rows else (
        [Fraction(0)] * t.n, [[Fraction(int(i == j)) for i in range(t.n)] for j in range(t.n)])
    if sol is None:
        return None
    z0, N = sol
    s, d = len(t.cone), len(N)
    # variables: the cone coordinates y (s of them), then w (d)
    cons: List[Con] = [((Fraction(0),) * s + c[0], c[1], c[2]) for c in _length_cons(t, z0, N)]
    for i, sp in enumerate(t.cone):
        F = t.splits[sp]
        c0 = sum((F[j] * z0[j] for j in range(t.n)), Fraction(0))
        row = [-sum((F[j] * v[j] for j in range(t.n)), Fraction(0)) for v in N]
        y = [Fraction(int(u == i)) for u in range(s)]
        cons.append((tuple(y + row), -c0, False))
        cons.append((tuple([-x for x in y] + [-x for x in row]), c0, False))
    for v in range(s + d - 1, s - 1, -1):
        cons = _eliminate(cons, v)
        if cons is None:
            return None
    cons = [(c[0][:s], c[1], c[2]) for c in cons]
    # empty when the strict system has no solution
    test = [(c[0], c[1], c[2]) for c in cons]
    for v in range(s - 1, -1, -1):
        test = _eliminate(test, v)
        if test is None:
            return None
    Z = Fraction(0)
    if s == 0:
        return {"kind": "point", "points": []}
    if s == 1:
        lo, hi = Z, R
        for coefs, const, _ in cons:
            a = coefs[0]
            if a > 0:
                lo = max(lo, -const / a)
            elif a < 0:
                hi = min(hi, -const / a)
        if lo > hi:
            return None
        return {"kind": "point" if lo == hi else "segment", "points": [[lo], [hi]] if lo != hi else [[lo]]}
    poly = [((Z, Z), ""), ((R, Z), ""), ((Z, R), "")]
    for coefs, const, _ in cons:
        poly = _clip(poly, const, coefs[0], coefs[1], "")
        if not poly:
            return None
    pts = []
    for q, _ in poly:
        if q not in pts:
            pts.append(q)
    if len(pts) >= 3 and _area2([(q, "") for q in pts]) != 0:
        return {"kind": "region", "points": [list(q) for q in pts]}
    if len(pts) == 1:
        return {"kind": "point", "points": [list(pts[0])]}
    far = max(((a, b) for a in pts for b in pts), key=lambda ab: (ab[0][0] - ab[1][0]) ** 2 + (ab[0][1] - ab[1][1]) ** 2)
    return {"kind": "segment", "points": [list(far[0]), list(far[1])]}


def images(st: Setup, R: Fraction) -> List[Dict[str, Any]]:
    """Where the types that are not full-dimensional (but not of lower
    dimension: those live on walls, already drawn) have curves over the
    points."""
    out = []
    for t in st.maps:
        if t.full or t.n < len(t.ev_rows) + 2:
            continue
        img = image(t, st.p, R)
        if img is None:
            continue
        why = explain(t, st.evaluated, st.legs)
        out.append({"type": t.id, "name": t.name, "cone": [list(sp) for sp in t.cone],
                    "kind": img["kind"],
                    "points": [[float(x) for x in q] for q in img["points"]],
                    "exact": [[str(x) for x in q] for q in img["points"]],
                    "reason": why["reason"] if why else ""})
    return out


def on_image(st: Setup, type_id: str, R: Fraction, frac: Fraction):
    """The point at fraction ``frac`` along a type's image (a segment), exactly."""
    t = next((x for x in st.maps if x.id == type_id), None)
    if t is None:
        raise ValueError("no such type")
    img = image(t, st.p, R)
    if img is None:
        raise ValueError("that type has no curve through these points")
    pts = img["points"]
    if not pts:
        return (), []
    P = pts[0]
    Q = pts[-1] if img["kind"] == "segment" else P
    frac = min(max(frac, Fraction(0)), Fraction(1))
    q = [P[i] + frac * (Q[i] - P[i]) for i in range(len(P))]
    return parse_point(point_json(t.cone, q))


# --- crossing walls: the types on the other side --------------------------------
# A curve of a full-dimensional type leaves its region when some edge length
# reaches 0. There the edge contracts to a vertex of valence 4 (a type of
# lower dimension, on the wall), and the other ways of resolving that vertex
# are the types that carry on, on the other side. They are built with the main
# app's own operations (contract, resolve).

def type_key(curve: Curve) -> frozenset:
    """What makes two types the same, whatever their ids: for every bounded
    edge, the legs (by name) on one side of it and its direction, plus the
    ends' directions. A tree with named leaves is determined by its splits."""
    legs = {e.id: e.name for e in curve.edges.values() if e.kind is not EdgeKind.BOUNDED}
    names = sorted(legs.values())
    anchor = names[0] if names else ""
    out = {("end", e.name, e.vec.x, e.vec.y) for e in curve.ends}
    for e in curve.bounded:
        side = _side(curve, e)
        here = tuple(sorted(n for i, n in legs.items() if curve.edges[i].tail in side))
        vec = e.vec
        if anchor not in here:                  # orient from the anchor's side
            here = tuple(sorted(set(names) - set(here)))
            vec = -vec
        out.add(("edge", here, vec.x, vec.y))
    return frozenset(out)


def _side(curve: Curve, e) -> set:
    seen = {e.tail}
    stack = [e.tail]
    while stack:
        v = stack.pop()
        for f in curve.incident(v):
            if f.kind is not EdgeKind.BOUNDED or f.id == e.id:
                continue
            w = f.other(v)
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return seen


def _cone_coords(cone: Cone, m_cone: Cone, m_lengths: List[Fraction]) -> Optional[List[Fraction]]:
    """A point of M_0,5 in the coordinates of ``cone``, continued linearly
    across one of its rays: in a neighbouring cone (sharing a ray) the other
    coordinate is minus the length along the new ray. None for a point that is
    not in the cone, on its rays or next to it."""
    have = dict(zip(m_cone, m_lengths))
    out = [have.get(sp, Fraction(0)) for sp in cone]
    others = [sp for sp in m_cone if sp not in cone]
    if len(others) > 1 or (others and len(cone) != 2):
        return None
    if others:
        missing = [i for i, sp in enumerate(cone) if sp not in have]
        if len(missing) != 1:
            return None
        out[missing[0]] = -have[others[0]]
    return out


def crossing_edge(t: TypeMap, p0: List[Fraction], m0: Tuple[Cone, List[Fraction]],
                  p1: List[Fraction], m1: Tuple[Cone, List[Fraction]]) -> Optional[str]:
    """The edge of a full-dimensional type whose length reaches 0 first on the
    straight way from (p0, m0), where the type has a curve, to (p1, m1); None
    when it has a curve all the way, or the way is not a continuous one."""
    if not t.full:
        return None
    y0 = _cone_coords(t.cone, *m0)
    y1 = _cone_coords(t.cone, *m1)
    if y0 is None or y1 is None:
        return None
    def lengths(p, y):
        r = list(p) + list(y)
        return {e.id: sum((t.inv[t.index[e.id]][j] * r[j] for j in range(t.n)), Fraction(0))
                for e in t.bounded}
    l0, l1 = lengths(p0, y0), lengths(p1, y1)
    best = None
    for eid, a in l0.items():
        b = l1[eid]
        if a > 0 and b <= 0:
            s = a / (a - b)
            if best is None or s < best[0]:
                best = (s, eid)
    return best[1] if best else None


def neighbours(curve: Curve, edge_id: str):
    """(the type on the wall, [the types on the other side]) when ``edge_id``
    shrinks to 0; the type itself is left out."""
    res = contract_edge(curve, edge_id)
    wall = res.curve
    v = res.merged_vertex
    me = type_key(curve)
    others = []
    if wall.valence(v) >= 4:
        for r in resolutions(wall, v):
            c = apply_resolution(wall, r).curve
            if type_key(c) != me:
                others.append(c)
    return wall, others


def points_through(t: TypeMap, cone: Cone, lengths: List[Fraction]) -> Optional[List[Fraction]]:
    """Points in the plane with a curve of the type over them and over the
    given point of M_0,5 (the root at the origin), or None."""
    if t.cone != cone:
        return None
    pin = [[1 if j == 0 else 0 for j in range(t.n)], [1 if j == 1 else 0 for j in range(t.n)]]
    rows = [t.splits[sp] for sp in t.cone] + pin
    sol = _affine_solutions(rows, list(lengths) + [Fraction(0), Fraction(0)], t.n)
    if sol is None:
        return None
    z0, N = sol
    w = _interior_point(_length_cons(t, z0, N), len(N))
    if w is None:
        return None
    z = [z0[i] + sum((N[j][i] * w[j] for j in range(len(N))), Fraction(0)) for i in range(t.n)]
    return [sum((Fraction(r[j]) * z[j] for j in range(t.n)), Fraction(0)) for r in t.ev_rows]
