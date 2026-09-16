"""Workspace: a forest of combinatorial types with edit propagation.

Types (nodes) are derived from one another by contraction/resolution, forming a
forest. Each node has a ``follow_parent`` flag (default True). Editing a node
propagates **transitively** to every following descendant by *replaying* that
descendant's operation on the updated parent, so parent slopes/markings/names/
colors flow down. A descendant whose ``follow_parent`` is False (and its whole
subtree) is left untouched.

v1 propagation is all-or-nothing per node. The replay machinery is deliberately
per-node so that selective (per-element/per-attribute) propagation can be added
later without reworking the model -- see ``docs/POSTPONED.md``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .curve import Curve, EdgeKind
from .geometry import Vec2, ZERO
from .balancing import apply_two_ends_edit
from .operations import (
    contract_edge,
    resolutions,
    apply_resolution,
    Resolution,
)

STATUS_OK = "ok"
STATUS_NEEDS_ATTENTION = "needs_attention"


@dataclass
class Operation:
    """How a node was derived from its parent."""

    kind: str                              # 'contract' | 'resolve'
    edge_id: Optional[str] = None          # contract: the contracted edge
    vertex_id: Optional[str] = None        # resolve: the 4-valent parent vertex
    side_a: Optional[Tuple[str, str]] = None
    side_b: Optional[Tuple[str, str]] = None
    new_vertex_id: Optional[str] = None    # resolve: the inserted child vertex
    new_edge_id: Optional[str] = None      # resolve: the inserted child edge


@dataclass
class TypeNode:
    id: str
    curve: Curve
    name: str
    parent_id: Optional[str] = None
    operation: Optional[Operation] = None
    follow_parent: bool = True
    children: List[str] = field(default_factory=list)
    status: str = STATUS_OK


class Workspace:
    def __init__(self) -> None:
        self.nodes: Dict[str, TypeNode] = {}
        self._counter = itertools.count(1)

    # --- ids ------------------------------------------------------------
    def _new_id(self) -> str:
        while True:
            cand = f"T{next(self._counter)}"
            if cand not in self.nodes:
                return cand

    # --- construction ---------------------------------------------------
    def add_root(self, curve: Curve, name: Optional[str] = None) -> TypeNode:
        nid = self._new_id()
        node = TypeNode(id=nid, curve=curve, name=name or nid)
        self.nodes[nid] = node
        return node

    def contract(self, node_id: str, edge_id: str, name: Optional[str] = None) -> TypeNode:
        parent = self._get(node_id)
        result = contract_edge(parent.curve, edge_id)
        op = Operation(kind="contract", edge_id=edge_id)
        return self._add_child(parent, result.curve, op, name)

    def resolve(self, node_id: str, res: Resolution, name: Optional[str] = None) -> TypeNode:
        parent = self._get(node_id)
        out = apply_resolution(parent.curve, res)
        op = Operation(
            kind="resolve",
            vertex_id=res.vertex,
            side_a=res.side_a,
            side_b=res.side_b,
            new_vertex_id=out.vertex_b,
            new_edge_id=out.new_edge,
        )
        return self._add_child(parent, out.curve, op, name)

    def _add_child(self, parent: TypeNode, curve: Curve, op: Operation,
                   name: Optional[str]) -> TypeNode:
        nid = self._new_id()
        node = TypeNode(id=nid, curve=curve, name=name or nid,
                        parent_id=parent.id, operation=op)
        self.nodes[nid] = node
        parent.children.append(nid)
        return node

    # --- edits (each propagates to following descendants) --------------
    def edit_slopes(self, node_id: str, edit_end_id: str, new_vec: Vec2,
                    dependent_end_id: str) -> None:
        node = self._get(node_id)
        apply_two_ends_edit(node.curve, edit_end_id, new_vec, dependent_end_id)
        self._propagate(node_id)

    def add_marking(self, node_id: str, vertex: str, *, id: Optional[str] = None,
                    name: Optional[str] = None, color: str = "") -> str:
        node = self._get(node_id)
        mid = id or self._fresh_marking_id(node.curve)
        node.curve.add_marking(mid, vertex, name=name or "", color=color)
        self._propagate(node_id)
        return mid

    def remove_marking(self, node_id: str, marking_id: str) -> None:
        node = self._get(node_id)
        e = node.curve.edges.get(marking_id)
        if e is None or e.kind is not EdgeKind.MARKING:
            raise ValueError(f"{marking_id!r} is not a marking")
        del node.curve.edges[marking_id]
        self._propagate(node_id)

    def rename_edge(self, node_id: str, edge_id: str, new_name: str) -> None:
        node = self._get(node_id)
        node.curve.rename_edge(edge_id, new_name)
        self._propagate(node_id)

    def set_color(self, node_id: str, edge_id: str, color: str) -> None:
        node = self._get(node_id)
        node.curve.set_color(edge_id, color)
        self._propagate(node_id)

    def set_follow(self, node_id: str, follow: bool) -> None:
        self._get(node_id).follow_parent = follow

    def rename_node(self, node_id: str, name: str) -> None:
        self._get(node_id).name = name

    # --- propagation ----------------------------------------------------
    def _propagate(self, node_id: str) -> None:
        node = self.nodes[node_id]
        for cid in node.children:
            child = self.nodes[cid]
            if not child.follow_parent:
                continue
            self._rederive(child)
            self._propagate(cid)

    def _rederive(self, node: TypeNode) -> None:
        parent = self.nodes[node.parent_id]  # type: ignore[index]
        op = node.operation
        assert op is not None
        try:
            if op.kind == "contract":
                node.curve = contract_edge(parent.curve, op.edge_id).curve  # type: ignore[arg-type]
            elif op.kind == "resolve":
                node.curve = self._replay_resolve(parent.curve, node, op)
            else:
                raise ValueError(f"unknown operation {op.kind!r}")
            node.status = STATUS_OK
        except Exception:
            node.status = STATUS_NEEDS_ATTENTION

    def _replay_resolve(self, parent_curve: Curve, node: TypeNode, op: Operation) -> Curve:
        want = {frozenset(op.side_a), frozenset(op.side_b)}  # type: ignore[arg-type]
        matches = [
            r for r in resolutions(parent_curve, op.vertex_id, include_crossings=True)  # type: ignore[arg-type]
            if {frozenset(r.side_a), frozenset(r.side_b)} == want and not r.is_crossing
        ]
        if not matches:
            raise ValueError("resolution no longer applies")
        out = apply_resolution(parent_curve, matches[0],
                               new_vertex_id=op.new_vertex_id, new_edge_id=op.new_edge_id)
        # preserve the inserted edge's presentation (name/color) across replays
        old = node.curve.edges.get(op.new_edge_id)  # type: ignore[arg-type]
        if old is not None:
            ne = out.curve.edges[op.new_edge_id]  # type: ignore[index]
            ne.name = old.name
            ne.color = old.color
        return out.curve

    # --- helpers --------------------------------------------------------
    def _get(self, node_id: str) -> TypeNode:
        if node_id not in self.nodes:
            raise ValueError(f"unknown node id {node_id!r}")
        return self.nodes[node_id]

    def _fresh_marking_id(self, curve: Curve) -> str:
        for i in itertools.count(1):
            cand = f"m{i}"
            if cand not in curve.edges:
                return cand

    def roots(self) -> List[TypeNode]:
        return [n for n in self.nodes.values() if n.parent_id is None]
