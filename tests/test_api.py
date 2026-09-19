import json

import pytest

from tropcurves.api import Session


def test_add_preset_and_render_is_json_serializable():
    s = Session()
    summ = s.add_preset("caterpillar_square")
    nid = summ["id"]
    r = s.render(nid)
    # fully JSON serializable
    text = json.dumps(r)
    assert text
    assert r["curve"]["vertices"]
    assert any(e["kind"] == "bounded" for e in r["curve"]["edges"])
    assert any(e["kind"] == "end" for e in r["curve"]["edges"])
    assert r["newton"]
    assert r["subdivision"] is not None
    assert len(r["subdivision"]["cells"]) == 2


def test_add_curve_from_spec_solves_slopes():
    s = Session()
    spec = {
        "vertices": ["v0", "v1"],
        "bounded": [{"id": "e", "tail": "v0", "head": "v1"}],  # vec solved
        "ends": [
            {"id": "a", "tail": "v0", "vec": [-1, 0]},
            {"id": "b", "tail": "v0", "vec": [0, -1]},
            {"id": "c", "tail": "v1", "vec": [1, 0]},
            {"id": "d", "tail": "v1", "vec": [0, 1]},
        ],
    }
    summ = s.add_curve(spec, name="mine")
    assert summ["num_bounded"] == 1
    r = s.render(summ["id"])
    assert r["subdivision"] is not None


def test_contract_resolutions_resolve_flow():
    s = Session()
    root = s.add_preset("caterpillar_square")
    child = s.contract(root["id"], "e", name="4val")
    assert child["num_bounded"] == 0
    v = next(iter(child["valences"]))
    reslist = s.list_resolutions(child["id"], v)
    assert len(reslist) == 3
    assert sum(1 for r in reslist if r["is_crossing"]) == 1
    triv = [r for r in reslist if not r["is_crossing"]][0]
    grand = s.resolve(child["id"], v, triv["index"], name="g")
    assert grand["num_bounded"] == 1


def test_resolve_crossing_index_rejected():
    s = Session()
    root = s.add_preset("caterpillar_square")
    child = s.contract(root["id"], "e")
    v = next(iter(child["valences"]))
    crossing = [r for r in s.list_resolutions(child["id"], v) if r["is_crossing"]][0]
    with pytest.raises(ValueError):
        s.resolve(child["id"], v, crossing["index"])


def test_edit_and_save_load_roundtrip():
    s = Session()
    root = s.add_preset("caterpillar_square")
    s.set_color(root["id"], "a", "#ff0000")
    s.contract(root["id"], "e")
    text = s.save()
    s2 = Session()
    s2.load(text)
    assert len(s2.list_nodes()) == 2
    # color survived
    r = s2.render(root["id"])
    a = next(e for e in r["curve"]["edges"] if e["id"] == "a")
    assert a["color"] == "#ff0000"


def test_render_reports_subdivision_error_gracefully():
    s = Session()
    # degenerate: two ends at v0 share direction (1,0) via weight -> forced overlap
    spec = {
        "vertices": ["v0", "v1", "v2"],
        "bounded": [{"id": "e1", "tail": "v0", "head": "v1"},
                    {"id": "e2", "tail": "v1", "head": "v2"}],
        "ends": [
            {"id": "A", "tail": "v0", "vec": [1, 2]},
            {"id": "B", "tail": "v0", "vec": [3, 0]},
            {"id": "C", "tail": "v1", "vec": [-3, -3]},
            {"id": "D", "tail": "v2", "vec": [2, -2]},
            {"id": "E", "tail": "v2", "vec": [-3, 3]},
        ],
    }
    summ = s.add_curve(spec)
    r = s.render(summ["id"])
    assert r["subdivision"] is None
    assert r["subdivision_error"]


def test_render_gives_each_marking_the_valence_it_is_drawn_from():
    # the UI sizes a marking by the valence of the vertex it hangs from, so the
    # render payload has to carry it
    s = Session()
    node = s.add_preset("caterpillar_square")
    s.add_marking_on_edge(node["id"], "e", "on-edge")     # a new trivalent vertex
    s.add_marking(node["id"], "v0", "at-vertex")          # v0 was trivalent -> 4
    marks = {m["name"]: m for m in s.render(node["id"])["curve"]["markings"]}
    assert marks["on-edge"]["valence"] == 3
    assert marks["at-vertex"]["valence"] == 4
    # and each sits exactly on its vertex
    verts = {v["id"]: (v["x"], v["y"]) for v in s.render(node["id"])["curve"]["vertices"]}
    for m in marks.values():
        assert tuple(m["at"]) == verts[m["tail"]]


def _five_valent_session():
    s = Session()
    spec = {"vertices": ["v"], "ends": [
        {"id": "e0", "tail": "v", "vec": [1, 0], "name": "l0"},
        {"id": "e1", "tail": "v", "vec": [0, 1], "name": "l1"},
        {"id": "e2", "tail": "v", "vec": [-1, 0], "name": "l2"},
        {"id": "e3", "tail": "v", "vec": [2, 1], "name": "l3"},
        {"id": "e4", "tail": "v", "vec": [-2, -2], "name": "l4"},
    ]}
    return s, s.add_curve(spec, name="five")["id"]


def test_preview_says_what_a_split_would_do():
    s, node = _five_valent_session()
    ok = s.preview_resolution(node, "v", ["e0", "e1"])
    assert ok["ok"] and ok["new_edge_vec"] == [-1, -1]
    assert "l0" in ok["label"] and "l1" in ok["label"]

    too_small = s.preview_resolution(node, "v", ["e0"])
    assert not too_small["ok"] and "two" in too_small["reason"]

    s2, n2 = Session(), None
    n2 = s2.add_curve({"vertices": ["v"], "ends": [
        {"id": "a", "tail": "v", "vec": [1, 0]}, {"id": "b", "tail": "v", "vec": [-1, 0]},
        {"id": "c", "tail": "v", "vec": [0, 1]}, {"id": "d", "tail": "v", "vec": [0, -1]},
        {"id": "e", "tail": "v", "vec": [2, 2]}, {"id": "f", "tail": "v", "vec": [-2, -2]},
    ]})["id"]
    crossing = s2.preview_resolution(n2, "v", ["a", "b"])
    assert not crossing["ok"] and crossing["is_crossing"]


def test_resolve_subset_creates_the_split_child():
    s, node = _five_valent_session()
    child = s.resolve_subset(node, "v", ["e0", "e1"], name="split")

    assert child["parent_id"] == node
    assert child["num_bounded"] == 1
    assert sorted(child["valences"].values()) == [3, 4]
    assert child["genus"] == 0
    # and the child can be split again
    big = [v for v, k in child["valences"].items() if k == 4][0]
    again = s.resolve_subset(child["id"], big, [e["id"] for e in
                             s.render(child["id"])["curve"]["edges"]
                             if e.get("tail") == big or e.get("head") == big][:2])
    assert sorted(again["valences"].values()) == [3, 3, 3]


def test_resolve_subset_refuses_a_crossing():
    s = Session()
    node = s.add_curve({"vertices": ["v"], "ends": [
        {"id": "a", "tail": "v", "vec": [1, 0]}, {"id": "b", "tail": "v", "vec": [-1, 0]},
        {"id": "c", "tail": "v", "vec": [0, 1]}, {"id": "d", "tail": "v", "vec": [0, -1]},
        {"id": "e", "tail": "v", "vec": [2, 2]}, {"id": "f", "tail": "v", "vec": [-2, -2]},
    ]})["id"]
    with pytest.raises(ValueError):
        s.resolve_subset(node, "v", ["a", "b"])
