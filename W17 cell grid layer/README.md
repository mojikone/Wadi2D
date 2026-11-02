# W17 cell grid layer

**Status (2026-11-02): done, D2 of his work order.** After every run the real cell grid is a vector layer under Model setup: the cells the solver stepped, coarse tiles coarse, cells outside the domain left out.

## How it works

The engine writes `cell_grid.gpkg` at the start of every run, before the first step, so a run with pixel maps off, a stopped run and a failed run have it too. If writing it fails, the run warns and carries on.

It is one line feature per tile, not a polygon per cell: 17 M polygons is more than a GIS can draw. A line runs along every edge that touches an active cell of the tile, and straight runs join, so a full tile is 66 lines. Each feature carries `cell_m`, `level` and `cells`. Measured on 16,641 full tiles, 17 M cells, the size of the full extent: 68 MB and 8.2 s at the start of the run. My estimate beforehand was 17 MB.

The dock adds it to Model setup with its sizes and scale in the name, for example `Cell grid, 10 to 40 m, drawn from 1:10,000 in`. It draws only once the finest cell reaches 1 mm on screen; further out the lines merge into a tint. It stays off the map sheets: it is a modeller's check, not a client's map.

## Results

`dock_cell_grid.py` through the real dock on Block 2 ground around Bidah, on `tests/dock/harness.py`, 21 of 21 (`log_dock_cell_grid.txt`):

- A uniform run, 20 m: the cells in the layer equal the cells the engine reported, one feature per tile, in the DEM's CRS, covering the domain.
- Pixel maps off, and a stopped run: the grid is there all the same.
- A mesh, 10 to 40 m: the cells equal the engine's, three sizes.
- Make map still works, and the grid is on no sheet.

**The checks did not catch the one real fault.** All 21 passed with a dark hairline that could not be seen over the DEM; only drawing the layer and looking showed it. It is thin orange now, for dark ground, pale ground and blue water alike. `tests/dock/harness.py` has `render` for that: a minimized QGIS window's canvas shows nothing, so a look has to be drawn off the screen.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W17 cell grid layer\dock_cell_grid.py" <throwaway folder> -Copy "W17 cell grid layer"
```
