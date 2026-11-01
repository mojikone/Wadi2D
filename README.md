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

**State (2026-11-01): building. Solver core runs on the RTX 5080 and on the CPU and passes its analytic tests; the hydrology, the engine pipeline and the QGIS plugin are in progress. Not yet usable end to end.** The profile, the decisions with their reasons,
the product requirements and the open questions are in `CLAUDE.md`.

## Iterations

| Folder | Date | What it holds | Status |
|---|---|---|---|
| `W1 research and design note` | 2026-10-29 | Toolchain gate, Block 2 inventory, research, benchmarks, prototypes, design note | live |

## Test case

Block 2 of the Batinah flood protection project (`D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2`): the HEC-HMS 4.12 model, the
0.5 m terrain and the W1 inflow peaks at the five dam sites. His files are read-only; copies for tests live under this folder.
