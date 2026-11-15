# W86 pixel maps speed

**Live (2026-11-15). Branch `perf/pixel-maps` off `feature/fast-products` (`5d902eb`); not merged, nothing pushed.**
His order: the fastest stable engine end to end, press Run to maps ready in QGIS; after the solver, the products are
the largest stage. On the night's Block 2 runs (aligned centre mesh, 20 m cells, 0.5 m pixel, 193 saved maps) the
pixel maps did not finish at all.

## What was wrong

Two faults, one in each half of the step. Both are the same mistake: every saved map was laid over every pixel of
the run at once, so the ground and the maxima of all of them had to be held somewhere at the same time.

**1. The strip (the aligned cells): no pixel raster existed for any aligned run at 0.5 m.** [Certain, measured by the
coordinator on run 3 and read in the code]
- `strip_ground` laid every strip pixel out on the host with 8 node weights and 8 64-bit indices each, 124 bytes a
  pixel. Run 3's strip is 902 million pixels: about 25 minutes on one core with the process's commit rising from 128
  to 240 GB on a 126 GB machine.
- `StripMaxima` then asked the card for the indices alone: one array of 57.75 GB on a 16 GB card. `OutOfMemoryError`,
  the products failed, and other jobs on the machine died with it for lack of memory (one of this session's own).
- The stage reported nothing: after "maps 193 of 193" at 60 % the progress stood still until the failure.
- Even where it fitted, it was slow: its sums are scatter-adds, which on the card are atomic adds from 1,600 threads
  to one address a cell. Measured on the Bidah window: 98 ns a pixel and map. Block 2 would have taken hours.
- [Certain, measured] The same job did not give the same rasters twice on the card. Two remakes of the Bidah window
  with the old code differ on 902,034 of 2,739,200 strip pixels of depth (at most 1.2e-5 m), and 2 pixels are wet in
  one and dry in the other. The atomic adds arrive in a different order each run.

**2. The squares: 8 to 10 s a map on run 1.** [Certain for the cause, from the code's own rule; the time is the run's]
- A square pixel needs its ground and three maxima on the card, 16 bytes. The step kept them there only if all of
  them fitted in 0.8 of the card's free memory. Run 3 keeps 246,016 squares (394 M pixels, 6.3 GB): they fitted,
  and its 193 maps took about 2.5 minutes, 2.4 ns a pixel and map. Run 1 keeps 633,716 squares (1,014 M pixels,
  16.2 GB): they did not fit, so every map carried the ground to the card four times and the maxima there and back,
  about 34 GB a map. 97 maps took 800 s before the machine ran out of memory.
- So the frame count was not the fault, and neither were the strip's cells, ground re-reads from disk or per-frame
  rasters: nothing was written or read from disk per map. What per map cost was the round trip of arrays that did
  not fit.

## What was done

**The rasters' windows are grouped into blocks that fit the device, and a block is finished before the next
begins.** Its ground goes up once, every saved map runs on it there, its maxima come down once, and its windows are
written. Memory follows the block, not the run.

- **The saved maps are read from the run's file once** and held reduced to the cells that take pixels (12 bytes a
  cell and map: 1.8 GB for run 3). A block's maps are a slice of memory. If they would pass 6 GB the file is read
  again for each group of bands.
- **Squares:** a block's kept cells are worked with a halo of `edge_passes` + 2 cells round them, the rule the time
  slider's views already use, so their pixels are those of the whole domain. The arithmetic is the old
  `PixelMaxima`, untouched.
- **Strip:** a block's strip cells are worked with the rings of neighbours their surface reads (`edge_passes` + 1
  through shared nodes, and one more ring for its levels). The ground comes through the same pieces as before, each
  read whole, so a hole's fill and a terrain object's edit give the same pixel. A pixel reads its cell's node slots,
  so the eight 64-bit indices a pixel are gone; the pixel arrays are worked in place. On the card a strip pixel takes
  about 80 bytes where it took 124 on the host and 96 on the card for weights and indices alone.
- **The strip's sums are loops in one order on both backends** (`products/strip_kernels.py`): a cell's pixels from
  first to last, a node's cells by rising number, a pixel's node slots as NumPy sums a row. Numba on the host, CUDA on
  the card, statement for statement, no multiply fused into an add. A cell whose offset has stopped moving takes no
  further Newton step, since the step would be the one it just took, to the bit.
- **The exact size of the rasters is found without reading the strip** (the cells that could reach each edge decide),
  so the files have the old origin and shape.
- **Progress:** the strip's part reports with the maps, block by block; one `pixel_blocks` event says how many
  blocks and how large. A try that runs out of device memory is made again in blocks of half the size, then a
  quarter, before the CPU is asked. `WADI2D_PIXEL_MEMORY_MB` caps a block on a shared card.
