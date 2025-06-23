# ValhallaNodes

**Where Node Data Rises Again**

ValhallaNodes brings World of Warcraft gathering nodes back from the afterlife. It scrapes data from WoWHead and exports it into Lua tables compatible with the GatherMate2 addon. Only the worthiest nodes ascend!

## Features
- Scrape Herbalism, Mining, Fishing, Gas Cloud, Treasure and Archaeology nodes from WoWHead
- Supports different expansions (selectable in the GUI)
- Converts map and node names to GatherMate2 IDs using editable JSON lookup files
- Exports Lua files for each node type
- User friendly Tkinter interface with Viking-flavored splash screen

## Usage
Run the `valhalla_nodes.py` script. Select the node types and expansion you want, choose an output directory, and click **Run**. Lua files will be created in the selected directory. Copy them into your `World of Warcraft/_retail_/Interface/AddOns/GatherMate2_Data/` folder.

## Extending Map and Node IDs
Map and node IDs are loaded from `map_ids.json` and `node_ids.json`. Edit these files to add new expansions or nodes. Each file uses simple key/value pairs to map names to IDs.

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

## Disclaimer
This project is not affiliated with Blizzard Entertainment. Use responsibly!
