#!/usr/bin/env python3
from __future__ import annotations

# ------------------------- Auto-install dependencies -------------------------
import subprocess
import sys

required_modules = ["requests", "bs4", "tkinter"]

for module in required_modules:
    try:
        __import__(module)
    except ImportError:
        print(f"Module '{module}' not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", module])

# ------------------------- Imports -------------------------
import os
import json
import re
import time
import hashlib
import pickle
from pathlib import Path
import threading

import requests
from bs4 import BeautifulSoup

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ------------------------- Configuration -------------------------
WOWHEAD_OBJECT_PAGES = {
    "herbalism": "https://www.wowhead.com/objects/herbs",
    "mining": "https://www.wowhead.com/objects/mining",
    "fishing": "https://www.wowhead.com/objects/fishing",
    "treasure": "https://www.wowhead.com/objects/treasure",
    "gas": "https://www.wowhead.com/objects/gas-clouds",
}

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

# ------------------------- Utility Functions -------------------------
def load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

# ------------------------- Fetch & Cache -------------------------
def fetch_with_retries(url: str, log_callback, retries: int = 3, delay: float = 1.0, session: requests.Session | None = None) -> str | None:
    sess = session or requests.Session()
    for attempt in range(1, retries + 1):
        try:
            res = sess.get(url, timeout=15)
            res.raise_for_status()
            return res.text
        except requests.RequestException as e:
            log_callback(f"Attempt {attempt} failed for {url}: {e}\n")
            time.sleep(delay)
    log_callback(f"Failed to fetch {url} after {retries} attempts.\n")
    return None

def cache_get(url: str) -> str | None:
    key = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / f"{key}.pkl"
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return None

def cache_set(url: str, content: str) -> None:
    key = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / f"{key}.pkl"
    with open(path, "wb") as f:
        pickle.dump(content, f)

# ------------------------- Scraping Logic -------------------------
def scrape_nodes(node_type: str, expansion: str, log_callback) -> list[dict]:
    page_url = WOWHEAD_OBJECT_PAGES.get(node_type.lower())
    if not page_url:
        log_callback(f"No Wowhead page for {node_type}\n")
        return []

    log_callback(f"Fetching {page_url}\n")
    html = cache_get(page_url) or fetch_with_retries(page_url, log_callback)
    if not html:
        return []
    cache_set(page_url, html)

    soup = BeautifulSoup(html, "html.parser")
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
    sess = requests.Session()
    for obj in objects:
        obj_id = obj.get("id")
        obj_name = obj.get("displayName") or obj.get("name") or node_type
        if not obj_id:
            log_callback(f"Skipping object without ID: {obj_name}\n")
            continue

        obj_url = f"https://www.wowhead.com/object={obj_id}"
        log_callback(f"  Fetching {obj_url}\n")
        obj_html = cache_get(obj_url) or fetch_with_retries(obj_url, log_callback)
        if not obj_html:
            continue
        cache_set(obj_url, obj_html)

        m = re.search(r"g_mapperData\s*=\s*(\{.*?\});", obj_html, flags=re.S)
        if not m:
            log_callback(f"    No mapper data found for {obj_name}\n")
            continue
        try:
            mapper = json.loads(m.group(1))
        except json.JSONDecodeError:
            log_callback(f"    Failed to parse mapper data for {obj_name}\n")
            continue

        for zone_entries in mapper.values():
            if not isinstance(zone_entries, list):
                continue
            for entry in zone_entries:
                if not isinstance(entry, dict):
                    log_callback(f"    Skipping invalid entry: {entry}\n")
                    continue
                map_name = entry.get("uiMapName")
                coords_list = entry.get("coords", [])
                if not coords_list:
                    log_callback(f"    No coordinates for {obj_name} in {map_name}\n")
                    continue
                for x, y in coords_list:
                    try:
                        nodes.append({
                            "map_name": map_name,
                            "node_name": obj_name,
                            "coords": (float(x), float(y))
                        })
                    except Exception:
                        log_callback(f"      Invalid coordinate ({x},{y}) for {obj_name}\n")
                        continue

    log_callback(f"Parsed {len(nodes)} nodes from {page_url}\n")
    return nodes

