"""The evaluation matrix of a combinatorial type.

The cell of the moduli space of parametrized rational tropical curves with a
given combinatorial type is an open cone with coordinates

    (x_0, y_0, l_e for every bounded edge e),

where ``(x_0, y_0)`` is the image of a chosen root vertex and ``l_e`` the length
of ``e``. An edge of length ``l`` with direction vector ``u`` (weight included,
as ``Edge.vec`` stores it) moves its head by ``l * u`` from its tail -- the map
is affine on each edge with slope ``u``. So the cell has dimension
``#bounded + 2``.

Every evaluation function here is linear on the cell, and the evaluation
matrix is the matrix of ``n`` of them together, one row per function, one
column per coordinate. The functions:

* ``x`` / ``y`` of a marking: that coordinate of the marking's image,
  ``x_0 + sum of l_e * u_e.x`` along the path from the root to the marking
  (``u_e`` taken in the direction of travel).
* a cross ratio of four legs (markings, as contracted ends, or ends)
  ``p1, p2, p3, p4``: as in Tyomkin (arXiv:1509.07453), the signed length of
  the intersection of the oriented path from ``p1`` to ``p3`` with the
  oriented path from ``p2`` to ``p4`` -- each common edge contributes
  ``+l_e`` where the two paths cross it in the same direction and ``-l_e``
  where they cross it in opposite directions. Only bounded edges can be
  common, the four legs being different.

Entries are integers; the determinant (when square) is computed exactly.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

from .curve import Curve, Edge, EdgeKind


def natural_key(s: str):
    """Sort key that orders embedded numbers by value: x2 before x10."""
    return [(0, int(t)) if t.isdigit() else (1, t.lower()) for t in re.split(r"(\d+)", s) if t]


# --- paths in the tree ------------------------------------------------------
def _path(curve: Curve, a: str, b: str) -> List[Tuple[Edge, str]]:
    """Bounded edges from vertex ``a`` to vertex ``b``, each with the vertex it
    is entered from (so its direction of travel is ``outgoing(from)``)."""
    if a == b:
        return []
    prev: Dict[str, Tuple[Edge, str]] = {}
    seen = {a}
    stack = [a]
    while stack:
        v = stack.pop()
        for e in curve.incident(v):
            if e.kind is not EdgeKind.BOUNDED:
                continue
            w = e.other(v)
            if w in seen:
                continue
            seen.add(w)
            prev[w] = (e, v)
            if w == b:
                stack = []
                break
            stack.append(w)
    if b not in prev:
        raise ValueError("the curve is not connected")
    out: List[Tuple[Edge, str]] = []
    v = b
    while v != a:
        e, frm = prev[v]
        out.append((e, frm))
        v = frm
    out.reverse()
    return out


def _sign(e: Edge, frm: str) -> int:
    """+1 when a path crosses ``e`` from tail to head, -1 the other way."""
    return 1 if frm == e.tail else -1


def _bounded_by_name(curve: Curve) -> List[Edge]:
    return sorted(curve.bounded, key=lambda e: natural_key(e.name or e.id))


# --- the setup the dialog offers --------------------------------------------
def _vertex_label(curve: Curve, v: str) -> str:
    names = sorted((e.name or e.id for e in curve.incident(v)), key=natural_key)
    return "vertex " + ", ".join(names)


def setup(curve: Curve) -> Dict[str, Any]:
    """What the evaluation-matrix dialog chooses from.

    ``roots``: markings first (by name), then the vertices carrying no marking
    (by their label, the names of the edges meeting there); each entry names
    the vertex it stands for. ``legs``: markings then ends, by name -- what a
    cross ratio takes. ``default_functions``: x and y of every marking.
    """
    markings = sorted(curve.markings, key=lambda m: natural_key(m.name or m.id))
    ends = sorted(curve.ends, key=lambda e: natural_key(e.name or e.id))
    marked = {m.tail for m in markings}
    roots = [{"vertex": m.tail, "label": m.name or m.id, "kind": "marking", "marking": m.id}
             for m in markings]
    others = [{"vertex": v, "label": _vertex_label(curve, v), "kind": "vertex"}
              for v in curve.vertices if v not in marked]
    roots += sorted(others, key=lambda r: natural_key(r["label"]))
    bounded = [{"id": e.id, "name": e.name or e.id} for e in _bounded_by_name(curve)]
    defaults = []
    for m in markings:
        defaults.append({"kind": "x", "marking": m.id})
        defaults.append({"kind": "y", "marking": m.id})
    return {
        "roots": roots,
        "markings": [{"id": m.id, "name": m.name or m.id} for m in markings],
        "legs": [{"id": e.id, "name": e.name or e.id, "kind": "marking"} for e in markings]
                + [{"id": e.id, "name": e.name or e.id, "kind": "end"} for e in ends],
        "bounded": bounded,
        "n": len(bounded) + 2,
        "default_functions": defaults,
    }


# --- the matrix --------------------------------------------------------------
def _leg(curve: Curve, lid: str, what: str) -> Edge:
    e = curve.edges.get(lid)
    if e is None or e.kind is EdgeKind.BOUNDED:
        raise ValueError(f"{what}: {lid!r} is not a marking or an end")
    return e


def function_label(curve: Curve, f: Dict[str, Any]) -> str:
    kind = f.get("kind")
    if kind in ("x", "y"):
        m = curve.edges.get(f.get("marking"))
        return f"{kind}({m.name if m else f.get('marking')})"
    if kind == "cross_ratio":
        names = [(curve.edges[p].name or p) if p in curve.edges else str(p) for p in f.get("points", [])]
        return "cr(" + ", ".join(names) + ")"
    return str(kind)


def row_of(curve: Curve, root: str, columns: Dict[str, int], f: Dict[str, Any]) -> List[int]:
    row = [0] * (len(columns) + 2)
    kind = f.get("kind")
    if kind in ("x", "y"):
        m = curve.edges.get(f.get("marking"))
        if m is None or m.kind is not EdgeKind.MARKING:
            raise ValueError(f"{kind}: {f.get('marking')!r} is not a marking")
        row[0 if kind == "x" else 1] = 1
        for e, frm in _path(curve, root, m.tail):
            u = e.outgoing(frm)
            row[columns[e.id]] += u.x if kind == "x" else u.y
        return row
    if kind == "cross_ratio":
        pts = list(f.get("points") or [])
        if len(pts) != 4:
            raise ValueError("a cross ratio takes four markings or ends")
        if len(set(pts)) != 4:
            raise ValueError("a cross ratio needs four different markings or ends")
        legs = [_leg(curve, p, "cross ratio") for p in pts]
        first = {e.id: _sign(e, frm) for e, frm in _path(curve, legs[0].tail, legs[2].tail)}
        for e, frm in _path(curve, legs[1].tail, legs[3].tail):
            if e.id in first:
                row[columns[e.id]] += first[e.id] * _sign(e, frm)
        return row
    raise ValueError(f"unknown evaluation function {kind!r}")


def determinant(m: List[List[int]]) -> int:
    n = len(m)
    a = [[Fraction(x) for x in r] for r in m]
    det = Fraction(1)
    for c in range(n):
        p = next((r for r in range(c, n) if a[r][c] != 0), None)
        if p is None:
            return 0
        if p != c:
            a[c], a[p] = a[p], a[c]
            det = -det
        det *= a[c][c]
        for r in range(c + 1, n):
            if a[r][c]:
                k = a[r][c] / a[c][c]
                a[r] = [x - k * y for x, y in zip(a[r], a[c])]
    assert det.denominator == 1
    return int(det)


def rank(m: List[List[int]]) -> int:
    a = [[Fraction(x) for x in r] for r in m]
    rows, cols = len(a), (len(a[0]) if a else 0)
    rk = 0
    for c in range(cols):
        p = next((r for r in range(rk, rows) if a[r][c] != 0), None)
        if p is None:
            continue
        a[rk], a[p] = a[p], a[rk]
        for r in range(rows):
            if r != rk and a[r][c]:
                k = a[r][c] / a[rk][c]
                a[r] = [x - k * y for x, y in zip(a[r], a[rk])]
        rk += 1
    return rk


def evaluation_matrix(curve: Curve, root: str, functions: List[Dict[str, Any]],
                      require_square: bool = True) -> Dict[str, Any]:
    """The matrix of ``functions`` on the cell, with the root vertex ``root``.

    Columns: ``x_0``, ``y_0``, then the bounded edges by name (so related
    types, sharing edge names, get comparable columns). With
    ``require_square`` (the default) there must be exactly ``#bounded + 2``
    functions.
    """
    if root not in curve.vertices:
        raise ValueError(f"unknown root vertex {root!r}")
    bounded = _bounded_by_name(curve)
    n = len(bounded) + 2
    if require_square and len(functions) != n:
        raise ValueError(f"need exactly {n} evaluation functions (#bounded edges + 2), "
                         f"got {len(functions)}")
    columns = {e.id: i + 2 for i, e in enumerate(bounded)}
    matrix = [row_of(curve, root, columns, f) for f in functions]
    out: Dict[str, Any] = {
        "columns": ["x0", "y0"] + [e.name or e.id for e in bounded],
        "column_ids": [None, None] + [e.id for e in bounded],
        "rows": [function_label(curve, f) for f in functions],
        "matrix": matrix,
        "rank": rank(matrix),
        "det": determinant(matrix) if len(matrix) == n else None,
    }
    return out
