"""A walk through the moduli space of a type, across its walls.

One combinatorial type, ``k`` of its markings evaluated (their images in the
plane fixed) and five legs (ends or markings) giving the map to M_{0,5}:

    ev x ft : M_{0,n}(R^2, Delta) -> (R^2)^k x M_{0,5}.

The type's cell has coordinates ``z = (x_0, y_0, l_e for every bounded edge)``
(see :mod:`evaluation`; ``l_e`` is the parametrizing length, the curve
stretches it by the edge's direction vector, weight included). On it both maps
are linear:

* ``ev``: the images ``(x, y)`` of the evaluated markings
  (:func:`evaluation.row_of`);
* ``ft``: the tree spanned by the five legs, stabilized. Every bounded edge
  splits the legs; a 2|3 split is a ray of M_{0,5}, named by its two-element
  side, and its length is the sum of the ``l_e`` inducing it (those edges form
  a path in the curve: the *skeleton*). The splits of one tree are compatible,
  so the type maps to a cone (two rays), a ray or the apex.

With the points fixed, a *full-dimensional* type (square, invertible map, two
rays) has exactly one curve over each point ``(a, b)`` of its cone where all
lengths ``z = A^{-1}(p, a, b)`` are positive: a convex region, whose sides on
the lines ``l_e = 0`` are the *walls*. Moving the point of M_{0,5} moves the
curve; at a wall an edge shrinks to length 0 and the curve becomes the type
with that edge contracted (a vertex of valence 4). Its *regenerations* are the
ways of resolving that vertex: going back, or on into a neighbouring type.

Everything is exact (``Fraction``); floats only come out for drawing.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .curve import Curve, EdgeKind
from .evaluation import _bounded_by_name, natural_key, row_of
from .layout import embed
from .operations import contract_edge, resolutions, apply_resolution

Split = Tuple[int, int]           # the two-element side, as indices into the legs
Cone = Tuple[Split, ...]          # sorted; 0, 1 or 2 splits


def compatible(s: Split, t: Split) -> bool:
    return not set(s) & set(t)


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


# --- why a type is not full-dimensional --------------------------------------
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
                              f"of M₀,₅, not onto an open set"}
    return {"kind": "other", "reason": "the map is not invertible on its cell"}


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


# --- the setup ----------------------------------------------------------------
def check(t: TypeMap) -> Dict[str, Any]:
    """Do the dimensions match, and is the map invertible on the cell?"""
    c = t.curve
    dim = len(c.ends) + len(c.markings) - 1         # |Delta| + n - 3 + 2
    target = len(t.ev_rows) + 2
    k = len(t.ev_rows) // 2
    msg = ""
    if dim != target:
        msg = (f"The moduli space has dimension {dim} but (R²)^{k} × M₀,₅ has {target}: "
               + ("evaluate more markings, or add markings and evaluate them."
                  if dim > target else "evaluate fewer markings, or add markings."))
    return {"ok": dim == target, "dim": dim, "target": target, "message": msg,
            "full": t.full, "multiplicity": int(t.det) if t.det is not None else None}


def skeleton(t: TypeMap) -> Dict[str, int]:
    """For each bounded edge inducing a ray of the type's cone, which one (its
    index in the cone): the two coloured paths."""
    out = {}
    for i, sp in enumerate(t.cone):
        row = t.splits[sp]
        for e in t.bounded:
            if row[t.index[e.id]]:
                out[e.id] = i
    return out


def start(t: TypeMap) -> Tuple[List[Fraction], List[Fraction]]:
    """Points and lengths in M_0,5 of the type's curve at generic lengths
    (root at the origin)."""
    z = [Fraction(0), Fraction(0)] + [Fraction(1) + Fraction(i + 1, 7 + i) for i in range(t.n - 2)]
    img = [sum((Fraction(r[j]) * z[j] for j in range(t.n)), Fraction(0)) for r in t.matrix]
    k2 = len(t.ev_rows)
    return img[:k2], img[k2:]


# --- the curve over a point ----------------------------------------------------
def curve_at(t: TypeMap, p: List[Fraction], lengths: List[Fraction]) -> Optional[List[Fraction]]:
    """The type's curve over (p, m): its coordinates z, if unique with every
    length >= 0 (a length 0 is the point on a wall); else None."""
    status, z = t.solve_at(p, lengths)
    if status != "unique":
        return None
    if any(z[t.index[e.id]] < 0 for e in t.bounded):
        return None
    return z


def picture(t: TypeMap, z: List[Fraction], render_curve) -> Dict[str, Any]:
    """The curve at the coordinates z, placed in the plane: drawn lengths are
    l_e times the weight (a length 0 draws as a point)."""
    lengths = {e.id: max(z[t.index[e.id]], Fraction(0)) * e.weight for e in t.bounded}
    eps = {k: (v if v > 0 else Fraction(1, 10 ** 9)) for k, v in lengths.items()}
    data = render_curve(t.curve, eps)
    pos = embed(t.curve, eps)
    ox, oy = float(z[0] - pos[t.root][0]), float(z[1] - pos[t.root][1])
    for v in data["vertices"]:
        v["x"] += ox; v["y"] += oy
    for e in data["edges"]:
        e["from"] = [e["from"][0] + ox, e["from"][1] + oy]
        e["to"] = [e["to"][0] + ox, e["to"][1] + oy]
    for m in data["markings"]:
        m["at"] = [m["at"][0] + ox, m["at"][1] + oy]
    return data


# --- the cell and its walls ----------------------------------------------------
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


def region(t: TypeMap, p: List[Fraction], R: Fraction) -> Optional[Dict[str, Any]]:
    """Where in the quadrant [0, R]^2 of its cone the full-dimensional type has
    a curve over the points, with the label of each side: an edge id (a wall),
    "a0" / "b0" (the axes) or "box"."""
    if not t.full:
        return None
    forms = t.length_forms(p)
    Z = Fraction(0)
    poly = [((Z, Z), "b0"), ((R, Z), "box"), ((R, R), "box"), ((Z, R), "a0")]
    for eid, (c, al, be) in forms.items():
        poly = _clip(poly, c, al, be, eid)
        if len(poly) < 3:
            return None
    if _area2(poly) <= 0:
        return None
    names = {e.id: e.name for e in t.bounded}
    walls = []
    for i, (P_, lab) in enumerate(poly):
        if lab in names:
            Q = poly[(i + 1) % len(poly)][0]
            walls.append({"from": [float(P_[0]), float(P_[1])], "to": [float(Q[0]), float(Q[1])],
                          "edge": lab, "name": names[lab]})
    return {"polygon": [[float(q[0]), float(q[1])] for q, _ in poly], "walls": walls}


def move(t: TypeMap, p: List[Fraction], y0: List[Fraction], y1: List[Fraction]):
    """Walk the point of M_0,5 straight from y0 towards y1 (coordinates of the
    type's cone) and stop at the first wall: (where it stops, the edge that
    reached length 0 there or None)."""
    forms = t.length_forms(p)
    def at(y):
        return {e: c + al * y[0] + be * y[1] for e, (c, al, be) in forms.items()}
    l0, l1 = at(y0), at(y1)
    best = None
    for e, a in l0.items():
        b = l1[e]
        if b < 0 and a >= 0:
            s = a / (a - b)
            if best is None or s < best[0]:
                best = (s, e)
    if best is None:
        return list(y1), None
    s = best[0]
    return [y0[i] + s * (y1[i] - y0[i]) for i in range(2)], best[1]


# --- at a wall: the type there and its regenerations -----------------------
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


def contract_at_wall(curve: Curve, edge_id: str):
    """The type on the wall where ``edge_id`` shrinks to 0, and the vertex of
    valence 4 (or more) it leaves."""
    res = contract_edge(curve, edge_id)
    return res.curve, res.merged_vertex


def regenerations(wall: Curve, vertex: str) -> List[Curve]:
    """Every way of resolving the wall's vertex by an edge (a crossing,
    which would be an edge of direction 0, is not one)."""
    return [apply_resolution(wall, r).curve for r in resolutions(wall, vertex)]


def step_into(t: TypeMap, p: List[Fraction], m: Tuple[Cone, List[Fraction]],
              scale: Fraction) -> Optional[List[Fraction]]:
    """From a point of a wall, a short step into the full-dimensional type's
    region, along the direction that lengthens its new edge(s): the cone
    coordinates of a point a little inside, or None when there is none (the
    new edge cannot grow by moving in M_0,5 with the points fixed)."""
    if not t.full:
        return None
    y0 = _cone_coords(t.cone, *m)
    if y0 is None:
        return None
    forms = t.length_forms(p)
    L0 = {e: c + al * y0[0] + be * y0[1] for e, (c, al, be) in forms.items()}
    if any(v < 0 for v in L0.values()):
        return None
    zero = [e for e, v in L0.items() if v == 0]
    if not zero:
        return y0
    d = [sum((forms[e][1] for e in zero), Fraction(0)), sum((forms[e][2] for e in zero), Fraction(0))]
    if d == [0, 0]:
        return None
    slope = {e: forms[e][1] * d[0] + forms[e][2] * d[1] for e in forms}
    if any(slope[e] <= 0 for e in zero):
        return None
    limit = None
    for e, v in L0.items():
        if v > 0 and slope[e] < 0:
            lim = v / -slope[e]
            limit = lim if limit is None else min(limit, lim)
    for i in range(2):
        if d[i] < 0:
            if y0[i] <= 0:
                return None
            lim = y0[i] / -d[i]
            limit = lim if limit is None else min(limit, lim)
    s = scale / 25 / max(slope[e] for e in zero)       # the new edge about scale/25 long
    if limit is not None:
        s = min(s, limit / 2)
    return [y0[0] + s * d[0], y0[1] + s * d[1]]
