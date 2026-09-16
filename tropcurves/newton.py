"""The Newton polygon of a combinatorial type, derived from its ends.

Each end ``(w, u)`` (weight ``w``, primitive direction ``u``) is dual to a
boundary edge of the Newton polygon of lattice length ``w`` whose outer normal
is ``u``. Concretely the Newton-polygon edge vector is ``rot90(end.vec)``; since
the ends satisfy global balancing ``sum end.vec == 0``, the rotated vectors also
sum to zero and close up into a convex polygon. Markings (direction zero) do not
contribute.

The polygon is defined only up to translation; we return it with its first
vertex at the origin, traversed counter-clockwise.
"""

from __future__ import annotations

from typing import List

from .curve import Curve
from .geometry import Vec2, rot90, polygon_from_edge_vectors


def newton_edge_vectors(curve: Curve) -> List[Vec2]:
    """The Newton-polygon edge vectors, one per end (``rot90`` of each end)."""
    return [rot90(e.vec) for e in curve.ends]


def newton_polygon(curve: Curve) -> List[Vec2]:
    """Return the Newton-polygon vertices (CCW, first vertex at the origin).

    Raises ``ValueError`` (via :func:`polygon_from_edge_vectors`) if the ends do
    not satisfy global balancing.
    """
    if not curve.ends:
        raise ValueError("curve has no ends; Newton polygon is undefined")
    return polygon_from_edge_vectors(newton_edge_vectors(curve))