- **`wadi2d/strips/pixels.py` is not edited.** Every file under `strips/` is hashed into the strip cache key, so an
  edit there rebuilds every user's aligned mesh once. The old whole-strip functions stay as the reference the tests
  compare against. Removing them is his call.
- **The quadtree's pixel path is as it was.**

**Cell maps (the coordinator's order of the same night, the owner's finding that the wadis were blank).**
`maps/max_depth.tif`, `max_level`, `max_speed`, `hazard` and `max_mean_depth` are written on the lattice, and the
squares a strip replaced are outside its mask. A replaced square now takes the value of the strip cell whose ring
holds its centre (`products/cell_maps.py`). At the end of a run, and by `wadi2d products` on a run made before, in
seconds. A strip keeps no arrival time, so `arrival.tif` stays blank on the strip. A run without a strip writes what
it wrote.

## The same numbers

The check window is the Bidah 03 dam of Block 2 (`s01_window_job.py`: W79's run 1 cut to 3.4 x 3.2 km, 0.5 m pixel,
30 h, 120 saved maps): 6,094 kept squares (9.75 M pixels), 1,638 aligned cells (2.74 M pixels, rings of up to 7
nodes), the dam's crest, dikes and spillway, and its pool. "Old" is the engine at `5d902eb`, exported with
`git archive`. The rasters are 6,440 x 6,840 pixels, 7,646,164 of them wet. `s03_compare.py` compares the four
rasters pixel for pixel; `s05_split.py` says whether a difference is on the strip or on the squares.

| Compared (Bidah window) | Squares, 41.3 M pixels | Strip, 2.74 M pixels |
|---|---|---|
| Old CPU against new CPU | identical, all four rasters | identical, all four rasters |
| Old GPU against new GPU | identical, all four rasters | 915,244 depth pixels differ, at most 1.5e-5 m |
| Old GPU against old GPU, the same job twice | identical | 902,034 depth pixels differ, at most 1.2e-5 m; 2 pixels wet in one only |
| New GPU against new CPU | 4.7 M depth pixels differ, at most 8e-6 m, as old GPU against old CPU | identical, all four rasters |
| New GPU in one block against several blocks | identical | 495,490 depth pixels differ, at most 9.5e-7 m; classes and speed identical |

Read: [Certain] on the CPU the new rasters are the old ones to the digit. On the card the squares are the old
card's to the digit. The strip on the card cannot be compared to the digit with the old card, because the old card
did not agree with itself; it is now the CPU's strip to the digit, and the same twice.

**One thing left that depends on the blocks** [Certain, measured, last row]: the strip's Newton fill, as the old code
wrote it, goes on until every cell of the lot has settled, so a cell that still moves by less than the tolerance can
take one more step in one lot than in another. Cut into several blocks, a strip pixel can differ from the one-block
answer in the last digit of float32 (9.5e-7 m here), no class changed. The cure is to stop each cell on its own
step, as the squares' fill does. It was not taken, because it moves the last digit against the old CPU code. His call.

Tests (`tests/products/`): `test_blocks.py` (one block and many blocks against the step as it was before W86, built
in the test from `PixelMaxima` and the old `strip_pixel_maxima`; the plan of blocks; the retry in smaller blocks),
`test_strip_kernels.py` (the row sum against NumPy's for rings of 4 to 19 nodes, the fill against the old scatter-add
fill, the card's four kernels against the host's to the digit), `test_ground_read.py` (any run of kept cells against
the whole read, holes filled), `test_cell_maps.py`. One existing test was changed, on purpose:
`tests/engine/test_strips_run.py::test_an_inflow_on_the_corridor_enters_the_strip` read "the squares only" off
`max_depth.tif` being blank on the strip; it now reads the squares from the results and checks that the map holds the
corridor.

## Time and memory

All of it measured while other work shared the machine, so read the times as upper figures.

| Bidah window, 120 maps | Old | New |
|---|---|---|
| CPU, whole step | 521.5 s | 135.7 s, peak 1.37 GB of host memory |
| of which the strip | about 340 s | about 10 s |
| GPU, whole step | 37 s | 17 to 19 s, peak 1.9 GB host |
| Strip, one map on the card | 0.270 s | 0.023 s |
| Strip, one map on the host | about 2.8 s | 0.079 s |

**Block 2 whole: run 3 of W79** (hybrid, aligned centre mesh at 20 m, 0.5 m pixel, 192 saved maps and the run's
peaks; 246,016 kept squares, 394 M pixels; 539,195 aligned cells, 902 M pixels). The run's products were remade from
its results on disk (`s02_remake.py`, `runs/block2_run3_gpu*.json`), the card free, with the run's own grid and strip
caches. "Old" is the run's own products stage as the coordinator measured it that night.