# ------------------------- Lua Export -------------------------
def format_coords(x: float, y: float) -> int:
    return int(x * 10000 + 0.5) * 1000000 + int(y * 10000 + 0.5)

def export_lua(node_type: str, nodes: list[dict], map_ids: dict, node_ids: dict, out_dir: str) -> None:
    ensure_dir(out_dir)
    lua_lines = [f"GatherMate2{node_type.capitalize()}Data = {{"]
    nodes_by_map: dict[int, dict[int, int]] = {}
    for item in nodes:
        map_id = map_ids.get(item["map_name"])
        node_id = node_ids.get(item["node_name"])
        if map_id is None or node_id is None:
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

# ------------------------- GUI -------------------------
class ValhallaNodesApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("ValhallaNodes")

        # Header
        header = tk.Label(master, text="ValhallaNodes", font=("Helvetica", 18, "bold"))
        header.pack(pady=5)
        tagline = tk.Label(master, text="Where Node Data Rises Again")
        tagline.pack(pady=2)

        # Frame
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
        for col, (name, var) in enumerate(self.node_vars.items()):
            chk = tk.Checkbutton(frame, text=name, variable=var)
            chk.grid(row=0, column=col, sticky="w")

        # Expansion
        tk.Label(frame, text="Expansion:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.expansion_map = load_json("expansions.json")
        expansions = list(self.expansion_map) if self.expansion_map else ["Dragonflight", "The War Within"]
        self.expansion_var = tk.StringVar(value=expansions[0])
        self.expansion_box = ttk.Combobox(frame, textvariable=self.expansion_var, state="readonly")
        self.expansion_box["values"] = expansions
        self.expansion_box.grid(row=1, column=1, sticky="w", pady=(5, 0))

        # Output directory
        self.out_dir_var = tk.StringVar(value=os.getcwd())
        tk.Label(frame, text="Output Directory:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        out_entry = tk.Entry(frame, textvariable=self.out_dir_var, width=40)
        out_entry.grid(row=2, column=1, columnspan=3, sticky="we", pady=(5, 0))
        tk.Button(frame, text="Browse", command=self.choose_dir).grid(row=2, column=4, sticky="w", pady=(5, 0))

        # Run button
        self.run_button = tk.Button(master, text="Run", command=self.run)
        self.run_button.pack(pady=5)

        # Progress bar
        self.progress_var = tk.IntVar(value=0)
        self.progress = ttk.Progressbar(master, orient="horizontal", length=400,
                                        mode="determinate", variable=self.progress_var)
        self.progress.pack(pady=(0, 5))

        # Log
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
        self.run_button.config(state="disabled")
        threading.Thread(target=self._run_scraping, daemon=True).start()

    def _run_scraping(self) -> None:
        expansion = self.expansion_var.get()
        allowed_ids = set(self.expansion_map.get(expansion, []))
        out_dir = self.out_dir_var.get()

        total_types = sum(1 for v in self.node_vars.values() if v.get())
        current_type = 0

        for node_type, var in self.node_vars.items():
            if not var.get():
                continue
            current_type += 1
            self.log_write(f"Starting scrape: {node_type}\n")
            self.progress_var.set(int((current_type - 1) / total_types * 100))

            nodes = scrape_nodes(node_type, expansion, self.log_write)
            if not nodes:
                continue

            if allowed_ids:
                nodes = [item for item in nodes if self.map_ids.get(item["map_name"]) in allowed_ids]

            export_lua(node_type, nodes, self.map_ids, self.node_ids, out_dir)
            self.log_write(f"Finished export: {node_type}\n")
            self.progress_var.set(int(current_type / total_types * 100))

        self.progress_var.set(100)
        self.log_write("All exports complete!\n")
        self.run_button.config(state="normal")
        messagebox.showinfo("ValhallaNodes", "Export complete")

# ------------------------- Main -------------------------
def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    app = ValhallaNodesApp(root)
    root.mainloop()
    return 0

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
