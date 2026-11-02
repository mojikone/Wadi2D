# W21 result lines

**Status (2026-11-02): done on QGIS 3.44.8, D9 of his work order.** One **Result lines** button opens a panel with the hydrograph, the depth, and the water surface with the terrain along a line, all moving with the time slider. Two kinds, labelled in the plot. 73 of 73 through the real dock. **The uncomfortable part: flow read from saved frames is a sketch, not a number. Across the flow it read 0.6 to 1.0 of the upfront line, and on a 30 m run it was as low as 0.6. See the limit below, and the one decision it leaves him.**

## [PRESERVE-CHECK]

KEEP, not touched:

- Upfront design points and lines: computed during the run by `Monitor`, written to `series/` and `results.h5`, the numbers of record. Their file format, their CSVs and the job format do not change.
- The saved frames, `results.h5`, `frames.nc`, the Time slider button and its mesh layer, the Temporal Controller set-up. A run writes nothing new; existing runs work as they are.
- Make map, pixel maps, the dock's seven sections and every other button.
- `forcing.py`, `run.py`, `schema.py` and `job_builder.py`: other branches are in them, and this work adds nothing to them.

CHANGE, additions only, nothing removed:

- Engine: a new subcommand `wadi2d lines`, which lists a run's upfront lines and points with their series, and reads any line from the saved frames.
- Dock: one new button **Result lines** in section 7, enabled when the Time slider button is. It opens a panel at the bottom of the QGIS window.
- Panel: choose an upfront line or point, draw a temporary line, or pick one from a layer; it shows the hydrograph, the depth, and the water surface with the terrain along the line, and follows the time slider. Each kind is labelled in the plot, and the plot states the limit of saved frames.
- Temporary lines live in a temporary scratch layer, added to the project when the first one is drawn.

FILES:

- New: `wadi2d/products/result_lines.py`, `plugin/wadi2d_qgis/line_view.py`, `plugin/wadi2d_qgis/line_plot.py`, `plugin/wadi2d_qgis/line_tool.py`, `plugin/wadi2d_qgis/result_lines.py`, tests, this folder.
- Edited, smallest edit: `wadi2d/engine/cli.py` (the subcommand), `plugin/wadi2d_qgis/protocol.py` (arguments), `plugin/wadi2d_qgis/sections/run.py` (the button), `plugin/wadi2d_qgis/dock.py` (the wiring), `plugin/wadi2d_qgis/README.md` (the use).

## How it works

- `wadi2d lines <run> --out f.json` lists a run's saved frames, its upfront lines and points, and their recorded series. `--line request.json` reads any line from the saved frames. Reading is in the engine, so QGIS loads no second HDF5 library, and the plugin only reads the JSON.
- **Upfront** lines and points are the ones set in section 6, computed during the run from the discharge on the faces. Those numbers are untouched and stay the numbers of record. An upfront line also gets a reading from the frames, so both curves stand on one plot and the difference is visible.
- **Temporary** lines are drawn on the map (click along, right-click to end, Escape to drop) or picked from a line layer. Drawn ones go to a QGIS temporary scratch layer on top of the run's group, in the run's CRS.
- The answer holds every frame, so moving the slider repaints and asks the engine nothing. The panel has its own slider, and once Time slider has been pressed it moves with the Temporal Controller, both ways. At each step it follows the rule the mesh layer follows, the last frame at or before the time, so the plot shows the frame the map shows.
- A run writes nothing new and nothing is added to its folder. Runs made before this work read the same way.

**The water surface** is one flat level per cell, as the cell holds it, over the DEM with the run's terrain objects applied. The level is the depth over the cell's lowest point, and that point comes from the run's own maps, `max_level` less the deepest depth, so a line needs no tables. If the DEM has moved, the ground drawn is each cell's lowest point, and the plot says so.

**The flow** is mean depth x speed x length, each sample turned by the angle between the line and the flow. A frame holds a speed and no direction, so the direction comes from the slope of the water around the sample. That is still "from depth and speed": the slope is depth over ground. It has a size and no sign. A cell counts down to 5 mm, far under the 5 cm floor of the maps, because a sheet that is dry on a map still runs: at the map's floor a rain-fed slope read 0.44 of its record, here 0.71.

## The limit, measured

Peak flow read from frames, as a share of the upfront line on the same run. All are `wadi2d lines` on the same line.

| Run | Cells, maps | Lines | Record seen at the frames | Estimate, of the record at the frames |
|---|---|---|---|---|
| Bidah, through the dock | 20 m, 5 min | Across, Axis, Oblique | 1.00 | 0.94, 0.94, 1.01 |
| Bidah, mesh, through the dock | 10 to 40 m, 5 min | Across | about 1.00 | 0.99 |
| Bidah, 19 test lines by script | 20 m, 5 min | 7 across the flow | 1.00 | 0.90 to 0.96 |
| | | 6 oblique, 45 degrees | 1.00 | 1.00 to 1.30, and 7.5 on one that runs along the flow |
| | | 6 bent | 1.00 | 1.00 to 1.23 |
| Bidah, `W13` | 20 m, 5 min | axis, edge | 1.00 | 0.94, 0.94 |
| Bidah, `W4` | 10 m, 5 min | axis, edge | 1.00 | 0.94, 0.89 |
| Full extent, `W2` | 30 m, 5 min | 5 dam lines | 0.98 to 1.00 | 0.60 to 0.96 |
| Full extent, `W12` | 30 m, 15 min | 5 dam lines | 0.88 to 1.00 | 0.62 to 0.96 |
| | | 11 closed rings | 0.89 to 1.00 | 0.46 to 3.9 |

