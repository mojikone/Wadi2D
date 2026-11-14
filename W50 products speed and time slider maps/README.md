# W50 products speed and time slider maps

**Live (2026-11-09). Design on `feature/face-local-radius`; his go the same night; the first speed-ups built on `feature/fast-products` (off it), not merged. Paused at 60 % of the weekly all-models usage, his rule. Resumed and finished on 2026-11-13 on `feature/products-option`, not merged: the last section below holds the current numbers; the "Built so far" table is the record of the first speed-ups.** His order of the night: the products
after a run are the bottleneck, not the solver; make them as fast as they can be, and show the results as HEC-RAS does,
on the time slider at small intervals (15 minutes), at pixel detail. His go is needed before building: it touches the
engine's product step and the plugin.

## Where the time goes (`profile_products.py`, `profile/`)

Block 2 at 20 m, W49's local-radius run (2.03 M cells, 36 h of storm, 7 saved frames), its products remade on a copy
of the run with every progress event stamped and the whole step under cProfile. The solver loop of that run took 276 s
on the GPU.

| Stage | Seconds | What it is |
|---|---|---|
| Grid and domain mask | 73 | the cached tables loaded (4 s) and the active mask recomputed from the DEM (70 s) |
| Ground | 109 | the 0.5 m DEM read in 57 windows under the wet cells |
| **Frames at the pixel** | **3.8** | the 7 frames and the run's peak laid over the ground on the GPU, about 0.5 s a frame |
| Rasters | 224 | depth, speed, depth x speed and hazard written as whole-block 0.5 m GeoTIFFs, 45 s each, one thread |
| Smoothed polygons | about 405 | class masks blurred, distance transforms, contours, shapely rings, on the CPU |
| Depth drawing | 804 | a 4.3 GB coloured picture of depth at 0.5 m, drawn block by block on the CPU |
| **Total** | **1,624** | 27 minutes, against 4.6 for the solver |

[Certain, measured] **Mapping is not slow; files and pictures are.** Laying a frame over the 0.5 m ground costs half a
second; everything else is reading the DEM, writing whole-block files that are mostly empty, and drawing on the CPU.

## How others show the flood on a time slider

