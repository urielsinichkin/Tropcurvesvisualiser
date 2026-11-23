"""The polyhedron of curves of one type through given constraints.

One combinatorial type and some constraints on where its curve lies:

* an evaluated marking: its image is a given point ``(x, y)`` -- two linear
  conditions;
* a constrained end: it lies on a given line parallel to it -- one condition,
  ``det(v, P) = c`` for the end's vertex ``P`` and direction ``v``.

The type's cell has coordinates ``z = (x_0, y_0, l_e for every bounded edge)``
(as in :mod:`evaluation` and :mod:`moduli`); every condition is linear in
``z``, so the curves of the type satisfying them form a polyhedron

    P = { z : C z = b,  l_e >= 0 }.

Its relative interior (every ``l_e > 0``) is the curves of precisely this
type. A face ``l_e = 0`` is a degeneration: the edge contracts, the curve
becomes the type with a vertex of higher valence, and from there its
*regenerations* (the resolutions of that vertex) lead on.

A polyhedron of dimension at most 2 is charted by its free coordinates
(usually edge lengths) and drawn; in higher dimension the walk goes along a
chosen direction of edge lengths, projected to the polyhedron.

Everything is exact (``Fraction``); a small simplex method (Bland's rule)
answers the linear programs: is there a curve of the precise type, which is
nearest to the last one, can a regeneration be entered.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .curve import Curve, EdgeKind
from .evaluation import _bounded_by_name, _path
from .moduli import _clip, _area2, _nullspace, _rref, solve
from .operations import apply_resolution, contract_edge, resolutions

F = Fraction


# --- linear programming ------------------------------------------------------
def lp_min(c: Sequence[Any], A: Sequence[Sequence[Any]], b: Sequence[Any]):
    """Minimize ``c . x`` subject to ``A x = b``, ``x >= 0`` (exactly).

    Returns ``("optimal", x)``, ``("infeasible", None)`` or
    ``("unbounded", None)``. Two phases, Bland's rule (so it terminates)."""
    n, m = len(c), len(A)
    rows = [[F(x) for x in r] for r in A]
    rhs = [F(x) for x in b]
    for i in range(m):
        if rhs[i] < 0:
            rows[i] = [-x for x in rows[i]]
            rhs[i] = -rhs[i]
    T = [rows[i] + [F(int(i == j)) for j in range(m)] + [rhs[i]] for i in range(m)]
    basis = [n + i for i in range(m)]

    def pivot(r: int, col: int) -> None:
        p = T[r][col]
        T[r] = [x / p for x in T[r]]
        for i in range(m):
            if i != r and T[i][col]:
                f = T[i][col]
                T[i] = [x - f * y for x, y in zip(T[i], T[r])]
        basis[r] = col

    def run(cost: List[F], allowed: List[int]) -> str:
        while True:
            red = {}
            for j in allowed:
                red[j] = cost[j] - sum((cost[basis[i]] * T[i][j] for i in range(m) if cost[basis[i]]), F(0))
            enter = next((j for j in allowed if red[j] < 0), None)
            if enter is None:
                return "optimal"
            cands = [(T[i][-1] / T[i][enter], basis[i], i) for i in range(m) if T[i][enter] > 0]
            if not cands:
                return "unbounded"
            pivot(min(cands)[2], enter)

    run([F(0)] * n + [F(1)] * m, list(range(n + m)))
    if any(T[i][-1] != 0 for i in range(m) if basis[i] >= n):
        return "infeasible", None
    for i in range(m):                       # artificials left at 0: out of the basis
        if basis[i] >= n:
            j = next((j for j in range(n) if T[i][j] != 0), None)
            if j is not None:
                pivot(i, j)
    status = run([F(x) for x in c] + [F(0)] * m, list(range(n)))
    if status != "optimal":
        return status, None
    x = [F(0)] * n
    for i in range(m):
        if basis[i] < n:
            x[basis[i]] = T[i][-1]
    return "optimal", x


