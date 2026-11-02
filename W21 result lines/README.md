# W21 result lines

**Status (2026-11-02): in progress, D9 of his work order.**

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
