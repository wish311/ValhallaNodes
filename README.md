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

### Headless / CLI mode
For scripting or CI (no Tkinter/display required):
```
python valhalla_nodes.py --headless --node-types herbalism,mining --expansion "The War Within" --out-dir ./out
```

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

Wowhead now sits behind bot-protection (Cloudflare/AWS WAF) that can return
`403 Forbidden` for automated requests regardless of network. The scraper
sends browser-like headers and retries transient failures, but if you see
"Wowhead blocked this request" in the log, it's this protection kicking in -
try again later or from a different network.

## Known Limitations / Not Yet Verified
- **Coordinate scale**: GatherMate2 stores coordinates as 0-1 fractions.
  Wowhead's page data is percentage-scaled (0-100), so the scraper divides
  by 100 (`normalize_coord`) before packing. This matches known Wowhead/
  GatherMate2 conventions but has not been re-verified against a live
  Wowhead payload (the bot-protection above blocked that check at the time
  this was written) - spot-check one exported node against its in-game
  position before trusting a full export.
- **Midnight (patch 12.0) zones**: not yet added to `expansions.json` /
  `map_ids.json`. Blizzard's Midnight "addon purge" targets combat addons
  (DBM, WeakAuras, damage meters, nameplates) and does not restrict
  gathering/map addons like GatherMate2, so no format changes are needed
  for that reason - only new zone/map IDs, once verified, need adding.

## Disclaimer
This project is not affiliated with Blizzard Entertainment. Use responsibly!

## License
This project is released under the [MIT License](LICENSE).

