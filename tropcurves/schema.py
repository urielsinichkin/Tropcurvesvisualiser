"""Versioned JSON (de)serialization for combinatorial types.

v1 serializes a single :class:`~tropcurves.curve.Curve`. The workspace/forest
schema (many types + derivation tree) is layered on top in a later phase and
will reuse ``curve_to_dict`` / ``curve_from_dict`` per node.
"""

from __future__ import annotations

import json
from typing import Any, Dict

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
        color=d.get("color", "#000000"),
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
