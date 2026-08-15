#!/usr/bin/env python3
"""ValhallaNodes - GatherMate2 Data Fixer & Node Importer.

Where node data rises again. Scrapes node information from WoWHead and
exports it in GatherMate2 Lua format. Includes a Tkinter GUI to make the
process user friendly, and a --headless CLI mode for scripting/CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# URLs for gathering object lists on Wowhead
WOWHEAD_OBJECT_PAGES = {
    "herbalism": "https://www.wowhead.com/objects/herbs",
    "mining": "https://www.wowhead.com/objects/mining",
    "fishing": "https://www.wowhead.com/objects/fishing",
    "treasure": "https://www.wowhead.com/objects/treasure",
    "gas": "https://www.wowhead.com/objects/gas-clouds",
}


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


def build_session() -> requests.Session:
    """Build a requests session that looks like a real browser and retries
    transient failures. Wowhead now sits behind bot-protection (Cloudflare/
    AWS WAF) that rejects bare ``requests`` calls with a 403; this reduces
    (but cannot guarantee against) being blocked.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.wowhead.com/",
        }
    )
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ------------------------- Scraping Logic ---------------------------

def normalize_coord(x: float, y: float) -> tuple[float, float]:
    """Convert Wowhead's percentage-based coordinates (0-100) into the
    0-1 fraction range GatherMate2's ``EncodeLoc`` expects. Coordinates
    stored as fractions (matching Blizzard's own map API) are what
    GatherMate2 packs; Wowhead's page data is percentage-scaled.
    """
    return x / 100.0, y / 100.0


def _fetch(session: requests.Session, url: str, log_callback) -> requests.Response | None:
    """GET a URL, logging a clear message on bot-block (403) or network failure."""
    try:
        res = session.get(url, timeout=15)
    except requests.RequestException as exc:
        log_callback(f"Failed to fetch {url}: {exc}\n")
        return None
    if res.status_code == 403:
        log_callback(
            f"Wowhead blocked this request (403 Forbidden) fetching {url}. "
            "This is Wowhead's bot protection rejecting the request - try again "
            "later or from a different network.\n"
        )
        return None
    try:
        res.raise_for_status()
    except requests.RequestException as exc:
        log_callback(f"Failed to fetch {url}: {exc}\n")
        return None
    return res


def scrape_nodes(node_type: str, expansion: str, log_callback, session: requests.Session | None = None) -> list[dict]:
    """Scrape nodes of a specific type from Wowhead using object pages.

    Returns a list of dictionaries with ``map_name``, ``node_name`` and
    ``coords`` (a tuple of x, y fractions in the 0-1 range). Any errors
    encountered are logged via ``log_callback``.
    """
    page_url = WOWHEAD_OBJECT_PAGES.get(node_type.lower())
    if not page_url:
        log_callback(f"No Wowhead page for {node_type}\n")
        return []

    session = session or build_session()

    log_callback(f"Fetching {page_url}\n")
    res = _fetch(session, page_url, log_callback)
    if res is None:
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
        obj_res = _fetch(session, obj_url, log_callback)
        if obj_res is None:
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
                        cx, cy = normalize_coord(float(x), float(y))
                        nodes.append({"map_name": map_name, "node_name": obj_name, "coords": (cx, cy)})
                    except Exception:
                        continue

    log_callback(f"Parsed {len(nodes)} nodes from {page_url}\n")
    return nodes


# ------------------------- Lua Export Logic -------------------------

def format_coords(x: float, y: float) -> int:
    """Pack 0-1 fraction coordinates into GatherMate2's storage integer.

    Mirrors GatherMate2's real ``GatherMate:EncodeLoc(x, y)``:
        floor(x * 10000 + 0.5) * 1000000 + floor(y * 10000 + 0.5) * 100
    The previous version of this function omitted the ``* 100`` on the y
    term, so GatherMate2's ``DecodeLoc`` (which divides that field by 100)
    read back a y coordinate 100x too small - every node rendered pinned
    near the top edge of its zone.
    """
    return int(x * 10000 + 0.5) * 1000000 + int(y * 10000 + 0.5) * 100


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def export_lua(
    node_type: str,
    nodes: list[dict],
    map_ids: dict,
    node_ids: dict,
    out_dir: str,
    log_callback=None,
) -> int:
    """Export scraped nodes into a Lua file compatible with GatherMate2.

    Returns the number of nodes skipped due to unknown map/node names.
    """
    ensure_dir(out_dir)
    lua_lines = [f"GatherMate2{node_type.capitalize()}Data = {{"]
    nodes_by_map: dict[int, dict[int, int]] = {}
    skipped = 0
    for item in nodes:
        map_id = map_ids.get(item["map_name"])
        node_id = node_ids.get(item["node_name"])
        if map_id is None or node_id is None:
            # Skip nodes with unknown IDs to avoid corrupt Lua files.
            skipped += 1
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

    if skipped and log_callback:
        log_callback(
            f"Skipped {skipped} {node_type} node(s) with an unknown map or node name "
            "- add them to map_ids.json / node_ids.json to include them.\n"
        )
    return skipped


