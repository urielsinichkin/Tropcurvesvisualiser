"""Tropical Curves Visualiser — core library.

Pure-Python, exact-integer core for rational (genus 0) plane parametrized
tropical curves. See ``docs/DESIGN.md``.
"""

from .geometry import Vec2, primitive, rot90, cross, dot, convex_hull, polygon_area2
from .curve import Curve, Edge, EdgeKind
from .balancing import (
    SlopeSolveError,
    solve_bounded,
    resolve_slopes,
    apply_two_ends_edit,
)
from .newton import newton_polygon
from .layout import embed, readable_lengths, generic_lengths
from .subdivision import build_subdivision, Subdivision, SubdivisionCell, SubdivisionError
from .operations import contract_edge, resolutions, apply_resolution, Resolution
from .workspace import Workspace, TypeNode, Operation
from . import schema

__all__ = [
    "Vec2",
    "primitive",
    "rot90",
    "cross",
    "dot",
    "convex_hull",
    "polygon_area2",
    "Curve",
    "Edge",
    "EdgeKind",
    "SlopeSolveError",
    "solve_bounded",
    "resolve_slopes",
    "apply_two_ends_edit",
    "newton_polygon",
    "embed",
    "readable_lengths",
    "generic_lengths",
    "build_subdivision",
    "Subdivision",
    "SubdivisionCell",
    "SubdivisionError",
    "contract_edge",
    "resolutions",
    "apply_resolution",
    "Resolution",
    "Workspace",
    "TypeNode",
    "Operation",
    "schema",
]

__version__ = "0.1.0"
