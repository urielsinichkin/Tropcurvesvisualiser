"""JSON-friendly session facade over the core.

This is the single seam the browser/Pyodide frontend talks to: every method
takes and returns plain JSON-able Python (dicts, lists, numbers, strings), so
the UI never touches core objects directly. It also computes *render data* (an
embedding of the curve plus its dual subdivision) for drawing.
"""

from __future__ import annotations

from fractions import Fraction
from math import hypot
from typing import Any, Dict, List, Optional

from .curve import Curve, EdgeKind
from .geometry import Vec2, primitive
from .balancing import resolve_slopes
from .newton import newton_polygon
from .layout import embed, readable_lengths, end_ray_length
from .subdivision import build_subdivision, SubdivisionError
from .operations import resolutions, resolution_for_subset
from .subdivision_import import import_subdivision
from .refined import (
    refined_multiplicity, vertex_multiplicities, balanced_split,
    MultiplicityError, MAX_SPLIT_ITEMS,
)
from .workspace import Workspace
from . import schema, builders


class Session:
    """Holds one workspace and exposes JSON operations for the UI."""

    def __init__(self) -> None:
        self.ws = Workspace()

    # --- persistence ----------------------------------------------------
    def save(self) -> str:
        return schema.dumps_workspace(self.ws)

    def load(self, text: str) -> None:
        self.ws = schema.loads_workspace(text)
        # A replay that failed when the file was written may well succeed now,
        # so give every type marked needs_attention one chance to heal.
        self.ws.retry_failed()

    # --- creating types -------------------------------------------------
    def add_preset(self, name: str) -> Dict[str, Any]:
        presets = {
            "line": builders.standard_line,
            "caterpillar_square": builders.caterpillar_square,
        }
        if name not in presets:
            raise ValueError(f"unknown preset {name!r}")
        node = self.ws.add_root(presets[name](), name=name)
        return self.node_summary(node.id)

    def add_curve(self, spec: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        """Create a root type from a spec.

        spec = {
          "vertices": ["v0", ...],
          "bounded":  [{"id","tail","head", "vec"?:[x,y], "name"?, "color"?}, ...],
          "ends":     [{"id","tail","vec":[x,y], "name"?, "color"?}, ...],
          "markings": [{"id","tail", "name"?, "color"?}, ...],
        }
        Bounded edges without a ``vec`` are solved by balancing.
        """
        c = Curve()
        for v in spec.get("vertices", []):
            c.add_vertex(v)
        for e in spec.get("bounded", []):
            vec = Vec2.from_iterable(e["vec"]) if e.get("vec") else Vec2(0, 0)
            c.add_bounded(e["id"], e["tail"], e["head"], vec,
                          name=e.get("name", ""), color=e.get("color", ""))
        for e in spec.get("ends", []):
            c.add_end(e["id"], e["tail"], Vec2.from_iterable(e["vec"]),
                      name=e.get("name", ""), color=e.get("color", ""))
        for e in spec.get("markings", []):
            c.add_marking(e["id"], e["tail"],
                          name=e.get("name", ""), color=e.get("color", ""))
        # solve any unspecified bounded slopes
        if any(b.get("vec") is None for b in spec.get("bounded", [])):
            resolve_slopes(c)
        c.validate()
        node = self.ws.add_root(c, name=name)
        return self.node_summary(node.id)

    def add_from_subdivision(self, cells: List[List[List[int]]],
                             name: Optional[str] = None) -> Dict[str, Any]:
        """Create a root type from a subdivision (a list of lattice cells).

        Each cell is a list of ``[x, y]`` lattice points. No markings are
        created; the parametrizing curve must be a connected genus-0 tree.
        """
        c = import_subdivision(cells)
        node = self.ws.add_root(c, name=name)
        return self.node_summary(node.id)

    # --- listing --------------------------------------------------------
    def list_nodes(self) -> List[Dict[str, Any]]:
        return [self.node_summary(nid) for nid in self.ws.nodes]

    def node_summary(self, node_id: str) -> Dict[str, Any]:
        n = self.ws.nodes[node_id]
        c = n.curve
        return {
            "id": n.id,
            "name": n.name,
            "parent_id": n.parent_id,
            "children": list(n.children),
            "follow_parent": n.follow_parent,
            "status": n.status,
            "genus": c.genus,
            "num_ends": len(c.ends),
            "num_markings": len(c.markings),
            "num_bounded": len(c.bounded),
            "valences": {v: c.valence(v) for v in c.vertices},
        }

    # --- editing (all propagate) ---------------------------------------
    def edit_slopes(self, node_id: str, edit_end_id: str, new_vec: List[int],
                    dependent_end_id: str) -> Dict[str, Any]:
        self.ws.edit_slopes(node_id, edit_end_id, Vec2.from_iterable(new_vec), dependent_end_id)
        return self.node_summary(node_id)

    def add_marking(self, node_id: str, vertex: str, name: str = "",
                    color: str = "") -> Dict[str, Any]:
        mid = self.ws.add_marking(node_id, vertex, name=name or None, color=color)
        return {"marking_id": mid, **self.node_summary(node_id)}

    def add_marking_on_edge(self, node_id: str, edge_id: str, name: str = "",
                            color: str = "") -> Dict[str, Any]:
        """Attach a marking part-way along an edge/end, subdividing it."""
        mid = self.ws.add_marking_on_edge(node_id, edge_id, name=name or None, color=color)
        return {"marking_id": mid, **self.node_summary(node_id)}

    def remove_marking(self, node_id: str, marking_id: str) -> Dict[str, Any]:
        self.ws.remove_marking(node_id, marking_id)
        return self.node_summary(node_id)

    def rename_edge(self, node_id: str, edge_id: str, new_name: str) -> Dict[str, Any]:
        self.ws.rename_edge(node_id, edge_id, new_name)
        return self.node_summary(node_id)

    def set_color(self, node_id: str, edge_id: str, color: str) -> Dict[str, Any]:
        self.ws.set_color(node_id, edge_id, color)
        return self.node_summary(node_id)

    def set_follow(self, node_id: str, follow: bool) -> Dict[str, Any]:
        self.ws.set_follow(node_id, follow)
        return self.node_summary(node_id)

    def retry(self, node_id: str) -> Dict[str, Any]:
        """Re-derive a type from its parent (for one marked needs_attention)."""
        self.ws.retry(node_id)
        return self.node_summary(node_id)

    def rename_node(self, node_id: str, name: str) -> Dict[str, Any]:
        self.ws.rename_node(node_id, name)
        return self.node_summary(node_id)

    def duplicate(self, node_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Copy a type into a new independent root (see ``Workspace.duplicate``)."""
        node = self.ws.duplicate(node_id, name=name)
        return self.node_summary(node.id)

    def descendants(self, node_id: str) -> List[str]:
        """Ids of every type derived from this one, transitively."""
        return self.ws.descendants(node_id)

    def delete(self, node_id: str) -> Dict[str, Any]:
        """Delete one type; its derived types move up (see ``Workspace.delete``)."""
        self.ws.delete(node_id)
        return {"removed": [node_id], "remaining": [n for n in self.ws.nodes]}

    # --- structural operations -----------------------------------------
    def contract(self, node_id: str, edge_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        child = self.ws.contract(node_id, edge_id, name=name)
        return self.node_summary(child.id)

    def list_resolutions(self, node_id: str, vertex: str) -> List[Dict[str, Any]]:
        c = self.ws.nodes[node_id].curve
        out = []
        for i, r in enumerate(resolutions(c, vertex, include_crossings=True)):
            out.append({
                "index": i,
                "label": r.label(c),
                "is_crossing": r.is_crossing,
                "new_edge_vec": r.new_edge_vec.to_list(),
                "side_a": list(r.side_a),
                "side_b": list(r.side_b),
            })
        return out

    def resolve(self, node_id: str, vertex: str, index: int,
                name: Optional[str] = None) -> Dict[str, Any]:
        c = self.ws.nodes[node_id].curve
        res = resolutions(c, vertex, include_crossings=True)[index]
        if res.is_crossing:
            raise ValueError("that pairing is a crossing, not a resolution")
        child = self.ws.resolve(node_id, res, name=name)
        return self.node_summary(child.id)

    def preview_resolution(self, node_id: str, vertex: str,
                           subset: List[str]) -> Dict[str, Any]:
        """What splitting ``vertex`` along ``subset`` would give, without doing it.

        Returns ``ok`` with the inserted edge's direction, or ``reason`` for why
        that choice is not a resolution -- so a picker can say so as you click.
        """
        c = self.ws.nodes[node_id].curve
        try:
            res = resolution_for_subset(c, vertex, subset)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}
        if res.is_crossing:
            return {"ok": False, "reason": "this split realizes as a crossing "
                                           "(a parallelogram), not a bounded edge",
                    "is_crossing": True}
        return {"ok": True, "is_crossing": False,
                "new_edge_vec": res.new_edge_vec.to_list(),
                "label": res.label(c)}

    def resolve_subset(self, node_id: str, vertex: str, subset: List[str],
                       name: Optional[str] = None) -> Dict[str, Any]:
        """Split ``vertex`` into one vertex carrying ``subset`` and one carrying the rest."""
        c = self.ws.nodes[node_id].curve
        res = resolution_for_subset(c, vertex, subset)
        if res.is_crossing:
            raise ValueError("that split is a crossing (a parallelogram), not a resolution")
        child = self.ws.resolve(node_id, res, name=name)
        return self.node_summary(child.id)

    # --- refined multiplicity -------------------------------------------
    def refined_multiplicity(self, node_id: str) -> Dict[str, Any]:
        """The Goettsche-Schroeter refined multiplicity of one type.

        ``defined`` is False with a ``reason`` when the curve is not trivalent
        (markings aside); otherwise ``text`` is the value and ``vertices``
        lists what each vertex contributed.
        """
        c = self.ws.nodes[node_id].curve
        try:
            vms = vertex_multiplicities(c)
            value = refined_multiplicity(c)
        except MultiplicityError as exc:
            return {"id": node_id, "name": self.ws.nodes[node_id].name,
                    "defined": False, "reason": str(exc)}
        return {
            "id": node_id,
            "name": self.ws.nodes[node_id].name,
            "defined": True,
            "text": value.text(),
            "is_polynomial": value.is_polynomial,
            "at_q_1": str(value.at_q(Fraction(1))),
            "vertices": [{"vertex": v.vertex, "mu": v.mu, "marked": v.marked,
                          "interior": v.interior, "factor": v.label()} for v in vms],
        }

    def refined_multiplicities(self, node_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        ids = list(self.ws.nodes) if node_ids is None else node_ids
        return [self.refined_multiplicity(nid) for nid in ids]

    def balanced_split(self, node_ids: List[str]) -> Dict[str, Any]:
        """Can these types be split in two halves of equal total multiplicity?

        Returns the halves when one exists. Every chosen type needs a defined
        multiplicity, since otherwise there is nothing to add up.
        """
        values, undefined = [], []
        for nid in node_ids:
            info = self.refined_multiplicity(nid)
            if not info["defined"]:
                undefined.append({"id": nid, "name": info["name"], "reason": info["reason"]})
            else:
                values.append(refined_multiplicity(self.ws.nodes[nid].curve))
        if undefined:
            return {"ok": False, "undefined": undefined}
        if len(node_ids) > MAX_SPLIT_ITEMS:
            return {"ok": False, "reason": f"pick at most {MAX_SPLIT_ITEMS} types "
                                           f"(this is a subset search over 2^n splits)"}
        total = values[0] if values else None
        for v in values[1:]:
            total = total + v
        chosen = balanced_split(values)
        out: Dict[str, Any] = {
            "ok": True,
            "found": chosen is not None,
            "total": total.text() if total is not None else "0",
        }
        if chosen is not None:
            picked = [node_ids[i] for i in chosen]
            half = values[chosen[0]] if chosen else None
            for i in chosen[1:]:
                half = half + values[i]
            out["subset"] = picked
            out["complement"] = [n for n in node_ids if n not in set(picked)]
            out["value"] = half.text() if half is not None else "0"
        return out

    # --- render data ----------------------------------------------------
    def render(self, node_id: str) -> Dict[str, Any]:
        n = self.ws.nodes[node_id]
        c = n.curve
        out: Dict[str, Any] = {
            "id": n.id,
            "name": n.name,
            "status": n.status,
            "curve": self._render_curve(c),
        }
        try:
            out["newton"] = [v.to_list() for v in newton_polygon(c)]
        except Exception as exc:  # no ends etc.
            out["newton"] = None
            out["newton_error"] = str(exc)
        try:
            sub = build_subdivision(c)
            out["subdivision"] = {
                "cells": [[v.to_list() for v in cell.vertices] for cell in sub.cells],
            }
            out["subdivision_error"] = None
        except SubdivisionError as exc:
            out["subdivision"] = None
            out["subdivision_error"] = str(exc)
        return out

    def _render_curve(self, c: Curve) -> Dict[str, Any]:
        pos = embed(c, readable_lengths(c))
        fpos = {v: (float(x), float(y)) for v, (x, y) in pos.items()}
        ray_len = end_ray_length(pos)   # the length the layout scored against

        vertices = [{"id": v, "x": fpos[v][0], "y": fpos[v][1]} for v in c.vertices]
        edges = []
        for e in c.bounded:
            a = fpos[e.tail]
            b = fpos[e.head]  # type: ignore[index]
            edges.append({
                "id": e.id, "name": e.name, "color": e.color, "kind": "bounded",
                "weight": e.weight, "from": list(a), "to": list(b),
                "vec": e.vec.to_list(), "tail": e.tail, "head": e.head,
            })
        for e in c.ends:
            a = fpos[e.tail]
            u, w = primitive(e.vec)
            norm = hypot(u.x, u.y) or 1.0
            b = (a[0] + ray_len * u.x / norm, a[1] + ray_len * u.y / norm)
            edges.append({
                "id": e.id, "name": e.name, "color": e.color, "kind": "end",
                "weight": w, "from": list(a), "to": list(b), "dir": [u.x, u.y],
                "vec": e.vec.to_list(), "tail": e.tail,
            })
        markings = [
            {"id": e.id, "name": e.name, "color": e.color, "at": list(fpos[e.tail]),
             "tail": e.tail, "valence": c.valence(e.tail)}
            for e in c.markings
        ]
        return {"vertices": vertices, "edges": edges, "markings": markings}
