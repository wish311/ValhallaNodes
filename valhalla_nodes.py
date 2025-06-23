#!/usr/bin/env python3
"""ValhallaNodes - GatherMate2 Data Fixer & Node Importer.

Where node data rises again. Scrapes node information from WoWHead and
exports it in GatherMate2 Lua format. Includes a Tkinter GUI to make the
process user friendly.
"""
from __future__ import annotations

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup


# URLs for gathering object lists on Wowhead
WOWHEAD_OBJECT_PAGES = {
    "herbalism": "https://www.wowhead.com/objects/herbs",
    "mining": "https://www.wowhead.com/objects/mining",
    "fishing": "https://www.wowhead.com/objects/fishing",
    "treasure": "https://www.wowhead.com/objects/treasure",
    "gas": "https://www.wowhead.com/objects/gas-clouds",
}
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# ------------------------- Utility Functions -------------------------

def load_json(path: str) -> dict:
    """Load JSON data from a file, returning an empty dict if missing."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict) -> None:
    """Save JSON data to a file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ------------------------- Scraping Logic ---------------------------

def scrape_nodes(node_type: str, expansion: str, log_callback) -> list[dict]:
    """Scrape nodes of a specific type from Wowhead using object pages.

    Returns a list of dictionaries with ``map_name``, ``node_name`` and
    ``coords`` (a tuple of x, y). Any errors encountered are logged via
    ``log_callback``.
    """
    page_url = WOWHEAD_OBJECT_PAGES.get(node_type.lower())
    if not page_url:
        log_callback(f"No Wowhead page for {node_type}\n")
        return []

    log_callback(f"Fetching {page_url}\n")
    try:
        res = requests.get(page_url, timeout=15)
        res.raise_for_status()
    except requests.RequestException as exc:
        log_callback(f"Failed to fetch {page_url}: {exc}\n")
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    script_text = next(
        (s.string or s.get_text() for s in soup.find_all("script") if "new Listview" in (s.string or s.get_text() or "")),
        None,
    )
    if not script_text:
        log_callback(f"No list data on {page_url}\n")
        return []

    match = re.search(r"new Listview\((\{.*?\})\);", script_text, flags=re.S)
    if not match:
        log_callback(f"Failed to parse list data on {page_url}\n")
        return []
    data_str = re.sub(r",\s*\"extraCols\":\[.*?\]\s*", "", match.group(1))
    try:
        objects = json.loads(data_str).get("data", [])
    except json.JSONDecodeError as exc:
        log_callback(f"Failed to decode list data on {page_url}: {exc}\n")
        return []

    nodes: list[dict] = []
    for obj in objects:
        obj_id = obj.get("id")
        obj_name = obj.get("displayName") or obj.get("name") or node_type
        if not obj_id:
            continue
        obj_url = f"https://www.wowhead.com/object={obj_id}"
        log_callback(f"  Fetching {obj_url}\n")
        try:
            obj_res = requests.get(obj_url, timeout=15)
            obj_res.raise_for_status()
        except requests.RequestException as exc:
            log_callback(f"    Failed to fetch {obj_url}: {exc}\n")
            continue
        m = re.search(r"g_mapperData\s*=\s*(\{.*?\});", obj_res.text, flags=re.S)
        if not m:
            continue
        try:
            mapper = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for zone_entries in mapper.values():
            for entry in zone_entries:
                map_name = entry.get("uiMapName")
                for x, y in entry.get("coords", []):
                    try:
                        nodes.append({"map_name": map_name, "node_name": obj_name, "coords": (float(x), float(y))})
                    except Exception:
                        continue

    log_callback(f"Parsed {len(nodes)} nodes from {page_url}\n")
    return nodes


# ------------------------- Lua Export Logic -------------------------

