# W50 products speed and time slider maps

**Live (2026-11-09). Design on `feature/face-local-radius`; his go the same night; the first speed-ups built on `feature/fast-products` (off it), not merged. Paused at 60 % of the weekly all-models usage, his rule.** His order of the night: the products
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
