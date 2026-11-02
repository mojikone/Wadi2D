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

**State (2026-11-01): version 1 built, not released. Engine and QGIS plugin work end to end on the RTX 5080 and on the CPU; 862 tests pass on branch `feature/terrain-tools`. Fit to try
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
| Terrain tools through the real dock: embankment, channel, channel with dykes, Preview, volumes | 54 of 54 on Block 2 ground. Normal depth and overtopping within 5 % for a crest up to half a cell wide; wider crests -13 % to +8 % | `W8 terrain tools/README.md` |
| Crests against HEC-RAS; UK EA benchmarks; an observed flood | **not done** | |

## Quick start

```
python -m venv .venv
.venv\Scripts\pip install -e .[gpu]
.venv\Scripts\wadi2d doctor
.venv\Scripts\python tools\install_plugin.py
```

Enable Wadi2D in QGIS and follow the dock from top to bottom; `plugin/wadi2d_qgis/README.md` is the walk-through. From the command line:

```
wadi2d hms-import <hms folder> --basin B --met M --control C --out job.json
wadi2d run job.json --dry-run --out run1
wadi2d run job.json --out run1
wadi2d arf job.json --out study1
```

To start a reservoir full, add to job.json `"initial_levels": [{"coordinates": [[x, y], ...], "level": 100.0}]`, on the datum of the DEM.

## Iterations

| Folder | Date | What it holds | Status |
|---|---|---|---|
| `W1 research and design note` | 2026-10-29 | Toolchain gate, Block 2 inventory, research, benchmarks, prototypes, design note | live |
| `W8 terrain tools` | 2026-11-01 | Embankments, channels, channels with dykes in engine and plugin; the crest sweep; dock check | live, branch `feature/terrain-tools`, not merged |

## Test case

Block 2 of the Batinah flood protection project (`D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2`): the HEC-HMS 4.12 model, the
0.5 m terrain and the W1 inflow peaks at the five dam sites. His files are read-only; copies for tests live under this folder.
