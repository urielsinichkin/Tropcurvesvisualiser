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


# --- refined multiplicity through the session ------------------------------
def _mu_curve(session, vecs, name, marked=False):
    spec = {"vertices": ["v"], "ends": [
        {"id": f"e{i}", "tail": "v", "vec": list(v), "name": f"{name}{i}"}
        for i, v in enumerate(vecs)]}
    if marked:
        spec["markings"] = [{"id": "m1", "tail": "v", "name": name + "p"}]
    return session.add_curve(spec, name=name)["id"]


def test_refined_multiplicity_reports_the_value_and_the_vertices():
    s = Session()
    node = _mu_curve(s, [(2, 0), (-1, 1), (-1, -1)], "two")
    info = s.refined_multiplicity(node)

    assert info["defined"] and info["text"] == "q^(1/2) + q^(-1/2)"
    assert info["is_polynomial"] and info["at_q_1"] == "2"
    assert info["vertices"] == [{"vertex": "v", "mu": 2, "marked": False,
                                 "interior": False, "factor": "[2]-"}]


def test_a_marking_on_an_edge_does_not_change_the_multiplicity():
    s = Session()
    node = s.add_preset("caterpillar_square")["id"]
    before = s.refined_multiplicity(node)["text"]
    s.add_marking_on_edge(node, "e", "mid")
    after = s.refined_multiplicity(node)

    assert after["defined"] and after["text"] == before
    assert [v["factor"] for v in after["vertices"]].count("1") == 1
    assert [v for v in after["vertices"] if v["interior"]][0]["marked"] is True


def test_refined_multiplicity_says_why_it_is_undefined():
    s = Session()
    node = s.add_preset("caterpillar_square")["id"]
    four = s.contract(node, "e")["id"]
    info = s.refined_multiplicity(four)

    assert not info["defined"]
    assert "trivalent" in info["reason"]


def test_balanced_split_finds_the_halves():
    s = Session()
    ids = [_mu_curve(s, [(2, 0), (-1, 1), (-1, -1)], "a"),
           _mu_curve(s, [(3, 0), (-1, 1), (-2, -1)], "b"),
           _mu_curve(s, [(2, 0), (-1, 1), (-1, -1)], "c"),
           _mu_curve(s, [(3, 0), (-1, 1), (-2, -1)], "d")]
    out = s.balanced_split(ids)

    assert out["ok"] and out["found"]
    assert sorted(out["subset"] + out["complement"]) == sorted(ids)
    assert len(out["subset"]) == 2
    # each half is one of each kind
    assert {s.refined_multiplicity(i)["text"] for i in out["subset"]} == \
           {s.refined_multiplicity(i)["text"] for i in out["complement"]}


def test_balanced_split_reports_when_there_is_none():
    s = Session()
    ids = [_mu_curve(s, [(2, 0), (-1, 1), (-1, -1)], "a"),
           _mu_curve(s, [(3, 0), (-1, 1), (-2, -1)], "b")]
    out = s.balanced_split(ids)

    assert out["ok"] and not out["found"]
    assert out["total"] == "q + q^(1/2) + 1 + q^(-1/2) + q^-1"


def test_balanced_split_needs_every_multiplicity_to_exist():
    s = Session()
    good = _mu_curve(s, [(2, 0), (-1, 1), (-1, -1)], "a")
    preset = s.add_preset("caterpillar_square")["id"]
    bad = s.contract(preset, "e")["id"]

    out = s.balanced_split([good, bad])

    assert not out["ok"]
    assert [u["id"] for u in out["undefined"]] == [bad]


# --- exporting part of a workspace -----------------------------------------
def _chain_session():
    s = Session()
    root = s.add_preset("caterpillar_square")["id"]
    mid = s.contract(root, "e", name="four")["id"]
    v = [x for x, k in s.node_summary(mid)["valences"].items() if k == 4][0]
    leaf = s.resolve(mid, v, 0, name="leaf")["id"]
    return s, root, mid, leaf


def test_exporting_everything_matches_a_plain_save():
    s, root, mid, leaf = _chain_session()
    assert s.export_subset([root, mid, leaf]) == s.save()


def test_a_skipped_middle_type_is_composed_away():
    s, root, mid, leaf = _chain_session()

    back = Session()
    back.load(s.export_subset([root, leaf]))

    assert sorted(n["id"] for n in back.list_nodes()) == sorted([root, leaf])
    assert back.node_summary(leaf)["parent_id"] == root
    assert [op.kind for op in back.ws.nodes[leaf].operations] == ["contract", "resolve"]
    # the curve came across unchanged, and edits still reach it
    assert back.render(leaf)["curve"] == s.render(leaf)["curve"]
    back.set_color(root, "a", "#ff0000")
    assert back.node_summary(leaf)["status"] == "ok"
    assert [e for e in back.render(leaf)["curve"]["edges"]
            if e["id"] == "a"][0]["color"] == "#ff0000"


def test_a_type_with_no_included_ancestor_becomes_a_root():
    s, root, mid, leaf = _chain_session()

    back = Session()
    back.load(s.export_subset([leaf]))

    assert [n["id"] for n in back.list_nodes()] == [leaf]
    assert back.node_summary(leaf)["parent_id"] is None
    assert back.ws.nodes[leaf].operations == []
    assert back.render(leaf)["curve"] == s.render(leaf)["curve"]


def test_exporting_a_subset_leaves_the_workspace_alone():
    s, root, mid, leaf = _chain_session()
    before = s.save()
    s.export_subset([leaf])
    assert s.save() == before


def test_exporting_an_unknown_id_is_refused():
    s, root, mid, leaf = _chain_session()
    with pytest.raises(ValueError):
        s.export_subset([root, "nope"])