def run_export(
    node_types: list[str],
    expansion: str,
    out_dir: str,
    expansion_map: dict,
    map_ids: dict,
    node_ids: dict,
    log_callback,
    session: requests.Session | None = None,
) -> None:
    """Scrape and export each requested node type. Shared by the GUI and the
    headless CLI so they can't drift out of sync."""
    allowed_ids = set(expansion_map.get(expansion, []))
    session = session or build_session()
    for node_type in node_types:
        nodes = scrape_nodes(node_type, expansion, log_callback, session=session)
        if not nodes:
            continue
        if allowed_ids:
            nodes = [item for item in nodes if map_ids.get(item["map_name"]) in allowed_ids]
        export_lua(node_type, nodes, map_ids, node_ids, out_dir, log_callback=log_callback)


# ------------------------- GUI Application -------------------------

class ValhallaNodesApp:
    def __init__(self, master) -> None:
        import tkinter as tk
        from tkinter import ttk, scrolledtext

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
        # Expansion mapping loaded from JSON so users can extend it
        self.expansion_map = load_json("expansions.json")
        expansions = list(self.expansion_map) if self.expansion_map else ["Dragonflight", "The War Within"]
        self.expansion_var = tk.StringVar(value=expansions[0])
        self.expansion_box = ttk.Combobox(frame, textvariable=self.expansion_var, state="readonly")
        self.expansion_box["values"] = expansions
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
        from tkinter import filedialog

        path = filedialog.askdirectory(initialdir=self.out_dir_var.get())
        if path:
            self.out_dir_var.set(path)

    def run(self) -> None:
        from tkinter import messagebox

        expansion = self.expansion_var.get()
        node_types = [name.lower() for name, var in self.node_vars.items() if var.get()]
        out_dir = self.out_dir_var.get()
        run_export(node_types, expansion, out_dir, self.expansion_map, self.map_ids, self.node_ids, self.log_write)
        messagebox.showinfo("ValhallaNodes", "Export complete")


# ------------------------- CLI Application ---------------------------

def run_cli(argv: list[str]) -> int:
    """Headless entry point - no Tkinter/display required. Useful for
    scripting and CI."""
    parser = argparse.ArgumentParser(description="ValhallaNodes headless exporter")
    parser.add_argument(
        "--node-types",
        default="herbalism,mining",
        help="Comma-separated node types: herbalism, mining, fishing, gas, treasure, archaeology",
    )
    parser.add_argument("--expansion", default=None, help="Expansion name from expansions.json to filter zones")
    parser.add_argument("--out-dir", default=os.getcwd(), help="Output directory for generated Lua files")
    parser.add_argument("--map-ids", default="map_ids.json")
    parser.add_argument("--node-ids", default="node_ids.json")
    parser.add_argument("--expansions", default="expansions.json")
    args = parser.parse_args(argv)

    expansion_map = load_json(args.expansions)
    map_ids = load_json(args.map_ids)
    node_ids = load_json(args.node_ids)
    expansion = args.expansion or next(iter(expansion_map), "")
    node_types = [n.strip() for n in args.node_types.split(",") if n.strip()]

    def log_callback(text: str) -> None:
        print(text, end="")

    run_export(node_types, expansion, args.out_dir, expansion_map, map_ids, node_ids, log_callback)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--headless" in argv:
        argv = [a for a in argv if a != "--headless"]
        return run_cli(argv)

    import tkinter as tk

    root = tk.Tk()
    ValhallaNodesApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
