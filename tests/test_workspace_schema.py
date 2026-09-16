from tropcurves import schema
from tropcurves.geometry import Vec2
from tropcurves.operations import resolutions
from tropcurves.workspace import Workspace
from tropcurves import builders


def _build_workspace():
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    child = ws.contract(root.id, "e", name="4valent")
    v = child.curve.vertices[0]
    res = resolutions(child.curve, v)[0]
    grand = ws.resolve(child.id, res, name="grand")
    ws.set_color(root.id, "a", "#ff0000")
    ws.add_marking(root.id, "v0", name="p1")
    ws.set_follow(grand.id, False)
    return ws, root, child, grand


def test_workspace_roundtrip():
    ws, root, child, grand = _build_workspace()
    text = schema.dumps_workspace(ws, indent=2)
    ws2 = schema.loads_workspace(text)

    assert set(ws2.nodes) == set(ws.nodes)
    for nid, n in ws.nodes.items():
        m = ws2.nodes[nid]
        assert m.name == n.name
        assert m.parent_id == n.parent_id
        assert m.follow_parent == n.follow_parent
        assert m.children == n.children
        assert m.status == n.status
        # curve preserved
        assert m.curve.vertices == n.curve.vertices
        assert set(m.curve.edges) == set(n.curve.edges)
        for eid, e in n.curve.edges.items():
            assert m.curve.edges[eid].vec == e.vec
            assert m.curve.edges[eid].color == e.color
            assert m.curve.edges[eid].name == e.name
        # operation preserved
        if n.operation is None:
            assert m.operation is None
        else:
            assert m.operation.kind == n.operation.kind
            assert m.operation.edge_id == n.operation.edge_id
            assert m.operation.new_edge_id == n.operation.new_edge_id


def test_workspace_counter_continues_after_load():
    ws, *_ = _build_workspace()
    ws2 = schema.loads_workspace(schema.dumps_workspace(ws))
    new = ws2.add_root(builders.standard_line())
    assert new.id not in ws.nodes  # a fresh, non-colliding id


def test_loaded_workspace_still_propagates():
    ws, root, child, grand = _build_workspace()
    ws2 = schema.loads_workspace(schema.dumps_workspace(ws))
    ws2.set_color(root.id, "b", "#00ff00")
    # child follows root -> updated
    assert ws2.nodes[child.id].curve.edges["b"].color == "#00ff00"
    # grand had follow_parent = False -> unchanged
    assert ws2.nodes[grand.id].curve.edges["b"].color != "#00ff00"
