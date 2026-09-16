"""Constructors for a few standard combinatorial types (for tests and demos)."""

from __future__ import annotations

from .curve import Curve
from .geometry import Vec2
from .balancing import resolve_slopes


def standard_line() -> Curve:
    """The standard degree-1 tropical line: one trivalent vertex, ends in
    directions (-1, 0), (0, -1), (1, 1). Newton polygon is the unit triangle."""
    c = Curve()
    c.add_vertex("v0")
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    c.add_end("b", "v0", Vec2(0, -1), name="b")
    c.add_end("d", "v0", Vec2(1, 1), name="d")
    return c


def caterpillar_square() -> Curve:
    """A 4-ended rational curve with one bounded edge, dual to the unit square.

    Vertices v0 -- e -- v1; ends a=(-1,0), b=(0,-1) at v0 and c=(1,0), d=(0,1)
    at v1. The bounded edge ``e`` is solved by balancing to (1, 1).
    """
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", name="e")  # vec solved below
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    c.add_end("b", "v0", Vec2(0, -1), name="b")
    c.add_end("c", "v1", Vec2(1, 0), name="c")
    c.add_end("d", "v1", Vec2(0, 1), name="d")
    resolve_slopes(c)
    return c
