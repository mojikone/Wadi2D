# W15 final plugin test

**Status (2026-11-02): done. 207 of 207 checks passed through the real dock in QGIS 3.44.8 on `main` at `06a4d40`, no failures, one run after another on real GPU runs, small areas only.** Each check runs in its own QGIS with a throwaway profile, so his open sessions were not touched. The windows closed themselves.

| Check | Covers | Result | Log |
|---|---|---|---|
| `dock_options.py` | Hybrid run, structures, Stop, occupied folder, reload in mid run, wrong inputs | 32 of 32 | `log_dock_options.txt` |
| `dock_terrain.py` | Embankment, channel, channel with dykes, tables, preview, spillway on a raised part, old kinds | 54 of 54 | `log_dock_terrain.txt` |
| `dock_outputs.py` | Pixel step, layers and colours, Make map, Stop in the pixel step, the edge blend reaches the run | 42 of 42 | `log_dock_outputs.txt` |
| `dock_mesh.py` | Mesh section, preview, refused run, mesh run, Stop, back to uniform | 42 of 42 | `log_dock_mesh.txt` |
| `dock_mesh_maps.py` | Pixel maps on a mesh, Make map from a folder | 37 of 37 | `log_dock_mesh_maps.txt` |

The scripts are the checks of `W7`, `W8`, `W9` and `W10`, pointed at the main checkout by environment variables; `dock_outputs.py` gains one check. The first pass stopped early for two reasons of the harness, not the plugin: the runner's finish test matched "done" in any line, so checks overlapped on the card, and `dock_terrain.py` looked for its table in an old scratch folder. Neither result counts; the table above is the second pass.

## Size check

`W12 full extent rerun/s03_make_map.py`: the Make map code on the full extent, 42,330 x 43,734 pixels and 1.1 GB of polygons. Three A3 sheets, PDF 138 MB, 2 min on hillshade, no error. QGIS holds still for those 2 min with a wait cursor. A harmless `ERROR 6` from GDAL's PNG driver appears on image export only.

## Not covered

- Another PC, and a PC with no GPU: item 6, his to ask for.
- **Not in the dock at all: the ARF study (`wadi2d arf`, command line only) and `initial_levels` (job.json only).** By his rule a feature not in the plugin is not done.
- The setup sheet on a full 2D run lists "Subbasin, lumped" in its legend with none on the map, and its subbasin labels crowd on a domain this large. Cosmetic.

## Rerun

`powershell -File "W15 final plugin test\run_all.ps1" <throwaway folder> <copy of the Block 2 HMS folder>`. `wgs.tif`, a small DEM in a geographic CRS, sits beside the HMS folder for the wrong-input check.
