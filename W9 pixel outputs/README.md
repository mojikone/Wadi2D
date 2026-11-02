# W9 pixel outputs

**Status (2026-11-01): live, on branch `feature/pixel-outputs`, not merged, not pushed.** Flood outputs moved from the scripts of `W2` and `W7` into the engine and the QGIS plugin. A run now makes pixel depth, hazard H1 to H6, smooth class polygons and a depth drawing by itself; the dock loads them grouped and styled, and **Make map** writes three A3 sheets. The map scripts of `W2` and `W7` are superseded. Their folders stay as the record.

## What is where

| In a run folder | What it is |
|---|---|
| `pixels/pixel_depth.tif`, `pixel_hazard.tif`, `pixel_speed.tif`, `pixel_dv.tif` | **The numbers of record**, at the DEM pixel |
| `pixels/map_layers.gpkg` | Smooth `hazard_classes` and `domain`; `subbasins`, `inflows`, `boundaries`, `design_lines`, `reaches`, so a sheet needs only the run folder |
| `pixels/depth_drawing.tif` | Depth for drawing: 2.5 m, soft wet edge. Not a number of record |
| `pixels/pixels.json` | Class areas, limits, and the area change from smoothing |
| `pixels/<run>_maps.pdf` | Make map |

Code: `wadi2d/products/` (`surface`, `pixels`, `ground`, `frames`, `hazard`, `smooth`, `setup_layers`, `step`, `runner`), `wadi2d/io/geopackage.py`; `plugin/wadi2d_qgis/` (`result_layers`, `map_sheets`, `map_notes`, `style`). Limits, floor and every number are in `config/schema.py`, `outputs.pixels` and `outputs.smooth`. `wadi2d products <run folder>` remakes the step on any run that saved maps.

## The sloped surface

`LEVEL_JUMP` is gone. Two cells are one body of water when both levels stand above their shared face (the sub-grid face invert, crest lines and walls included), or when the higher level stands above it and the depths are within a factor of 2: one flow stepping down a slope steeper than the cells can follow. Anything else keeps its own level. A corner is the mean over the cells joined there. No frame field was needed.

One thing was added that was not asked for, because a real run needs it: **each cell is filled to its own mean depth under that surface.** A level is a flat fill, so on a slope with thin flow it stands under the true surface. Without the fill a sheet on a hillside either vanishes under the sloped surface or stacks up as a wedge at the low end of each cell, the stipple of the first film. Volume at the pixels now equals volume in the cell.

