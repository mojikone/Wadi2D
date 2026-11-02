# W26 suggested breaklines

**Status (2026-11-02): D4 of his work order, built and tested on `feature/suggest-breaklines`, rebased on `main` after D3, not merged, nothing pushed.** A Suggest breaklines button in the Mesh section makes an editable layer: a bank line either side of every defined wadi, never on the thalweg; crests found by the top-hat of W5; the user deletes what is wrong and feeds the rest to Structures as crest lines, or to the Mesh section's table of refinement lines, which the same layer fills. 32 of 32 through the real dock on Bidah.

**The finding that matters: bank lines used as crest lines cost the peak, 10 to 22 % on Bidah and 30 to 36 % on Faydh 01, and triple the steps; the lines are where his rule puts them, and the loss is the engine's crest face, which passes at most critical flow and sets the step on every face the flood crosses.** Lowering the same lines a metre below the ground leaves most of the loss in place, so it is not the elevations. Bank lines must not go in as crest lines until the engine has a face that carries the ground along a line without the weir law; as refinement lines they only refine, which is what a bank line can safely do today. Nothing was tuned to hide this.

## [PRESERVE-CHECK]

- KEEP: every existing command, the job schema, the solver, the tables, the mesher and the Mesh section as D3 left it (its table, preview, zones, local stepping); the Structures section and its crest lines, which is how a suggested line reaches the engine (no new object kind); `wadi2d.mesh.streams` untouched, read only; GeoPackage layers without Z written byte for byte as before; the dock's run, preview, estimate and map paths.
- CHANGE: a new package `wadi2d/breaklines/` and one subcommand `wadi2d breaklines JOB --out FOLDER`; `VectorLayer.has_z` in `wadi2d/io/geopackage.py` (default off; on, 3D WKB and `z = 1` in `gpkg_geometry_columns`); a new `plugin/wadi2d_qgis/suggest_lines.py`; in `plugin/wadi2d_qgis/sections/mesh.py` the button, its row, its connect and the import, nothing else; a paragraph and a table row in the plugin README; one test in `tests/engine/test_io.py`. Nothing removed, no behaviour changed.
- FILES: `wadi2d/breaklines/{__init__,settings,window,pixels,thalweg,banks,crests}.py`; `wadi2d/engine/cli.py` (`_breaklines`, one subparser); `wadi2d/io/geopackage.py`; `plugin/wadi2d_qgis/suggest_lines.py`; `plugin/wadi2d_qgis/sections/mesh.py`; `plugin/wadi2d_qgis/README.md`; `tests/breaklines/`, `tests/plugin/test_suggest_lines.py`, `tests/engine/test_io.py`; this folder.

Written before the first edit; amended on the way, nothing removed: the slope cap on crests, the tributary and meander rules on banks, and the mesh-table fields, each described below with what made it necessary.

## What it does

`wadi2d breaklines JOB --out FOLDER` writes `suggested_breaklines.gpkg` with two layers, written with the standard library, no second GDAL:

- `breaklines`, 3D lines: `name`, `kind` (`stream bank`, `dam`, `road`, `other crest`), `side` (bank: left or right looking downstream), `height_m`, `length_m`, `area_km2`, `slope`, `score`, `why`, and `near_dx`, `rows`, `far_dx` for the Mesh section's table (the job's cell beside the line, the schema's 4 rows, the job's coarsest cell). Sorted by `score` = height x length, m2, the face of the line above the ground, so the lines that matter most come first. Every vertex carries the ground elevation at the line, so the layer goes to the Structures section as Crest lines with no field.
- `thalwegs`, 2D: `area_km2`, `incised_m`, `length_m`: the rows of cells the banks stand either side of. Reference only; the dock loads it read-only and names it so.

**The ground** (`window.py`) is the job's grid window read at the mesher's analysis pixel (5 m, or the largest divisor of the cell not above it), the same coarsened read the mesher uses; WhiteboxTools breaches and gives the D8 pointer and accumulation. A DEM without a CRS makes WhiteboxTools write nothing in silence; the error now says so.

**Thalwegs** (`thalweg.py`): pixels draining at least `mesh.stream_area_mid_km2` (1 km2), walked downstream from every head or junction to the next junction, smoothed over 5 vertices, simplified at half a pixel.

