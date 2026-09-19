"""Versioned JSON (de)serialization for combinatorial types.

v1 serializes a single :class:`~tropcurves.curve.Curve`. The workspace/forest
schema (many types + derivation tree) is layered on top in a later phase and
will reuse ``curve_to_dict`` / ``curve_from_dict`` per node.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .curve import Curve, Edge, EdgeKind
from .geometry import Vec2

SCHEMA_VERSION = 1


def edge_to_dict(e: Edge) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": e.id,
        "kind": e.kind.value,
        "tail": e.tail,
        "vec": e.vec.to_list(),
        "name": e.name,
        "color": e.color,
    }
    if e.head is not None:
        d["head"] = e.head
    return d


def edge_from_dict(d: Dict[str, Any]) -> Edge:
    return Edge(
        id=d["id"],
        kind=EdgeKind(d["kind"]),
        tail=d["tail"],
        head=d.get("head"),
        vec=Vec2.from_iterable(d["vec"]),
        name=d.get("name", ""),
        color=d.get("color", ""),
    )


def curve_to_dict(curve: Curve) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "curve",
        "vertices": list(curve.vertices),
        "edges": [edge_to_dict(e) for e in curve.edges.values()],
    }


def curve_from_dict(d: Dict[str, Any]) -> Curve:
    version = d.get("schema")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version {version!r}; expected {SCHEMA_VERSION}")
    curve = Curve()
    for vid in d["vertices"]:
        curve.add_vertex(vid)
    for ed in d["edges"]:
        curve.add_edge(edge_from_dict(ed))
    return curve


def dumps(curve: Curve, *, indent: int | None = None) -> str:
    return json.dumps(curve_to_dict(curve), indent=indent)


def loads(text: str) -> Curve:
    return curve_from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# workspace (forest of derived types)
# ---------------------------------------------------------------------------
def _operation_to_dict(op) -> Optional[Dict[str, Any]]:
    if op is None:
        return None
    d: Dict[str, Any] = {"kind": op.kind}
    for f in ("edge_id", "vertex_id", "new_vertex_id", "new_edge_id"):
        if getattr(op, f) is not None:
            d[f] = getattr(op, f)
    if op.side_a is not None:
        d["side_a"] = list(op.side_a)
    if op.side_b is not None:
        d["side_b"] = list(op.side_b)
    if op.split_pieces:
        d["split_pieces"] = list(op.split_pieces)
    return d


def _operation_from_dict(d: Optional[Dict[str, Any]]):
    from .workspace import Operation

    if d is None:
        return None
    return Operation(
        kind=d["kind"],
        edge_id=d.get("edge_id"),
        vertex_id=d.get("vertex_id"),
        side_a=tuple(d["side_a"]) if "side_a" in d else None,
        side_b=tuple(d["side_b"]) if "side_b" in d else None,
        new_vertex_id=d.get("new_vertex_id"),
        new_edge_id=d.get("new_edge_id"),
        split_pieces=list(d.get("split_pieces", [])),
    )


def workspace_to_dict(ws) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "kind": "workspace",
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "parent_id": n.parent_id,
                "operation": _operation_to_dict(n.operation),
                "follow_parent": n.follow_parent,
                "children": list(n.children),
                "status": n.status,
                "curve": curve_to_dict(n.curve),
            }
            for n in ws.nodes.values()
        ],
    }


def workspace_from_dict(d: Dict[str, Any]):
    import itertools
    import re

    from .workspace import Workspace, TypeNode

    if d.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version {d.get('schema')!r}")
    ws = Workspace()
    max_num = 0
    for nd in d["nodes"]:
        node = TypeNode(
            id=nd["id"],
            curve=curve_from_dict(nd["curve"]),
            name=nd.get("name", nd["id"]),
            parent_id=nd.get("parent_id"),
            operation=_operation_from_dict(nd.get("operation")),
            follow_parent=nd.get("follow_parent", True),
            children=list(nd.get("children", [])),
            status=nd.get("status", "ok"),
        )
        ws.nodes[node.id] = node
        m = re.fullmatch(r"T(\d+)", node.id)
        if m:
            max_num = max(max_num, int(m.group(1)))
    ws._counter = itertools.count(max_num + 1)
    return ws


def dumps_workspace(ws, *, indent: int | None = None) -> str:
    return json.dumps(workspace_to_dict(ws), indent=indent)


def loads_workspace(text: str):
    return workspace_from_dict(json.loads(text))