Three things to read from it:

- **The interval costs little at 5 min and up to 12 % at 15 min**, worst on the smallest catchment, Bidah 03 at 21 km2.
- **The estimate is the larger limit, and it is worst on coarse cells.** Faydh 01 at 30 m reads 0.60. [Likely, not tested] a cell's speed is the mean of its opposite faces, so a flow that enters by the west face and leaves by the south reads 0.71 of its speed, and a diagonal wadi at 30 m does that all the way down. A frame cannot undo this.
- **A closed ring is no use.** [Likely] its record is the net through it, and the estimate has no sign, so water going in and coming out add up: up to 3.9 x. A line that crosses a wadi twice counts it twice, and the plot says so.

What was tried and why this one:

| Reading | Across the flow | Oblique | Bent |
|---|---|---|---|
| Depth x speed x length, no direction | 1.5 to 6 | 2.2 to 45 | 2.1 to 6.7 |
| Mean depth x speed x length, no direction | 0.98 to 1.51 | 1.4 to 25 | 1.35 to 3.5 |
| **Mean depth, turned by a 3 x 3 reading of the slope** | **0.90 to 0.96** | **1.00 to 1.30, one 7.5** | **1.00 to 1.23** |

The same 19 lines; the first two rows at the 5 cm floor. A plain "depth and speed", as the work order puts it, reads 1.4 to 25 x on any line not square to the flow, so the direction is added, from the same frames. A mean direction over a wet stretch was tried too: better on one line, 0.37 on a bent one, so it was dropped.

The plot states all this in its footer: the interval, that a peak between frames is not seen, that flow is estimated and is not a number of record, the 0.6 to 1.0, a line along the flow, a wadi crossed twice.

## To decide

Whether a run should save the discharge on the faces with each frame. Then a line drawn afterwards would be read off the same faces an upfront line uses, with no estimate and a sign, limited by the interval alone. It costs more disk, on the order of 5/3 of a frame [Guessing], and only new runs would have it. It changes what a run writes, so it is his call. Not built.

## Results

`dock_result_lines.py` through the real dock on Block 2 ground around Bidah, 73 of 73 (`log_dock_result_lines.txt`), plugin and engine confirmed from this worktree:

- The button after a run, a panel, the upfront lines listed, both kinds labelled, the limit stated, nothing added to the run folder.
- Upfront peaks on the plot equal the run's series files; the three ratios above.
- A line drawn through the real map tool, by mouse events on the canvas: its vertices where they were clicked, on a scratch layer on top of the group, in the run's CRS. Escape, and a single point, draw nothing.
- A line picked from a layer, and the same line from a layer in degrees, reads the same. A map in degrees draws in metres.
- At every step of the Temporal Controller the plot's frame equals the frame the mesh layer picks; the surface changes at 23 steps; the panel's own slider moves the map and the canvas.
- A line off the model says so; Remove takes it off the list and the layer.
- Upfront points: depth and level as recorded, labelled, no section. Temporary lines carry to the next run and read it.
- Too few frames: an upfront line keeps its record and says why. A finished run chosen by its folder reads again. A mesh, 10 to 40 m.
- The panel leaves with the plugin, and takes its files with it.

Speed: a drawn line on the plot in about 1.5 s on Bidah, most of it the engine starting. On the full extent, 17.1 M cells and 144 frames, a 1.1 km line took 1.3 s by the command line, through the real engine and off the disk.

**Looked at:** the plot with an upfront line, a temporary line, an upfront point and a mesh line, at two frames; the plot stacked in a tall window; the panel in the whole QGIS window; the map with the drawn line at two scales. Kept here as `plot_*.png` and `map_temporary_line.png`. The first plot hid the hydrograph's peak under its legend and ran the clock into the titles, which no check would have said; both are fixed.

29 engine tests in `tests/products/test_result_lines.py`, 32 in `tests/plugin/test_line_view.py`.

## Known small things

- The map does not reach the last saved frame: the Time slider sets its step from the first two frames, a second or so short of the mean, so the controller's last step starts before the last frame. The panel's slider reaches it. That is `W19`'s step and was left alone.
- A flow is shown as a size, so an upfront line's record is drawn as a size too. The series files keep the sign.
- A long line takes wider samples: at most 2,000, a quarter of a cell until then.

## Not tested

- QGIS other than 3.44.8, including the laptop's 3.40.14.
- The full extent through the dock: only the command line.
- The line drawn by a hand and the rubber band seen while drawing: the check drives the real tool with mouse events in a minimised window.
- The DEM moved, and terrain objects under a line: by the engine tests only.
- A section on a real shaped object.
- Any flood record: all of this is against the model's own upfront lines.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "<full path>\W21 result lines\dock_result_lines.py" <throwaway folder> -Copy "W21 result lines"
```

From a worktree the harness needs `.venv` beside the repository: a junction to the main checkout's works.