Pass marks (`s01_freeboard.py`, `freeboard.json`, s09b's channel, 45 m wide on 30 m cells; tested in `tests/products/test_surface.py`). "Fill" is the flat fill of the same water, which is what a cell really holds:

| Slope, freeboard 1.5 x flat error | Flat error | False bank pixels | Surface error, level | Surface error, fill | Mark |
|---|---|---|---|---|---|
| 1 %, 0.19 m | 0.125 m | 0 % | 0.000 m | 0.000 m | 0 %, at most 0.062 m |
| 5 %, 0.94 m | 0.625 m | 0 % | 0.000 m | 0.000 m | 0 %, at most 0.312 m |
| 10 %, 1.88 m | 1.250 m | 0 % | 0.000 m | 0.000 m | 0 %, at most 0.625 m |

The channel in these cases is built by hand, so the surface is recovered almost by construction. **The check that counts is the solver's own water** (`s02_real_channel.py`, `real_channel.json`), a steady channel on real tables: 99 % of channel pixels within 3, 2 and 1 mm of the steady depth at 1, 5 and 10 %, and no bank pixel wet in any.

A bank standing above a neighbouring wet cell stays dry: unit test with a 2 m channel and a film on the bank, and the bank pixels of the channel's own cell stay at zero.

**Bidah unaffected**, output only (`s05_compare_run.py`, `unchanged_run.json`): the hybrid job rerun on this branch gives series files byte for byte identical at every design line, Bidah 03 included, and identical `max_depth`, `max_speed`, `hazard`.

## Hazard

`H1 to H5` limits, floor 0.05 m and the rule are as the brief, in the schema. `maps/hazard.tif`, the engine's cell hazard, stays.

**CPU and GPU give the same answer**: on the whole hybrid run, 2.96 M pixels, 193 maps, not one pixel takes another class; largest depth difference 1e-6 m (`s06_cpu_gpu.py`, `cpu_gpu.json`).

## Map interval

Default stays 900 s; the dock's other choice is 300 s, with a plain note that it takes three times the disk. The estimate says the disk, an upper end at 10 B per cell per map, measured on the full extent; dry ground compresses to a third of that on the hybrid run.

Peak hazard no longer leans on the interval. After the saved maps the step reads the run's own peaks, watched every 4 steps: the depth and speed of each cell, and the cell's peak depth x speed, which lifts that cell's pixels by the ratio it missed, at most 3 x (`peak_lift`).

Full extent, 239 M pixels, every map or every third of the 5-minute run (`s03_frames.py`, `frames_sensitivity.json`), km2:

| | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| 300 s, maps alone, the method of W2 | 1,109 | 802 | 383 | 712 | 1,183 | 437 |
| 900 s, maps alone | 1,119 | 799 | 384 | 707 | 1,165 | 419 |
| 300 s, with the run's peaks | 1,109 | 801 | 384 | 712 | 1,186 | 439 |
| 900 s, with the run's peaks | 1,116 | 799 | 386 | 708 | 1,184 | 436 |

Without the peaks 15-minute maps lose 4 % of H6; with them 0.7 %, and 99.4 % of pixels keep their class between the two intervals.

Against W2's issued maps (flat fill, 5-minute): H1 989 to 1,109, H2 777 to 801, H3 392 to 383, H4 709 to 712, H5 1,170 to 1,186, H6 438 to 439. **H1 grows 12 % because thin sheets now keep their own depth instead of falling under the sloped surface.** That is the fill above, and it is a change of the number, not only of the picture.

Hybrid run against W7's rasters (`unchanged_run.json`), km2:

| | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| W7, s06, 15-minute | 14.4 | 6.5 | 1.0 | 4.0 | 11.6 | 10.1 |
| This branch | 16.6 | 6.8 | 1.0 | 4.0 | 12.3 | 10.3 |

## Smoothing

Classes are drawn from cumulative masks (H3 and above, H4 and above, ...), each softened by the same Gaussian, 1 pixel, and contoured at the value that holds its raw area, so a class keeps its area; a polygon is the difference of two contours, so classes share edges with no gap and no overlap. Patches and holes under 500 m2 go. Depth is drawn at 2.5 m with a fade over the wet edge. Domain and subbasin outlines are smoothed; the polygon that masks rain is not.

| Hybrid, area change from smoothing | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| % | +1.9 to +4.1 | -0.2 to +0.1 | below 0.2 | below 0.1 | below 0.05 | below 0.05 |

Under 1 % for H3 and above, as asked. **H1 is not under 1 %**: 5 m stipple closes up. Wet area added 1.8 km2, removed 2.1 km2, of 51: pixels moved along an edge, not water invented, though at that scale a pixel of H1 can sit where the raster has none.

Regenerated W7 maps: `maps/Wadi2D_hybrid_Block2_maps.pdf`, from the run in the session scratchpad by the code of the button (`s04_maps.py`, satellite background as W7). `maps/crop_hazard_100pct.jpg` and `crop_depth_100pct.jpg` are 300 dpi crops at full A3: no stair on class edges, wet edges, domain or subbasin lines.

## Through the real dock

`plug_check.py` in a separate QGIS 3.44.8, throwaway profile, branch code for plugin and engine, real GPU runs: **41 of 41** (`log_plugin_run.txt`). Hybrid run; bar and status follow the step; groups, colours, ramp; no band line in the panel or on the sheets; Make map, twice, and on a finished run picked by its folder; five-minute maps reach the job; Stop in the pixel step ends in 1 s with the run still finished and no half-written file; the step switched off.

Bugs this found that no test had: the engine lingered after a stop until the dock killed it at 30 s, because a reader thread kept h5py's lock; the layer panel kept its band line, having drawn the legend before the order was set. Running it on the full extent found a third: the GPU memory pool grew until Windows paged the card, 17 s a map, now 1.4 s.

Also learned: QGIS with `QT_QPA_PLATFORM=offscreen` draws every letter as a box, so sheets need the normal platform. Loading rasterio's GDAL and pyogrio's beside CuPy kills the interpreter, so the GeoPackage is written with `sqlite3`; GDAL reads it in a process of its own in the tests.

## Not done or not tested

- **Decided here, for him to check:** the fill to mean depth and `peak_lift` are not in the brief.
- A pixel that peaks later than its cell is scaled by its cell's ratio. An estimate, not a saved moment.
- Another PC, a PC with no GPU through the plugin, QGIS other than 3.44.8.
- A run with crest lines or burn lines through the pixel step on real terrain: the code is shared with the tables, the case was not run.
- A slope across a bend, as in W2: still untested. The checks are straight channels.
- Make map blocks QGIS while it exports, about 7 s here; a larger domain will take longer.
- The satellite background is Google imagery, as W7: check its terms before client use. Hillshade is the dock's default.

Rerun: from the repository root with `PYTHONPATH` on it, `s01` to `s03`, `s05` to `s07` with the project venv; `s04` with `python-qgis-ltr.bat`, without offscreen. Rasters and `runs/` stay out of git.
