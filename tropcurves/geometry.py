"""Exact integer lattice geometry in the plane.

Everything here is exact: vectors are pairs of Python ``int`` s, so gcd,
primitive directions, balancing and Newton-polygon construction carry no
floating-point error. Floats only enter later, in the drawing/layout pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Vec2:
    """An immutable 2D integer lattice vector."""

    x: int
    y: int

    def __post_init__(self) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise TypeError("Vec2 components must be int")

    # --- arithmetic -----------------------------------------------------
    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    def __mul__(self, k: int) -> "Vec2":
        if not isinstance(k, int):
            raise TypeError("Vec2 can only be scaled by an int")
        return Vec2(self.x * k, self.y * k)

    __rmul__ = __mul__

    # --- predicates -----------------------------------------------------
    def is_zero(self) -> bool:
        return self.x == 0 and self.y == 0

    # --- serialization --------------------------------------------------
    def to_list(self) -> List[int]:
        return [self.x, self.y]

    @staticmethod
    def from_iterable(it: Iterable[int]) -> "Vec2":
        a = list(it)
        if len(a) != 2:
            raise ValueError("Vec2 needs exactly two components")
        return Vec2(int(a[0]), int(a[1]))

    def __iter__(self):
        yield self.x
        yield self.y


ZERO = Vec2(0, 0)


def dot(a: Vec2, b: Vec2) -> int:
    return a.x * b.x + a.y * b.y


def cross(a: Vec2, b: Vec2) -> int:
    """The scalar cross product ``a.x*b.y - a.y*b.x``."""
    return a.x * b.y - a.y * b.x


def rot90(v: Vec2) -> Vec2:
    """Rotate ``v`` by +90 degrees (counter-clockwise): (x, y) -> (-y, x)."""
    return Vec2(-v.y, v.x)


def primitive(v: Vec2) -> Tuple[Vec2, int]:
    """Split ``v`` into ``(u, w)`` with ``v == w * u``.

    ``w = gcd(|x|, |y|) >= 0`` is the (lattice) weight and ``u`` is the
    primitive direction. The zero vector returns ``(Vec2(0, 0), 0)``.
    """
    g = math.gcd(abs(v.x), abs(v.y))
    if g == 0:
        return ZERO, 0
    return Vec2(v.x // g, v.y // g), g


def weight(v: Vec2) -> int:
    """The lattice length ``gcd(|x|, |y|)`` of ``v``."""
    return math.gcd(abs(v.x), abs(v.y))


# ---------------------------------------------------------------------------
# Angular ordering (exact, no atan2)
# ---------------------------------------------------------------------------
def _half(v: Vec2) -> int:
    """0 for the upper half-plane (angle in [0, pi)), 1 for the lower.

    The positive x-axis is in half 0; the negative x-axis is in half 1. Used to
    give a total angular order together with the cross product.
    """
    if v.y > 0 or (v.y == 0 and v.x > 0):
        return 0
    return 1


def _angle_cmp(a: Vec2, b: Vec2) -> int:
    """Compare two nonzero vectors by angle in ``[0, 2*pi)`` (exact)."""
    ha, hb = _half(a), _half(b)
    if ha != hb:
        return -1 if ha < hb else 1
    c = cross(a, b)
    if c > 0:
        return -1  # a is clockwise-before b -> smaller angle
    if c < 0:
        return 1
    return 0  # same direction


angle_key = cmp_to_key(_angle_cmp)


def sort_by_angle(vectors: Sequence[Vec2]) -> List[Vec2]:
    """Return ``vectors`` sorted by increasing angle in ``[0, 2*pi)``."""
    return sorted(vectors, key=angle_key)


def polygon_from_edge_vectors(edge_vectors: Sequence[Vec2]) -> List[Vec2]:
    """Assemble a convex lattice polygon from edge vectors summing to zero.

    The edge vectors are sorted by angle and accumulated from the origin,
    yielding the vertices of a convex polygon traversed counter-clockwise. The
    caller guarantees ``sum(edge_vectors) == 0`` (raises otherwise).

    Returns the list of vertices (length ``len(edge_vectors)``), the first at
    the origin. Degenerate zero edge vectors are ignored.
    """
    nonzero = [v for v in edge_vectors if not v.is_zero()]
    total = Vec2(sum(v.x for v in nonzero), sum(v.y for v in nonzero))
    if not total.is_zero():
        raise ValueError("edge vectors must sum to zero to close a polygon")
    ordered = sort_by_angle(nonzero)
    verts: List[Vec2] = [ZERO]
    for v in ordered[:-1]:
        verts.append(verts[-1] + v)
    return verts


def polygon_area2(verts: Sequence[Vec2]) -> int:
    """Twice the absolute (lattice) area of a simple polygon (shoelace)."""
    s = 0
    n = len(verts)
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        s += a.x * b.y - b.x * a.y
    return abs(s)


def convex_hull(points: Sequence[Vec2]) -> List[Vec2]:
    """Convex hull (counter-clockwise) of lattice points via monotone chain.

    Returns hull vertices with no collinear interior points and no repeated
    final point. Handles duplicates; returns the unique points for <= 2 inputs.
    """
    pts = sorted(set((p.x, p.y) for p in points))
    if len(pts) <= 1:
        return [Vec2(x, y) for x, y in pts]
    if len(pts) == 2:
        return [Vec2(x, y) for x, y in pts]

    def crs(o, a, b) -> int:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[int, int]] = []
    for p in pts:
        while len(lower) >= 2 and crs(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[int, int]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and crs(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [Vec2(x, y) for x, y in hull]
