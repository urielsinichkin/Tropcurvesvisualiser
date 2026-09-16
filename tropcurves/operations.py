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
from typing import Dict, List, Optional, Tuple

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
# resolution of a 4-valent vertex
# ---------------------------------------------------------------------------
@dataclass
class Resolution:
    """One trivalent resolution of a 4-valent vertex.

    ``side_a`` / ``side_b`` are the edge-id pairs on each new vertex, and
    ``new_edge_vec`` is the direction of the inserted bounded edge (outgoing from
    the ``side_a`` vertex), forced by balancing. ``is_crossing`` is True when the
    forced edge is zero -- the pairing realizes as a transverse crossing
    (parallelogram) rather than a genuine bounded edge, and is not offered as a
    trivalent resolution.
    """

    vertex: str
    side_a: Tuple[str, str]
    side_b: Tuple[str, str]
    new_edge_vec: Vec2
    is_crossing: bool

    def label(self, curve: Curve) -> str:
        def nm(pair):
            return "{" + ", ".join(sorted(curve.edges[i].name for i in pair)) + "}"
        kind = "crossing" if self.is_crossing else "edge"
        return f"{nm(self.side_a)} | {nm(self.side_b)}  ({kind})"


def _incident_flags(curve: Curve, vertex: str) -> List[Edge]:
    return curve.incident(vertex)


def resolutions(curve: Curve, vertex: str, *, include_crossings: bool = False) -> List[Resolution]:
    """All (up to 3) resolutions of a 4-valent vertex.

    By default returns only genuine trivalent resolutions (a nonzero inserted
    edge). Set ``include_crossings=True`` to also list the pairing(s) that
    realize as a crossing (zero inserted edge).
    """
    flags = _incident_flags(curve, vertex)
    if len(flags) != 4:
        raise ValueError(
            f"vertex {vertex!r} has valence {len(flags)}; v1 resolves only 4-valent vertices"
        )
    outs = {f.id: f.outgoing(vertex) for f in flags}
    ids = [f.id for f in flags]
    out: List[Resolution] = []
    # the three ways to split 4 flags into 2 + 2 (fix ids[0], pair it with each)
    for j in (1, 2, 3):
        a = (ids[0], ids[j])
        b = tuple(i for i in ids if i not in a)  # type: ignore[assignment]
        vec = -(outs[a[0]] + outs[a[1]])
        is_crossing = vec.is_zero()
        if is_crossing and not include_crossings:
            continue
        out.append(Resolution(vertex=vertex, side_a=a, side_b=b,  # type: ignore[arg-type]
                              new_edge_vec=vec, is_crossing=is_crossing))
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


def _fresh_vertex_id(curve: Curve, base: str) -> str:
    for i in itertools.count(1):
        cand = f"{base}_{i}"
        if cand not in curve._vset:
            return cand


def _fresh_edge_id(curve: Curve) -> str:
    for i in itertools.count(1):
        cand = f"edge_{i}"
        if cand not in curve.edges:
            return cand