| Run 3, Block 2 | Old | New, blocks cut by the card (8) | New, blocks also cut by the host (23) |
|---|---|---|---|
| Outcome | failed, no pixel raster | four rasters, 5.2 GB, 125.5 km2 in classes | the same four rasters, `pixels.json` equal |
| Wall, whole step | 28 min to the failure | 18.2 min | 26.5 min, with other work on the cores for its first third |
| of which | ground 22 s, the squares' maps 2.5 min, the strip's ground 25 min on one core, then the card refused one array of 57.75 GB | saved maps read 29 s, blocks 17.0 min, layers 6 s | saved maps read 32 s, blocks 25.1 min, layers 6 s |
| Peak host memory | 240 GB of commit on a 126 GB machine | 26.8 GB | 20.8 GB |
| Peak on the card | 57.75 GB asked for | 12.0 GB | 12.6 GB |
| Progress while the strip is worked | none | every map of every block | the same |

The first cut held 26.8 GB on the host, over the 20 GB the session was allowed: a block of 113 M strip pixels is
gathered, put in order and written there. A block now also fits 6 GB of host memory (last column,
`HOST_RESULT_BYTES` in `products/blocks.py`): the peak fell to 20.8 GB, less than hoped, because about 10 GB is not
the block's (the tables, the strip, the saved maps, the squares' ground of the one band), and the 23 blocks took 8
minutes longer than the 8, part of it this session's own tests on the cores. That is the shipped setting: the machine
ran out of memory three times that night, and a PC with 32 GB must be able to make these maps. A larger figure buys
back time on his machine; it was not measured. His call.

[Certain] The cell maps of the same remake: 563,991 squares the strip replaced now hold their strip cell's value
(`max_depth.tif` has 3,509,086 cells with a value where it had 2,945,095), and every lattice cell holds what it held.

Not measured: run 1 (rain on every cell: 1,014 M square pixels and 868 M strip pixels). By proportion [Guessing] 25
to 30 minutes on the free card. The squares cost about 2.4 ns a pixel and map there as before (they are the old
arithmetic); the strip cost about 4.5 ns a pixel and map on run 3, which is where the time now is.

**Found in the run's own results, not a fault of this step:** the saved peak speeds hold nonsense at a few cells.
Run 3's `maxima/speed` reaches 2.7e7 m/s (12 lattice cells over 30 m/s) and its strip's 7.3e8 m/s. The pixel speed
and depth x speed rasters and `pixels.json` (`speed_max_ms` 24,048,986) carry it, as the old step would have. The
cure is in the solver's record of the peak, not here.

## Found on the way, not changed

- **A remake from another checkout rebuilds every table.** The grid and strip cache keys hash the bytes of the code
  that builds them. A git worktree checks the same commit out with other line endings than the checkout a run was
  made from (11 files differed here, in line endings alone), so a remake from it misses every cache and builds
  Block 2's tables and aligned mesh again. The same would happen to a release unpacked on another machine. Hashing
  the text and not the bytes cures it, and changes every key once. His call. `s07_engine.py` is the way round it
  used here.
- **Strip cells under 5 cm are all mapped.** The squares leave out a cell whose mean depth never reaches
  `cell_depth`; the strip maps every one of its cells (run 1: 307,744 of 542,980 pass the rule). Giving the strip the
  squares' rule would cut about 40 % of its work, and would blank strip pixels that are over 5 cm in a cell that is
  under it on average. Not done: it changes the rasters.
- **The squares could take the same kind of kernels** as the strip and run several times faster on the card, but
  their sums would then be in the CPU's order and the last digits on the card would move against the old card. Not
  done for that reason. His call.

## Not done

Of the coordinator's later orders of the night: the time-slider file (`frames.nc`) still leaves the strip's cells
out; the on-demand pixel layer (`W51`) still draws a strip run as cell values with the strip blank, and the dock
still loads the mesh file by default; progress in the products' other stages (the layers, the drawing) is as it
was. The full suite was not run: the targeted files only, one at a time, by the session's memory rule.

## Files

- `s01_window_job.py` writes `jobs/window_bidah.json`.
- `s02_remake.py RUN TAG [--engine FOLDER] [--backend] [--memory-mb]` remakes a run's products in `runs/TAG`, timed,
  with the process's own peak memory. `runs/*.json` are its reports.
- `s03_compare.py A B`, `s05_split.py A B` compare rasters. `s04_probe.py RUN` times one map a pixel.
- `s06_plan.py RUN` says how a run would be cut into blocks, without making anything.
- `s07_engine.py THEIRS OUT` makes an engine folder that hits another checkout's caches.
- Scripts that import `wadi2d` are run with `PYTHONPATH` at the checkout that holds this branch.
- `runs/` (rasters, results, the timing reports `runs/*.json`, which hold this PC's paths) and `jobs/` are not in git.
