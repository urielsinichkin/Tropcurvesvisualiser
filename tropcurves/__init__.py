"""Tropical Curves Visualiser — core library.

Pure-Python, exact-integer core for rational (genus 0) plane parametrized
tropical curves. See ``docs/DESIGN.md``.
"""

from .geometry import Vec2, primitive, rot90, cross, dot, convex_hull
from .curve import Curve, Edge, EdgeKind
from .balancing import (
    SlopeSolveError,
    solve_bounded,
    resolve_slopes,
    apply_two_ends_edit,
)
from .newton import newton_polygon
from . import schema

__all__ = [
    "Vec2",
    "primitive",
    "rot90",
    "cross",
    "dot",
    "convex_hull",
    "Curve",
    "Edge",
    "EdgeKind",
    "SlopeSolveError",
    "solve_bounded",
    "resolve_slopes",
    "apply_two_ends_edit",
    "newton_polygon",
    "schema",
]

__version__ = "0.1.0"
