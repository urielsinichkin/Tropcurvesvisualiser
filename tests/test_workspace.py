import pytest

from tropcurves.geometry import Vec2
from tropcurves.newton import newton_polygon
from tropcurves.operations import resolutions
from tropcurves.workspace import Workspace, STATUS_OK, STATUS_NEEDS_ATTENTION
from tropcurves import builders


def _root_and_contracted():
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    child = ws.contract(root.id, "e", name="4valent")
    return ws, root, child


def test_contract_creates_child_link():
    ws, root, child = _root_and_contracted()
    assert child.parent_id == root.id
    assert child.id in root.children
    assert child.curve.valence(child.curve.vertices[0]) == 4


def test_color_propagates_to_child():
    ws, root, child = _root_and_contracted()
    ws.set_color(root.id, "a", "#ff0000")
    assert child.curve.edges["a"].color == "#ff0000"


def test_rename_propagates_to_child():
    ws, root, child = _root_and_contracted()
    ws.rename_edge(root.id, "a", "alpha")
    assert child.curve.edges["a"].name == "alpha"


def test_slope_edit_propagates_and_stays_balanced():
    ws, root, child = _root_and_contracted()
    ws.edit_slopes(root.id, "a", Vec2(-2, -1), dependent_end_id="c")
    assert root.curve.edges["a"].vec == Vec2(-2, -1)
    # child re-derived from the edited parent
    assert child.curve.edges["a"].vec == Vec2(-2, -1)
    assert child.curve.is_balanced()
    # ends match -> same Newton polygon on both
    assert set((v.x, v.y) for v in newton_polygon(root.curve)) == \
        set((v.x, v.y) for v in newton_polygon(child.curve))


def test_marking_propagates_to_child():
    ws, root, child = _root_and_contracted()
    mid = ws.add_marking(root.id, "v0", name="p1", color="#00ff00")
    assert mid in child.curve.edges
    assert child.curve.edges[mid].name == "p1"
    assert child.curve.is_balanced()


def test_follow_flag_off_blocks_propagation():
    ws, root, child = _root_and_contracted()
    ws.set_follow(child.id, False)
    ws.set_color(root.id, "a", "#123456")
    assert child.curve.edges["a"].color != "#123456"


def test_transitive_propagation_through_resolve():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    res = resolutions(child.curve, v)[0]
    grand = ws.resolve(child.id, res, name="grand")
    ws.set_color(root.id, "a", "#abcdef")
    assert child.curve.edges["a"].color == "#abcdef"
    assert grand.curve.edges["a"].color == "#abcdef"  # propagated two levels
    assert grand.status == STATUS_OK
    assert grand.curve.is_balanced()


def test_resolve_new_edge_presentation_preserved_on_replay():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    res = resolutions(child.curve, v)[0]
    grand = ws.resolve(child.id, res)
    ws.rename_edge(grand.id, grand.operation.new_edge_id, "middle")
    ws.set_color(grand.id, grand.operation.new_edge_id, "#777777")
    # editing the root re-derives grand; the inserted edge keeps its name/color
    ws.set_color(root.id, "a", "#010101")
    assert grand.curve.edges[grand.operation.new_edge_id].name == "middle"
    assert grand.curve.edges[grand.operation.new_edge_id].color == "#777777"


def test_needs_attention_when_resolve_no_longer_applies():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    res = resolutions(child.curve, v)[0]
    grand = ws.resolve(child.id, res)
    assert grand.status == STATUS_OK
    # add a marking at the resolved 4-valent vertex -> it becomes 5-valent, so
    # the stored resolution can no longer be replayed
    ws.add_marking(child.id, v)
    assert grand.status == STATUS_NEEDS_ATTENTION
