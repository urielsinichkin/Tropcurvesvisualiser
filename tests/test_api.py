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