**Banks** (`banks.py`), his rules of 2026-11-01: sections every 10 m across each thalweg; the bed is the lowest ground within a pixel across; a bank is where the ground first stands `mesh.incision_depth` (0.5 m) above the bed, searched out to half of `mesh.incision_width` (100 m); past that, that side has no bank. No section where the thalweg is not incised by the mesher's measure, so a stream crossing an open plain gets no bank and the flow finds its own way. A bank stands at least one cell from the thalweg, so the thalweg keeps a row of cells of its own: the point is pushed out until it clears the thalweg *line*, not only its own section, and the smoothed line's vertices again, because smoothing cuts chords inside a bend (the dock found a vertex 3 m from a gorge thalweg before this). A bank point within a cell of another thalweg is dropped: the dock found a main-wadi bank running across a tributary's mouth, which a crest face would have closed. A line breaks where a section finds no bank, where the bank jumps by more than three sections, or where a vertex cannot clear; pieces under 100 m go.

**Crests** (`crests.py`): W5's top-hat, ground less its opening with a 40 m disc, at 0.5 m, the W5 row with the fewest lines elsewhere among those finding over 80 % of the highway. Past the raster edge the ground continues by odd reflection, as `incision` does: the plain opening called the top of every slope reaching the edge a crest (the first smoke run drew the raster's north and south edges as two "roads"). A one-pixel gap is closed first: where a crest crosses the edge of a cut, the mixed pixel there reads below the ground the opening restores and cut a 1 km road in three. Objects under 100 m across go; the rest is thinned (Zhang-Suen, vectorised NumPy) and walked into lines between junctions, counting branches as runs around the 8-ring so a staircase is one line (the first walk split a bar at 27 degrees into 48 pieces). Kind: a crest crossing a defined wadi, one incised by the mesher's measure, is a `dam` (a dam, or a road with a culvert); a straight one over 1 km a `road`; the rest `other crest`.

**The slope cap**, added after looking at Bidah and Faydh: at 0.5 m the top-hat traces every rock spur and gully edge of the mountains, 630 crests over 95 km on Bidah's 21 km2, 2,982 over 428 km on Faydh's 75 km2, 95 % of all lines. Under Bidah's hill crests the ground (the opened surface) has a median slope of 0.32; under the fan's, 0.03 (p90 0.10). A crest on ground steeper than `ground_slope_max` 0.15 is left out unless it is a dam: those spurs are the mountain itself, which the sub-grid tables already hold. It keeps 294 of 630 on Bidah and 217 of 2,982 on Faydh. [Likely] 15 % is a reading of two catchments, not a law; it is one named setting in `settings.py`, like every other number here.

**The dock** (`suggest_lines.py`): the button builds the job as the terrain preview does (ground and domain, no rain, no boundary), runs the command with a one hour limit, and loads the file beside the run folder (`<run folder>_breaklines/`) as a layer in editing, styled by kind, with the thalwegs beneath. A folder that already holds a suggestion is never written again, the user may have edited it and QGIS still holds it open: the next goes to `_2`, as runs do. The message says what was found, what to do next, and that a crest face is not free.

## Results

### Through the real dock

`dock_suggest.py` on `tests/dock/harness.py`, Block 2 ground around Bidah (the 5 m GGC terrain, the dam catchment) at 10 m, throwaway profile, on the rebased branch: **32 of 32** (`log_dock_suggest.txt`). Refused without a DEM; 111 banks along 21 thalwegs and 428 crests in 17 s; the layer valid, in editing, 3D, in the DEM's CRS, its fields the engine's, biggest first, every line with a reason, every bank vertex at least one cell from every thalweg (min 10.0 m, median 14.9); the file beside the run folder; the same layer fills the Mesh table with 10, 4, 40; one line deleted and saved, the file loses it; the rest run as 521 crest lines with their vertex elevations through the Structures section with no field; a second click goes to `_2` and is whole again. Renders in `dock_renders/`, looked at: the lines draw over the DEM, banks either side of the dashed thalweg, the table filled.

