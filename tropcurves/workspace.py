"""Workspace: a forest of combinatorial types with edit propagation.

Types (nodes) are derived from one another by contraction/resolution, forming a
forest. Each node records the steps that derive it from its parent -- usually
one, more once a type in between has been deleted -- and has a
``follow_parent`` flag (default True). Editing a node propagates
**transitively** to every following descendant by *replaying* those steps on
the updated parent, so parent slopes/markings/names/colors flow down. A
descendant whose ``follow_parent`` is False (and its whole subtree) is left
untouched.

Deleting a type never removes anything else: its children move up to its
parent, carrying its steps in front of their own, so each stays the same
derivation expressed from one type further up.

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
    resolution_for_sides,
    apply_resolution,
    add_marking_on_edge,
    EdgeMarkingResult,
    Resolution,
    _fresh_edge_id,
    _fresh_vertex_id,
)

STATUS_OK = "ok"
STATUS_NEEDS_ATTENTION = "needs_attention"


@dataclass
class Operation:
    """How a node was derived from its parent."""

    kind: str                              # 'contract' | 'resolve'
    edge_id: Optional[str] = None          # contract: the contracted edge
    split_pieces: List[str] = field(default_factory=list)
    """contract: further pieces the contracted edge has since been split into.

    Subdividing an edge in the parent (to hang a marking on it) turns one edge
    into two. A child that contracts it should still identify the same two
    vertices, so the replay contracts every piece -- the marking then lands on
    the merged vertex, which is exactly where a marked point in the interior of
    a shrinking edge ends up.
    """
    vertex_id: Optional[str] = None        # resolve: the 4-valent parent vertex
    side_a: Optional[Tuple[str, ...]] = None    # resolve: the flags on each side
    side_b: Optional[Tuple[str, ...]] = None
    new_vertex_id: Optional[str] = None    # resolve: the inserted child vertex
    new_edge_id: Optional[str] = None      # resolve: the inserted child edge


@dataclass
class TypeNode:
    id: str
    curve: Curve
    name: str
    parent_id: Optional[str] = None
    operations: List[Operation] = field(default_factory=list)
    """How this type is derived from its parent, in order.

    Usually one step. It grows when the type in between is deleted: the
    deleted type's steps are prepended, so this type is still exactly what it
    was, now expressed from further up. A root has none.
    """
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

    def duplicate(self, node_id: str, name: Optional[str] = None) -> TypeNode:
        """Copy a type into a new, independent **root**.

        The copy carries the same graph, slopes, markings, names and colors, but
        gets no parent, no derivation operation and none of the original's
        children. That keeps it genuinely independent: editing either one leaves
        the other alone, and no propagation can overwrite the copy. (A copy that
        still followed the original's parent would just be re-derived away.)
        """
        src = self._get(node_id)
        return self.add_root(src.curve.copy(), name=name or self._fresh_node_name(src.name))

    def descendants(self, node_id: str) -> List[str]:
        """Every type derived from this one, transitively."""
        out: List[str] = []
        stack = list(self._get(node_id).children)
        while stack:
            nid = stack.pop()
            node = self.nodes.get(nid)
            if node is None:
                continue
            out.append(nid)
            stack.extend(node.children)
        return out

    def delete(self, node_id: str) -> str:
        """Remove one type. Nothing else is ever removed with it.

        Its derived types take its place rather than being cut loose: each one
        moves up to the deleted type's parent, with the deleted type's steps
        prepended to its own, so it is still exactly the same derivation --
        contract this, then resolve that -- just expressed from one type
        further up. Deleting a root leaves its children as independent roots,
        since there is nothing left to derive them from.

        Edits made *directly* to the deleted type (a marking added on it, a
        recolor) are not part of any recorded step, so they go with it: a
        later re-derivation rebuilds its children without them. Nothing is
        re-derived now, though -- deleting one type does not redraw another.
        """
        node = self._get(node_id)
        parent = self.nodes.get(node.parent_id) if node.parent_id else None
        for cid in node.children:
            child = self.nodes.get(cid)
            if child is None:
                continue
            if parent is None:
                child.parent_id = None
                child.operations = []
                child.follow_parent = True
                child.status = STATUS_OK
            else:
                child.parent_id = parent.id
                child.operations = [*node.operations, *child.operations]
                # a type that was not following stays not following: the break
                # was put there on purpose, and merging must not undo it
                child.follow_parent = child.follow_parent and node.follow_parent
        if parent is not None:
            # keep the deleted type's place in the parent's list
            at = parent.children.index(node_id)
            parent.children[at:at + 1] = node.children
        self.nodes.pop(node_id, None)
        return node_id

    def _fresh_node_name(self, base: str) -> str:
        used = {n.name for n in self.nodes.values()}
        cand = f"{base} copy"
        if cand not in used:
            return cand
        for i in itertools.count(2):
            numbered = f"{base} copy {i}"
            if numbered not in used:
                return numbered

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
                        parent_id=parent.id, operations=[op])
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

    def add_marking_on_edge(self, node_id: str, edge_id: str, *,
                            name: Optional[str] = None, color: str = "") -> str:
        """Attach a marking part-way along an edge/end, subdividing it."""
        node = self._get(node_id)
        res = add_marking_on_edge(node.curve, edge_id, name=name or "", color=color,
                                  reserved=self._subtree_ids(node_id))
        self._remap_after_split(node_id, res)
        self._propagate(node_id)
        return res.marking

    def _subtree_ids(self, node_id: str) -> set:
        """Every vertex/edge id the derived types already claim.

        Ids are inherited by derivation, so a fresh id invented here must dodge
        the ones a child invented for itself (its resolution's new vertex and
        edge). Otherwise the parent and the child would be using one id for two
        different things and the child could no longer be rebuilt.
        """
        out: set = set()
        for nid in self.descendants(node_id):
            n = self.nodes[nid]
            out.update(n.curve.vertices)
            out.update(n.curve.edges)
            for op in n.operations:
                out.update(x for x in (op.new_vertex_id, op.new_edge_id) if x)
        return out

    def _remap_after_split(self, node_id: str, res: EdgeMarkingResult) -> None:
        """Keep derived operations pointing at what they used to point at.

        A derived type records its operation by flag id, against the parent as
        it was. Subdividing an edge rewrites that picture in one place: at
        ``res.moved_flag_vertex`` the flag that was ``split_edge`` is now
        ``new_edge``, and the original edge is now two edges end to end.
        Updating the records here keeps each child the *same* derivation --
        separating the same four directions, identifying the same two vertices
        -- instead of failing to replay or quietly degenerating something else.
        """
        for nid in self._following(node_id):
            for op in self.nodes[nid].operations:
                self._remap_operation(op, res)

    def _remap_operation(self, op: Operation, res: EdgeMarkingResult) -> None:
        if op.kind == "resolve" and op.vertex_id == res.moved_flag_vertex:
            op.side_a = _subst(op.side_a, res.split_edge, res.new_edge)
            op.side_b = _subst(op.side_b, res.split_edge, res.new_edge)
        elif op.kind == "contract" and res.split_edge in [op.edge_id, *op.split_pieces]:
            op.split_pieces = [*op.split_pieces, res.new_edge]

    def _following(self, node_id: str) -> List[str]:
        """Descendants reachable through types that follow their parent."""
        out: List[str] = []
        stack = list(self._get(node_id).children)
        while stack:
            nid = stack.pop()
            node = self.nodes.get(nid)
            if node is None or not node.follow_parent:
                continue
            out.append(nid)
            stack.extend(node.children)
        return out

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
        try:
            curve = parent.curve
            for op in node.operations:
                curve = self._replay(curve, node, op)
            node.curve = curve
            node.status = STATUS_OK
        except Exception:
            node.status = STATUS_NEEDS_ATTENTION

    def _replay(self, curve: Curve, node: TypeNode, op: Operation) -> Curve:
        """One recorded step, applied to the curve the step before left."""
        if op.kind == "contract":
            for eid in [op.edge_id, *op.split_pieces]:
                curve = contract_edge(curve, eid).curve  # type: ignore[arg-type]
            return curve
        if op.kind == "resolve":
            return self._replay_resolve(curve, node, op)
        raise ValueError(f"unknown operation {op.kind!r}")

    def _replay_resolve(self, parent_curve: Curve, node: TypeNode, op: Operation) -> Curve:
        try:
            res = resolution_for_sides(parent_curve, op.vertex_id, op.side_a, op.side_b)  # type: ignore[arg-type]
        except ValueError:
            res = self._repair_sides(parent_curve, op)
        if res.is_crossing:
            raise ValueError("that split no longer gives a bounded edge")

        prev_edge_id = op.new_edge_id
        new_vertex_id, new_edge_id = op.new_vertex_id, op.new_edge_id
        # The parent may have taken these ids since (an edge subdivided under a
        # marking, say). Re-using one would collide, so take fresh ones and keep
        # the record in step -- what the resolution *is* has not changed.
        if new_vertex_id in parent_curve._vset:
            new_vertex_id = _fresh_vertex_id(parent_curve, op.vertex_id)  # type: ignore[arg-type]
            op.new_vertex_id = new_vertex_id
        if new_edge_id in parent_curve.edges:
            new_edge_id = _fresh_edge_id(parent_curve)
            op.new_edge_id = new_edge_id

        out = apply_resolution(parent_curve, res,
                               new_vertex_id=new_vertex_id, new_edge_id=new_edge_id)
        # preserve the inserted edge's presentation (name/color) across replays
        old = node.curve.edges.get(prev_edge_id)  # type: ignore[arg-type]
        if old is not None:
            ne = out.curve.edges[new_edge_id]  # type: ignore[index]
            taken = {e.name for e in out.curve.edges.values() if e.id != new_edge_id}
            if old.name and old.name not in taken:
                ne.name = old.name   # else the parent has since taken that name
            ne.color = old.color
        return out.curve

    def _repair_sides(self, parent_curve: Curve, op: Operation) -> Resolution:
        """Recover a recorded split whose flag ids were renamed out from under it.

        ``_remap_after_split`` keeps records current as edits happen, but a
        workspace saved before that existed -- or edited some way not yet
        accounted for -- can hold a split naming a flag that is no longer at the
        vertex. When exactly one recorded id is gone and exactly one flag at the
        vertex is unaccounted for, the correspondence between them is forced, so
        the recorded split still names a real resolution. Repair the record in
        place: this is reading a rename, not picking anew. Anything less clear
        cut raises, and the type is flagged rather than guessed at.
        """
        recorded = set(op.side_a or ()) | set(op.side_b or ())
        present = {f.id for f in parent_curve.incident(op.vertex_id)}  # type: ignore[arg-type]
        missing, extra = recorded - present, present - recorded
        if len(missing) != 1 or len(extra) != 1:
            raise ValueError("resolution no longer applies")
        old, new = missing.pop(), extra.pop()
        side_a = _subst(op.side_a, old, new)
        side_b = _subst(op.side_b, old, new)
        res = resolution_for_sides(parent_curve, op.vertex_id, side_a, side_b)  # type: ignore[arg-type]
        op.side_a, op.side_b = side_a, side_b
        return res

    # --- healing ---------------------------------------------------------
    def retry(self, node_id: str) -> str:
        """Re-derive one type from its parent, then everything under it."""
        node = self._get(node_id)
        if node.parent_id is None:
            raise ValueError("a root type is not derived from anything")
        self._rederive(node)
        self._propagate(node_id)
        return node.status

    def retry_failed(self) -> List[str]:
        """Re-derive every type marked ``needs_attention``; returns those healed.

        A replay that failed against the parent of the moment can succeed later
        -- the parent was edited again, or the replay itself got better -- so a
        workspace gets one attempt to heal when it is loaded. Parents are
        retried before their children, and a type that heals re-derives its own
        subtree, since those were rebuilt from a stale curve.
        """
        healed: List[str] = []
        for root in self.roots():
            for nid in [root.id, *self.descendants(root.id)]:
                node = self.nodes[nid]
                if node.parent_id is None or not node.follow_parent:
                    continue
                if node.status != STATUS_NEEDS_ATTENTION:
                    continue
                self._rederive(node)
                if node.status == STATUS_OK:
                    healed.append(nid)
                    self._propagate(nid)
        return healed

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


def _subst(group: Optional[Tuple[str, ...]], old: str, new: str) -> Optional[Tuple[str, ...]]:
    """``group`` with ``old`` replaced by ``new``."""
    if group is None:
        return None
    return tuple(new if x == old else x for x in group)
