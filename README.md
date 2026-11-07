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

**State (2026-11-01): version 1 built, not released. Engine and QGIS plugin work end to end on the RTX 5080 and on the CPU; 1,835 tests pass. Fit to try
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
| `W39 gridded 200-yr rain test` | 2026-11-07 | His 200-yr grid (DSS, NetCDF) and PMP raster through the dock, hybrid and full 2D on Bidah 03 at 30 m | done, 41 of 44; the 3 are the two files differing by 0.265 %; his answers recorded: the grid's 157 mm governs, the PMP raster's values stand, ARF at the drainage area |
| `W40 mesh and breakline research` | 2026-11-07 | The mesh and engine options for breaklines (square tiles plus aligned strips, open-source meshers, GPU speed, sub-grid, GPL fit) against the three measured errors | done as research: fix the faces, keep the tiles; he rejects that conclusion until an aligned mesh is tested on his cases, so a MeshKernel strip race is next |
| `W41 hybrid design lines` | 2026-11-07 | Why a hybrid design line reads almost nothing: lumped water enters below the dam lines (HMS route) or passes in a reach (generated basin) | fixed and merged: lumped water enters on the wadi above every line, a design line on a reach reads the network; 23 of 24 through the dock, Faydh 01's raw peak the one failure |
| `W42 benchmark data` | 2026-11-07 | UK EA 2D benchmark package (Tests 1 to 7) and the Iber weir flume set (194 runs, oblique weirs), downloaded on his permission; raw data out of git | ready for the cap and the mesh race |
| `W37 dock backend and ARF` | 2026-11-07 | The engine choice and the depth-area study in the dock, his option A with interpolation and lumped-only exact reruns | done, 55 of 55 through the dock; -0.39 % against an exact-area run |
| `W36 breakline faces` | 2026-11-07 | A face that follows the ground along a line without the weir law | built, not merged: 3 of 4 bank cases within 3 %, Faydh 01 20 m -11.1 %; free overfall 2.6-3.8 x critical; his decision |
| `W38 surge warning and lumped series` | 2026-11-07 | His choice (a) for the inflow surge: lines over an inflow's cells named; lumped elements' series in the Result lines panel | done, 10 of 10 through the dock; four dam lines sit on local inflow cells, his decision |
| `W35 hand-back resume rerun` | 2026-11-07 | W32's hand-back resume case on the resume fix | done, 19 of 19 series to the last digit |
| `W34 reservoir start level` | 2026-11-07 | Dams start empty; a start per dam (empty, spillway, level) for scenarios; one pool only; dock table and initial water | done, 23 of 23 through the dock; Bidah 3.833 Mm3 at 100 m, +2.5 % on W32's polygon |
| `W33 backend parity` | 2026-11-06 | Why CPU and GPU part on the Block 2 hybrid; the resume re-phase fixed; a driver crash with two CUDA processes | done: sensitivity, not a backend fault, Faydh 01 −2.5 % reproduced and explained; resume byte for byte; the driver fault cleared by a reboot |
| `W32 combinations test` | 2026-11-02 | The combinations nobody ran: CPU twin through the new sections, generated basin with gridded storm, mesh, resume, full extent, hand-back at a dam | done, 4 of 6; CPU and GPU diverge on the Block 2 hybrid, resume re-phases the series clock |
| `W30 face frames` | 2026-11-02 | Face discharges saved with every map; a line after the run of record | done, 42 of 42 through the dock; 1.001 of the upfront lines, 1.58 x disk |
| `W29 conserving routing` | 2026-11-02 | A conserving Muskingum-Cunge (Todini 2007) beside the HMS-faithful one | done, 29 of 29 through the dock; volume 1.000000, peaks within 0.14 % |
| `W31 ring flicker` | 2026-11-02 | Why the S5 and S11 rings flicker: a pond surge at a lumped inflow, not the refresh split; rings on a subbasin's edge pass half the hydrograph | done, no code changed; his call on a momentum source or a warning |
| `W28 final merge test` | 2026-11-02 | Every dock scenario of the work order on the merged `main` | done, 497 of 497 |
| `W27 basin wiring` | 2026-11-02 | D6b: the generated basin in the run and the dock, inflows and hand-backs from the routes, the lag choice, the rain-once check | done on QGIS 3.44.8, Bidah 52 of 52 and Block 2 26 of 26; generated NRCS 1.05 to 1.59 x HMS, HMS-style lag 0.88 to 1.26 |
| `W26 suggested breaklines` | 2026-11-02 | D4: Suggest breaklines, an editable layer of banks and crests, with the bank-line runs on Bidah and Faydh | done, 32 of 32 through the dock; bank lines as crest lines cost the peak 10 to 36 %, so banks go to the Mesh table |
| `W25 hand-back and transmission loss` | 2026-11-02 | D6c: 2D flow handed to a lumped reach during the run, mass closed; D6d: dry-bed transmission loss, off by default | done, engine only; Muskingum-Cunge as HMS does it does not conserve volume; Fizh stays 2.2 x Q100 at 150 mm/h |
| `W23 mesh controls` | 2026-11-02 | D3: refinement lines in the Mesh section, near, rows and far, actual sizes shown before a run | done on QGIS 3.44.8, 67 of 67; a band alone -7.8 %, with the stream rules -4.1 % |
| `W24 basin model` | 2026-11-02 | D6a: subbasins, reaches, junctions and reservoirs from the DEM, `basin.json` and `basin.gpkg` | done, engine only; Block 2 areas within 0.2 %, peaks 1.05 to 1.58 x HMS from the lag method alone: HMS's lags are 0.474 x Kirpich, not NRCS |
| `W22 profile editor` | 2026-11-02 | D7: a graphical editor per structure, drag, type, undo, with the preview under it | done on QGIS 3.44.8, 120 of 120 through the real dock |
| `W21 result lines` | 2026-11-02 | D9: the Result lines panel on the time slider, upfront and temporary lines | done on QGIS 3.44.8, 73 of 73; flow from frames reads 0.6 to 1.0 of upfront lines |
| `W20 storm section` | 2026-11-02 | D5: a Storm section, hyetograph, design storm, gridded rain from NetCDF, DSS and GeoTIFF folders | done on QGIS 3.44.8, 41 of 41 through the real dock; raw peaks of `S5_ring` and `S11_ring` are noise, see it |
| `W19 time slider` | 2026-11-02 | D1: the saved frames as a mesh layer on the Temporal Controller | done on QGIS 3.44.8, 31 of 31 through the dock |
| `W18 boundary table` | 2026-11-02 | D8: a table of kinds and values for one line layer | done, 34 of 34 through the dock |
| `W17 cell grid layer` | 2026-11-02 | D2: the real cell grid in Model setup after every run | done, 21 of 21 through the dock |
| `W16 release package` | 2026-11-02 | The Windows package and installer | live; `v0.1.1` published as a pre-release; 0.1.0 passed on a second PC; a PC with no NVIDIA card not yet |

## Test case

Block 2 of the Batinah flood protection project (`D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2`): the HEC-HMS 4.12 model, the
0.5 m terrain and the W1 inflow peaks at the five dam sites. His files are read-only; copies for tests live under this folder.
