# W8 terrain tools

**Status (2026-11-01): merged to `main` and pushed. Embankment, channel and channel with dykes work in the engine and through the real dock on Block 2 ground. One limit stands: overtopping is within 5 % only for a crest up to half a cell wide; wider crests spread from -13 % to +8 %, depending on where the line falls in the cell.**

## What was built

Three kinds, one formula. The new ground is the old ground clamped between a cut surface (bed, then the inner slope carried up) and a fill surface (inner slope, crest, outer slope), so each pixel settles itself. A channel has only the cut, an embankment only the fill, a channel with dykes both. A bank turns from dyke to cut exactly where the ground passes its top, with no step, and each bank does so on its own along the line. That last part is what HEC-RAS cannot do.

| Asked for | Where | How to use it |
|---|---|---|
| Embankment, channel, channel_dyke | `wadi2d/terrain/earthworks.py`, `template.py` | Dock section 3, or `terrain.objects` |
| Section three ways | `sections.py` | Number or field per value; CSV table; start level, slope and freeboard. They mix |
| Openings | `earthworks.py` | Text field: `120-180 left; 600-650`. The raised part ends in a slope either side |
| Lining | `tables/core.py` | Manning n per pixel on the faces, not per cell |
| Transitions and ends | `sections.py`, `earthworks.py` | Linear between stations; open, closed or taper; a raised part always ends in a slope |
| Validation in plain words | `checks.py` | Before every run and in Preview |
| Outputs | `report.py` | `terrain/volumes.csv`, `volumes_by_station.csv`, modified terrain on request |
| Plugin | `sections/shaped_rows.py`, `preview.py`, `profile_view.py`, `shaped.py` | Fields, table picker, Preview terrain, sections dialog, volumes in the final message |

Added beyond the list: a spillway drawn on an embankment takes the fill out of its pixels; checks for a square-cut end, a table shorter than its line, a step between stations, and a line leaving the grid; `wadi2d terrain` as a command; a change raster beside the modified terrain.

## Results

| Test, set before starting | Limit | Result |
|---|---|---|
| Exact pixels of a cut, a fill and a mixed section against hand numbers | exact | pass, also at 30, 45 and 72 degrees |
| Straight trapezoid, 3 cells wide, 0 and 45 degrees, Manning normal depth | 5 % | about -3.5 % at 0 degrees; pass at both |
| Lined channel at its lining's depth, ground n 0.12, lining 0.03 | 5 % | pass |
| Channel between dykes, 0 and 45 degrees (added) | 5 % | pass |
| Dyke holds to 0.3 m under its crest, including a diagonal on 8 m cells | no flow | 0.0 m3/s |
| Dyke overtopped, critical flow, embankment, channel_dyke, diagonal | 5 % | pass at the tested geometry; see the limit below |
| Spillway on a real embankment, its rating (added) | 5 % | pass |
| Still water over every object | exact | 0.0 m/s above every crest; 1.2e-6 m/s partly wet, the same as an old burn line on that ground |
| Cut and fill against the analytic prism, away from the ends | 1 % | pass: straight 1.000, diagonal 1.003; mixed section exact against its hand area |
| Mixed channel on `GGC_2_MERGE_HDSM_5.tif` | runs | left bank changes 14 times, right 6; mass error 7e-10 |
| Real dock in QGIS 3.44.8, throwaway profile, GPU | all | 54 of 54, `log_plugin_run.txt` |

CPU and GPU agree to four decimals on three overtopping cases (`crest_sweep.py gpu`).

## What was found on the way

**The crest limit read the wrong head.** A crest face caps discharge at critical flow for the level in the cell before it. That is right for a thin crest in still water. On a crest as wide as the cells, that cell has already spent its velocity head, and Q fell to 0.78 of critical at 2 m cells: finer cells were worse. Faces of shaped objects now carry a negative coefficient, which reads the energy head, and the limit eases as the crest takes up more of a cell and goes once the cells resolve it. Crest lines, spillways and natural crests keep positive coefficients and run the same path, so no validated dam result moves. This touched both solver kernels, a few lines each.

**Object pixels must be float32.** Still water first showed 7e-5 m/s, and it looked like round-off. It was not: the same ground baked into a DEM gave zero. A DEM holds float32, so pixel differences fit the solver's float32 tables exactly and cancel. Objects wrote float64 pixels, whose differences rounded into a false head at every face. They now round to float32, and the speed is zero.

**A table's path was in the cache key.** The plugin copies a table into each run folder, so identical numbers rebuilt the grid every run. Only the real dock showed it.

**Three bugs no check caught** showed in the screenshots: the section panel flooded red, labels on top of each other, and Preview leaving the map zoomed out. Fixed.

## Limit: overtopping against crest width

`crest_sweep.csv`: Q over critical flow, crest over cell size R, side slopes 2 and 3, four positions of the line in the cell, 136 runs.

| R | Typical | Q / Qcrit | Within 5 % |
|---|---|---|---|
| up to 0.5 | 3 to 5 m crest on 10 to 20 m cells | 0.948 to 1.003 | 54 of 56 |
| 0.5 to 1 | 4 to 6 m crest on 6 to 8 m cells | 0.930 to 1.074 | 21 of 32 |
| 1 to 2 | 4 to 6 m crest on 4 m cells | 0.870 to 1.077 | 10 of 24 |
| 2 and above | crest resolved | 0.914 to 1.080 | 9 of 24 |

With the old limit, an earlier sweep of the same kind ran from 0.75 to 0.98. The spread left is real: at one R the result depends on how much of the crest falls upstream of the face, which also changes with flow direction, so one coefficient cannot remove it. The coefficients are fitted to this sweep at 0.6 m head, on a straight dyke. They are not a physical law. Do not use a design discharge over a wide crest at finer cells than R = 0.5 without a check.

**Other heads, checked at review.** `crest_heads.csv`: the same box at 0.3, 0.6 and 1.2 m, five crest and cell pairs, two snaps, 30 runs on the CPU backend. Crest up to half a cell: 0.941 to 1.011, so about 6 %, one point over the 5 % bar. R 0.75: 0.913 to 1.049. R 1.5: 0.912 to 1.065. R 2: 0.938 to 0.970. The head adds no new failure to the sweep above. The run now warns in plain words when a crest passes `crest_accurate_ratio`, 0.5 of a cell, because a limit that lives only in this file does not reach the person in the dock.

## Not done, not tested

- A `normal` boundary and its width, rechecked at review: the 2.5 x normal depth of the first test does not reproduce. A straight trapezoid at steady flow gives the same depth at half widths 10, 20 and 47 m: 0.96 x normal depth away from the outlet, 0.88 to 0.90 x at 120 m from it. A run of 2,400 s showed +16 %, which was still the filling transient. So the boundary draws the level down near itself and its width does not matter. Keep design points well upstream of an outlet.
- Tailwater submergence of a shaped crest is untested.
- Flow round a bend in a channel. Bends are tested for geometry only.
- Crests against HEC-RAS: still not run.
- Preview rasters hold only the tiles the objects reach; a run's modified terrain holds the whole domain.
- The ground under a crest line is the raw DEM, so a dyke tied into another object's fill still gets faces there. They do no harm.
- Other PCs, the CPU backend through the dock, QGIS versions other than 3.44.8.

## Files

`plug_check.py` drives the dock, `engine_worktree.py` pins it to this branch (the dock strips `PYTHONPATH`, and the venv's editable install points at the main checkout: without this the dock runs the old engine). `prove_real_ground.py` is the script proof on real ground, run before any plugin work. `crest_sweep.py` makes `crest_sweep.csv`. The PNGs are from the real dock.