def format_coords(x: float, y: float) -> int:
    """Convert floating point coordinates to GatherMate2 packed integer."""
    return int(x * 10000 + 0.5) * 1000000 + int(y * 10000 + 0.5)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def export_lua(node_type: str, nodes: list[dict], map_ids: dict, node_ids: dict, out_dir: str) -> None:
    """Export scraped nodes into a Lua file compatible with GatherMate2."""
    ensure_dir(out_dir)
    lua_lines = [f"GatherMate2{node_type.capitalize()}Data = {{"]
    nodes_by_map: dict[int, dict[int, int]] = {}
    for item in nodes:
        map_id = map_ids.get(item["map_name"])
        node_id = node_ids.get(item["node_name"])
        if map_id is None or node_id is None:
            # Skip nodes with unknown IDs to avoid corrupt Lua files.
            continue
        packed = format_coords(*item["coords"])
        nodes_by_map.setdefault(map_id, {})[packed] = node_id
    for m_id, entries in nodes_by_map.items():
        lua_lines.append(f"  [{m_id}] = {{")
        for packed, n_id in entries.items():
            lua_lines.append(f"    [{packed}] = {n_id},")
        lua_lines.append("  },")
    lua_lines.append("}")

    lua_path = os.path.join(out_dir, f"{node_type.capitalize()}Data.lua")
    with open(lua_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lua_lines))


# ------------------------- GUI Application -------------------------

class ValhallaNodesApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("ValhallaNodes")

        # Branding Header
        header = tk.Label(master, text="ValhallaNodes", font=("Helvetica", 18, "bold"))
        header.pack(pady=5)
        tagline = tk.Label(master, text="Where Node Data Rises Again")
        tagline.pack(pady=2)

        # Frame for options
        frame = tk.Frame(master)
        frame.pack(pady=5, fill="x")

        self.node_vars = {
            "Herbalism": tk.BooleanVar(value=True),
            "Mining": tk.BooleanVar(value=True),
            "Fishing": tk.BooleanVar(value=False),
            "Gas": tk.BooleanVar(value=False),
            "Treasure": tk.BooleanVar(value=False),
            "Archaeology": tk.BooleanVar(value=False),
        }

        col = 0
        for name, var in self.node_vars.items():
            chk = tk.Checkbutton(frame, text=name, variable=var)
            chk.grid(row=0, column=col, sticky="w")
            col += 1

        # Expansion dropdown
        tk.Label(frame, text="Expansion:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.expansion_var = tk.StringVar(value="Dragonflight")
        self.expansion_box = ttk.Combobox(frame, textvariable=self.expansion_var, state="readonly")
        self.expansion_box["values"] = ["Dragonflight", "The War Within"]
        self.expansion_box.grid(row=1, column=1, sticky="w", pady=(5, 0))

        # Output directory selector
        self.out_dir_var = tk.StringVar(value=os.getcwd())
        tk.Label(frame, text="Output Directory:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        out_entry = tk.Entry(frame, textvariable=self.out_dir_var, width=40)
        out_entry.grid(row=2, column=1, columnspan=3, sticky="we", pady=(5, 0))
        tk.Button(frame, text="Browse", command=self.choose_dir).grid(row=2, column=4, sticky="w", pady=(5, 0))

        # Run button
        tk.Button(master, text="Run", command=self.run).pack(pady=5)

        # Log window
        self.log = scrolledtext.ScrolledText(master, width=80, height=20, state="disabled")
        self.log.pack(padx=5, pady=5, fill="both", expand=True)

        # Load mappings
        self.map_ids = load_json("map_ids.json")
        self.node_ids = load_json("node_ids.json")

    def log_write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.yview("end")
        self.log.configure(state="disabled")

    def choose_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.out_dir_var.get())
        if path:
            self.out_dir_var.set(path)

    def run(self) -> None:
        expansion = self.expansion_var.get()
        out_dir = self.out_dir_var.get()
        for node_type, var in self.node_vars.items():
            if not var.get():
                continue
            nodes = scrape_nodes(node_type, expansion, self.log_write)
            if not nodes:
                continue
            export_lua(node_type, nodes, self.map_ids, self.node_ids, out_dir)
        messagebox.showinfo("ValhallaNodes", "Export complete")


def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    app = ValhallaNodesApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
