# W100 maps the RAS Mapper way

**Live (2026-11-16). Branch `feature/maps-surface` off `feature/fast-products` (`c29d44f`); not merged, nothing
pushed.** His go of 2026-11-16 on the proposal after his review of the Block 2 maps: maps that look like RAS Mapper's,
light and easy to use. Two faults, both in the drawing and not in the run: (1) square steps at cell edges (diagonal on
the aligned cells) and water "collecting in the cell" on hillsides; (2) maps too heavy to use (four rasters of 9.1 G
pixels, 3.5 GB each, no overviews; `results.h5` 11 GB). The deep-water clip of the depth styles was fixed before this
iteration (`9a90af0`) and is not touched here.

## The answer

Block 2's three 2D runs of W79 remade from their saved results (no solver run), into `runs/after_*` of this folder,
the W79 folders untouched (`s06_remake.py`, its figures in `results/after_*.json`; the grid and strip caches in this folder's own `runs/cache`, built once).
"Before" is W79's own rasters (W9's rule at 0.5 m, v0.4.0) with W93's timing of the same remake on the same card;
"after" is this branch's defaults (the continuous surface at 2 m, LERC 1 mm, overviews, no depth x speed).

| Block 2, GPU, 192 saved maps | 2D (run 1) | Hybrid Lumped (run 3) | Hybrid 2D (run 4) |
|---|---|---|---|
| Rasters of record, before | 4 files, **10,452 MB**, 93,120 x 97,480 px, no overviews | 7,147 MB | 8,184 MB |
| Rasters of record, after | 3 files, **514 MB**, 23,400 x 24,410 px, 7 overviews | **282 MB** | **315 MB** |
| Products step, before | 1,740 s (v0.4.0), 582 s (W93) | 822 s, 265 s | 1,319 s (W79, v0.4.0) |
| Products step, after (wall, the engine command) | **177 s** | **86 s** | **127 s** |
| Peak host working set, before (W93) / after | 21.9 / 20.8 GB (commit 32.2) | 17.4 / 11.9 GB | n/a / 15.2 GB |
| Peak card over its start, before (W93) / after | 12.0 / 11.4 GB | 12.5 / 12.4 GB | n/a / 12.6 GB |
| Hazard classes H1..H6, km2, before | 71.9, 35.5, 18.4, 30.7, 61.6, 43.4 (261.4) | 59.7, 29.3, 15.4, 24.3, 39.4, 11.7 (179.9) | 60.1, 29.3, 16.0, 25.2, 44.4, 30.6 (205.8) |
| Hazard classes H1..H6, km2, after | 109.7, 43.9, 21.4, 33.5, 65.4, 43.4 (317.4) | 82.6, 31.9, 16.0, 24.8, 40.0, 11.8 (207.1) | 83.3, 32.0, 16.7, 25.7, 44.9, 30.7 (233.3) |