# --- the cell and its constraints ---------------------------------------------
class Cell:
    """A type's cell with constraints: points for markings (by name) and line
    values for ends (by name)."""

    def __init__(self, curve: Curve, points: Dict[str, Sequence[Any]] = None,
                 lines: Dict[str, Any] = None):
        self.curve = curve
        self.root = curve.vertices[0]
        self.bounded = _bounded_by_name(curve)
        self.index = {e.id: i + 2 for i, e in enumerate(self.bounded)}
        self.n = len(self.bounded) + 2
        by_name = {e.name: e for e in curve.edges.values() if e.kind is not EdgeKind.BOUNDED}
        rows: List[List[int]] = []
        rhs: List[F] = []
        self.points = {k: (F(str(v[0])), F(str(v[1]))) for k, v in (points or {}).items()}
        self.lines = {k: F(str(v)) for k, v in (lines or {}).items()}
        for name, (px, py) in self.points.items():
            e = by_name.get(name)
            if e is None or e.kind is not EdgeKind.MARKING:
                raise ValueError(f"no marking named {name!r}")
            rows += [self.vertex_row(e.tail, "x"), self.vertex_row(e.tail, "y")]
            rhs += [px, py]
        for name, c in self.lines.items():
            e = by_name.get(name)
            if e is None or e.kind is not EdgeKind.END:
                raise ValueError(f"no end named {name!r}")
            rows.append(self.line_row(e))
            rhs.append(c)
        self.C, self.b = rows, rhs
        aug = [[F(x) for x in r] + [v] for r, v in zip(rows, rhs)]
        self.consistent = self.n not in (_rref(aug, self.n + 1) if aug else [])
        plain = [[F(x) for x in r] for r in rows]
        piv = _rref(plain, self.n) if plain else []
        self.free = [c for c in range(self.n) if c not in piv]
        self.N = _nullspace(rows, self.n) if rows else \
            [[F(int(i == j)) for i in range(self.n)] for j in range(self.n)]
        self.dim = len(self.N) if self.consistent else None

    # positions in the plane
    def vertex_row(self, v: str, kind: str) -> List[int]:
        row = [0] * self.n
        row[0 if kind == "x" else 1] = 1
        for e, frm in _path(self.curve, self.root, v):
            u = e.outgoing(frm)
            row[self.index[e.id]] += u.x if kind == "x" else u.y
        return row

    def line_row(self, end) -> List[int]:
        """det(v, P) for the end's vertex P: constant along the end's line."""
        rx, ry = self.vertex_row(end.tail, "x"), self.vertex_row(end.tail, "y")
        v = end.vec
        return [v.x * b - v.y * a for a, b in zip(rx, ry)]

    @staticmethod
    def dot(row: Sequence[Any], z: Sequence[F]) -> F:
        return sum((F(a) * b for a, b in zip(row, z) if a), F(0))

    def positions(self, z: Sequence[F]) -> Dict[str, Tuple[F, F]]:
        return {v: (self.dot(self.vertex_row(v, "x"), z), self.dot(self.vertex_row(v, "y"), z))
                for v in self.curve.vertices}

    def lengths(self, z: Sequence[F]) -> Dict[str, F]:
        return {e.id: z[self.index[e.id]] for e in self.bounded}

    def values(self, z: Sequence[F]) -> Dict[str, Any]:
        """Where the markings are and the line value of every end, at z."""
        pts, lines = {}, {}
        for e in self.curve.edges.values():
            if e.kind is EdgeKind.MARKING:
                pts[e.name] = (self.dot(self.vertex_row(e.tail, "x"), z), self.dot(self.vertex_row(e.tail, "y"), z))
            elif e.kind is EdgeKind.END:
                lines[e.name] = self.dot(self.line_row(e), z)
        return {"points": pts, "lines": lines}

    def satisfies(self, z: Sequence[F]) -> bool:
        return all(self.dot(r, z) == v for r, v in zip(self.C, self.b))

    # --- linear programs -----------------------------------------------------
    def _lp_vars(self):
        """Columns for z: x0 and y0 split in a positive and a negative part,
        the lengths as they are. Returns (count, z of a solution x)."""
        m = len(self.bounded)
        def z_of(x):
            return [x[0] - x[1], x[2] - x[3]] + list(x[4:4 + m])
        def col(j):                # the LP columns of z's coordinate j, with signs
            return [(0, 1), (1, -1)] if j == 0 else [(2, 1), (3, -1)] if j == 1 else [(j + 2, 1)]
        return 4 + m, z_of, col

    def interior(self, cap: F = F(1)) -> Tuple[Optional[F], Optional[List[F]]]:
        """The largest t <= cap with a curve whose lengths are all >= t, and
        that curve; (None, None) when no curve satisfies the constraints.
        t > 0: curves of precisely this type exist."""
        if not self.consistent:
            return None, None
        nz, z_of, col = self._lp_vars()
        m = len(self.bounded)
        t, s0, u = nz, nz + 1, nz + 1 + m          # t, slacks s_e, u (t + u = cap)
        nv = u + 1
        A, b = [], []
        for r, v in zip(self.C, self.b):
            row = [F(0)] * nv
            for j, a in enumerate(r):
                if a:
                    for k, sgn in col(j):
                        row[k] += sgn * a
            A.append(row); b.append(v)
        for i in range(m):                          # l_e - t - s_e = 0
            row = [F(0)] * nv
            row[4 + i] = F(1); row[t] = F(-1); row[s0 + i] = F(-1)
            A.append(row); b.append(F(0))
        row = [F(0)] * nv
        row[t] = F(1); row[u] = F(1)
        A.append(row); b.append(F(cap))
        c = [F(0)] * nv
        c[t] = F(-1)
        status, x = lp_min(c, A, b)
        if status != "optimal":
            return None, None
        return x[t], z_of(x)

    def fit(self, z_prev: Sequence[F]) -> Tuple[Optional[F], Optional[List[F]]]:
        """A curve satisfying the constraints near z_prev (L1), with every
        length at least half the largest margin (so of the precise type when
        there is one): (margin, z), or (None, None) when there is none."""
        t, zi = self.interior()
        if t is None:
            return None, None
        if t == 0:
            return t, zi
        mu = t / 2
        n, m = self.n, len(self.bounded)
        zp = [F(x) for x in z_prev]
        # z = zp + d+ - d-; lengths: (zp + d+ - d-)_e - s_e = mu
        nv = 2 * n + m
        A, b = [], []
        for r, v in zip(self.C, self.b):
            row = [F(0)] * nv
            for j, a in enumerate(r):
                row[j] += a; row[n + j] -= a
            A.append(row); b.append(v - self.dot(r, zp))
        for i in range(m):
            j = 2 + i
            row = [F(0)] * nv
            row[j] = F(1); row[n + j] = F(-1); row[2 * n + i] = F(-1)
            A.append(row); b.append(mu - zp[j])
        c = [F(1)] * (2 * n) + [F(0)] * m
        status, x = lp_min(c, A, b)
        if status != "optimal":
            return t, zi
        return t, [zp[j] + x[j] - x[n + j] for j in range(n)]

    # --- the chart (dimension <= 2) ------------------------------------------
    def axis_name(self, col: int) -> str:
        if col < 2:
            return ("x", "y")[col] + "₀"
        return self.bounded[col - 2].name or self.bounded[col - 2].id

    def forms(self, z: Sequence[F]) -> Dict[str, Tuple[F, F, F]]:
        """Each length as c + alpha a + beta b in the free coordinates (a, b)
        (missing ones 0), around z."""
        k = len(self.free)
        w = [z[c] for c in self.free] + [F(0)] * (2 - k)
        out = {}
        for e in self.bounded:
            j = self.index[e.id]
            al = self.N[0][j] if k > 0 else F(0)
            be = self.N[1][j] if k > 1 else F(0)
            out[e.id] = (z[j] - al * w[0] - be * w[1], al, be)
        return out

    def at_chart(self, z: Sequence[F], w: Sequence[F]) -> List[F]:
        """The point of the polyhedron with free coordinates w."""
        out = list(z)
        for i, c in enumerate(self.free):
            d = F(w[i]) - z[c]
            if d:
                out = [x + d * y for x, y in zip(out, self.N[i])]
        return out

    def region(self, z: Sequence[F], box: Sequence[Sequence[F]]) -> Optional[Dict[str, Any]]:
        """Where in the box (one interval per free coordinate) the curves of
        this type lie: a polygon (dimension 2) or an interval (1), with the
        walls (where an edge reaches length 0) labelled by the edge."""
        k = len(self.free)
        names = {e.id: e.name for e in self.bounded}
        forms = self.forms(z)
        # a side of the box where a charted length is 0 is a wall of that edge
        def side(i: int, at: F) -> str:
            c = self.free[i]
            return self.bounded[c - 2].id if c >= 2 and at == 0 else "box"
        if k == 2:
            (a0, a1), (b0, b1) = box
            poly = [((a0, b0), side(1, b0)), ((a1, b0), "box"), ((a1, b1), "box"), ((a0, b1), side(0, a0))]
            for eid, (c, al, be) in forms.items():
                poly = _clip(poly, c, al, be, eid)
                if len(poly) < 3:
                    return None
            if _area2(poly) <= 0:
                return None
            walls = []
            for i, (P, lab) in enumerate(poly):
                if lab in names:
                    Q = poly[(i + 1) % len(poly)][0]
                    walls.append({"from": [float(P[0]), float(P[1])], "to": [float(Q[0]), float(Q[1])],
                                  "edge": lab, "name": names[lab]})
            return {"polygon": [[float(q[0]), float(q[1])] for q, _ in poly], "walls": walls}
        if k == 1:
            lo, hi = box[0]
            lo_lab, hi_lab = side(0, lo), "box"
            for eid, (c, al, _) in forms.items():
                if al > 0:
                    x = -c / al
                    if x > lo:
                        lo, lo_lab = x, eid
                elif al < 0:
                    x = -c / al
                    if x < hi:
                        hi, hi_lab = x, eid
                elif c < 0:
                    return None
            if lo >= hi:
                return None
            walls = [{"at": [float(x), 0.0], "edge": lab, "name": names[lab]}
                     for x, lab in ((lo, lo_lab), (hi, hi_lab)) if lab in names]
            return {"interval": [float(lo), float(hi)], "walls": walls}
        return None

    def move(self, z: Sequence[F], w1: Sequence[F]) -> Tuple[List[F], Optional[str]]:
        """Straight from z towards the point with free coordinates w1; stop
        where the first edge reaches length 0: (the point, that edge or None)."""
        z1 = self.at_chart(z, w1)
        return self.go(z, [b - a for a, b in zip(z, z1)], F(1))

    def go(self, z: Sequence[F], v: Sequence[F], t: F) -> Tuple[List[F], Optional[str]]:
        """z + s v for s up to t, stopping at the first length to reach 0."""
        best = None
        for e in self.bounded:
            j = self.index[e.id]
            if v[j] < 0 and z[j] >= 0:
                s = z[j] / -v[j]
                if s <= t and (best is None or s < best[0]):
                    best = (s, e.id)
        s = best[0] if best else t
        out = [a + s * d for a, d in zip(z, v)]
        if best:
            out[self.index[best[1]]] = F(0)
        return out, best[1] if best else None

    # --- a direction (dimension > 2) -----------------------------------------
    def project(self, z: Sequence[F], delta: Dict[str, Any]) -> Dict[str, Any]:
        """The direction of edge lengths ``delta`` (edge id -> amount; x0, y0
        not moved), projected orthogonally to the polyhedron's directions; how
        far it goes (to the first length reaching 0) and which edge that is."""
        D = [F(0)] * self.n
        for eid, a in delta.items():
            if eid in self.index:
                D[self.index[eid]] = F(str(a))
        k = len(self.N)
        if k == 0 or not any(D):
            return {"v": [F(0)] * self.n, "t_max": None, "edge": None}
        G = [[sum((self.N[i][j] * self.N[l][j] for j in range(self.n)), F(0)) for l in range(k)]
             for i in range(k)]
        rhs = [sum((self.N[i][j] * D[j] for j in range(self.n)), F(0)) for i in range(k)]
        status, y = solve(G, rhs)
        if status != "unique":
            return {"v": [F(0)] * self.n, "t_max": None, "edge": None}
        v = [sum((y[i] * self.N[i][j] for i in range(k)), F(0)) for j in range(self.n)]
        best = None
        for e in self.bounded:
            j = self.index[e.id]
            if v[j] < 0:
                s = z[j] / -v[j]
                if best is None or s < best[0]:
                    best = (s, e.id)
        return {"v": v, "t_max": best[0] if best else None, "edge": best[1] if best else None}