Earlier passes of the same scenario found the three faults named above (the mouth, the meander, the file held open) and one of my own (the scenario imported the plugin before the dock put it on the path). The Faydh-size window (75 km2) suggests in about a minute.

### Bank lines against none (the test he asked for)

The rain-on-grid head-to-head jobs frozen in W1 (Bidah, 21 km2, 0.5 m terrain) and W11 (Faydh 01, 74 km2), cut to 16 h, which holds the peak, maps off, only the suggested **bank lines** in, as crest lines with their vertex elevations, exactly what the dock sends. Nothing tuned. Peaks, m3/s, at the design lines of each case; extent is the wet area at the end, km2, at `outputs.wet_depth`. The 20 m runs use the 20 m domain polygon of their case, so 20 m rows compare only with each other. The 5 m runs without lines are the reference. GPU shared with other work: no timings; steps are what the solver took.

| Run | Cells | Lines | Steps | Peak at axis | Against no lines | Against 5 m | Wet, km2 |
|---|---|---|---|---|---|---|---|
| Bidah 5 m, none (reference) | 880,024 | 0 | 132,702 | 623.9 | | | 3.107 |
| Bidah 10 m, none | 220,006 | 0 | 78,914 | 621.9 | | -0.3 % | 3.283 |
| Bidah 10 m, bank lines | 220,006 | 82 | 262,274 | 561.4 | **-9.7 %** | -10.0 % | 3.284 |
| Bidah 10 m, bank lines 1 m below ground (diagnostic) | 220,006 | 82 | 262,274 | 573.2 | -7.8 % | -8.1 % | 3.277 |
| Bidah 20 m, none | 55,067 | 0 | 42,220 | 601.6 | | | 3.679 |
| Bidah 20 m, bank lines | 55,067 | 82 | 131,495 | 471.3 | **-21.7 %** | | 3.711 |
| Faydh 01 5 m, none (reference) | 3,020,656 | 0 | 301,473 | 1,887.1 | | | 3.906 |
| Faydh 01 10 m, none | 755,164 | 0 | 154,391 | 1,873.8 | | -0.7 % | 4.433 |
| Faydh 01 10 m, bank lines | 755,164 | 225 | 276,629 | 1,310.1 | **-30.1 %** | -30.6 % | 4.623 |
| Faydh 01 20 m, none | 188,814 | 0 | 88,589 | 1,835.2 | | | 5.398 |
| Faydh 01 20 m, bank lines | 188,814 | 225 | 140,498 | 1,183.2 | **-35.5 %** | | 5.619 |

The second line of each case (`s13_edge`, `box_mid`) moves with the first within a point. Bidah 10 m without lines reads 0.3 % off the 5 m reference, Faydh 0.7 %, and 20 m 3.6 % and 2.7 % off: the uniform grid is converged at 10 m, which is why W11 ran there. The no-line numbers are W1's and W11's own (601.6 and 1,835 at 20 m), so the engine on this branch has not moved. Mass error 2e-8 to 4e-8 throughout. The first set of line runs, on lines before the tributary and meander rules, is in `results_first_lines.jsonl`: Bidah -8.9 % and -15.4 %, Faydh -28 % and -30 %, the same reading.

**Why the bank lines hurt, as far as the runs show.** [Certain, from the diagnostic row] The same lines a metre below the ground change no face elevation (a face closes up to the higher of crest and ground) and still cost 7.8 % and the same 3.3 x steps: so three quarters of the loss at 10 m is the crest-face treatment itself, not the elevations. [Likely] A crest line turns every face on its staircase into a weir face: flow across it is capped at critical flow (decision 19) and the face sets the step. A design flood in a 20 to 40 m wide gorge stands metres above a bank placed 0.5 m above the low-flow bed, so it crosses the staircase obliquely along the whole reach, and every crossing is throttled and every face shortens the step. The flood arrives later (the peak moves 150 to 450 s) and lower, and the wet area grows 1 to 4 %, which is water held back. The remaining quarter is the vertex elevations: interpolated straight between simplified vertices on a gorge wall, they stand above the true ground between them. The loss grows with the cell (20 m worse than 10 m) and with the catchment (Faydh's banks are 116 km against Bidah's 34). I did not look inside the solver for this; W3's dry-face finding and decision 19's thin-crest treatment are the places to look.