- **HEC-RAS (RAS Mapper).** [Likely, from the 2D manual as quoted, not the current page] Results maps are "dynamic":
  RAS Mapper reads the computed results from file, computes the map in memory for what is on screen, and displays it;
  nothing is written. The slider steps through the run at the mapping output interval. Stored maps (rasters on disk)
  are made only when asked, from the Manage Results Maps window. Sources: [2D manual 5.0, archived](https://webarchive.library.unt.edu/web/20161020213247/http://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS%205.0%202D%20Modeling%20Users%20Manual.pdf),
  [Kleinschmidt, static maps](https://forum.kleinschmidtgroup.com/ras-post/creating-static-results-maps-shapefiles-or-rasters-using-ras-mapper),
  [Kleinschmidt, exporting many maps](https://forum.kleinschmidtgroup.com/ras-post/post-processing-with-ras-mapper-exporting-a-large-number-of-results-maps).
- **TUFLOW HPC.** [Likely, from the manual as summarised] The map output (XMDF or NetCDF on the cells) is written at the
  Map Output Interval and viewed as a mesh layer; high-resolution rasters of depth and water level are a separate output
  with their own interval and cell size (the manual's example 3600 s at 0.5 m), the level interpolated from the cells and
  the depth that level less the sub-grid ground; maxima are tracked every time step. Sources:
  [TUFLOW HR output](https://wiki.tuflow.com/TUFLOW_HR_Output), [manual, map outputs](https://docs.tuflow.com/classic-hpc/manual/2026.0/Map-2.html),
  [Quadtree and SGS FAQ](https://wiki.tuflow.com/Quadtree_and_Sub-Grid_Sampling_FAQ).

Wadi2D today: the engine saves frames every 15 minutes by default (`outputs.map_every_s` 900); the time slider (W19)
shows them as cell values on a mesh layer, which draws the 20 m cells as blocks; the pixel products are the peak only.

## The design, for his decision

**1. Time slider maps drawn on demand, RAS Mapper's way (recommended).** A results layer in the plugin that draws, for
the time on the Temporal Controller and the area on screen, the frame's depth, speed or hazard at the pixel, from the
saved cell frames and the DEM, with the engine's own pixel rule (the same code that makes the record maps, so the
slider and the record agree). Nothing is written per frame. The plugin never imports the engine, so the drawing runs
in an engine process the plugin keeps open and asks for one image at a time (extent, size, time, field).
[Guessing until built] A screen of about 2 M pixels costs well under a second on the GPU, so the slider plays at the
saved interval at any zoom. Cost: about 4 MB a frame on disk for Block 2 at 20 m, which the runs already write.

**2. Time slider maps written as files, TUFLOW's way.** Depth rasters per frame at a chosen interval and pixel, wet
tiles only, played by QGIS from a stack. Simpler in the plugin, but disk and write time grow with every frame and every
pixel: at 0.5 m over Block 2 even sparse files would be hundreds of MB a frame. Not recommended.

**3. The record maps made fast, with either.** The peak depth, speed, depth x speed and hazard rasters stay the numbers
of record. Make them:
- written only where wet, as tiled, compressed, sparse GeoTIFFs with several threads (224 s of whole-block writing now);
- from a ground cache kept with the grid cache (109 s of DEM reading now, every run and every remake);
- with the active mask kept with the grid cache (70 s now, on every remake);
- the 4.3 GB depth drawing off by default and made only when asked (804 s now): QGIS draws the depth raster in colour
  itself;
- the smoothed polygons kept, on demand or behind a tick, and later on the GPU (about 405 s now).

[Guessing until measured] Block 2's record maps from 27 minutes to about 2 to 4 minutes, most of it the polygons when
asked for.

**Order, if he agrees:** 3 first (it pays on every run, and it is engine work only), then 1 (the plugin layer and the
render process), each with its own branch, tests and a check through the real dock.

## Built so far (`feature/fast-products`, his go of 2026-11-09)

| Stage | Before | After | How it was checked |
|---|---|---|---|
| One 0.7 GB raster band | 56.5 s | 7.6 s | compression on every core; the same content |
| The depth drawing | 819.5 s | 162.6 s | blocks on the GPU, overviews on every core; differs only at the faded wet edge (0.002 % of drawn pixels over 1 cm, at most 0.10 m, none inside the wet area: the libraries break ties differently where a dry pixel is equally near two wet ones) |
| The domain mask | 65.9 s | 29.1 s | read in bands on threads; identical (`check_reader.py`) |
| The DEM read | masked float64 arrays and a hole fill on every strip | plain arrays; the fill skipped where nothing needs it | identical windows inside, across and outside the DEM; the shortcut never taken where a terrain object edits a strip with holes |

Tests: terrain, products and tables pass (258), a GPU-against-CPU drawing test added. **Not done:** the full suite on
this branch; the whole remake of Block 2 timed again and its four rasters compared to the digit with the run before;
the smoothed polygons (about 405 s, untouched); the time-slider layer drawn on demand. [Guessing until measured] the
remake from 27 minutes to about 10.

## Finished: the drawing as an option, and the record maps fast (2026-11-13, `feature/products-option`)

**Live. On `feature/products-option` (off `feature/fast-products`), not merged, nothing pushed.** His list of
2026-11-09: the smoothed polygons and the depth drawing as an option, and W50 finished. A stopped worker's WIP commit
was reviewed, kept where it held, tested and recommitted in pieces with the rest.

**[Certain, measured] Block 2's products with the drawing off now take 72 s, from 502 s on the commit before this
branch and 1,624 s on 2026-11-09; the four rasters of record are identical to the 2026-11-09 run's, pixel for pixel.**
All timings below were taken while other work shared the machine (the CPU at 100 % from other processes for most of
the evening), so they are slower than an idle machine would give, the "before" and "after" alike.

### What a run does now

- **`outputs.smooth.enabled` is off by default.** A run writes the four rasters of record, `pixels.json` and
  `pixels/map_layers.gpkg` with the domain outline, subbasins, inflows, boundaries, design lines and reaches. The
  hazard polygons and the 4.3 GB depth drawing are made only when asked.
- **The dock:** a tick in the Run section, "Smooth map polygons and depth picture (slower)", unticked, greyed out when
  the pixel maps are off, written into the job only when ticked.
- **Make map on a run without them has the engine make them first**, from the run's own rasters of record
  (`wadi2d drawings RUN_DIR`), with its progress in the dock, then writes the same three sheets as before; the polygons
  and the picture join the run's layer group, the depth picture taking over from the depth raster. I chose this over
  composing the sheets from the rasters: the hazard sheet is the polygons, so the sheets stay what he has seen, and the
  cost is paid once per run, only when a sheet is wanted. A run made with the tick draws nothing again.
- **The drawing made later is the run's own:** same polygons, same picture, same statistics as a run with the tick
  (tested on the uniform grid and on a mesh); on Block 2 the polygons drawn from the read-back rasters are
  byte-identical to the 2026-11-09 polygons.
- **One change in kind, on a mesh only:** the depth picture there is now drawn from the depth of record (dry under the
  depth floor), as on the uniform grid, where it was drawn from every kept pixel's depth. It is a picture, not a
  number of record.

### Where the time went, and what was done

| Stage, Block 2 at 20 m, remake | 2026-11-09 | Commit before this branch | Now, drawing off | Now, drawing on |
|---|---|---|---|---|
| Start: tables from the cache, domain mask | 73 | 55 | 6 | 5 |
| Ground under the kept cells | 109 | 252 | 11 | 13 |
| Frames at the pixel (GPU) | 4 | 13 | 14 | 15 |
| Rasters of record (+ the layers) | 224 | 182 | 41 | 48 (with the read-back) |
| Polygons | about 405 | | | 342 |
| Depth drawing (GPU) | 804 | | | 258 |
| **Total, s** | **1,624** | **502** | **72** | **681** |

The 2026-11-09 column is `profile/stages.json` (an idle machine, the old code throughout); the other columns are
`timings/stages_*.json` from `time_products.py` (`base_off`, `new2_off`, `new2_on`), the "before" run on
`git archive 8128178` of the engine; "drawing on" includes the boxed polygons below. The same remake before the
polygons were boxed (`new_on`) took 1,094 s, 676 of them polygons and 342 the drawing, under a heavier load: the
load moved between runs, so the box's own gain is read from the six-block bench, not from these two totals.
The remade run folders (`remake/`, 2 to 7 GB each, with their own grid cache) are not in git;
`time_products.py TAG on|off` remakes one from W49's run and `compare_rasters.py TAG` checks it.

- **The domain mask is kept beside the grid cache** (`mask_<key>.npz`, keyed by the DEM, the window, the cell, the
  domain polygon and the table builder's code): 30 to 50 s of every start and remake gone.
- **The ground is read tile by tile on every core.** The step read each strip of tiles whole, from its first to its
  last kept column, on one thread: the whole 0.5 m DEM, and 25 of its 57 strips a second time with a distance-transform
  fill because a kept pixel was a hole. Now only the box of each tile's kept cells is read, one DEM handle per thread;
  a hole takes its nearest good pixel from a margin round the tile, widened until that pixel is provably the one the
  whole strip's fill took (any pixel beyond the margin strictly farther); GDAL's block cache is held at 256 MB while
  they read, because freeing a large cache cost 1.2 s a handle (21 s). `terrain/dem.py` is untouched, since it is
  hashed into every grid cache key. Measured alone: 153 s to 11.6 s, ground identical.
- **The rasters are written window by window over the wet ground** (8 x 8 blocks of 256 pixels, only where a kept cell
  or a strip pixel falls) into sparse GeoTIFFs, so the 17 GB whole band is never made and empty blocks take no room.
- **The polygons work on each class mask's own box** (despeckle, blur and contours), the part of a 4,096-pixel block
  the class occupies. Despeckling and the blur are identical to the last bit by construction (labels join 4-neighbours,
  and past the kernel's reach the blur is exactly zero); the contours move with the box's origin and differ from the
  whole block's in the last bit of a coordinate: on six Block 2 blocks 2.7 x faster, the worst band moved 4.7e-10 m
  (Hausdorff) and its area 2.3e-10 m2 (`bench_polygon_box.py`). On the whole of Block 2 (`compare_polygons.py`,
  `timings/compare_polygons_new_on_new2_on.json`): of 669 bands 485 are byte-identical and 184 moved by at most
  5.4e-9 m, their areas by at most 3.1e-9 m2; the drawn area of every class is the same to the fourth decimal of a km2.
  Float noise, not a change in the map.

### Checked

- **Rasters of record** (`compare_rasters.py`, every pixel of `pixel_depth`, `pixel_speed`, `pixel_dv`,
  `pixel_hazard` against `profile/block2_b20/pixels` of 2026-11-09, made before any W50 change): **identical, maximum
  difference 0**, with the drawing off and on; grids, CRS and nodata the same; 216.6 M wet pixels; files 2 % smaller
  (sparse). Class areas in `pixels.json` identical.
- **Through the real dock** (`dock_smooth_option.py`, QGIS 3.44.8, a throwaway profile, Bidah at 20 m):
  **32 of 32**: the tick unticked and greyed out with the pixel maps off; a run with it off loads its setup, record
  and cell groups with no Flood maps and the depth of record shown; Make map draws first with the drawing's own words
  and bar, then writes the PDF, the rasters of record untouched, the run's engine log untouched; a second Make map
  draws nothing again; a run with the tick on loads Flood maps and Make map needs no engine. Log in
  `log_dock_smooth_option.txt`. The last check was added after a first pass of 31 of 31, which showed the finished
  run's clock on the status line as the drawing started and ended; fixed in the plugin, then 32 of 32.
- **Tests:** new ones for the default, `wadi2d drawings` (equal to a ticked run, uniform grid and mesh, refused with
  no rasters, stopped by the stop file, layers made for an old run), the mask cache, the band writer, `add_layer` on
  a GeoPackage held open, the window painting against the whole band, the tiled ground against the whole strip
  (holes, strip edges, a margin that must grow), the boxed despeckle, blur and contours against the whole array, the
  plugin's tick in the job, `has_record` and `has_drawings`, and the QGIS sheet test in both states.
  `tests/products tests/plugin tests/dock tests/terrain` with `tests/engine/test_io.py` and `test_run.py`: 788
  passed; `tests/plugin` again after the last plugin change: 491 passed. Each of the first three commits was tested
  alone in an exported tree. The full suite is the coordinator's, at the merge.

### Not done, and for his decision

- Whether the drawing should stay off by default: the record maps and the sheets are unaffected either way; a run
  that never presses Make map saves the whole drawing.
- The polygons are still most of a drawing's time on the densest blocks, where a class fills its block; a GPU or
  region-by-region contouring is the next step if he wants the drawing faster.
- The time-slider layer drawn on demand at the pixel (design point 1 above), his go needed.