# --- degenerations -------------------------------------------------------------
def coords_from(cell: Cell, pos: Dict[str, Tuple[F, F]], lengths: Dict[str, F],
                merged: Optional[str] = None) -> List[F]:
    """The coordinates of ``cell``'s curve from vertex positions and lengths
    of another curve with the same ids (a vertex it lacks is at ``merged``;
    an edge it lacks has length 0)."""
    r = pos.get(cell.root) or pos[merged]
    return [r[0], r[1]] + [lengths.get(e.id, F(0)) for e in cell.bounded]


def contract(cell: Cell, z: Sequence[F], edge_id: str):
    """The curve at z, where ``edge_id`` has length 0, as the type with that
    edge contracted: (curve, merged vertex, its coordinates)."""
    res = contract_edge(cell.curve, edge_id)
    pos, ls = cell.positions(z), cell.lengths(z)
    w = Cell(res.curve)
    return res.curve, res.merged_vertex, coords_from(w, pos, ls)


def regenerate(wall: Curve, vertex: str, z_wall: Sequence[F], points, lines,
               scale: F = F(1)) -> List[Dict[str, Any]]:
    """Every resolution of the wall's vertex, with the point a short way into
    it when the curve can go on into it (with the constraints kept), else why
    not."""
    wcell = Cell(wall)
    pos, ls = wcell.positions(z_wall), wcell.lengths(z_wall)
    out = []
    for r in resolutions(wall, vertex):
        res = apply_resolution(wall, r)
        cell = Cell(res.curve, points, lines)
        z0 = coords_from(cell, pos, ls, merged=vertex)
        entry = _entry(cell, z0, res.new_edge, scale) if cell.consistent else None
        out.append({"curve": res.curve, "new_edge": res.new_edge, "z": entry,
                    "side": list(r.side_b), "why": "" if entry else _why_not(cell)})
    return out