**What this means for the feature.** A bank line is the right geometry for a refinement line and the wrong input for a crest line as the engine stands. The layer carries `near_dx`, `rows` and `far_dx`, so it can serve the Mesh section's table; that use was checked in the dock (the table fills) and not run through a flood. Crest lines belong to roads, dams and dykes, which a flood overtops rarely; the plugin README and the dock's message now say so.

### The W5 highway test, rerun

Same corridor, terrain and reference as `W5 automatic breaklines test/s01_highway.py` (Bathinah Highway CL, 40.8 km in a 3 km corridor of 273 km2, the 5 m blended terrain): found is the share of highway samples within 30 m of a line, elsewhere the length of lines away from the highway, some of it real roads and dykes the test has no layer for. `highway.py`, `highway_results.json`.

| Reading | Found | Elsewhere, km | Lines |
|---|---|---|---|
| W5, raw skeleton, disc 40 m, 0.5 m (its table) | 82 % | 376 | |
| Raw skeleton as built (odd reflection, one-pixel closing), scored as W5 did | 84.5 % | 461 | |
| Lines as written, no slope cap | 74.0 % | 211 | 1,218 |
| Lines as written | 74.0 % | 211 | 1,218: 12 road, 1,206 other crest |

The lines lose 10 points of the highway to the 100 m minimum and the walk's breaks at junctions, and halve what lies elsewhere. The slope cap changes nothing on the plain, as it should. Only 12 of the highway's pieces read as `road`: the embankment breaks at culverts and junctions into pieces under 1 km, so the straight-and-long rule rarely fires; the kind is a label for the reviewer, nothing downstream reads it.

## What the lines get wrong

- **Bank lines as crest lines cost the peak**, above. Not a fault of the lines; a limit of the object they become.
- **Crests in the mountains are the mountain**: without the cap, 95 % of all crests; with it, 294 on Bidah and 217 on Faydh, still mostly gully edges and terrace fronts on the fans. The cap is a judgement at 15 %.
- **Dams are mostly not dams**: 41 of Faydh's 217 crests cross a defined wadi, and on a gorge catchment those are spurs the smoothed thalweg cuts through at bends. The label says "a dam, or a road with a culvert"; the reviewer decides.
- **Braided reaches get several short bank pairs**, one per branch of the D8 tree, overlapping within a cell of each other; a gorge meander breaks a bank into pieces where a vertex cannot clear the thalweg (Faydh: 225 pieces for 116 km).
- **A bank at 0.5 m above the bed is the low-flow channel's edge**, not the flood's: the rise comes from the mesher's incision depth, one number for both.
- **Two parallel thalwegs on a flat bed**: a perfectly flat synthetic channel gave D8 two streams; real ground did not show it.

## Not tested

Suggested banks as refinement lines through a flood (the table fills; no run). Crests from the suggestion through a flood, beyond the highway's recall. A road layer or a dam layer as the truth for `road` and `dam`. The full extent (15,398 km2 at 5 m is 600 M pixels: the thinning and the walk are not written for that, and the dock's one hour limit would end it). A DEM at a pixel that does not divide the cell (the largest divisor is taken, said in the event). The CPU backend for the runs here (all GPU). Any PC but this one.

## Rerun

```
.venv\Scripts\wadi2d breaklines job.json --out lines1
python "W26 suggested breaklines\bank_runs.py" bidah suggest
python "W26 suggested breaklines\bank_runs.py" faydh suggest
powershell -File "W26 suggested breaklines\run_all.ps1"          # the no-line runs and the first line runs
powershell -File "W26 suggested breaklines\run_lines.ps1"        # the line runs on the lines as shipped
python "W26 suggested breaklines\highway.py"
python "W26 suggested breaklines\draw.py" bidah [x y half_width]
powershell -File tests\dock\run_check.ps1 "W26 suggested breaklines\dock_suggest.py" <throwaway folder> -Copy "W26 suggested breaklines"
```

The terrain of the frozen cases is not committed; `draw.py` and `bank_runs.py` read it from the main checkout and never write there.