[Certain, measured; the times with this session's other work on the machine, so upper figures.] The maps of record
are **20 to 26 times lighter** and the step **2 to 3 times faster** than W93's and 10 times faster than v0.4.0's.
[Certain] **The class areas grew: +21 % of wet area on the 2D run, +15 % and +13 % on the hybrids, nearly all of it
H1 (thin water, +53 % on the 2D run), H6 unchanged.** It is the rule and not the pixel: W9's rule at 2 m reads
261.8 km2 against 261.4 at 0.5 m (`results/rule_cell_fill_2m_run1.json`). The cut hid every cell whose mean depth never
reached 5 cm, also where its own pixels stood deeper (a rill in a cell of sheet); the rasters now show them. That is
a change of the numbers of record, not only of the picture, and it is his call whether the hazard map should show it
(the depth floor, `depth_floor`, 5 cm, decides a pixel now, as RAS Mapper's plot tolerance does).

**The water the map draws against the run's own** (`s05_volume.py`, `results/volume_*.json`): the step run on the 2D
run's wettest saved map alone (t = 14.0 h), every drop drawn (depth floor 1 micrometre, every digit kept), the drawn
depth times the pixel area summed, against each cell's mean depth times its area (squares and aligned cells):

| 2D run, t = 14.0 h, 2 m pixel | Drawn, Mm3 | Of the run's 178.04 Mm3 |
|---|---|---|
| W9's rule (`cell_fill`, no cell cut): each cell refilled | 178.02 | 0.9999 |
| **Continuous (the default)** | **179.73** | **1.0095** |
| Corners alone (RAS Mapper's sloping mode) | 177.52 | 0.9971 |
| Continuous before the hollow cap (step 6 above) | 199.65 | 1.121 |

[Certain] On the continuous surface the aligned cells draw 110.69 Mm3 of their 110.48 (+0.2 %) and the squares 69.04 of
67.55 (+2.2 %); by the cells' own mean depth: over 30 cm +0.1 %, 5 to 30 cm +5 %, 1 to 5 cm +16 %, under 1 cm 1.95 of
1.29 Mm3 (2.4 M hill cells). Corners alone hold the total nearly as well here because the deep water dominates it,
but they lose the thin sheets (the tilted-plane test: under 20 % of a 4 to 6 cm sheet) where the continuous surface
gains a little. [Likely] Acceptable against RAS Mapper's practice: HEC states its default sloping mode is not volume
conservative and names the horizontal mode for any map whose volume is used; a map here is not a volume of record
either, the run's own is, and within 1 % on the whole run it is closer than RAS Mapper promises.

Pictures (`pictures/`, the plugin's colours: the pixel depth ramp with the dock's 5 cm cutoff, the AIDR classes, the
raw DEM's hillshade, the run's cells in grey), all from the 2D run (W79 run 1), each window in three: `1_before`
(W79's own raster, W9's rule at 0.5 m), `2_after` (the map of record, 2 m), `3_after_detail` (the same rule at 0.5 m
by `wadi2d window`):

- `pool_depth_*.png`, `pool_hazard_*.png`: the R2A pool and its dam (437,800 to 439,800 E, 2,714,600 to 2,716,400 N).
- `hill_depth_*.png`, `hill_hazard_*.png`: a hillside of RIJ-S12, rain on the grid, with the cell grid (440,600 to
  441,200 E, 2,716,900 to 2,717,350 N).
- `reach_depth_*.png`, `reach_hazard_*.png`: an aligned-cell reach and its join with the squares, with the cells
  (440,300 to 441,100 E, 2,717,300 to 2,717,800 N).

How much the depth steps at cell edges against inside the cells, on the same windows at 0.5 m (`s04_steps.py`; the
share of side-by-side pixel pairs, one wet and one dry, east-west / north-south; a surface with no step at edges reads
the same at edges and inside):

| Window, 0.5 m | Wet-dry at cell edges | Inside cells | Mean depth change at edges, wet pairs | Inside | Across the strip join: wet-dry, mean change |
|---|---|---|---|---|---|
| Hillside, before (W79) | 0.148 / 0.152 | 0.023 / 0.019 | 8 mm | 7 mm | n/a (no strip) |
| Hillside, after | **0.095 / 0.085** | 0.029 / 0.026 | 12 mm (99th percentile 15 cm) | 7 mm | n/a |
| Reach, before (W79) | 0.049 / 0.060 | 0.008 / 0.009 | 11 / 12 mm | 9 / 11 mm | **0.198 / 0.197, 93 / 89 mm** |
| Reach, after | 0.036 / 0.031 | 0.012 / 0.013 | 12 / 14 mm | 9 / 11 mm | **0.030 / 0.044, 21 / 12 mm** |
| Reach, corners alone (RAS's sloping) | 0.016 / 0.016 | 0.012 / 0.013 | 11 / 12 mm | 10 / 12 mm | 0.202 / 0.222, 126 / 153 mm |

[Certain, measured] The join between the aligned cells and the squares, the staircase beside every wadi, is gone (a
wet-dry change on a fifth of the join's pixel pairs before, 3 to 4 % after). On the hillside the cell-edge cuts fell by
40 % but did not vanish: the edges that remain are brinks (a sheet against a rill, depths unlike, the face kept as a
step on purpose) and the cells the hollow cap lowered, and where they remain the step is larger than before (99th
percentile 15 cm against 6.6 cm), because W9's rule eased every edge over two cells and this one does not. Corners
alone are smoothest at the lattice's edges and worst at the join, and they lose the thin sheets (the volume table).

## What the others do (research before building, his standing rule)

**HEC-RAS Mapper.** Sources: HEC-RAS 5.0.2 release notes, item 7 "RAS Mapper - Describe sloping/hybrid modes" (HEC's
own PDF); the RAS Mapper User's Manual, *Mapping Results / Mapping Options* and *Settings and Options* (HEC
Confluence, latest); the 2D User's Manual 6.3, *Map Rendering Modes*.

- [Certain] *Horizontal*: each cell's single computed water surface drawn flat across the cell and intersected with the
  terrain. HEC: true to the engine and "volume conservative", the mode to use for stored maps whose volume feeds
  other work; on steep ground with shallow water it stair-steps into separate bodies from cell to cell.
- [Certain] *Sloping (cell corners)*, the default of the current manual: water surfaces interpolated from the cell
  corners; HEC states it is not volume conservative and can show more or less water than the engine holds. The 5.0.2
  notes give the two failures: on steep ground with very shallow flow (rain on grid) cells "don't have enough water to
  connect" and large areas draw dry; a cell over a ravine whose corners are high ground draws far more water than
  exists. Corners are shared only "if water goes over a face".
- [Certain] *Sloping (cell corners + faces)* adds the face water surfaces; options *depth-weighted faces* (a face's
  surface weighted by its depth, deep faces count more) and *shallow water reduces to horizontal* (a shallow cell
  falls back to the horizontal mode, more water shown, stair-stepping again). 5.0.2's *hybrid* did the same two tricks
  and also "dragged" the corner values so their average equals the cell's computed surface.
- [Certain] Stored maps and dynamic maps use the same render mode; a stored depth grid is wet or dry per terrain pixel;
  a "Plot all map values with a depth greater than" tolerance drops very shallow pixels; dynamic maps are drawn on the
  fly from the terrain's pyramid level for the zoom, so the depth shown changes with the zoom.
- [Guessing] How RAS Mapper decides "water goes over a face" exactly, and its default depth tolerance: not found in
  HEC's pages.

**SFINCS sub-grid (hydromt-sfincs, `workflows/downscaling.py`, read in the code).**
- [Certain] `downscale_floodmap`: every DEM pixel takes a water level, `nearest` (the level of the cell holding the
  pixel, "the classic bathtub", the default) or `bilinear` between cell centres (citing Sanders and Schubert 2019,
  PRIMo); depth is that level minus the DEM, kept where above `hmin`, 0.05 m by default. No connectivity in the step
  itself; removing disconnected flooding is a separate post-process. Written as a COG: DEFLATE, predictor 2, 256
  blocks, overviews by `nearest`.

**TUFLOW HPC with sub-grid sampling (TUFLOW Wiki, *TUFLOW HR Output*).**
- [Certain] HR depth is the computed water level interpolated to each output point minus the sub-grid elevation there;
  cell-centre levels are first interpolated to the cell corners. Three corner methods: A as the standard output; B
  checks sheet flow at faces and ignores the upstream cell's level; C (default) does B and also weights by the number
  of wet sub-grid points, so in-stream cells govern. With B and C, sheet-flow cells may draw dry. The default output
  cell is the SGS sampling distance. TUFLOW's guidance: HR output is for presentation; convergence and benchmarking
  use the standard output.

**What is taken, and what is not.**
- [Certain, all three] Depth = an interpolated water surface minus the terrain at the pixel, wet by a per-pixel floor;
  no per-cell volume refill. Taken: this is the rule now.
- [Certain] Corners shared only where water passes the face (RAS); taken, with the face's ground from the tables
  (crest lines and walls included), so the surface is never carried over high ground.
- [Certain, tried and set aside] Depth-weighted sharing (RAS depth-weighted faces, TUFLOW method C's in-stream
  bias). Joining every face water passes and weighting the levels by depth squared drew the hillside window best
  (the share of wet-dry changes at cell edges equal to that inside cells, 0.026 against 0.029), but two faults showed:
  weighted everywhere, a plane of water down a 20 % slope read 0.125 m off at a quadtree interface; weighted only at
  steps between unlike depths, a film on a flat bank top beside a deep channel took the channel's level at the brink,
  its surface plunged, and the fill that held its water lifted the next cell's surface by 17 cm (a test wadi). The
  rule kept is W9's join (a pool, or one flow of alike depths, the shallower at least half the deeper) plus a dry cell
  that water spills into: a brink keeps a step at the face, where the water does fall.
- [Certain] The known failure of corners alone on steep rain-on-grid ground (RAS 5.0.2, TUFLOW B and C): reproduced
  here, a sheet of 4 to 6 cm on a 10 % slope draws under 20 % of its water. Not taken as RAS's cure (horizontal for
  shallow cells, which is the stair-step he rejected); instead each corner also takes the move that makes its cells'
  surfaces hold their own water (one Newton fill a cell, already in the engine), interpolated through the corners so it
  never steps at an edge. This is RAS 5.0.2's "drag the corner values so their average matches the computed cell" done
  on the volume and not on the mean level. [Likely] closest to SFINCS's bilinear in spirit; none of the three does it.
- Not taken: SFINCS's `nearest` (the bathtub: the cell's flat level, the stair-step) and its no-connectivity default.
- Taken from all three: maps of record at a pixel coarser than the terrain where the cells allow it, the full detail
  drawn on demand (RAS's dynamic maps, TUFLOW's HR grids), and overviews in the files (SFINCS writes COGs).

## The rule now (`outputs.pixels.surface`, default `continuous`)

A map's water surface over a cell is the surface through its four corners (bilinear on squares, Wachspress through
the nodes on aligned cells); the depth of a pixel is that surface less its ground (the modified terrain, as the tables
read it), and a pixel is wet when that depth reaches `depth_floor` (5 cm). Per saved map:

1. Two cells share their corners where water passes the face between them (a wet side's level above the face's
   ground, crest lines and walls included) and they are one body of water there: both levels above the face, or a
   step between depths alike (`link_ratio`, the shallower at least half the deeper), or a dry cell the water spills
   into (`products/surface.py`, `face_joins`). A corner's cells are its whole connected ring of four (`corner_components`;
   W9's groups missed the long way round and gave two joined cells different values at a shared corner a quarter of
   the time on random ground).
