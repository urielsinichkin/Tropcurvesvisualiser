"""JSON-friendly session facade over the core.

This is the single seam the browser/Pyodide frontend talks to: every method
takes and returns plain JSON-able Python (dicts, lists, numbers, strings), so
the UI never touches core objects directly. It also computes *render data* (an
embedding of the curve plus its dual subdivision) for drawing.
"""

from __future__ import annotations

from fractions import Fraction
from math import hypot
from typing import Any, Dict, List, Optional, Tuple

from .curve import Curve, EdgeKind
from .geometry import Vec2, primitive
from .balancing import resolve_slopes
from .newton import newton_polygon
from .layout import embed, end_ray_length, display_lengths, layout_reference
from .subdivision import build_subdivision, SubdivisionError
from .operations import resolutions, resolution_for_subset, apply_resolution, smooth_vertex
from .subdivision_import import import_subdivision
from .refined import (
    refined_multiplicity, vertex_multiplicities, balanced_split, balanced_split_numbers,
    maximal_balanced_subsets, MultiplicityError, MAX_SPLIT_ITEMS, MAX_MAXIMAL_ITEMS,
)
from .workspace import Workspace
from . import schema, builders, evaluation, moduli, polyhedron


class Session:
    """Holds one workspace and exposes JSON operations for the UI."""

    def __init__(self) -> None:
        self.ws = Workspace()
        self._layout_cache: Dict[Any, Any] = {}

    # --- layout -----------------------------------------------------------
    @staticmethod
    def _geometry_key(c: Curve) -> tuple:
        """What the layout depends on: the graph and slopes, not names or colors."""
        return (tuple(c.vertices),
                tuple(sorted((e.id, e.kind.value, e.tail, e.head or "", e.vec.x, e.vec.y)
                             for e in c.edges.values())))

    def _node_layout(self, node_id: str) -> tuple:
        """(lengths, cache key) for drawing a type, fitted to its parent's picture.

        Recursive up the derivation tree, so each type resembles its parent as
        drawn, and cached on the geometry of the whole chain, so an unchanged
        ancestor is not laid out again.
        """
        n = self.ws.nodes[node_id]
        parent = self.ws.nodes.get(n.parent_id) if n.parent_id else None
        ref, pkey = None, None
        if parent is not None:
            plengths, pkey = self._node_layout(parent.id)
            ref = layout_reference(parent.curve, plengths)
        key = (self._geometry_key(n.curve), pkey)
        hit = self._layout_cache.get(key)
        if hit is None:
            if len(self._layout_cache) > 512:
                self._layout_cache.clear()
            hit = display_lengths(n.curve, ref)
            self._layout_cache[key] = hit
        return hit, key

    # --- persistence ----------------------------------------------------
    def save(self) -> str:
        return schema.dumps_workspace(self.ws)

    def export_subset(self, node_ids: List[str]) -> str:
        """Save only these types, as a workspace that stands on its own.

        A left-out type does not orphan what came after it: the export is the
        workspace with everything unselected *deleted*, so each kept type is
        re-attached to its nearest kept ancestor, carrying the skipped steps in
        front of its own, and one with no kept ancestor becomes a root. What is
        exported therefore reads back as the same curves, still derived from
        one another wherever both ends were included.
        """
        keep = set(node_ids)
        unknown = [n for n in keep if n not in self.ws.nodes]
        if unknown:
            raise ValueError(f"unknown type id(s): {', '.join(sorted(unknown))}")
        copy = schema.loads_workspace(schema.dumps_workspace(self.ws))
        for nid in list(copy.nodes):
            if nid not in keep:
                copy.delete(nid)
        return schema.dumps_workspace(copy)

    def load(self, text: str, append: bool = False) -> List[str]:
        """Load a workspace file, replacing the current one -- or, with
        ``append``, adding its types alongside the current ones (see
        ``Workspace.merge``). Returns the ids of the types loaded."""
        incoming = schema.loads_workspace(text)
        if append:
            added = self.ws.merge(incoming)
        else:
            self.ws = incoming
            added = list(incoming.nodes)
        # A replay that failed when the file was written may well succeed now,
        # so give every type marked needs_attention one chance to heal.
        self.ws.retry_failed()
        return added

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
            "description": n.description,
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

    def move_marking(self, node_id: str, marking_id: str, target_kind: str,
                     target_id: str) -> Dict[str, Any]:
        """Move a marking into an edge (``target_kind`` "edge") or onto a
        vertex ("vertex"); see ``Workspace.move_marking``."""
        if target_kind == "edge":
            self.ws.move_marking(node_id, marking_id, edge=target_id)
        elif target_kind == "vertex":
            self.ws.move_marking(node_id, marking_id, vertex=target_id)
        else:
            raise ValueError(f"unknown target kind {target_kind!r}")
        return self.node_summary(node_id)

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

    def move_type(self, node_id: str, to_index: int) -> Dict[str, Any]:
        """Move a type among its siblings (see ``Workspace.move_type``)."""
        self.ws.move_type(node_id, int(to_index))
        return self.node_summary(node_id)

    def set_description(self, node_id: str, text: str) -> Dict[str, Any]:
        """Set a type's description (free text; empty clears it)."""
        self.ws.set_description(node_id, text)
        return self.node_summary(node_id)

    def duplicate(self, node_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Copy a type into a new independent root (see ``Workspace.duplicate``)."""
        node = self.ws.duplicate(node_id, name=name)
        return self.node_summary(node.id)

    def descendants(self, node_id: str) -> List[str]:
        """Ids of every type derived from this one, transitively."""
        return self.ws.descendants(node_id)

    def delete(self, node_id: str, with_descendants: bool = False) -> Dict[str, Any]:
        """Delete a type: alone, its derived types moving up, or together with
        all of them (see ``Workspace.delete``)."""
        removed = self.ws.delete(node_id, with_descendants=with_descendants)
        return {"removed": removed, "remaining": [n for n in self.ws.nodes]}

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

    def render_resolution(self, node_id: str, vertex: str,
                          subset: List[str]) -> Dict[str, Any]:
        """Drawing data for what a resolution would produce, without making it.

        The workspace is untouched. ``new_edge`` is the id of the inserted edge,
        so a preview can pick it out. A crossing split has nothing to draw and
        raises.
        """
        c = self.ws.nodes[node_id].curve
        res = resolution_for_subset(c, vertex, subset)
        if res.is_crossing:
            raise ValueError("that split is a crossing (a parallelogram), not a resolution")
        out = apply_resolution(c, res)
        # drawn as the child would be: fitted to this type's picture
        plengths, _ = self._node_layout(node_id)
        lengths = display_lengths(out.curve, layout_reference(c, plengths))
        return {"curve": self._render_curve(out.curve, lengths), "new_edge": out.new_edge,
                "new_edge_vec": res.new_edge_vec.to_list()}

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

    # --- evaluation matrix -----------------------------------------------
    def evaluation_setup(self, node_id: str) -> Dict[str, Any]:
        """Root choices, legs and default functions for the evaluation matrix."""
        return evaluation.setup(self.ws.nodes[node_id].curve)

    def evaluation_matrix(self, node_id: str, root_vertex: str,
                          functions: List[Dict[str, Any]],
                          columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """The matrix of ``functions`` on the type's cell (see ``evaluation``),
        its columns in the order ``columns`` (keys from the setup) if given."""
        return evaluation.evaluation_matrix(self.ws.nodes[node_id].curve, root_vertex,
                                            functions, columns=columns)

    def refined_multiplicities(self, node_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        ids = list(self.ws.nodes) if node_ids is None else node_ids
        return [self.refined_multiplicity(nid) for nid in ids]

    def balanced_split(self, node_ids: List[str], at_q_1: bool = False) -> Dict[str, Any]:
        """Can these types be split in two halves of equal total multiplicity?

        Returns the halves when one exists. Every chosen type needs a defined
        multiplicity, since otherwise there is nothing to add up. With
        ``at_q_1`` only the values at q = 1 (the Mikhalkin multiplicities)
        have to balance, not the whole refined multiplicities.
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
        if at_q_1:
            values = [v.at_q(Fraction(1)) for v in values]
        total = values[0] if values else None
        for v in values[1:]:
            total = total + v
        text = (lambda v: str(v)) if at_q_1 else (lambda v: v.text())
        chosen = balanced_split_numbers(values) if at_q_1 else balanced_split(values)
        out: Dict[str, Any] = {
            "ok": True,
            "found": chosen is not None,
            "at_q_1": at_q_1,
            "total": text(total) if total is not None else "0",
        }
        if chosen is not None:
            picked = [node_ids[i] for i in chosen]
            half = values[chosen[0]] if chosen else None
            for i in chosen[1:]:
                half = half + values[i]
            out["subset"] = picked
            out["complement"] = [n for n in node_ids if n not in set(picked)]
            out["value"] = text(half) if half is not None else "0"
        return out

    def maximal_balanced_subsets(self, node_ids: List[str], at_q_1: bool = False,
                                 limit: int = 200) -> Dict[str, Any]:
        """The maximal sub-collections of these types that split in balanced
        halves (see ``refined.maximal_balanced_subsets``), largest first, each
        with one such split and the common total -- for when the whole set does
        not balance. ``at_q_1`` compares the values at q = 1 only. At most
        ``limit`` are listed (``count`` says how many there are).
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
        if len(node_ids) > MAX_MAXIMAL_ITEMS:
            return {"ok": False, "reason": f"pick at most {MAX_MAXIMAL_ITEMS} types for this search"}
        if at_q_1:
            values = [v.at_q(Fraction(1)) for v in values]
        text = (lambda v: str(v)) if at_q_1 else (lambda v: v.text())
        try:
            found = maximal_balanced_subsets(values)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}
        results = []
        for members, plus in found[:limit]:
            idx = [i for i in range(len(node_ids)) if members >> i & 1]
            a = [i for i in idx if plus >> i & 1]
            b = [i for i in idx if not plus >> i & 1]
            half = values[a[0]]
            for i in a[1:]:
                half = half + values[i]
            results.append({
                "members": [node_ids[i] for i in idx],
                "subset": [node_ids[i] for i in a],
                "complement": [node_ids[i] for i in b],
                "value": text(half),
            })
        return {"ok": True, "at_q_1": at_q_1, "count": len(found),
                "truncated": len(found) > limit, "results": results}

    # --- the moduli map: a walk across walls (see ``moduli``) -----------
    # Every call names the type, the evaluated markings and the five legs;
    # points are {marking: [x, y]} and a point of M_0,5 is {splits, lengths}
    # (rationals as strings, see ``moduli.point_json``).
    # ``same`` lists groups of evaluated markings required to be one point of
    # the plane: the walk is then on the cycle where their evaluations agree.
    def _walk_map(self, node_id: str, evaluated: List[str], legs: List[str],
                  same: Optional[List[List[str]]] = None) -> "moduli.TypeMap":
        n = self.ws.nodes[node_id]
        if len(legs) != 5 or len(set(legs)) != 5:
            raise ValueError("choose exactly five different legs")
        return moduli.TypeMap(n.id, n.name, n.curve, evaluated, legs, same or ())

    @staticmethod
    def _walk_points(t: "moduli.TypeMap", evaluated: List[str], points: Dict[str, Any]) -> List[Fraction]:
        out: List[Fraction] = []
        for m in t.rep_names:                 # one point for each group
            xy = points.get(m)
            if xy is None:
                raise ValueError(f"no point given for {m!r}")
            out += [Fraction(str(xy[0])), Fraction(str(xy[1]))]
        return out

    def moduli_add_marking(self, node_id: str, vertex: str) -> Dict[str, Any]:
        """Put a marking on a vertex, unless the vertex would then carry as
        many markings as other edges."""
        c = self.ws.nodes[node_id].curve
        inc = c.incident(vertex)
        marks = sum(1 for e in inc if e.kind is EdgeKind.MARKING)
        if marks + 1 >= len(inc) - marks:
            raise ValueError(f"this vertex has {len(inc) - marks} other edges, so it can carry at most "
                             f"{len(inc) - marks - 1} marking{'s' if len(inc) - marks - 1 != 1 else ''}")
        return self.add_marking(node_id, vertex)

    def moduli_move_marking(self, node_id: str, marking: str, vertex: Optional[str] = None,
                            edge: Optional[str] = None) -> Dict[str, Any]:
        """Move a marking (by name) onto a vertex -- e.g. another marking's,
        so that the two sit on one vertex -- or into an edge. A vertex keeps
        more other edges than markings."""
        c = self.ws.nodes[node_id].curve
        m = next((e for e in c.markings if e.name == marking), None)
        if m is None:
            raise ValueError(f"no marking named {marking!r}")
        if vertex is not None and vertex != m.tail:
            inc = [e for e in c.incident(vertex) if e.id != m.id]
            marks = sum(1 for e in inc if e.kind is EdgeKind.MARKING)
            other = len(inc) - marks
            if marks + 1 >= other:
                raise ValueError("that point is inside an edge, with room for one marking only"
                                 if other <= 2 else
                                 f"that vertex has {other} other edges and already {marks} "
                                 f"marking{'s' if marks != 1 else ''}: it can carry no more "
                                 f"(a vertex needs more other edges than markings)")
        self.ws.move_marking(node_id, m.id, vertex=vertex, edge=edge)
        return self.node_summary(node_id)

    # --- the polyhedron of curves through constraints (polyhedron/) --------
    # A type, points for some markings {name: [x, y]} and line values for some
    # ends {name: c}; z is a point of the type's cell (strings, exact).
    def _poly(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any]) -> "polyhedron.Cell":
        return polyhedron.Cell(self.ws.nodes[node_id].curve, points or {}, lines or {})

    @staticmethod
    def _zs(z) -> List[str]:
        return [str(x) for x in z]

    @staticmethod
    def _zf(z) -> List[Fraction]:
        return [Fraction(str(x)) for x in z]

    def poly_start(self, node_id: str) -> Dict[str, Any]:
        """The type's curve as the main app draws it (root at the origin)."""
        cell = self._poly(node_id, {}, {})
        lengths, _ = self._node_layout(node_id)
        z = [Fraction(0), Fraction(0)] + [
            Fraction(float(lengths.get(e.id, 1))).limit_denominator(64) / e.weight for e in cell.bounded]
        return {"z": self._zs(z)}

    def poly_values(self, node_id: str, z: List[Any]) -> Dict[str, Any]:
        """Where each marking is and each end's line value, at z."""
        vals = self._poly(node_id, {}, {}).values(self._zf(z))
        return {"points": {k: [str(a), str(b)] for k, (a, b) in vals["points"].items()},
                "lines": {k: str(c) for k, c in vals["lines"].items()}}

    def poly_fit(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                 z: List[Any]) -> Dict[str, Any]:
        """A curve of the type through the constraints, near z: whether there
        is one (and of the precise type), the polyhedron's dimension."""
        cell = self._poly(node_id, points, lines)
        t, z2 = cell.fit(self._zf(z))
        out = {"feasible": t is not None, "precise": bool(t), "dim": cell.dim, "z": None, "picture": None}
        if t is not None:
            out["z"] = self._zs(z2)
            out["picture"] = moduli.picture(cell, z2, self._render_curve)
        return out

    def poly_view(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                  z: List[Any], box: Optional[List[List[Any]]] = None) -> Dict[str, Any]:
        """The curve at z, its lengths, the polyhedron's dimension and, up to
        dimension 2, the chart: its axes (free coordinates), the point, the
        box shown (grown to keep the point well inside) and the region."""
        cell = self._poly(node_id, points, lines)
        zf = self._zf(z)
        out: Dict[str, Any] = {
            "id": node_id, "name": self.ws.nodes[node_id].name, "dim": cell.dim,
            "satisfied": cell.satisfies(zf),
            "picture": moduli.picture(cell, zf, self._render_curve),
            "lengths": {e.name: str(zf[cell.index[e.id]]) for e in cell.bounded},
            "high": [v for v in cell.curve.vertices if cell.curve.valence(v) >= 4],
            "chart": None,
        }
        if cell.dim is not None and 1 <= cell.dim <= 2:
            w = [zf[c] for c in cell.free]
            bx = self._poly_box(cell, w, box)
            out["chart"] = {"axes": [{"name": cell.axis_name(c), "length": c >= 2} for c in cell.free],
                            "coords": [str(x) for x in w], "box": [[str(a), str(b)] for a, b in bx],
                            "region": cell.region(zf, bx)}
        return out

    @staticmethod
    def _poly_box(cell, w: List[Fraction], box) -> List[Tuple[Fraction, Fraction]]:
        """The chart's box: [0, R] along a length, an interval of width R
        around the point otherwise; grown (R doubled) while the point is not
        well inside."""
        def nice(x: Fraction) -> Fraction:
            r = Fraction(1, 4)
            while r < x:
                r *= 2
            return r
        out = []
        for i, c in enumerate(cell.free):
            if box and i < len(box):
                lo, hi = Fraction(str(box[i][0])), Fraction(str(box[i][1]))
            elif c >= 2:
                lo, hi = Fraction(0), nice(2 * w[i] + Fraction(1, 4))
            else:
                R = nice(abs(w[i]) + 1)
                lo, hi = w[i] - R, w[i] + R
            while not (lo + (hi - lo) / 20 <= w[i] <= hi - (hi - lo) * 3 / 20) and hi - lo < 10 ** 6:
                if c >= 2:
                    hi = lo + 2 * (hi - lo)
                else:
                    mid, R = (lo + hi) / 2, hi - lo
                    lo, hi = mid - R, mid + R
            out.append((lo, hi))
        return out

    def poly_move(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                  z: List[Any], to: List[Any]) -> Dict[str, Any]:
        """Towards the point of the chart with free coordinates ``to``,
        stopping at the first degeneration (an edge reaching length 0)."""
        cell = self._poly(node_id, points, lines)
        z2, edge = cell.move(self._zf(z), [Fraction(str(x)) for x in to])
        return {"z": self._zs(z2), "wall": edge and {"edge": edge, "name": cell.curve.edges[edge].name}}

    def poly_direction(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                       z: List[Any], delta: Dict[str, Any]) -> Dict[str, Any]:
        """A direction of edge lengths (edge id -> amount) projected to the
        polyhedron, and how far it goes before an edge reaches 0."""
        cell = self._poly(node_id, points, lines)
        p = cell.project(self._zf(z), delta or {})
        e = p["edge"]
        return {"v": self._zs(p["v"]), "moves": any(p["v"]),
                "t_max": str(p["t_max"]) if p["t_max"] is not None else None,
                "wall": e and {"edge": e, "name": cell.curve.edges[e].name},
                "change": {cell.curve.edges[eid].name: str(p["v"][j]) for eid, j in cell.index.items() if p["v"][j]}}

    def poly_at(self, node_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                z: List[Any], v: List[Any], t: Any) -> Dict[str, Any]:
        """z + t v (stopping at a degeneration), and the curve there."""
        cell = self._poly(node_id, points, lines)
        z2, edge = cell.go(self._zf(z), self._zf(v), Fraction(str(t)))
        return {"z": self._zs(z2), "wall": edge and {"edge": edge, "name": cell.curve.edges[edge].name},
                "picture": moduli.picture(cell, z2, self._render_curve)}

    def _poly_root(self, curve: Curve) -> str:
        """The library's type with exactly this curve (same ids), or a new root."""
        key = self._geometry_key(curve)
        for nid, n in self.ws.nodes.items():
            if self._geometry_key(n.curve) == key:
                return nid
        return self.ws.add_root(curve).id

    def poly_wall(self, node_id: str, edge_id: str, points: Dict[str, Any], lines: Dict[str, Any],
                  z: List[Any], scale: Any = 1, with_regenerations: bool = True) -> Dict[str, Any]:
        """The degeneration where ``edge_id`` has length 0: the type with it
        contracted (kept in the library), the point there, and the
        regenerations of the vertex it leaves -- each drawn small, whether it
        is the type we came from and whether the curve can go on into it."""
        cell = self._poly(node_id, points, lines)
        wall, vertex, zw = polyhedron.contract(cell, self._zf(z), edge_id)
        wid = self._poly_root(wall)
        back = moduli.type_key(cell.curve)
        regs = []
        for i, r in enumerate(polyhedron.regenerate(wall, vertex, zw, points, lines, Fraction(str(scale)))
                              if with_regenerations else []):
            regs.append({"index": i, "back": moduli.type_key(r["curve"]) == back,
                         "enter": r["z"] is not None, "why": r["why"],
                         "picture": self._render_curve(r["curve"])})
        return {"wall_id": wid, "vertex": vertex, "z": self._zs(zw), "edge": cell.curve.edges[edge_id].name,
                "regenerations": regs}

    def poly_regenerations(self, node_id: str, vertex: str, points: Dict[str, Any], lines: Dict[str, Any],
                           z: List[Any], scale: Any = 1, came_from: Optional[str] = None) -> Dict[str, Any]:
        """The regenerations of a vertex of valence >= 4 of the current type
        (``came_from``: the type the walk came from, to mark the way back)."""
        back = moduli.type_key(self.ws.nodes[came_from].curve) if came_from in self.ws.nodes else None
        regs = []
        for i, r in enumerate(polyhedron.regenerate(self.ws.nodes[node_id].curve, vertex, self._zf(z),
                                                    points, lines, Fraction(str(scale)))):
            regs.append({"index": i, "back": moduli.type_key(r["curve"]) == back,
                         "enter": r["z"] is not None, "why": r["why"],
                         "picture": self._render_curve(r["curve"])})
        return {"wall_id": node_id, "vertex": vertex, "z": [str(x) for x in z], "regenerations": regs}

    def poly_regenerate(self, wall_id: str, vertex: str, index: int, points: Dict[str, Any],
                        lines: Dict[str, Any], z: List[Any], scale: Any = 1) -> Dict[str, Any]:
        """Go on into a regeneration: its type (in the library) and the point
        a short way in."""
        r = polyhedron.regenerate(self.ws.nodes[wall_id].curve, vertex, self._zf(z), points, lines,
                                  Fraction(str(scale)))[int(index)]
        if r["z"] is None:
            return {"id": None, "why": r["why"]}
        return {"id": self._poly_root(r["curve"]), "z": self._zs(r["z"])}

    def moduli_remove_marking(self, node_id: str, marking_id: str) -> Dict[str, Any]:
        """Take a marking off the type, merging the point it leaves inside an
        edge back into the edge (unlike ``remove_marking``)."""
        node = self.ws.nodes[node_id]
        c = node.curve
        m = c.edges.get(marking_id)
        if m is None or m.kind is not EdgeKind.MARKING:
            raise ValueError(f"{marking_id!r} is not a marking")
        at = m.tail
        del c.edges[marking_id]
        smooth_vertex(c, at)
        c.validate()
        self.ws._propagate(node_id)
        return self.node_summary(node_id)

    def moduli_check(self, node_id: str, evaluated: List[str], legs: List[str],
                     same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Dimensions, invertibility (with the reason when not) and the cone."""
        t = self._walk_map(node_id, evaluated, legs, same)
        out = moduli.check(t)
        out["why"] = moduli.explain(t, evaluated, legs)
        out["cone"] = [list(sp) for sp in t.cone]
        return out

    def moduli_start(self, node_id: str, evaluated: List[str], legs: List[str],
                     same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Points and a point of M_0,5 with a curve of the type over them."""
        t = self._walk_map(node_id, evaluated, legs, same)
        p, ls = moduli.start(t)
        at = {m: [str(p[2 * i]), str(p[2 * i + 1])] for i, m in enumerate(t.rep_names)}
        for g in t.groups:                      # the others of a group: the same point
            for m in g[1:]:
                at[m] = at[g[0]]
        return {"points": at, "m": moduli.point_json(t.cone, ls)}

    def moduli_view(self, node_id: str, evaluated: List[str], legs: List[str],
                    points: Dict[str, Any], m: Dict[str, Any], radius: Any,
                    same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Everything the explorer draws: the curve over the point (placed in
        the plane), its skeleton, the cell of M_0,5 with the point in it, and
        (for a full-dimensional type) the region and its walls up to radius."""
        t = self._walk_map(node_id, evaluated, legs, same)
        p = self._walk_points(t, evaluated, points)
        cone, ls = moduli.parse_point(m)
        out: Dict[str, Any] = {"id": node_id, "name": self.ws.nodes[node_id].name,
                               "full": t.full, "cone": [list(sp) for sp in t.cone],
                               "skeleton": moduli.skeleton(t),
                               "multiplicity": int(t.det) if t.det is not None else None}
        y = moduli._cone_coords(t.cone, cone, ls)
        out["coords"] = [str(v) for v in y] if y is not None else None
        z = moduli.curve_at(t, p, y) if y is not None else None
        out["picture"] = moduli.picture(t, z, self._render_curve) if z is not None else None
        out["lengths"] = ({e.name: str(z[t.index[e.id]]) for e in t.bounded} if z is not None else None)
        out["region"] = moduli.region(t, p, Fraction(str(radius))) if t.full else None
        why = moduli.explain(t, evaluated, legs)
        out["why"] = why["reason"] if why else ""
        return out

    def moduli_move(self, node_id: str, evaluated: List[str], legs: List[str],
                    points: Dict[str, Any], y_from: List[Any], y_to: List[Any],
                    same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Move the point of M_0,5 (cone coordinates) and stop at the first wall."""
        t = self._walk_map(node_id, evaluated, legs, same)
        if not t.full:
            raise ValueError("the point only moves on a full-dimensional type")
        p = self._walk_points(t, evaluated, points)
        y, eid = moduli.move(t, p, [Fraction(str(v)) for v in y_from], [Fraction(str(v)) for v in y_to])
        y = [max(v, Fraction(0)) for v in y]
        names = {e.id: e.name for e in t.bounded}
        return {"m": moduli.point_json(t.cone, y), "coords": [str(v) for v in y],
                "wall": {"edge": eid, "name": names[eid]} if eid else None}

    def _walk_root(self, curve: Curve) -> str:
        """The library's type equal to this curve, or a new root holding it."""
        key = moduli.type_key(curve)
        for nid, n in self.ws.nodes.items():
            if moduli.type_key(n.curve) == key:
                return nid
        return self.ws.add_root(curve).id

    def moduli_wall(self, node_id: str, edge_id: str, evaluated: List[str],
                    legs: List[str], same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """The type on the wall where edge_id shrank to 0 (kept in the library)
        and its regenerations: each resolution of the vertex left there, drawn
        small, with whether it is the type we came from and whether the point
        can move on it."""
        node = self.ws.nodes[node_id]
        wall, vertex = moduli.contract_at_wall(node.curve, edge_id)
        wall_id = self._walk_root(wall)
        back = moduli.type_key(node.curve)
        regs = []
        for i, c in enumerate(moduli.regenerations(wall, vertex)):
            t = moduli.TypeMap("", "", c, evaluated, legs, same or ())
            why = moduli.explain(t, evaluated, legs)
            regs.append({"index": i, "back": moduli.type_key(c) == back, "full": t.full,
                         "why": why["reason"] if why else "", "picture": self._render_curve(c)})
        return {"wall_id": wall_id, "vertex": vertex, "edge": node.curve.edges[edge_id].name,
                "regenerations": regs}

    def moduli_regenerate(self, wall_id: str, vertex: str, index: int, evaluated: List[str],
                          legs: List[str], points: Dict[str, Any], m: Dict[str, Any],
                          scale: Any, same: Optional[List[List[str]]] = None) -> Dict[str, Any]:
        """Leave the wall into a regeneration: its type (an existing equal one
        is reused) and a point of M_0,5 a little way into its region."""
        wall = self.ws.nodes[wall_id].curve
        c = moduli.regenerations(wall, vertex)[int(index)]
        nid = self._walk_root(c)
        t = self._walk_map(nid, evaluated, legs, same)
        p = self._walk_points(t, evaluated, points)
        y = moduli.step_into(t, p, moduli.parse_point(m), Fraction(str(scale)))
        if y is None:
            why = moduli.explain(t, evaluated, legs)
            return {"id": nid, "m": None,
                    "why": why["reason"] if why else "its new edge does not grow when the point moves"}
        return {"id": nid, "m": moduli.point_json(t.cone, y)}

    # --- render data ----------------------------------------------------
    def render(self, node_id: str) -> Dict[str, Any]:
        n = self.ws.nodes[node_id]
        c = n.curve
        lengths, _ = self._node_layout(node_id)
        out: Dict[str, Any] = {
            "id": n.id,
            "name": n.name,
            "status": n.status,
            "curve": self._render_curve(c, lengths),
        }
        try:
            out["newton"] = [v.to_list() for v in newton_polygon(c)]
        except Exception as exc:  # no ends etc.
            out["newton"] = None
            out["newton_error"] = str(exc)
        try:
            # the displayed lengths first, so the parallelograms are the drawn crossings
            sub = build_subdivision(c, lengths=lengths)
            marked = {m.tail for m in c.markings}
            out["subdivision"] = {
                "cells": [[v.to_list() for v in cell.vertices] for cell in sub.cells],
                # per cell: the vertex it is dual to (None for a crossing),
                # and whether that vertex carries a marking
                "cell_vertices": [cell.vertex for cell in sub.cells],
                "marked": [cell.vertex in marked for cell in sub.cells],
                # every side of every cell, with the curve edge it is dual to
                "edges": [{"a": e.a.to_list(), "b": e.b.to_list(), "edge": e.edge}
                          for e in sub.edges],
            }
            out["subdivision_error"] = None
        except SubdivisionError as exc:
            out["subdivision"] = None
            out["subdivision_error"] = str(exc)
        return out

    def _render_curve(self, c: Curve, lengths=None) -> Dict[str, Any]:
        if lengths is None:
            lengths = display_lengths(c)
        pos = embed(c, lengths)
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
