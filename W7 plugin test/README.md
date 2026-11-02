# W7 plugin test

**Status (2026-11-01): done. 32 of 32 checks passed through the real dock in a real QGIS 3.44.8 window, then one bug found by inspection and fixed.** Throwaway profile, so his open sessions were not touched. Tested on branch `fix/dry-face-advection`. `plug_check.py` drives the dock; `log_plugin_run.txt` is its record.

| Scenario | What ran | Result |
|---|---|---|
| Hybrid, HMS into 2D | Block 2 HMS project, `FM_200yr`, 17 subbasins lumped, S13 in 2D, 40 m, 506,615 cells, 48 h from the control file, GPU | Finished in 75 s against 64 s estimated. 103 Mm3 entered 2D from the lumped subbasins. Mass error 1e-8. Hydrographs at five dams, maps loaded, control file's duration said in plain words |
| Structures | Crest line, spillway with C and length, wall, burn line, per-line boundaries, CN raster, Manning raster, live layer | Finished, all in the job |
| Stop | Stop button in mid run | Stopped on request, maps written |
| Occupied folder | Run into a folder holding a run | Goes to the next free name, says so |
| Reload | Plugin unloaded in mid run | New dock picks the run up and finishes it |
| Mistakes | No output folder, no rain, empty HMS folder, geographic DEM, domain with no CRS, wrong engine path | Each refused with one plain sentence; engine recovered |
| Installer | `tools/install_plugin.py` into a fresh profile, QGIS's own loader, unload | Loads, finds the engine, unloads |

## Bug found

`protocol.py` named a folder on this PC as the default engine, so on any other PC the dock said Engine not found. It passed every check here. Fixed in `7cfa51e`: the installer writes `engine.txt` beside the plugin.

## Not in the plugin yet

The ARF multi-run, `initial_levels`, the map interval, pixel hazard, and DEM blending run from the command line or scripts only.

## Not tested

Another PC, a PC with no NVIDIA GPU (the CPU backend through the plugin), HMS projects other than Block 2, a project with subbasins that lack polygons, QGIS versions other than 3.44.8. The HMS project here was a scratch copy.

## Hybrid maps (`maps/`)

The plugin test ran with no losses on the 2D area, because the dock's curve number defaults to none and nothing said so. The plugin now says so (`6b3ecf3`). `maps/` reruns the same job at 20 m with the project CN grid, from the command line: 17 subbasins lumped, S13 and the plain in 2D. 103.3 Mm3 enters from the hills, 39.1 Mm3 is rain on the 2D area after losses, 139.0 Mm3 leaves, mass error 2e-8.

| Dam section | Peak, m3/s | Hour |
|---|---|---|
| Faydh 01 | 849 | 13.3 |
| Bidah 03 | 668 | 12.3 |
| R5A | 1,030 | 14.1 |
| R2A | 1,545 | 13.7 |
| Z4C | 2,040 | 14.9 |

S13 is rain-on-grid, so Bidah 03 carries the fast 2D response. In this hybrid the lumped hydrographs enter at their outlets and the 2D model carries them down the wadis; HMS reaches are not routed. `Wadi2D_hybrid_Block2_maps.pdf` is three A3 sheets from a QGIS print layout. Pixel hazard here comes from 15-minute maps. The engine warned of 20.9 m against the wall at (430,701, 2,727,390).

`Wadi2D_results.qgz` at the repository root opens every final layer, grouped. It holds absolute or relative paths into `W2 full extent run` and `W7 plugin test/maps`; neither raster folder is in git.

