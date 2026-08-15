import os
import json
import tempfile

import pytest

from valhalla_nodes import load_json, format_coords, normalize_coord, export_lua, run_export


def test_load_json_missing(tmp_path):
    path = tmp_path / "missing.json"
    assert load_json(str(path)) == {}


def test_load_json_existing(tmp_path):
    path = tmp_path / "data.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"a": 1}, f)
    assert load_json(str(path)) == {"a": 1}


def test_format_coords():
    packed = format_coords(12.3, 45.6)
    assert packed == 123045600000


def _gathermate2_decode(packed: int) -> tuple[float, float]:
    """Mirror GatherMate2's real GatherMate:DecodeLoc(id), so this test
    catches any future regression in the packed integer format instead of
    only checking format_coords against itself."""
    x = (packed // 1000000) / 10000
    y = (packed % 1000000 // 100) / 10000
    return x, y


def test_format_coords_round_trips_through_gathermate2_decode():
    x, y = _gathermate2_decode(format_coords(0.3742, 0.6805))
    assert x == pytest.approx(0.3742)
    assert y == pytest.approx(0.6805)


def test_normalize_coord_converts_wowhead_percentage_to_fraction():
    assert normalize_coord(37.42, 68.05) == pytest.approx((0.3742, 0.6805))


def test_export_lua(tmp_path):
    nodes = [{"map_name": "Testland", "node_name": "Foo", "coords": (0.1, 0.2)}]
    map_ids = {"Testland": 42}
    node_ids = {"Foo": 99}
    export_lua("herbalism", nodes, map_ids, node_ids, str(tmp_path))
    lua_path = tmp_path / "HerbalismData.lua"
    assert lua_path.exists()
    content = lua_path.read_text().splitlines()
    assert content[0] == "GatherMate2HerbalismData = {"
    assert content[1].strip() == "[42] = {"
    assert any("99" in line for line in content)


def test_export_lua_logs_and_counts_skipped_unknown_nodes(tmp_path):
    nodes = [
        {"map_name": "Testland", "node_name": "Foo", "coords": (0.1, 0.2)},
        {"map_name": "Unknown Zone", "node_name": "Foo", "coords": (0.3, 0.4)},
    ]
    map_ids = {"Testland": 42}
    node_ids = {"Foo": 99}
    messages = []
    skipped = export_lua("herbalism", nodes, map_ids, node_ids, str(tmp_path), log_callback=messages.append)
    assert skipped == 1
    assert any("Skipped 1" in msg for msg in messages)


def test_run_export_filters_by_expansion_and_exports(tmp_path, monkeypatch):
    import valhalla_nodes

    def fake_scrape(node_type, expansion, log_callback, session=None):
        return [
            {"map_name": "InZone", "node_name": "Foo", "coords": (0.1, 0.2)},
            {"map_name": "OutOfZone", "node_name": "Foo", "coords": (0.3, 0.4)},
        ]

    monkeypatch.setattr(valhalla_nodes, "scrape_nodes", fake_scrape)

    expansion_map = {"TestExpansion": [42]}
    map_ids = {"InZone": 42, "OutOfZone": 7}
    node_ids = {"Foo": 99}
    logs = []

    run_export(["herbalism"], "TestExpansion", str(tmp_path), expansion_map, map_ids, node_ids, logs.append)

    lua_path = tmp_path / "HerbalismData.lua"
    assert lua_path.exists()
    content = lua_path.read_text()
    assert "[42]" in content
    assert "[7]" not in content