2. A corner takes the mean level of its wet cells.
3. Each wet cell's surface of that shape is moved by one Newton fill until it holds the cell's own water (the fill of
   W9, once instead of four times), and a corner then also takes the mean of those moves. The move is what keeps a thin
   sheet on a slope: the levels alone lie under the ground there (the wedge of a flat fill).
4. A corner's move may not lift the surface over the lowest face round it that its cells do not share
   (`corner_sills`, `capped_moves`): a sheet spread over its cell stops short of a face its water never crosses.
5. A dry cell that water spills into takes pixels too, so that water ends on its ground and not on the cell edge.
6. A wet cell whose surface spans a hollow it holds no water for is lowered until it holds its own
   (`_hold_water`): it draws more than it holds, by a quarter or 3 cm of mean depth (`volume_slack`,
   `volume_slack_m`), and somewhere deeper than its own level stands over its lowest ground. This is RAS Mapper's
   ravine failure ("the water-surface will try to render across the four corners, creating dramatically more water
   over the low-ground center than actually exists", HEC-RAS 5.0.2 notes), found on Block 2's mountains: on a
   kilometre square of them (433,652 to 434,652 E, 2,709,824 to 2,710,824 N; cells with 7 to 13 m of relief) cells
   holding a millimetre drew a metre in their gullies, 9.3 times the water the square held at the run's wettest map;
   with the cap 1.16 times. Capping every cell that draws more than it holds cut the hillsides into blocks again
   (wet-dry changes at cell edges 0.16 against 0.03 inside), so a thin sheet that draws more than its own but never
   deeper than its own level is left alone; the cap makes a step only in a cell whose surface had spanned a gully.
7. The run's own peak of depth x speed between saved maps (`peak_lift`) is laid on through the corners too, not one
   number a cell, so the hazard classes do not step at an edge either.
8. The aligned cells and the squares meet (`products/strip_join.py`): the squares take each replaced square beside
   them as a neighbour that takes no pixels, holding the water of the strip cell whose ring holds its centre, across a
   face whose ground is the square's lowest join face; their surface at the join corners is kept map by map, and a
   strip cell takes it at a node of a join face the same rule joins. Before, a square beside the strip saw nothing
   there and every join was a step: a staircase along the strip's edge, diagonal beside every oblique wadi.

No cell is cut for its mean depth any more (`kept_cells`: every cell that was ever wet); `cell_depth` is read only by
`surface: cell_fill`, which is W9's rule unchanged (the maps made before W100, to the digit: W86's and W93's block
tests pass on it). `surface: corners` is RAS Mapper's sloping mode (no moves), kept for comparison. The quadtree takes
the rule through the same object (`MeshMaxima`), its ghosts' moves as before. CPU and GPU are one source (`xp`); the
time slider's renderer (`wadi2d render`) builds the same object, so the screen and the stored map agree at the same
pixel (an aligned or quadtree run is still drawn one value a cell there, W51's limit).

## Light maps

- **The pixel of record** (`outputs.pixels.pixel_m`): left empty, the coarsest multiple of the DEM pixel within
  `auto_pixel_m` (2 m) that divides the cell and gives it `auto_cell_pixels` (8) across, never finer than the job's own
  DEM stride (`products/ground.py`, `auto_stride`). Block 2 at 20 m on the 0.5 m DEM: 2 m, ten pixels a cell, a
  sixteenth of the pixels. A 10 m job maps at 1 m, a 5 m job at the DEM's 0.5 m. **A job that states `pixel_m` keeps
  it**: every resolved configuration written before W100 says `0.0`, the DEM's own, so a remake of an old run with its
  own configuration still maps at 0.5 m (the remakes below set it empty). The ground of a coarser pixel is the DEM's
  pixel picked at the stride, as the tables at a stride read it: a channel narrower than 2 m can fall between picks,
  so its deepest pixel is in the detail, not in the map of record.
- **Compression**: depth and speed in LERC within `max_error_m` (1 mm; m/s for speed) then DEFLATE (`LERC_DEFLATE`,
  GDAL 2.4 and later, QGIS's own builds included); the nodata of a dry pixel is kept exactly. `max_error_m: 0` keeps
  every digit (DEFLATE with the floating-point predictor). The classes stay DEFLATE, lossless.
- **Overviews** inside each file (`overviews`, on): halved until a side is under 256 pixels; depth and speed averaged
  over their wet pixels, the classes by the class most of them hold (mode).
- **Depth x speed** is no longer written (`dv_raster`, off): the hazard classes are made from it as before. The
  plugin loads it when it is there and leaves it out when it is not.
- **The detail on demand**: `wadi2d window RUN XMIN YMIN XMAX YMAX [--pixel 0.5]` writes depth, speed and hazard of a
  window at the DEM's pixel (or another) into `RUN/pixels/windows/`, each pixel what the whole run at that pixel holds
  there, to the digit (tested): the cells round the window it reads (the halo, and the strip's reach), the whole run's
  datum. The time slider at the pixel (W51) is the other way to the 0.5 m detail.

Where the 20 times come from, the 2D run (run 1), MB (`results/after_*.json`, `lossless_2m_run1.json`; the LERC-only
row the lossless files re-encoded, same blocks):

| Run 1 | depth | speed | hazard | depth x speed | total |
|---|---|---|---|---|---|
| Before: W79, W9's rule, 0.5 m, DEFLATE, no overviews | 3,412 | 3,377 | 107 | 3,556 | 10,452 |
| 2 m, every digit (DEFLATE, float predictor), no overviews | 269.4 | 272.0 | 24.6 | not written | 566.0 |
| 2 m, LERC within 1 mm, no overviews | 157.6 | 146.3 | 24.6 | not written | 328.5 |
| **2 m, LERC within 1 mm, overviews (the default)** | **241.5** | **232.3** | **40.1** | not written | **513.9** |

[Certain, measured] Leaving out depth x speed takes a third; the 2 m pixel the rest of the factor (a sixteenth of the
pixels, though 21 % more of them wet); LERC at 1 mm 0.58 and 0.54 of every digit; the overviews add 53 to 63 % back
(more than the third a pyramid's pixels count, [Likely] because a reduced pixel is wet where any of its four is). They
are what makes the whole map open in seconds, so they stay; a coarser error on the overviews alone (GDAL's
`MAX_Z_ERROR_OVERVIEW`) is a further saving, not tried.

## results.h5 (measured, nothing changed: it is the solver's record)

The 2D run's file is 10.3 GiB (`s07_results_size.py`, `results/results_size_run1.json`): 192 saved maps, each of five
lattice fields over the whole 2,368 x 2,464 lattice (5.8 M cells, 2.9 M of them active) and three strip fields.

| Stored, GiB | depth | mean depth | speed | qx | qy | strip (3 fields) | maxima, series, mask |
|---|---|---|---|---|---|---|---|
| 2D run (W79 run 1) | 1.83 | 1.88 | 1.89 | 1.71 | 1.69 | 1.12 | 0.06 |

Options, every one measured on 4 of the maps re-encoded and scaled to all 192 (lossless ones checked bit for bit):

- [Certain] **The face discharges `qx`, `qy` are a third of the file (3.4 GiB).** They are W30's saved face flows
  (`outputs.face_discharge`, on): a line drawn after the run reads them as a line of record. Off, the file is about
  6.9 GiB; the price is W21's estimate (0.6 to 1.0 of the record) for lines drawn later. His call.
- [Certain] Lossless re-encoding gains little: the byte shuffle with gzip 4 takes the lattice fields 3 % smaller
  (7.19 to 6.95 GiB as re-encoded) at 18 % more write time (float32 noise does not shuffle well); LZF 8 % larger.
- [Certain] **The strip fields are stored in chunks of 128 values** (`(1, 128)`), so they hardly compress (0.38 of
  0.39 GiB a field); chunks of 65,536 with the shuffle take them from 1.01 to 0.74 GiB. A change of the writer's chunk
  shape only, lossless; not made here (the writer is the solver's), proposed.
- [Certain] Fewer maps: 900 s between maps gives 192 for 48 h; the file scales with it.
- Not proposed: storing the record lossy (a scaled 16-bit integer); the record is what everything is redone from.

## The smoothed polygons and the depth drawing

Left as they are (code, `outputs.smooth.enabled`, off by default, `wadi2d drawings`). [Likely] they should be
retired: they were made to hide the blocks of W9's surface, and the continuous surface has none to hide; RAS Mapper
draws no such second product, its depth map is the depth map. A map sheet (Make map) still draws the class polygons
for the PDF; with the new rasters the raster classes themselves print cleanly at 2 m. His call; retiring them is a
dock and a Make map change, not made here.

## Tests

New:

- `tests/products/test_continuous_surface.py` (18): a sheet of 4 to 6 cm on a 10 % plane of 20 m cells (each cell's
  level its own flat fill, a wedge 0.6 m deep) is drawn with no step at cell edges (the mean change across an edge no
  more than inside a cell plus 2 mm) and holds the sheet within 15 %, where the levels alone lose 80 % of it and W9's
  cells without their passes step at every edge; no cell cut for its mean depth; a terrace beside a channel stays dry
  with a film on it; a crest line at 102 m keeps a pool at 101 m from the 100 m ground beyond (and a dry cell beyond
  takes nothing); water spilling into a dry cell ends on its rising ground, not at the edge; a pool 12 m deep drawn
  flat to 1 mm; a cell holding a millimetre whose surface draws 2 m in a gully is lowered to hold its own, while a
  sheet drawing twice its water but nowhere deeper than its own level is left alone; the card and the host the same; the halo of each rule; the map's pixel rule (8 cases).
- `tests/products/test_record_rasters.py` (7): every float within the bound and every dry pixel kept, with LERC and
  without; reduced copies read back; LERC at 1 mm under 60 % of lossless DEFLATE; class overviews by mode; overview
  levels.
- In `tests/products/test_blocks.py` (5 more): the continuous surface in many blocks equals one block to the digit
  (squares; aligned cells with the join); a drawn window equals the whole run's rasters there to the digit (both);
  the strip and the squares meet without a step (the mean change across the join no more than twice that inside).

Changed on purpose, each named in its file:

- `test_cell_edges.py`: tests W9's refill and eased edges, now under `surface: cell_fill`; the backend test over the
  three rules.
- `test_blocks.py`: W86's and W93's tests on W9's rule at the DEM's pixel, lossless, depth x speed written (`RECORD`),
  the terms they were written on; the out-of-memory retry test passes the window by keyword.
- `test_step.py`: depth x speed not written by default (asked for in the lift test); CPU against GPU within the
  compression's bound on each side; "wet only in the wadi": the rain's own sheet on the flat bank tops (4.9 cm a cell
  at its peak) now shows where the ground dips (under 5 % of the bank pixels, under 15 cm), where the cut hid it.
- `tests/render/conftest.py`: the yardstick keeps the cells the rule keeps; the record lossless for its 2e-4 m
  comparison. `test_renderer.py`: "a coarser pixel holds each cell's water to 2e-4 m" (W9's promise) is now "a
  coarser drawing draws the water of the native one within 10 %".

Passed on the final code (`75ab870`), one file at a time (`NUMBA_NUM_THREADS=8`), **302 of 302 in 25 files**:
`tests/products` test_continuous_surface 18, test_record_rasters 7, test_surface 18, test_cell_edges 10,
test_mesh_pixels 14, test_blocks 13, test_step 30, test_terrain_pixels 2, test_cell_maps 3, test_smooth 26,
test_time_slider 14, test_hazard 12, test_ground_read 8, test_fill_kernels 2, test_strip_kernels 10,
test_strip_weights 8, test_result_lines 29, test_face_flow 13, test_cell_grid 12; `tests/render` test_renderer 17,
test_server 6; `tests/engine` test_strips_run 15, test_fill_pits 4; `tests/demstore/test_products.py` 4;
`tests/plugin/test_map_notes.py` 7. The full suite was not run (his rule).

## Not done

- The time slider at the pixel still draws an aligned-cell or quadtree run one value a cell (W51's limit), so on
  Block 2's runs, all aligned, the 0.5 m detail on screen is the drawn window (`wadi2d window`), not the slider. The
  slider's lattice runs use the same rule as the maps (same object), tested to 2e-4 m against the step.
- A face between two cells that water passes but whose depths are unlike (a brink) keeps a step at the face: the
  remaining cell-edge line on hillsides, where a rill and a sheet meet (the share of wet-dry changes at cell edges on
  the hillside window, 0.095 and 0.085 against 0.029 and 0.026 inside cells, was 0.15 with W9's cut; 0.026 with
  every face joined and depth weights, set aside for the brink fault above). Where such a step remains it is sharper
  than W9's eased edge (99th percentile 15 cm against 6.6 cm).
- Volume: the maps no longer hold each cell's water exactly (see the numbers above); RAS Mapper's sloping mode does
  not either. A volume read off a map is not a volume of record; the run's own is.
- The plugin's styles, the dock and Make map are as they were (the dock is the redesign's). Make map's sheets were
  not remade.
- `results.h5`: nothing changed (options above).
- Not run: the full suite (his rule: one file at a time). QGIS was not opened on the new rasters. [Certain] The GDAL
  bundled with both QGIS installed here, 3.44.8 (GDAL 3.12.2) and 3.36.2 (GDAL 3.8.5), lists LERC_DEFLATE; the office
  PC's QGIS is 3.36.2. QGIS 3.36.2's own `gdalinfo` and `gdal_translate` read the 2D run's new depth raster, its LERC
  and its seven overviews (24,410 x 23,400 down to 191 x 183), and a 1 % read of it.

## For the dock (requests, not built: the dock is the redesign's, `feature/dock-redesign`)

- A **Map pixel** field in the Run section: empty (the rule, 2 m on Block 2), or a number; with the note that a
  coarser pixel is a sixteenth of the files at 2 m and the detail stays on the time slider and in a drawn window.
- A **Window at the terrain pixel** button: draw a rectangle on the map, and `wadi2d window` writes its 0.5 m depth,
  speed and hazard into the run's `pixels/windows/` and loads them in the run's group (styled as the record), with
  the time it took on the status line (about a minute for a 1 km square of Block 2, most of it reading the saved maps).
- A **Water surface** choice in the advanced settings: continuous (default), corners (RAS Mapper's sloping, for
  comparison), cells filled (the maps before W100).
- A **Depth x speed raster** tick (off), for the few who use it beside the classes.
- The display cutoff of the depth styles (W88) applies to the new rasters as to the old; nothing to change there.

## Files

- `s01_cache_folder.py W79_CACHE OUT`: a cache folder of this iteration that reads W79's caches without writing into
  them (hard links, junctions for the DEM stores).
- `s02_tables.py RUN CACHE`: a finished run's tables built (or found) in that cache.
- `s03_windows.py RUN CACHE OUT --window NAME XMIN YMIN XMAX YMAX ... --rules a,b --pixel M`: the rasters of windows by
  each surface rule.
- `s04_steps.py RUN RASTER...`: how much a raster steps at the lattice's cell edges and across the strip's join,
  against inside the cells.
- `s05_volume.py RUN CACHE OUT --map NAME`: the water a map draws against the run's own at one saved moment.
- `s06_remake.py RUN TAG --cache CACHE [--set k=v]`: a run's maps of record made again here, timed, memory and sizes.
- `s07_results_size.py RUN OUT.json`: what fills `results.h5`, and what other lossless layouts would take.
- `s08_pictures.py BEFORE AFTER WINDOWS OUT`, `pictures.py`: the pictures, in the plugin's colours.
- `pictures/`: the before and after pictures. `results/`: the measured figures quoted here (JSON). `runs/` (rasters, remakes, logs, the cache) is not in git.
