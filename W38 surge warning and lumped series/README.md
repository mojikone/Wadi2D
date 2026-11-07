# W38 surge warning and lumped series

**Status (2026-11-07): done on QGIS 3.44.8, his choice (a) for W31's inflow surge, branch `feature/surge-warning`. A run now names every result line that crosses the cells where a lumped hydrograph enters the grid, before it starts. The Result lines panel offers every lumped element's inflow and outflow of record beside the lines. Through the real dock on the Block 2 hybrid, 10 of 10. Found: at 20, 40 and 80 m, four of the five dam lines (Faydh 01, R2A, R5A, Z4C) also sit on the cells where a local subbasin's hydrograph enters. Whether those dam lines count all of it is untested, and it bears on mode (b) design flows.**

[PRESERVE-CHECK]
- KEEP: every number of every run; the lines, points and frames the panel showed before; the surge itself (no momentum source, no spreading: his choice (a)).
- CHANGE: a `warn` event per line over an inflow's cells (`wadi2d/engine/line_checks.py`, called once from `run.py`); the run listing (`catalogue` in `wadi2d/products/result_lines.py`) carries the lumped network's series; the panel lists them as "Lumped element: <name>" with inflow and outflow (`line_view.py`, `result_lines.py`).
- FILES: those, and tests in `tests/engine/test_line_checks.py`, `tests/engine/test_handback.py`, `tests/products/test_result_lines.py`, `tests/plugin/test_line_view.py`.

## The warning

A line is named when any face under it has one of its two cells among an inflow's cells. The words point the reader to `series/network_<name>.csv` or to moving the line downstream. On the uniform grid only; the mesh is not checked.

## Through the dock (`dock_surge.py`, `log_dock_surge.txt`)

The W20 storm scenario's Block 2 hybrid on the HMS 100-yr storm, at 80 m:

| Check | Result |
|---|---|
| S5 ring and S11 ring named | yes |
| Lumped elements in the panel | 40, after the lines |
| S5 shown from the network | peak 629.5 m3/s, the CSV's own |

Lines named, with the peaks of the hydrographs entering beneath them (80 m run):

| Line | Line peak, m3/s | Entering beneath it, peak m3/s |
|---|---|---|
| S5 ring | 15.9 | S5 629.5 |
| S11 ring | 6.6 | S11 492.7 |
| S1 ring, S2 ring | 11.9, 10.0 | S1 549.2, S2 441.6 |
| S6 ring | 8.8 | S6 326.9 |
| S14 ring | 467.3 | S14 447.9 |
| Bidah 03 ring | 55.6 | S13 302.3 |
| **Faydh 01** (dam line) | 506.6 | S12 426.2 |
| **R2A** (dam line) | 1,118.5 | S9 293.9, S10 66.4 |
| **R5A** (dam line) | 788.7 | S16 268.2, S17 171.6, S18 31.8 |
| **Z4C** (dam line) | 1,674.2 | S4 252.3 |

The same four dam lines are named at 40 m and at 20 m (a 60 s run of the dock's own job, `runs/` not kept).

- [Certain] The rings on a subbasin's edge read a few per cent of what enters beneath them at 80 m; at 40 m W31 found about half. A ring there is no measurement of the subbasin.
- [Certain] The dam lines carry the whole flow from upstream, and the hydrograph of one local subbasin, or of several, enters on cells the line touches.
- **[Guessing] Part of that local hydrograph may enter downstream of the line and never be counted, so a dam line can read low by up to that share.** Not measured: it needs a run with the inflow moved upstream of the line, or the line moved downstream. W1 found mode (b) within 3 % of HMS at the five dams, which argues against a large error, but that was a different setup. **This is for his decision before mode (b) design flows are quoted from these lines:** move the dam lines below the inflow cells, place lumped inflows upstream of design lines in the engine, or measure first.

## Not tested

- The mesh: no warning is computed there.
- A lumped element's series on a run resumed from a checkpoint: the network series are written at the end, as before.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W38 surge warning and lumped series\dock_surge.py" <throwaway folder> -Copy "W38 surge warning and lumped series"
```
