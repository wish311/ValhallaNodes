import os
import json
import tempfile

import pytest

from valhalla_nodes import load_json, format_coords, export_lua


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
    assert packed == 123000456000


def test_export_lua(tmp_path):
    nodes = [{"map_name": "Testland", "node_name": "Foo", "coords": (1.0, 2.0)}]
    map_ids = {"Testland": 42}
    node_ids = {"Foo": 99}
    export_lua("herbalism", nodes, map_ids, node_ids, str(tmp_path))
    lua_path = tmp_path / "HerbalismData.lua"
    assert lua_path.exists()
    content = lua_path.read_text().splitlines()
    assert content[0] == "GatherMate2HerbalismData = {"
    assert content[1].strip() == "[42] = {"
    assert any("99" in line for line in content)

