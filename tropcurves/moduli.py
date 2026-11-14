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
        if status == "free":
            notes.append({"type": t.id, "name": t.name,
                          "note": "the fibre over this point is not a point (positive-dimensional)"})
            continue
        ls = {e.id: z[t.index[e.id]] for e in t.bounded}
        if any(v <= 0 for v in ls.values()):
            continue
        found.append({
            "type": t.id, "name": t.name,
            "multiplicity": int(t.det) if t.full else None,
            "full": t.full,
            "on_wall": not t.full,
            "lengths": [{"edge": e.id, "name": e.name, "value": str(ls[e.id]),
                         "float": float(ls[e.id])} for e in t.bounded],
            "picture": render(t, z),
        })
    found.sort(key=lambda f: natural_key(f["name"]))
    count = sum(f["multiplicity"] or 0 for f in found)
    return {"preimages": found, "count": count, "notes": notes,
            "on_wall": any(f["on_wall"] for f in found) or len(cone) < 2}


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
    return None, None
