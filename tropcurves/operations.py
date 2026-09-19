"""Structural operations that derive new combinatorial types.

* :func:`contract_edge` -- contract a bounded edge, merging its endpoints.
* :func:`resolutions` / :func:`apply_resolution` -- resolve a 4-valent vertex
  into a trivalent one by inserting a new bounded edge (v1: 4-valent only).

Both preserve the ends, hence the Newton polygon. Each returns enough of an
element map (vertex identifications, new edge ids) for the workspace to
propagate edits from a parent to a derived child.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .curve import Curve, Edge, EdgeKind
from .geometry import Vec2, ZERO
from .balancing import resolve_slopes


# ---------------------------------------------------------------------------
# contraction
# ---------------------------------------------------------------------------
@dataclass
class ContractResult:
    curve: Curve
    merged_vertex: str                 # surviving vertex id
    removed_vertex: str                # id that was merged away
    vertex_map: Dict[str, str]         # parent vertex id -> child vertex id
    removed_edge: str                  # contracted edge id


def contract_edge(curve: Curve, edge_id: str) -> ContractResult:
    """Contract the bounded edge ``edge_id``, merging its two endpoints.

    The head vertex is merged into the tail; every edge incident to the head is
    reattached to the tail. Slopes are unchanged, so the merged vertex stays
    balanced. Returns the new curve and the vertex identification.
    """
    e = curve.edges.get(edge_id)
    if e is None:
        raise ValueError(f"unknown edge id {edge_id!r}")
    if e.kind is not EdgeKind.BOUNDED:
        raise ValueError(f"can only contract a bounded edge, not {e.kind.value}")

    keep, drop = e.tail, e.head  # type: ignore[assignment]
    new = curve.copy()
    del new.edges[edge_id]
    for other in new.edges.values():
        if other.tail == drop:
            other.tail = keep
        if other.head == drop:
            other.head = keep
    new.vertices = [v for v in new.vertices if v != drop]
    new._vset.discard(drop)

    vmap = {v: v for v in curve.vertices}
    vmap[drop] = keep
    return ContractResult(curve=new, merged_vertex=keep, removed_vertex=drop,
                          vertex_map=vmap, removed_edge=edge_id)


# ---------------------------------------------------------------------------
# resolution of a vertex of valence >= 4
# ---------------------------------------------------------------------------
@dataclass
class Resolution:
    """One resolution of a vertex: its flags split in two, joined by an edge.

    ``side_a`` / ``side_b`` are the flag ids on each of the two new vertices --
    every flag of the original vertex, in one group or the other, each group
    holding at least two so that neither new vertex is 2-valent.
    ``new_edge_vec`` is the direction of the inserted bounded edge (outgoing
    from the ``side_a`` vertex), forced by balancing. ``is_crossing`` is True
    when that comes out zero: the split realizes as a transverse crossing
    (parallelogram) rather than a genuine bounded edge, and cannot be applied.

    A 4-valent vertex has only 2+2 splits, so both new vertices are trivalent
    and the result is a maximal cell of the moduli space. Splitting a bigger
    vertex is still one step -- the pieces may need resolving in turn.
    """

    vertex: str
    side_a: Tuple[str, ...]
    side_b: Tuple[str, ...]
    new_edge_vec: Vec2
    is_crossing: bool

    def label(self, curve: Curve) -> str:
        def nm(group):
            return "{" + ", ".join(sorted(curve.edges[i].name for i in group)) + "}"
        kind = "crossing" if self.is_crossing else "edge"
        return f"{nm(self.side_a)} | {nm(self.side_b)}  ({kind})"


def _incident_flags(curve: Curve, vertex: str) -> List[Edge]:
    return curve.incident(vertex)


def resolution_for_sides(curve: Curve, vertex: str,
                         side_a: Iterable[str], side_b: Iterable[str]) -> Resolution:
    """The resolution splitting ``vertex``'s flags into these two groups.

    The groups must together be exactly the flags at the vertex, with at least
    two in each -- a group of one would leave a 2-valent vertex, which says
    nothing new, and an empty one no vertex at all. The inserted edge's
    direction is then forced by balancing.
    """
    flags = _incident_flags(curve, vertex)
    present = {f.id for f in flags}
    a, b = tuple(side_a), tuple(side_b)
    both = list(a) + list(b)
    if len(set(both)) != len(both) or set(both) != present:
        raise ValueError(
            f"the two sides must partition the {len(present)} flags at {vertex!r}"
        )
    if len(a) < 2 or len(b) < 2:
        raise ValueError("each side needs at least two flags")
    outs = {f.id: f.outgoing(vertex) for f in flags}
    vec = -sum((outs[i] for i in a), ZERO)
    return Resolution(vertex=vertex, side_a=a, side_b=b,
                      new_edge_vec=vec, is_crossing=vec.is_zero())


def resolution_for_subset(curve: Curve, vertex: str, subset: Iterable[str]) -> Resolution:
    """The resolution putting ``subset`` on one new vertex and the rest on the other."""
    chosen = tuple(dict.fromkeys(subset))    # de-duplicate, keep order
    rest = tuple(f.id for f in _incident_flags(curve, vertex) if f.id not in set(chosen))
    return resolution_for_sides(curve, vertex, chosen, rest)


def resolutions(curve: Curve, vertex: str, *, include_crossings: bool = False) -> List[Resolution]:
    """Every resolution of a vertex of valence >= 4.

    One per way of splitting the flags in two (the two sides are interchangeable,
    so each split is listed once). By default only genuine resolutions -- a
    nonzero inserted edge -- are returned; ``include_crossings=True`` also lists
    the splits that realize as a crossing.

    The count grows quickly with valence (3 splits at valence 4, 10 at 5, 25 at
    6), so past 4 the UI has you choose a side rather than reading a list.
    """
    flags = _incident_flags(curve, vertex)
    d = len(flags)
    if d < 4:
        raise ValueError(f"vertex {vertex!r} has valence {d}; nothing to resolve below 4")
    ids = [f.id for f in flags]
    out: List[Resolution] = []
    # Each split has exactly one side containing ids[0], of size 2 .. d-2, so
    # enumerating those subsets lists every split exactly once.
    for size in range(2, d - 1):
        for rest in itertools.combinations(ids[1:], size - 1):
            res = resolution_for_subset(curve, vertex, (ids[0],) + rest)
            if res.is_crossing and not include_crossings:
                continue
            out.append(res)
    return out


@dataclass
class ResolveResult:
    curve: Curve
    vertex_a: str
    vertex_b: str
    new_edge: str
    vertex_map: Dict[str, str]   # parent vertex -> child vertex (the 4-valent one -> vertex_a)


def apply_resolution(curve: Curve, res: Resolution,
                     *, new_vertex_id: Optional[str] = None,
                     new_edge_id: Optional[str] = None) -> ResolveResult:
    """Build the child curve for a resolution (must be a genuine, nonzero edge)."""
    if res.is_crossing:
        raise ValueError("cannot insert a bounded edge for a crossing resolution")
    v = res.vertex
    new = curve.copy()
    va = v                                   # reuse v as the side_a vertex
    vb = new_vertex_id or _fresh_vertex_id(new, v)
    new.add_vertex(vb)
    # move side_b flags from v to vb
    for eid in res.side_b:
        e = new.edges[eid]
        if e.tail == v:
            e.tail = vb
        elif e.head == v:
            e.head = vb
    eid_new = new_edge_id or _fresh_edge_id(new)
    new.add_bounded(eid_new, va, vb, res.new_edge_vec)
    vmap = {vv: vv for vv in curve.vertices}
    vmap[v] = va
    return ResolveResult(curve=new, vertex_a=va, vertex_b=vb, new_edge=eid_new, vertex_map=vmap)


@dataclass
class EdgeMarkingResult:
    """What :func:`add_marking_on_edge` did -- an element map for propagation.

    ``split_edge`` kept the subdivided edge's id and ``new_edge`` is the piece
    that was cut off it. At ``moved_flag_vertex`` -- the endpoint that ended up
    on the far side of the new vertex -- the flag that used to be ``split_edge``
    is now ``new_edge``; every other flag in the curve is untouched. Derived
    types record their operations by flag id, so this is what they need in
    order to keep meaning the same thing (see ``Workspace._remap_after_split``).
    """

    vertex: str               # the new vertex, carrying the marking
    new_edge: str             # the bounded piece cut off the original edge
    marking: str
    split_edge: str           # the piece that kept the original id
    moved_flag_vertex: str


def add_marking_on_edge(curve: Curve, edge_id: str, *, marking_id: Optional[str] = None,
                        name: str = "", color: str = "",
                        reserved: Iterable[str] = ()) -> EdgeMarkingResult:
    """Attach a marking part-way along an edge or end. Mutates ``curve``.

    The edge is subdivided: a new vertex is introduced on it and both pieces
    keep the edge's direction vector, so they leave the new vertex in exactly
    opposite directions. Together with the marking (a contracted end, direction
    zero) the new vertex is therefore balanced automatically, and since this
    adds one vertex and one bounded edge the curve stays a tree.

    Subdividing an **end** keeps the original id and name on the unbounded
    piece, so an end remains the same end -- ends carry the Newton polygon and
    are what slope editing refers to -- and the new bounded piece gets a fresh
    id. For a bounded edge the original id stays on the tail-side piece.

    ``reserved`` names ids that must not be handed out even though they are
    free in this curve; the workspace passes the ids its derived types have
    already claimed, so a subdivision here cannot collide with them there.
    """
    e = curve.edges.get(edge_id)
    if e is None:
        raise ValueError(f"unknown edge id {edge_id!r}")
    if e.kind is EdgeKind.MARKING:
        raise ValueError("a marking cannot carry another marking")

    reserved = frozenset(reserved)
    w = _fresh_vertex_id(curve, e.tail, reserved)
    curve.add_vertex(w)
    new_edge_id = _fresh_edge_id(curve, reserved)

    if e.kind is EdgeKind.BOUNDED:
        head = e.head
        e.head = w                                      # tail --e--> w
        curve.add_bounded(new_edge_id, w, head, e.vec)  # w --new--> head
        moved = head
    else:
        tail = e.tail
        curve.add_bounded(new_edge_id, tail, w, e.vec)  # tail --new--> w
        e.tail = w                                      # the end now leaves w
        moved = tail

    mid = marking_id or _fresh_marking_id(curve, reserved)
    curve.add_marking(mid, w, name=name, color=color)
    return EdgeMarkingResult(vertex=w, new_edge=new_edge_id, marking=mid,
                             split_edge=edge_id, moved_flag_vertex=moved)  # type: ignore[arg-type]


def _fresh_marking_id(curve: Curve, reserved: Iterable[str] = ()) -> str:
    taken = set(curve.edges) | set(reserved)
    for i in itertools.count(1):
        cand = f"m{i}"
        if cand not in taken:
            return cand


def _fresh_vertex_id(curve: Curve, base: str, reserved: Iterable[str] = ()) -> str:
    taken = set(curve._vset) | set(reserved)
    for i in itertools.count(1):
        cand = f"{base}_{i}"
        if cand not in taken:
            return cand


def _fresh_edge_id(curve: Curve, reserved: Iterable[str] = ()) -> str:
    taken = set(curve.edges) | set(reserved)
    for i in itertools.count(1):
        cand = f"edge_{i}"
        if cand not in taken:
            return cand
