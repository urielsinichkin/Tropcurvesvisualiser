"""Embedding a combinatorial type in the plane.

Slopes (primitive directions) are fixed by the combinatorial type; only the
positive **lengths** of bounded edges and the root position are free. This
module places the tree's vertices from a choice of lengths.

Two callers use this:

* the drawing/GUI layer wants a *readable* embedding (spread out, few near
  collisions) -- see :func:`readable_lengths` (a simple heuristic for now;
  aesthetic tuning is deferred, see ``docs/POSTPONED.md``);
* the subdivision builder wants a *generic* embedding in a maximal-dimensional
  chamber, so that self-crossings are transverse and isolated -- see
  :func:`generic_lengths`.

Positions use :class:`fractions.Fraction` so intersections stay exact.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Dict, Optional, Tuple

from .curve import Curve, EdgeKind
from .geometry import Vec2, primitive

Point = Tuple[Fraction, Fraction]


def _root_of(curve: Curve, root: Optional[str]) -> str:
    if root is not None:
        if root not in curve.vertices:
            raise ValueError(f"unknown root vertex {root!r}")
        return root
    if not curve.vertices:
        raise ValueError("curve has no vertices")
    return curve.vertices[0]


def embed(
    curve: Curve,
    lengths: Optional[Dict[str, Fraction]] = None,
    root: Optional[str] = None,
) -> Dict[str, Point]:
    """Return vertex positions from bounded-edge lengths (exact rationals).

    ``lengths`` maps bounded-edge id -> positive length; missing edges default to
    length 1. ``root`` (default: first vertex) is placed at the origin. Requires
    a connected tree.
    """
    if not curve.is_connected():
        raise ValueError("cannot embed a disconnected curve")
    r = _root_of(curve, root)
    lengths = {k: Fraction(v) for k, v in (lengths or {}).items()}

    pos: Dict[str, Point] = {r: (Fraction(0), Fraction(0))}
    stack = [r]
    while stack:
        v = stack.pop()
        vx, vy = pos[v]
        for e in curve.incident(v):
            if e.kind is not EdgeKind.BOUNDED:
                continue
            w = e.other(v)
            if w in pos:
                continue
            L = lengths.get(e.id, Fraction(1))
            if L <= 0:
                raise ValueError(f"edge length must be positive (edge {e.name!r})")
            u, _ = primitive(e.outgoing(v))  # primitive ray direction v -> w
            pos[w] = (vx + L * u.x, vy + L * u.y)
            stack.append(w)
    return pos


def readable_lengths(curve: Curve) -> Dict[str, Fraction]:
    """A simple, deterministic length choice for display.

    Unit lengths for now. A proper readability optimizer (spread vertices, avoid
    label/edge collisions, keep a good aspect ratio) is deferred; see
    ``docs/POSTPONED.md``.
    """
    return {e.id: Fraction(1) for e in curve.bounded}


def generic_lengths(curve: Curve, seed: int = 1) -> Dict[str, Fraction]:
    """Distinct, deterministic lengths for a generic (maximal-chamber) embedding.

    Uses well-separated rationals so that, for typical inputs, self-crossings are
    transverse and isolated. The subdivision builder additionally verifies
    general position and re-seeds if a degeneracy is detected.
    """
    lengths: Dict[str, Fraction] = {}
    for i, e in enumerate(curve.bounded):
        # Values in [1, 2), all distinct, depending on seed.
        num = 1 + ((seed * 2654435761 + i * 40503) % 997)
        lengths[e.id] = Fraction(997 + num, 997)
    return lengths
