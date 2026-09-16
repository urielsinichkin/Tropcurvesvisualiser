"""The abstract combinatorial type: a rational plane tropical curve.

The object of record is *tree + slopes + markings* plus presentation (names and
colors). Genus 0 means the graph on vertices and bounded edges is a tree; ends
and markings are legs attached at vertices.

Orientation convention: a bounded edge stores a single integer direction
``vec`` from ``tail`` to ``head``. The *outgoing* vector at ``tail`` is ``+vec``
and at ``head`` is ``-vec``. Ends store ``vec`` pointing outward from their
attachment vertex. Markings are contracted ends with ``vec == (0, 0)``.

Balancing at a vertex ``V`` is ``sum of outgoing vectors of incident edges = 0``.
"""

from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .geometry import Vec2, ZERO, primitive


class EdgeKind(enum.Enum):
    BOUNDED = "bounded"
    END = "end"
    MARKING = "marking"


@dataclass
class Edge:
    """A bounded edge, an unbounded end, or a marking (contracted end)."""

    id: str
    kind: EdgeKind
    tail: str  # vertex id; for END/MARKING this is the attachment vertex
    head: Optional[str] = None  # vertex id for BOUNDED, else None
    vec: Vec2 = ZERO  # direction tail->head (BOUNDED) or outward (END); ZERO for MARKING
    name: str = ""
    color: str = "#000000"

    def __post_init__(self) -> None:
        if self.kind is EdgeKind.BOUNDED:
            if self.head is None:
                raise ValueError(f"bounded edge {self.id!r} needs a head vertex")
        else:
            if self.head is not None:
                raise ValueError(f"{self.kind.value} edge {self.id!r} must not have a head")
        if self.kind is EdgeKind.MARKING and not self.vec.is_zero():
            raise ValueError(f"marking {self.id!r} must have zero direction")

    # --- derived quantities --------------------------------------------
    @property
    def weight(self) -> int:
        _, w = primitive(self.vec)
        return w

    @property
    def primitive_dir(self) -> Vec2:
        u, _ = primitive(self.vec)
        return u

    def endpoints(self) -> List[str]:
        return [self.tail] if self.head is None else [self.tail, self.head]

    def other(self, vertex: str) -> Optional[str]:
        if self.kind is not EdgeKind.BOUNDED:
            return None
        if vertex == self.tail:
            return self.head
        if vertex == self.head:
            return self.tail
        raise ValueError(f"vertex {vertex!r} is not an endpoint of edge {self.id!r}")

    def outgoing(self, vertex: str) -> Vec2:
        """The outgoing direction of this edge as seen from ``vertex``."""
        if vertex == self.tail:
            return self.vec
        if self.kind is EdgeKind.BOUNDED and vertex == self.head:
            return -self.vec
        raise ValueError(f"vertex {vertex!r} is not incident to edge {self.id!r}")


