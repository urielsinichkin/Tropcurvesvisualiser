import json

import pytest

from tropcurves import schema
from tropcurves.geometry import Vec2
from tropcurves.curve import EdgeKind
from tropcurves import builders


def test_roundtrip_caterpillar():
    c = builders.caterpillar_square()
    c.add_marking("m1", "v0", name="p1", color="#00ff00")
    text = schema.dumps(c, indent=2)
    d = schema.loads(text)
    assert d.vertices == c.vertices
    assert set(d.edges) == set(c.edges)
    for eid, e in c.edges.items():
        de = d.edges[eid]
        assert de.kind is e.kind
        assert de.tail == e.tail
        assert de.head == e.head
        assert de.vec == e.vec
        assert de.name == e.name
        assert de.color == e.color
    assert d.is_balanced()
    assert d.is_tree()


def test_schema_version_present():
    c = builders.standard_line()
    d = json.loads(schema.dumps(c))
    assert d["schema"] == schema.SCHEMA_VERSION
    assert d["kind"] == "curve"


def test_rejects_unknown_version():
    c = builders.standard_line()
    d = schema.curve_to_dict(c)
    d["schema"] = 999
    with pytest.raises(ValueError):
        schema.curve_from_dict(d)


def test_marking_serialized_without_head():
    c = builders.standard_line()
    c.add_marking("m1", "v0")
    d = schema.curve_to_dict(c)
    md = next(e for e in d["edges"] if e["id"] == "m1")
    assert "head" not in md
    assert md["vec"] == [0, 0]
    assert md["kind"] == EdgeKind.MARKING.value
