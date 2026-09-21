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
from .operations import (
    contract_edge,
    resolutions,
    resolution_for_sides,
    resolution_for_subset,
    apply_resolution,
    Resolution,
)
from .refined import (
    refined_multiplicity,
    vertex_multiplicity,
    balanced_split,
    q_integer_minus,
    q_integer_plus,
    MultiplicityError,
    RefinedValue,
    Laurent,
)
from .subdivision_import import import_subdivision
from .workspace import Workspace, TypeNode, Operation
from .api import Session
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
    "resolution_for_sides",
    "resolution_for_subset",
    "refined_multiplicity",
    "vertex_multiplicity",
    "balanced_split",
    "q_integer_minus",
    "q_integer_plus",
    "MultiplicityError",
    "RefinedValue",
    "Laurent",
    "import_subdivision",
    "Workspace",
    "TypeNode",
    "Operation",
    "Session",
    "schema",
]

__version__ = "0.1.0"