class Curve:
    """A rational plane tropical curve (combinatorial type).

    Holds vertices (ids) and edges (by id). Provides incidence, balancing,
    genus, and validation. Slope solving lives in :mod:`tropcurves.balancing`.
    """

    def __init__(self) -> None:
        self.vertices: List[str] = []
        self.edges: Dict[str, Edge] = {}
        self._vset: set[str] = set()

    # --- construction ---------------------------------------------------
    def add_vertex(self, vid: str) -> str:
        if vid in self._vset:
            raise ValueError(f"duplicate vertex id {vid!r}")
        self.vertices.append(vid)
        self._vset.add(vid)
        return vid

    def _check_vertex(self, vid: str) -> None:
        if vid not in self._vset:
            raise ValueError(f"unknown vertex id {vid!r}")

    def add_edge(self, edge: Edge) -> Edge:
        if edge.id in self.edges:
            raise ValueError(f"duplicate edge id {edge.id!r}")
        self._check_vertex(edge.tail)
        if edge.head is not None:
            self._check_vertex(edge.head)
        if edge.name and any(e.name == edge.name for e in self.edges.values()):
            raise ValueError(f"duplicate edge name {edge.name!r}")
        if not edge.name:
            edge.name = self._auto_name(edge.kind)
        self.edges[edge.id] = edge
        return edge

    def add_bounded(self, id: str, tail: str, head: str, vec: Vec2 = ZERO, **kw) -> Edge:
        return self.add_edge(Edge(id, EdgeKind.BOUNDED, tail, head, vec, **kw))

    def add_end(self, id: str, tail: str, vec: Vec2, **kw) -> Edge:
        return self.add_edge(Edge(id, EdgeKind.END, tail, None, vec, **kw))

    def add_marking(self, id: str, tail: str, **kw) -> Edge:
        return self.add_edge(Edge(id, EdgeKind.MARKING, tail, None, ZERO, **kw))

    _NAME_PREFIX = {EdgeKind.BOUNDED: "e", EdgeKind.END: "l", EdgeKind.MARKING: "x"}

    def _auto_name(self, kind: EdgeKind) -> str:
        prefix = self._NAME_PREFIX[kind]
        used = {e.name for e in self.edges.values()}
        for i in itertools.count(1):
            cand = f"{prefix}{i}"
            if cand not in used:
                return cand

    # --- queries --------------------------------------------------------
    def edges_of(self, kind: EdgeKind) -> List[Edge]:
        return [e for e in self.edges.values() if e.kind is kind]

    @property
    def bounded(self) -> List[Edge]:
        return self.edges_of(EdgeKind.BOUNDED)

    @property
    def ends(self) -> List[Edge]:
        return self.edges_of(EdgeKind.END)

    @property
    def markings(self) -> List[Edge]:
        return self.edges_of(EdgeKind.MARKING)

    def incident(self, vertex: str) -> List[Edge]:
        self._check_vertex(vertex)
        return [e for e in self.edges.values() if vertex in e.endpoints()]

    def valence(self, vertex: str) -> int:
        """Number of incident edges (bounded, ends and markings all count)."""
        return len(self.incident(vertex))

    # --- balancing ------------------------------------------------------
    def balancing_residual(self, vertex: str) -> Vec2:
        total = ZERO
        for e in self.incident(vertex):
            total = total + e.outgoing(vertex)
        return total

    def is_balanced(self, vertex: Optional[str] = None) -> bool:
        vs = self.vertices if vertex is None else [vertex]
        return all(self.balancing_residual(v).is_zero() for v in vs)

    # --- topology -------------------------------------------------------
    def components_and_cycles(self) -> tuple[int, int]:
        """Return ``(#connected components, first Betti number)`` of the graph
        on vertices and bounded edges (legs ignored)."""
        parent = {v: v for v in self.vertices}

        def find(a: str) -> str:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        n_edges = 0
        for e in self.bounded:
            n_edges += 1
            ra, rb = find(e.tail), find(e.head)  # type: ignore[arg-type]
            if ra != rb:
                parent[ra] = rb
        roots = {find(v) for v in self.vertices}
        comps = len(roots)
        betti = n_edges - len(self.vertices) + comps
        return comps, betti

    @property
    def genus(self) -> int:
        _, betti = self.components_and_cycles()
        return betti

    def is_connected(self) -> bool:
        if not self.vertices:
            return True
        comps, _ = self.components_and_cycles()
        return comps == 1

    def is_tree(self) -> bool:
        return self.is_connected() and self.genus == 0

    # --- validation -----------------------------------------------------
    def validate(self, *, require_balanced: bool = True) -> None:
        """Raise ``ValueError`` if the curve is not a valid genus-0 type.

        Checks: connected tree (genus 0), no zero-length bounded edge, ends and
        markings well-formed, and (optionally) balancing at every vertex.
        """
        if not self.vertices:
            raise ValueError("curve has no vertices")
        if not self.is_connected():
            raise ValueError("curve is not connected")
        if self.genus != 0:
            raise ValueError(f"curve has genus {self.genus}, expected 0 (a tree)")
        for e in self.bounded:
            if e.vec.is_zero():
                raise ValueError(f"bounded edge {e.name!r} ({e.id!r}) is degenerate (zero vector)")
        for e in self.ends:
            if e.vec.is_zero():
                raise ValueError(f"end {e.name!r} ({e.id!r}) has zero direction")
        if require_balanced:
            for v in self.vertices:
                r = self.balancing_residual(v)
                if not r.is_zero():
                    raise ValueError(f"vertex {v!r} is not balanced (residual {r.to_list()})")

    # --- presentation edits --------------------------------------------
    def rename_edge(self, edge_id: str, new_name: str) -> None:
        if edge_id not in self.edges:
            raise ValueError(f"unknown edge id {edge_id!r}")
        if not new_name:
            raise ValueError("name must be non-empty")
        for e in self.edges.values():
            if e.id != edge_id and e.name == new_name:
                raise ValueError(f"duplicate edge name {new_name!r}")
        self.edges[edge_id].name = new_name

    def set_color(self, edge_id: str, color: str) -> None:
        if edge_id not in self.edges:
            raise ValueError(f"unknown edge id {edge_id!r}")
        self.edges[edge_id].color = color

    def copy(self) -> "Curve":
        import dataclasses

        new = Curve()
        new.vertices = list(self.vertices)
        new._vset = set(self._vset)
        # Vec2 and str fields are immutable, so a field-wise dataclass copy is a
        # safe deep-enough clone of each edge.
        new.edges = {eid: dataclasses.replace(e) for eid, e in self.edges.items()}
        return new

    def __repr__(self) -> str:
        return (f"Curve(vertices={len(self.vertices)}, bounded={len(self.bounded)}, "
                f"ends={len(self.ends)}, markings={len(self.markings)}, genus={self.genus})")