def _entry(cell: Cell, z0: List[F], new_edge: str, scale: F) -> Optional[List[F]]:
    """From z0 (the new edge of length 0), a short step into the type: along
    a direction of the polyhedron that lengthens the new edge and shortens no
    edge already at 0. None when there is none."""
    k = len(cell.N)
    if k == 0:
        return None
    zero = [e.id for e in cell.bounded if z0[cell.index[e.id]] == 0 and e.id != new_edge]
    conds = [(new_edge, F(1))] + [(e, F(0)) for e in zero]
    nv = 2 * k + len(conds)
    A, b = [], []
    for i, (eid, rhs) in enumerate(conds):            # (N w)_e - s = rhs
        j = cell.index[eid]
        row = [F(0)] * nv
        for l in range(k):
            row[l] = cell.N[l][j]; row[k + l] = -cell.N[l][j]
        row[2 * k + i] = F(-1)
        A.append(row); b.append(rhs)
    status, x = lp_min([F(0)] * nv, A, b)
    if status != "optimal":
        return None
    w = [x[l] - x[k + l] for l in range(k)]
    v = [sum((w[l] * cell.N[l][j] for l in range(k)), F(0)) for j in range(cell.n)]
    jn = cell.index[new_edge]
    s = F(scale) / 25 / v[jn]
    for e in cell.bounded:
        j = cell.index[e.id]
        if v[j] < 0 and z0[j] > 0:
            s = min(s, z0[j] / -v[j] / 2)
    return [a + s * d for a, d in zip(z0, v)]


def _why_not(cell: Cell) -> str:
    if not cell.consistent:
        return "no curve of this type satisfies the constraints"
    if not cell.N:
        return "the constraints fix this type's curve, and there its new edge has length 0"
    return "with the constraints kept, its new edge cannot grow from here"
