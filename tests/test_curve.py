import pytest

from tropcurves.curve import Curve, Edge, EdgeKind
from tropcurves.geometry import Vec2, ZERO
from tropcurves import builders


def test_line_is_balanced_tree():
    c = builders.standard_line()
    assert c.is_tree()
    assert c.genus == 0
    assert c.is_balanced()
    assert c.valence("v0") == 3
    assert len(c.ends) == 3
    assert len(c.bounded) == 0


def test_caterpillar_structure():
    c = builders.caterpillar_square()
    assert c.is_tree()
    assert c.is_balanced()
    assert c.edges["e"].vec == Vec2(1, 1)
    assert c.edges["e"].weight == 1
    assert c.valence("v0") == 3 and c.valence("v1") == 3


def test_outgoing_orientation():
    c = builders.caterpillar_square()
    e = c.edges["e"]
    assert e.outgoing("v0") == Vec2(1, 1)
    assert e.outgoing("v1") == Vec2(-1, -1)
    with pytest.raises(ValueError):
        e.outgoing("v0_nope")


def test_marking_has_zero_direction_and_no_effect():
    c = builders.standard_line()
    c.add_marking("m1", "v0", name="p1")
    assert c.edges["m1"].vec == ZERO
    assert c.is_balanced("v0")  # marking contributes 0
    assert c.valence("v0") == 4  # marking counts as incident


def test_marking_rejects_nonzero():
    with pytest.raises(ValueError):
        Edge("m", EdgeKind.MARKING, "v0", None, Vec2(1, 0))


def test_bounded_requires_head():
    with pytest.raises(ValueError):
        Edge("e", EdgeKind.BOUNDED, "v0", None, Vec2(1, 0))


def test_end_rejects_head():
    with pytest.raises(ValueError):
        Edge("l", EdgeKind.END, "v0", "v1", Vec2(1, 0))


def test_duplicate_ids_and_names():
    c = Curve()
    c.add_vertex("v0")
    c.add_end("a", "v0", Vec2(-1, 0), name="a")
    with pytest.raises(ValueError):
        c.add_end("a", "v0", Vec2(0, -1))  # duplicate id
    with pytest.raises(ValueError):
        c.add_end("a2", "v0", Vec2(0, -1), name="a")  # duplicate name


def test_auto_naming_unique():
    c = Curve()
    c.add_vertex("v0")
    e1 = c.add_end("id1", "v0", Vec2(-1, 0))
    e2 = c.add_end("id2", "v0", Vec2(0, -1))
    e3 = c.add_end("id3", "v0", Vec2(1, 1))
    names = {e1.name, e2.name, e3.name}
    assert names == {"l1", "l2", "l3"}


def test_genus_and_cycle_detection():
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e1", "v0", "v1", Vec2(1, 0))
    c.add_bounded("e2", "v0", "v1", Vec2(1, 0))  # parallel edge -> a cycle
    comps, betti = c.components_and_cycles()
    assert comps == 1
    assert betti == 1
    assert c.genus == 1
    assert not c.is_tree()


def test_validate_rejects_positive_genus():
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e1", "v0", "v1", Vec2(1, 0))
    c.add_bounded("e2", "v0", "v1", Vec2(1, 0))
    with pytest.raises(ValueError):
        c.validate(require_balanced=False)


def test_validate_rejects_degenerate_edge():
    c = Curve()
    c.add_vertex("v0")
    c.add_vertex("v1")
    c.add_bounded("e", "v0", "v1", ZERO)
    c.add_end("a", "v0", Vec2(-1, 0))
    c.add_end("b", "v1", Vec2(1, 0))
    with pytest.raises(ValueError):
        c.validate(require_balanced=False)


def test_validate_accepts_good_curve():
    c = builders.caterpillar_square()
    c.validate()  # should not raise


def test_rename_and_color():
    c = builders.caterpillar_square()
    c.rename_edge("e", "middle")
    assert c.edges["e"].name == "middle"
    with pytest.raises(ValueError):
        c.rename_edge("e", "a")  # clashes with end a
    c.set_color("e", "#ff0000")
    assert c.edges["e"].color == "#ff0000"


def test_copy_is_independent():
    c = builders.caterpillar_square()
    d = c.copy()
    d.edges["e"].vec = Vec2(9, 9)
    d.edges["e"].name = "changed"
    assert c.edges["e"].vec == Vec2(1, 1)
    assert c.edges["e"].name == "e"
