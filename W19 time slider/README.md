# W19 time slider

**Status (2026-11-02): done on QGIS 3.44.8, D1 of his work order.** One **Time slider** button exports a run's saved frames as one CF-UGRID NetCDF file and loads it as a mesh layer with depth, speed and hazard, which moves with QGIS's Temporal Controller. Cell frames only, as he decided: no per-frame pixel maps.

## First, the check he asked for: does QGIS read the time axis?

Yes, after one trap. A hand-written NetCDF-4 file read at first as one raster with no time and no datasets, because `h5py` stores Python text as variable-length strings and QGIS's reader then skips the mesh. Stored as fixed-length text, QGIS 3.44.8 reads a real mesh: the three datasets, the time axis with its reference date, the temporal properties switched on, the same pixel changing colour between frames, and a time picking its frame. `tests/products/test_time_slider.py` holds the text rule.

Scale, measured on a synthetic mesh: 4 M cells, 8 frames, 135 MB, written in 2 s, read and drawn in 40 s at 2.7 GB. [Likely] the full extent, 17 M cells, takes about 3 min and 12 GB in QGIS, which waits meanwhile; the dock says so before it starts. Not run at that size.

## How it works

- `wadi2d frames <run>` writes `frames.nc` beside the results. Nothing is written until asked, so a run costs nothing extra; a second click reuses the file while it is newer than the results.
- The mesh is the real cells, active ones only: on a quadtree the tiles from `cell_grid.gpkg` with the mask from `results.h5`, so neither the DEM nor the tables are needed, and the slider still works after the inputs have moved.
- A cell below the depth floor (`outputs.pixels.depth_floor`) is left out of all three datasets, so dry ground draws as nothing.
- The button sets the Temporal Controller to the run's whole time with one step per saved frame, opens its panel, and switches the Flood maps group off: the run's maximum under a flood that is still rising would read as the flood.
- The date on the slider is a stand-in, as a run has no date: 1 January 2000, 00:00, is the start of the run.

## What these frames are not

They are cell values, the depth at a cell's deepest point, and hazard from that depth and the cell's speed. They show how the flood moves. The pixel rasters stay the numbers of record, and a cell's hazard here reads higher than the pixel hazard of a shallow bank inside that cell.

## Results

`dock_time_slider.py` through the real dock on Block 2 ground around Bidah, 31 of 31 (`log_dock_time_slider.txt`):

- One face per cell, all three datasets, every saved frame, in the DEM's CRS, on top of the run's group.
- What QGIS reads equals what the engine saved: wet cells and the deepest cell at three frames, against `results.h5`, read with no QGIS involved.
- The Temporal Controller is set to animate, one step per frame, its panel open, and the canvas moves with it.
- A second click reuses the file. Fewer than two saved maps gets a plain message.
- A mesh, 10 to 40 m: one face per real cell, 103,792.

The frames were drawn at three times and in hazard, and looked at.

**Found by running it.** Setting a mesh layer's value range after a shader with no source ramp crashes QGIS outright, which froze the dock: the order is in the code with its reason. `NoResampling` is the name of the flat-cell setting in this QGIS.

## Not tested

- QGIS other than 3.44.8; the laptop has 3.40.14 and is the obvious next check.
- The full extent in QGIS.
- Stepping the panel by hand: the check drives the same controller the panel drives, and the panel was seen open only as a widget.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W19 time slider\dock_time_slider.py" <throwaway folder> -Copy "W19 time slider"
```
