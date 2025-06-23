# ValhallaNodes

**Where Node Data Rises Again**

ValhallaNodes brings World of Warcraft gathering nodes back from the afterlife. It scrapes data from WoWHead and exports it into Lua tables compatible with the GatherMate2 addon. Only the worthiest nodes ascend!

## Features
- Scrape Herbalism, Mining, Fishing, Gas Cloud, Treasure and Archaeology nodes from WoWHead
- Visits every node's object page and uses its **Maps** tab to collect coordinates
- Supports different expansions (selectable in the GUI)
- Converts map and node names to GatherMate2 IDs using editable JSON lookup files
- Exports Lua files for each node type
- User friendly Tkinter interface with Viking-flavored splash screen

## Usage
Run the `valhalla_nodes.py` script. Select the node types and expansion you want, choose an output directory, and click **Run**. Lua files will be created in the selected directory. Copy them into your `World of Warcraft/_retail_/Interface/AddOns/GatherMate2_Data/` folder.

## Extending Map and Node IDs
Map and node IDs are loaded from `map_ids.json` and `node_ids.json`. Edit these files to add new maps or nodes. Each file uses simple key/value pairs to map names to IDs.

Expansions are mapped to lists of zone IDs using `expansions.json`. The GUI drop-down is populated from this file so you can easily add support for future content.

```json
{
  "Elwynn Forest": 37,
  "Durotar": 1411
}
```

```json
{
  "Peacebloom": 201,
  "Copper Vein": 181
}
```
## Running Tests
Run all tests with `python -m pytest`.


## Prerequisites and Limitations
ValhallaNodes requires an active internet connection. The script visits each
Wowhead object page and reads the **Maps** tab to retrieve coordinates.
Scraping many pages can be slow and excessive requests may be throttled by
Wowhead.

## Disclaimer
This project is not affiliated with Blizzard Entertainment. Use responsibly!

## License
This project is released under the [MIT License](LICENSE).

