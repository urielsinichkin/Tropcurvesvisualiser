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


def test_duplicate_copies_curve_as_independent_root():
    ws, root, child = _root_and_contracted()
    ws.set_color(root.id, "a", "#ff0000")
    ws.add_marking(root.id, "v0", name="p1")

    dup = ws.duplicate(root.id)

    # an independent root: no parent, no operation, none of root's children
    assert dup.parent_id is None
    assert dup.operation is None
    assert dup.children == []
    assert dup.id != root.id
    # same content
    assert set(dup.curve.edges) == set(root.curve.edges)
    assert dup.curve.edges["a"].color == "#ff0000"
    assert dup.curve.edges["a"].vec == root.curve.edges["a"].vec
    assert [e.name for e in dup.curve.markings] == ["p1"]
    assert dup.curve.is_balanced() and dup.curve.is_tree()


def test_duplicate_is_isolated_from_the_original():
    ws, root, child = _root_and_contracted()
    dup = ws.duplicate(root.id)

    # editing the original must not touch the copy...
    ws.set_color(root.id, "a", "#111111")
    assert dup.curve.edges["a"].color != "#111111"
    # ...and the copy's own edits must not touch the original
    ws.set_color(dup.id, "a", "#222222")
    assert root.curve.edges["a"].color == "#111111"
    # the original's child still follows the original only
    assert child.curve.edges["a"].color == "#111111"


def test_duplicate_names_avoid_collisions():
    ws, root, child = _root_and_contracted()
    first = ws.duplicate(root.id)
    second = ws.duplicate(root.id)
    assert first.name == "root copy"
    assert second.name == "root copy 2"
    explicit = ws.duplicate(root.id, name="my variant")
    assert explicit.name == "my variant"


def test_delete_leaf_removes_it_and_unlinks_from_parent():
    ws, root, child = _root_and_contracted()
    removed = ws.delete(child.id)
    assert removed == [child.id]
    assert child.id not in ws.nodes
    assert child.id not in root.children
    assert root.id in ws.nodes


def test_delete_detaches_children_into_roots_by_default():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    grand = ws.resolve(child.id, resolutions(child.curve, v)[0])
    before = {e.id: e.vec for e in child.curve.bounded}

    removed = ws.delete(root.id)

    assert removed == [root.id]
    assert root.id not in ws.nodes
    # the derived types survive, promoted to independent roots
    assert child.id in ws.nodes and grand.id in ws.nodes
    assert child.parent_id is None
    assert child.operation is None      # can't be replayed without its parent
    assert child.status == STATUS_OK
    assert {e.id: e.vec for e in child.curve.bounded} == before  # curve intact
    # the grandchild still hangs off the child, which is untouched
    assert grand.parent_id == child.id
    assert grand.id in child.children


def test_delete_cascade_removes_the_whole_subtree():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    grand = ws.resolve(child.id, resolutions(child.curve, v)[0])

    removed = ws.delete(root.id, cascade=True)

    assert set(removed) == {root.id, child.id, grand.id}
    assert ws.nodes == {}


def test_descendants_are_transitive():
    ws, root, child = _root_and_contracted()
    v = child.curve.vertices[0]
    grand = ws.resolve(child.id, resolutions(child.curve, v)[0])
    assert set(ws.descendants(root.id)) == {child.id, grand.id}
    assert ws.descendants(grand.id) == []


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


# --- markings placed on an edge, and what that does to derived types -------
def test_marking_on_an_end_propagates_through_a_resolution():
    # the user's case: resolve a 4-valent vertex, then mark one of the ends
    # that was separated by the resolution. The end is subdivided, so the flag
    # at the resolved vertex is now the stub -- the resolution still separates
    # the same four directions and must replay.
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    four = ws.contract(root.id, "e")                 # one 4-valent vertex
    v = four.curve.vertices[0]
    res = next(r for r in resolutions(four.curve, v) if "a" in r.side_a + r.side_b)
    child = ws.resolve(four.id, res)
    assert child.status == STATUS_OK

    ws.add_marking_on_edge(four.id, "a", name="p")

    assert child.status == STATUS_OK
    child.curve.validate()
    assert len(child.curve.markings) == 1            # the marking came along
    assert child.curve.edges["a"].vec == four.curve.edges["a"].vec
    assert newton_polygon(child.curve) == newton_polygon(four.curve)


def test_subdivision_does_not_steal_ids_a_child_already_uses():
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    four = ws.contract(root.id, "e")
    v = four.curve.vertices[0]
    child = ws.resolve(four.id, resolutions(four.curve, v)[0])
    claimed = {child.operation.new_vertex_id, child.operation.new_edge_id}

    ws.add_marking_on_edge(four.id, "a")

    parent_new = set(four.curve.vertices) | set(four.curve.edges)
    assert not (claimed & parent_new)                # ids kept apart
    assert child.status == STATUS_OK


def test_marking_a_contracted_edge_still_identifies_the_same_vertices():
    # the child is "the type where edge e has length 0"; a marked point in the
    # interior of e ends up at the merged vertex, so both pieces contract
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    child = ws.contract(root.id, "e")
    assert len(child.curve.vertices) == 1

    ws.add_marking_on_edge(root.id, "e", name="p")

    assert child.status == STATUS_OK
    child.curve.validate()
    assert len(child.curve.vertices) == 1            # still one merged vertex
    assert len(child.curve.bounded) == 0             # no piece left behind
    assert len(child.curve.markings) == 1
    assert child.curve.markings[0].tail == child.curve.vertices[0]


def test_stale_recorded_pairing_is_repaired_on_replay():
    # a workspace saved before the records were kept in step can name a flag
    # that has since been renamed; the correspondence is forced, so it heals
    ws = Workspace()
    root = ws.add_root(builders.caterpillar_square(), name="root")
    four = ws.contract(root.id, "e")
    v = four.curve.vertices[0]
    child = ws.resolve(four.id, resolutions(four.curve, v)[0])
    recorded = child.operation.side_a, child.operation.side_b
    ws.add_marking_on_edge(four.id, "a")

    op = child.operation
    op.side_a, op.side_b = recorded            # rewind to the pre-edit ids
    child.status = STATUS_NEEDS_ATTENTION
    healed = ws.retry_failed()

    assert healed == [child.id]
    assert child.status == STATUS_OK
    child.curve.validate()
    # the record now names the stub that took 'a'-s place at the vertex
    assert "a" not in op.side_a + op.side_b
