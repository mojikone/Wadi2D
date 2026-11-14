# W51 time slider pixel layer

**Live (2026-11-13). Branch `feature/slider-layer` (off `feature/fast-products`), not merged, not pushed.** W50's
design item 1, his go of 2026-11-09: the saved frames on QGIS's Temporal Controller at the terrain pixel, drawn for
what is on screen, RAS Mapper's way, nothing written per frame. The cell slider (W19, `frames.nc`) and the peak maps
stay as they were.

## What was built

**Engine, `wadi2d render <run>`** (`wadi2d/render/`, begun by a stopped worker in `31d85df`, reviewed and finished
here). One process kept open; one JSON line a request on stdin, one JSON head plus raw bytes an answer on stdout
(library chatter is moved to stderr so it cannot land inside a picture). Operations: `values` (float32, NaN or a given
nodata), `image` (BGRA with a caller's ramp), `point` (depth, speed, class at the finest pixel), `stats`, and `lines` /
`line`, which answer what `wadi2d lines` does, so the Result lines panel can later stop starting a process per
hydrograph (1.6 s each); the panel itself is unchanged.

- The pixel rule is the product step's own object (`PixelMaxima`) built on a window of cells with a halo of
  `edge_passes + 2` cells, so a view's pixels equal the whole-domain answer; ground from the same `RasterBed`, pixel
  edits and datum, read in tiles on threads and cached (`outputs.slider.ground_cache_mb`, 2 GB).
- A cell at least `outputs.slider.cell_pixels` (4) screen pixels wide is drawn at the pixel, on the coarsest DEM step
  no coarser than a screen pixel; further out each cell draws its own value (the cell slider's numbers), a screen
  pixel taking the highest of the cells under it.
- Time is not interpolated: the last saved map at or before the slider's time (0.5 s tolerance), and the answer says
  which.
- Ground not read yet: the drawing waits `ground_wait_s` (0.4 s), then draws a coarser ground already held or the
  cells and says how many tiles are still coming; the plugin asks again.
- GPU (CuPy) with the CPU from one source; a GPU out of memory moves the process to the CPU and says so.

**Fixed in the WIP.** The far-out pooling took floor(screen pixel / cell): at 56 m a screen pixel on 20 m cells it
pooled 40 m blocks and skipped every third cell, so a wadi one cell wide could vanish. Now the block is at least a
screen pixel (ceil). The WIP's own test expected that and failed; it was the only one of its 15 that failed.

**Plugin.** A button *Time slider at the pixel* under *Time slider* in the Run section starts the process for the last
run (the Engine choice of the Run section applies), shows what it says while it gets ready, and then adds
*Flood over time, pixels* on top of the run's group and sets the Temporal Controller one step a saved map.

## The mechanism, and why

A **raster layer with a Python data provider** (`slider_layer.py`, provider key `wadi2d_slider`), not a
`QgsPluginLayer`. QGIS asks the provider for one band over the extent and size on screen and passes the controller's
time in the provider's temporal capabilities, so everything else is QGIS's own: the colours are the depth renderer of
record (`style.style_pixel_depth`) and can be restyled; the legend, Identify, the layer's temporal settings, a pan, a
zoom and every controller step work as for any raster; a saved project reopens the layer (the provider registers when
the plugin starts). A plugin layer would have needed its own renderer, its own Identify tool, its own legend and its
own redraw on the slider. A raster layer whose file is swapped would have needed a draw before QGIS's draw on every
pan, and a file written per frame, which is what the design rules out.

Band 1 is depth, 2 speed, 3 the hazard class. The plugin never imports the engine: `render_client.py` starts the
process with the same program, arguments and cleaned environment as every engine command (`protocol.parse_engine`,
`clean_env`, new `render_args`), with no window. It speaks plain pipes behind one lock and not `QProcess`, because QGIS
draws on its own threads and a `QProcess` belongs to the thread that made it. One process a run; it ends when its
input closes, so it never outlives QGIS.

Three QGIS 3.44.8 facts found on the way, each handled in the code:

- A provider copy (`clone`) handed to C++ and not held in Python stops answering, and QGIS draws nothing, without an
  error. The providers are held in Python until QGIS deletes them.
- An exception raised in a provider method called from C++ ends QGIS. Every such method catches what it raises and
  draws nothing, with a line in the message log.
- QGIS's Identify tool moves the clicked point to the centre of the screen pixel under it. The value is the terrain
  pixel at that point, so at a coarse zoom it can be the pixel next to the one clicked.

## Checks

**Unit** (`tests/render`, 23; `tests/plugin/test_render_client.py`, 4; with `tests/plugin` and `tests/products`, 675 tests, exit 0):

- At the native pixel a drawn frame equals the product step's object run over the whole domain on that one frame,
  within 2e-4 m on depth and speed (the fill's own tolerance), on three frames.
- A window inside the domain equals the whole-domain answer.
- With the record's peak made a saved frame, the highest of the drawn frames equals the record rasters at every
  pixel. On the real run no frame stands above the record.
- Far out, cells draw the cell slider's numbers.
- GPU and CPU draw the same: depth and speed within 1e-3 m, classes differing at under 1e-4 of the pixels.
- The protocol: in process, and as the real command on real pipes.
- The result-line operations give what `wadi2d lines` gives.
- A mesh and an aligned-cell run fall back to cells and say so.
- The client asked from nine threads at once.
- A folder with no run fails in words.

**Real dock** (`dock_slider_pixels.py`, a throwaway QGIS 3.44.8 profile under the worktree's `out/`, 39 of 39,
`log_dock_slider_pixels.txt`, pictures in `shots/`). The run: Bidah at 20 m on the 5 m DEM the dock checks use, maps
every 5 minutes, 24 maps, on the GPU. The checks:

- The layer is in, temporal, styled as the record, and the controller reaches the last map.
- The numbers QGIS received equal the engine's renderer run in a separate process: largest difference 0.0 m.
- Whole view, a pan, 3 km and 500 m zooms, and five slider positions were drawn, each showing the last map at or
  before its time.
- All 24 controller steps were drawn as an animation.
- The canvas follows the controller.
- QGIS's Identify tool reads the slider's map at the terrain pixel: 3.4601 m, the engine's own figure.
- No saved map stands above the record.

The canvas of a minimized window draws nothing, so the drawings are QGIS map render jobs on the same settings.

## Redraw times

**Bidah at 20 m, 5 m DEM, GPU, through QGIS** (render job of the layer alone, 1920 x 1080):

| View | First | Again |
|---|---|---|
| Whole domain, cells | 0.058 s | 0.058 s |
| Pan, cells | 0.054 s | 0.054 s |
| 3 km, 5 m pixel | 0.353 s | 0.137 s |
| 500 m, 5 m pixel | 0.154 s | 0.138 s |

Slider steps took 0.128 to 0.139 s. The animation over 24 steps averaged 0.147 s a step, at most 0.172 s. The layer
was ready 2.4 s after the click.

**Block 2 at 20 m** (W49's local-radius run, 2.03 M cells, 6 saved maps, 0.5 m DEM), full screen 1920 x 1080, through
the renderer the process uses (`time_block2.py`, `block2_times.json`):

| View | Backend | Cold | Again | Next map | Pan, cold | Pan, again |
|---|---|---|---|---|---|---|
| Whole block, cells at 40 m a value | GPU | 0.412 | 0.021 | 0.158 | 0.010 | 0.009 |
| Whole block, cells at 40 m a value | CPU | 0.276 | 0.156 | 0.277 | 0.118 | 0.125 |
| A wadi, 3 km, 1.0 m pixel | GPU | 1.015 | 0.092 | 0.139 | 0.196 | 0.073 |
| A wadi, 3 km, 1.0 m pixel | CPU | 0.579 | 0.141 | 0.188 | 0.300 | 0.215 |
| 500 m window, 0.5 m pixel | GPU | 0.227 | 0.078 | 0.121 | 0.085 | 0.066 |
| 500 m window, 0.5 m pixel | CPU | 0.235 | 0.118 | 0.122 | 0.134 | 0.180 |

Times are in seconds. A first run on the GPU, before the cache was warm, gave the same figures within 0.05 s
(`block2_times_first_gpu.json`). Other workers shared the GPU and the CPU throughout, so the times were taken under
shared load.

[Certain, measured] Every drawing of a view already read is under 0.3 s on either backend, and under 0.16 s on the
GPU: the 0.5 s target holds. The exception is the first look at a wadi, about 1 s. That second is reading the 0.5 m
ground. In the layer the wait is capped at 0.4 s, after which the cells show and the pixels follow on the next
redraw. [Likely] The CPU is as fast as the GPU at this size, because the cost is reading frames and ground, not the
arithmetic.

**Opening Block 2 the first time took 322 s.** The grid cache key had changed with this branch's terrain code, so
the tables were built again, as `wadi2d products` does; the process says so while it waits. Opened again: 7.3 to
7.8 s.

## Limits, and what is his to decide

- **A quadtree or an aligned-strip run is drawn one value a cell**, and the dock says so. On a strip run the aligned
  cells are not drawn at all, so the main channel of such a run is blank on this layer; the cell slider shows it. The
  pixel rule on those runs (`MeshMaxima`, `StripMaxima`) on a window is the next piece, not built.
- **The first look at an area of the 0.5 m DEM costs about a second** on Block 2. A ground cache kept with the grid
  cache (W50 item 3) would remove it.
- **Without a time on the canvas, the layer shows the canvas's map, else the last map drawn, else the run's last
  map.** A print layout with temporal settings of its own gets its own time.
- **Not done:**
  - the Result lines panel switched to the open process (only the server side is there);
  - a run on a moved DEM was not tried;
  - it was not clicked in the owner's own QGIS window, only in the throwaway profile.
- The dock check needs the worktree's `.venv`. Here it is a directory junction to the main venv, which git ignores.
