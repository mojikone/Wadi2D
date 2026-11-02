# W20 storm section

**Status (2026-11-02): done on QGIS 3.44.8, D5 of his work order.** A Storm section in the dock: steady rain, a hyetograph table, a design storm with its pattern and area reduction, gridded rain from NetCDF, DSS or a folder of GeoTIFFs. The same rain reaches the 2D cells and the lumped subbasins. Radar and satellite products stay for later, as he decided; a satellite file in NetCDF or DSS reads today.

## [PRESERVE-CHECK], [BROAD]

Declared before the work, and he said go.

- **KEEP:** the uniform and hypothetical storms, the HMS import, the ARF study, `depth_grid`, and every old `job.json`. Their code path did not change.
- **CHANGE:** two new storm kinds; a per-pixel rain path through `Forcing`; a Storm section that takes **Rain** and **Lasting** out of Hydrology; the sections below it renumber, 5 Structures to 8 Run. An HMS project still brings its own storm, and now it can be replaced from the section.
- **FILES:** `wadi2d/config/schema.py`, `wadi2d/forcing.py`, `wadi2d/run.py`, `wadi2d/engine/cli.py`, `wadi2d/hms/dss.py` (additions only), `wadi2d/io/identity.py`, new `wadi2d/storm/{rain_frames,gridded,hyetograph}.py`, `wadi2d/hydrology/cell_rain.py`, `wadi2d/io/rain/`, `wadi2d/engine/rain_info.py`, `plugin/.../job_builder.py`, `dock.py`, `map_notes.py`, `sections/hydrology.py`, new `sections/storm.py` and `storm_rows.py`.
- `dock.hydrology.rain` and `.hours` still reach the boxes, so the dock checks of older W folders run unchanged. `W15`'s `dock_options.py` also reads `rain_box`, which is gone; that one line would need changing in a copy.

## How it works

- **Every rain file becomes the same thing:** `RainFrames`, mm fallen in each period, north row first, NaN for no data. A format is one new file in `wadi2d/io/rain/`; nothing else knows it exists.
- **A 2D cell** reads the pixel its centre stands in. Cells sharing a pixel and a curve number share one excess, so a refresh computes pairs, not cells: a rain grid has thousands of pixels where a domain has millions of cells.
- **A lumped subbasin** takes the mean of the pixels under its polygon, weighted by shared area. A subbasin smaller than a pixel still has rain: a satellite pixel is about 10 km wide. The polygon mean of `DepthGrid`, which counts cell centres, would have left such a subbasin with none.
- **Area reduction belongs to design storms.** A hyetograph or gridded rain is the rain itself, and the job refuses a table on them.
- **The rain file is part of a run's identity**, a GeoTIFF folder too, so a changed file refuses a resume.
- **The dock asks the engine what a file holds** through `wadi2d rain`: QGIS must not load a second HDF5 library.

## What the readers will not do

- NetCDF: regular grids only; a curvilinear or Gaussian grid is refused, not interpolated. No calendars but the standard ones.
- **A bare time could close its period or open it, and no attribute says which.** That choice moves the rain by one period. Bounds settle it where a file has them; otherwise the section's choice, closes by default.
- Rain accumulated from the start of a forecast is not unpicked. A run warns when every frame holds at least the one before.
- GeoTIFFs have no time and no units: the job gives the period, and they are mm unless it says otherwise.
- A hypothetical pattern is a table the user supplies. I did not type in the SCS curves from memory, and his own storms use a specified pattern.
- HMS met files with gridded precipitation or a specified hyetograph are not imported; only the Hypothetical Storm is. The section replaces such a storm by hand.

## DSS grids

`wadi2d/io/rain/dss_grid.py` carries its reasoning in its header. `hecdss` returns the south row first, and a round trip through `hecdss` cannot show that, so it was shown from outside it, in `dss evidence/`:

| Check | Result |
|---|---|
| GeoTIFF sampled by coordinate, imported by HEC Vortex | north row stored last; reader equal cell by cell |
| ESRI ASCII through HEC's Asc2DssGrid | north row stored last |
| Dss2AscGrid and Vortex reading a grid back | north row first, both |
| Real HRAP frame against Vortex's north-up GeoTIFF | 100.000 % of 159 x 335 cells equal; 81.4 % the other way up |
| **HEC-HMS `tenk` sample: 4 subbasins over 98 hours against HMS's own PRECIP-INC** | **0.000000 mm apart; up to 5 mm in an hour the other way up** |

Two real HEC-written files are embedded in `tests/storm/test_rain_dss.py`, so the orientation stays pinned on any PC.

- `hecdss` cuts `srsDefinition` to 599 characters on read, and PSD93 / UTM 40N is 616, so a file in the project's own system would have been refused. `read_grid` widens the buffer through a private layer of `hecdss`; a test fails if that layer changes.
- His IMERG files have `D == E` in the pathname, so they read as instantaneous: **Period, min** must be set for them.
- Frames of different extent: no real file clipped frame by frame turned up in 395 scanned, and HEC-HMS 4.13 gives wrong rain on clipped frames, so it cannot be the reference. The rule in the header is inferred, and a wrong call changes only the missing-data note, not the depth.
- Not read: 77 of the largest candidate files. DSS version 6 is refused with a message; convert it first.
- [Likely] A very large grid, 61 frames of 4012 x 10365, would take about 4 min and 20 GB. Not run.

## Results

`dock_storm.py` through the real dock, Bidah at 40 m and Block 2 at 40 m (`log_dock_storm.txt`).

The known answer is steady rain, 60 mm in 1 h. Each of these holds the same rain differently and must return the same water:

| Rain | Against steady |
|---|---|
| Hyetograph typed in the table, 4 x 15 mm | equal within 1e-5 |
| Design storm, 100 mm, ARF 0.6 | equal within 1e-5 |
| NetCDF-4 from the real NetCDF library through GDAL, lat/lon on UTM cells | equal within 1e-4 |
| Classic NetCDF from the same library | equal within 1e-4 |

- A file from a real library, because a reader tested only on files its author wrote proves little. This found one trap: a coordinate variable in NetCDF-4 is a dimension scale with no scale of its own.
- A start date halfway through leaves half the rain.
- GeoTIFF folder with rain on the northern half only: rain within 2 % of the northern cells' share, and the map shows it there. The same rain from a DSS file, stored south row first, lands in the same place.
- A mesh keeps the volume of a uniform storm on the same mesh. A first test against the box's own area failed by 2.3 %: coarse cells overhang the box, so the mesh's area is larger than the domain's, for any storm. That is the mesh's, and not the rain's.
- Bad table, bad file, and a mesh cell whose centre lies past the rain grid's edge: refused or read in plain terms.

**Lumped and 2D take the same rain.** The Block 2 hybrid at 40 m, 100-yr: the HMS storm, then the same storm written out as 288 five-minute GeoTIFF frames. Rain on the plain 35,884,012 against 35,884,012 m3, water from the hills 84,501,544 against 84,501,544 m3. Every steady line within 0.34 %.

**A finding that has nothing to do with rain.** `S5_ring` and `S11_ring` flicker. `S5_ring` reads 480 m3/s raw but 325 as a 15-minute mean, moving about 107 m3/s from one minute to the next, in the HMS run as much as in the frames run. Their raw peaks moved 2.2 % between two runs with the same water, so the check judges steady lines and names these. [Guessing] The cause sits near where a lumped hydrograph enters at 40 m: the inflow's split among its cells is decided anew at each refresh. Not investigated, and it means a raw peak on a line near an inflow can read high. A 15-minute mean is the fair number there until it is.

Found by running it: `hecdss` writes its log to stdout around the answer, so the dock looks for the JSON line; two quick edits of the rain settings let the older answer overwrite the newer label, so an older query is now disconnected.

## Not tested

- QGIS other than 3.44.8.
- A real rainfall event end to end through the dock: his IMERG and WRF DSS files were read by the reader, not run.
- A full-extent run with gridded rain, and the memory of a large rain grid.
- ARF study (`wadi2d arf`) on the new kinds: it refuses them, by design, and that refusal has no dock path because the study is command line only.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W20 storm section\dock_storm.py" <throwaway folder> -Copy "W20 storm section"
```
