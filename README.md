# Wadi2D

A CUDA 2D shallow-water solver with the hydrology inside the same model, for wadi flood work: steep hill catchments, alluvial fans,
braided wadis, several outfalls. Full shallow-water equations, sub-grid terrain in cells and faces (a breakline on high ground is a
wall until overtopped), a mesh generator, catchment delineation, HEC-HMS-style lumped hydrology for the hills with rain-on-grid for
the plain, ARF the HMS depth-area way, gridded rainfall input, terrain modification for dams and channels, a Windows UI with a live
view of the run. Design flows at design points and full-catchment flood maps, in minutes on one GPU.

That is the full scope. **Version 1** (decided 2026-10-29) ships the solver on a uniform grid with sub-grid tables and crest-aware faces,
the HMS-file hydrology, rain-on-grid, the ARF multi-run, the dam objects and a QGIS plugin as the UI; the mesh generator, the standalone
UI, in-app delineation, most gridded-rainfall formats, local time stepping and multi-PC runs follow in version 2. The keep/defer list with
its reasons is in `CLAUDE.md`.

**State (2026-11-01): version 1 built, not released. Engine and QGIS plugin work end to end on the RTX 5080 and on the CPU; 0 tests pass. Fit to try
and to compare; not yet fit to sign a design with: rain-on-grid peaks disagree with HEC-HMS by 1.4 to 2.1 x on Block 2. HEC-RAS agrees with Wadi2D on one
catchment, so the gap is method and not a solver defect, but no gauge says which method is right. Design flows stay on the lumped-hills mode.** The profile, the decisions with their reasons and
the open questions are in `CLAUDE.md`.

| Check | Result | Where |
|---|---|---|
| Analytic: still water, dam break, jump, supercritical channel, rain on planes, crest | pass, within 1 to 3 % | `tests/solver`, design note section 3 |
| Same code as HMS: 26,889 peaks on four projects | within 0.12 % | `validation/hms_replication.md`, `hms_heldout.md` |
| HEC-RAS 6.6, one 3 x 3 km fan, inflow only | +2.6 cm on max level, F 0.94, 39 x faster | `validation/ras_head_to_head.md` |
| Block 2 lumped hills with 2D plain, five dams, against HMS | within 3 % | `validation/block2_full.md` |
| Dam routing against Modified Puls | peak outflow within 1.6 % | same |
| Rain-on-grid against HEC-RAS 6.6, Bidah 21 km2, same excess, 10 m | 622.0 / 621.9 m3/s, read as within about 4 %; 145 x faster | `validation/ras_rain_on_grid.md` |
| Rain-on-grid against HMS, whole catchment | **open**: 1.4 to 2.1 x; RAS alone gives 1.72 x at Bidah; no gauge says which is right | `validation/block2_full.md`, decision 20 |
| Full project boundary, 15,398 km2, 17.1 M cells at 30 m, 36 h | 68 min on the RTX 5080, mass error 4e-8; extent against his 200-yr layer F 0.40, cause unknown | `W2 full extent run/README.md` |
| QGIS plugin through the real dock: hybrid HMS into 2D, structures, stop, reload, mistakes | 32 of 32, one bug found and fixed on the branch | `W7 plugin test/README.md` |
| Pixel depth and hazard after every run, smooth maps, A3 sheets from the dock | see the folder; a 10 % channel on the solver's own water reads to 1 mm, no false bank pixel | `W9 pixel outputs/README.md` |
| Terrain tools through the real dock: embankment, channel, channel with dykes, Preview, volumes | 54 of 54 on Block 2 ground. Normal depth and overtopping within 5 % for a crest up to half a cell wide; wider crests -13 % to +8 % | `W8 terrain tools/README.md` |
| Crests against HEC-RAS; UK EA benchmarks; an observed flood | **not done** | |

## Quick start

To use it: download `Wadi2D-<version>-windows.zip` from the releases, unzip it, double-click `install_wadi2d.bat`, then tick Wadi2D in QGIS's plugin manager. Its `README.txt` has the first run. Windows only so far; tested on one PC (`W16 release package`).

To work on it, from a clone:

```
python -m venv .venv
.venv\Scripts\pip install -e .[gpu,mesh]
.venv\Scripts\wadi2d doctor
.venv\Scripts\python tools\install_plugin.py
```

Enable Wadi2D in QGIS and follow the dock from top to bottom; `plugin/wadi2d_qgis/README.md` is the walk-through. From the command line:

```
wadi2d hms-import <hms folder> --basin B --met M --control C --out job.json
wadi2d run job.json --dry-run --out run1
wadi2d run job.json --out run1
wadi2d arf job.json --out study1
wadi2d products run1
wadi2d frames run1
```

A run makes its pixel maps by itself; `wadi2d products` makes them again on any run folder that saved maps.

To start a reservoir full, add to job.json `"initial_levels": [{"coordinates": [[x, y], ...], "level": 100.0}]`, on the datum of the DEM.

## Work order

His decisions of 2026-11-02, in order: D2 see the mesh, D8 boundaries table, D1 time slider, D5 Storm section, D9 result lines, D7 profile editor, D3 mesh controls, D4 automatic breaklines, D6 HMS-style model inside. Detail in `CLAUDE.md`, section Work order. A feature is done only when it is in the plugin and tested through the real dock.

## Iterations

| Folder | Date | What it holds | Status |
|---|---|---|---|
| `W1 research and design note` | 2026-10-29 | Toolchain gate, Block 2 inventory, research, benchmarks, prototypes, design note | live |
| `W9 pixel outputs` | 2026-11-01 | Pixel depth and hazard in the engine, sloped surface, smooth maps, Make map | live; replaces the map scripts of `W2` and `W7` |
| `W8 terrain tools` | 2026-11-01 | Embankments, channels, channels with dykes in engine and plugin; the crest sweep; dock check | live, merged |
| `W10 mesher` | 2026-11-01 | Quadtree, local time stepping, the mesher, the Mesh section of the dock | live, merged, off by default. Local stepping gains nothing on a uniform grid; a mesh saves time above about 1 M cells, memory below |
| `W11 validation round two` | 2026-11-01 | Crest lines against RAS, a second catchment, the envelope, the extent F, the Fizh gauge, Shaheen at Lihban | done; second catchment 1.001 of RAS at 10 m, read as about 5 %. No independent check of crest discharge; the 100-yr run is 3.4 x the Fizh gauge's Q100 |
| `W12 full extent rerun` | 2026-11-01 | W2's job on the merged engine | live; quote this, not `W2`, for current numbers. Passes its rule; the peak rise is the dry-face fix |
| `W13 time step test` | 2026-11-01 | Does a design peak depend on the step | done: 0.23 % at a quarter of the step |
| `W14 cell edge steps` | 2026-11-01 | Why depth maps drew as cell-sized blocks, the edge blend | live, merged |
| `W15 final plugin test` | 2026-11-02 | The five dock checks on merged `main`, small areas | done: 207 of 207 |
| `W20 storm section` | 2026-11-02 | D5: a Storm section, hyetograph, design storm, gridded rain from NetCDF, DSS and GeoTIFF folders | done on QGIS 3.44.8, 41 of 41 through the real dock; raw peaks of `S5_ring` and `S11_ring` are noise, see it |
| `W19 time slider` | 2026-11-02 | D1: the saved frames as a mesh layer on the Temporal Controller | done on QGIS 3.44.8, 31 of 31 through the dock |
| `W18 boundary table` | 2026-11-02 | D8: a table of kinds and values for one line layer | done, 34 of 34 through the dock |
| `W17 cell grid layer` | 2026-11-02 | D2: the real cell grid in Model setup after every run | done, 21 of 21 through the dock |
| `W16 release package` | 2026-11-02 | The Windows package and installer | live; `v0.1.1` published as a pre-release; 0.1.0 passed on a second PC; a PC with no NVIDIA card not yet |

## Test case

Block 2 of the Batinah flood protection project (`D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2`): the HEC-HMS 4.12 model, the
0.5 m terrain and the W1 inflow peaks at the five dam sites. His files are read-only; copies for tests live under this folder.
