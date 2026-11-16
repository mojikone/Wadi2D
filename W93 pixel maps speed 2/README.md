# W93 pixel maps speed 2

**Live (2026-11-15). Branch `perf/pixel-maps-2` off `main` (v0.4.0, `69473b1`); not merged, nothing pushed.**
The order: make the pixel maps of full-2D Block 2 runs fast, the rasters identical to the digit against v0.4.0.
W79's stage table had them at 1,624 s for the 2D run (8.4 s a saved map), 1,319 s Hybrid 2D, 855 s Hybrid Lumped.
`W86 pixel maps speed` is the design this builds on (blocks sized to the card, a block's ground up once, every
saved map on it there, the strip's sums in a fixed order).

## The answer

| Block 2, remade from the saved maps on disk (GPU, 193 maps) | v0.4.0 | this branch |
|---|---|---|
| 2D (W79 run 1): the products step, from start to rasters | **1,740 s** | **582 s** |
| of which the saved maps' pixel work (`maps` stage) | 1,547 s | 492 s |
| peak host memory (working set) / card | 19.1 / 12.7 GB | 21.9 / 12.0 GB |
| Hybrid Lumped (W79 run 3): the products step | **822 s** | **265 s** |
| of which the `maps` stage | 727 s | 215 s |
| peak host memory / card | 15.6 / 12.6 GB | 17.4 / 12.5 GB |
| the four rasters and `pixels.json` against v0.4.0 | | **identical, every pixel** (run 1: 1,045,756,555 wet pixels; run 3: 719,492,250) |

Read: [Certain, measured] 3.0 x faster on the 2D run and 3.1 x on Hybrid Lumped, with every raster equal to
v0.4.0's to the bit (`s03_compare.py`, all four rasters and the statistics), and the same on the Bidah window of
W86 (squares, strip cells, the dam's crest, dikes and spillway). **Host memory rose** on the 2D run from 19.1 to
21.9 GB, over the 20 GB asked for: the price of reading the next block and writing the last while the card
works (see below). [Certain] Every figure was measured with another session's mesh jobs on the cores (and, for the
v0.4.0 runs, the cache rebuilt first: 818 s and 428 s, taken out of the 1,740 and 822 above), so read them as upper
figures. Hybrid 2D (W79 run 4) was not remade; it shares run 1's tables and mesh, and by its map count it lies
between the two.

## Where an 8 s map went (v0.4.0, run 1, first 3 of 24 blocks, `s04_profile.py`, the card synchronised round each part)

| Part | s, 3 blocks | per block |
|---|---|---|
| squares' ground for the band (one read of 12 blocks' cells) | 140.5 | |
| strip block's pixels, ground and Wachspress weights (host) | 76.9 | 25.6 |
| squares on the card, 194 maps | 56.3 | 18.8 |
| strip on the card, 194 maps | 31.1 | 10.4 |
| saved maps read from `results.h5` (squares 31.0, strip 14.9, once) | 45.9 | |
| writing the block's windows | 20.8 | 6.9 |

[Certain] So the time was not on the card: more than half was host work done one thing after another, with the
card idle meanwhile (50 % busy over the maps stage). Inside the card's share the Newton fill was most of it
(squares: the three edge passes' fills and the final fill 49 of 55 s; strip: the fills 16 of 31 s).

- **The squares' ground took 140 s a band** because every terrain object (Block 2's run 1 has its 31 pit fills as
  `fill` objects) sends every strip of tiles down the whole-strip read, and that path ran on one thread.
- **The strip's Wachspress weights** were a dozen NumPy array operations over runs of 4 M pixels, one core: 12 to
  25 s a block.
- Frames that raise no maximum were not the cost: the brief's first candidate. A cell's maps can be ruled out only
  after its offsets are known (they come from the three edge passes of its neighbours), so skipping the final
  fill saves the smallest part; it is in, and saves what it can.

## What was done (each its own commit, each identical to the bit)

1. **Squares' Newton fill on the card in one kernel a step** (`products/fill_kernels.py`). The old step was five
   array operations over the moving cells' pixels plus a copy of those cells as others stopped. First the masked
   gaps and the count in one kernel with CuPy's own sum after it (the same array, so the same sum), then, where it
   checks out, the sum in the kernel too, in the order CUB's segmented sum adds a row of one tile; then the whole
   step (sum, step, offset, whether the cell goes on) in one kernel over every cell, the stopped ones left alone, a
   look at the card every third step. **The in-kernel sum is used for a cell size only after a check on the card
   against CuPy's own sum gives the same bits**; on this card and CuPy 14.2 rows of 1,024 to 4,095 pixels agree
   (Block 2's 20 m cells at 0.5 m are 1,600), 7 to 400 do not and keep CuPy's sum. A batch whose cells are all wet
   uses its arrays in place, no gather or scatter.
2. **The strip's sums a warp to a cell** (`products/strip_kernels.py`): the pixels read side by side, added by every
   lane in the pixels' order, so the one-thread sum to the digit (tested on cells of 0 to 2,000 pixels). On a
   synthetic block it is no faster than the thread kernel (0.47 against 0.43 ms a step): the cache had covered the
   scattered reads. Kept, harmless; the gain on the strip came from the look every third step.
3. **A map's square cell is not filled where it cannot raise a pixel** (`may_raise`): the fill walks down from the
   offset where every pixel is wet, so no pixel is deeper than that start over the ground, and a pixel's speed is
   never over its corners' largest; where those bounds (margins of 0.1 % and 1 mm, far over float32's rounding)
   stand under every pixel's held maxima the final fill, speed and maxima are skipped. The corner products stay
   cuBLAS's over every wet cell of the batch, so the cells filled keep their digits.
4. **Two lanes beside the card** (`products/step.py`): the next block's ground and strip pixels are read on one
   thread, the last block's windows written on another, the four rasters of a block on four threads, each its own
   file in the same window order; the first band's ground is read while the saved maps are.
5. **The whole-strip read on the reading threads** (`products/ground.py`), two strips at a time, each on its
   thread's own handle and through the same window as before.
6. **The Wachspress weights in one compiled pass a pixel** (`products/strip_weights.py`): NumPy's steps in float64
   one for one, the row's sum as NumPy's pairwise sum adds a row (tested to the digit on rings of 3 to 12 nodes).
   25.6 s a block to 0.5 s. `strips/pixels.py` is not edited (every file of `strips/` is hashed into the strip
   cache key, W86).

After all six, a block of run 1 is about 11 s of squares and 11 s of strip on the card, the lanes keeping up
(their reads 5 s and writes 6 s a block). The card is busy about 60 % of the maps stage: what is left is the
fills' look-and-launch rhythm and the cell-level steps in Python between them.

## Found on the way

- **[Certain] On the card the squares' last digits depend on how a run is cut into blocks.** The corner products
  are cuBLAS matrix products, and cuBLAS picks another kernel for a product of fewer than about 100 rows (tested:
  31 rows and fewer give other bits than the same rows inside 40,000; 100 rows and more give the same). A block or
  batch with few wet cells therefore differs in the last digit from the same cells in a larger one. W86's "blocks
  identical to one block" was tested on the CPU. Not changed: it is how v0.4.0 computes, and every change here keeps
  the products on the same rows. A test now compares like cuts with like (`test_cells_a_map_cannot_raise_...`).
- **The host memory.** The lanes hold the next block's inputs and the last block's results beside the current
  block. Cut from 28.4 GB (first try) by reading two strips whole at once instead of four, freeing a block's host
  copies once they are on the card and reading the next band only once the band before has let its ground go; still
  21.9 GB on run 1 at its peak. Lower would need smaller blocks, and a different cut of blocks moves the
  squares' last digits (the finding above), so the plan of blocks was left as v0.4.0 makes it. His call: 20 GB with
  the lanes off (as v0.4.0, slower) or this.
- A remake of a v0.4.0 run rebuilds its tables once: the run's caches were made by the code before W91, and the
  cache keys hash the builders (W86's note). 818 s on run 1, 428 s on run 3.

## Tests

New: `tests/products/test_fill_kernels.py` (the card's fill against the old steps to the digit, 1 to 4,000 cells,
7 to 40 pixels a side; the host's unchanged), `tests/products/test_strip_weights.py`, in
`tests/products/test_strip_kernels.py` the warp kernels against the thread kernels, in `tests/products/test_blocks.py`
the skip on and off in one block and in many. Run one file at a time on this branch, the card free: every file of `tests/products` (216 passed), `tests/render` (23) and `tests/engine/test_strips_run.py` (15). The full suite was not run.

## Files

- `s02_remake.py RUN TAG --engine FOLDER --backend gpu` remakes a run's products in `runs/TAG`, timed, the peak
  working set, a 2 s memory trace in `runs/TAG.log` and the card's mean busy share over the maps stage.
- `s03_compare.py A B` compares the four rasters pixel for pixel and `pixels.json`.
- `s04_profile.py RUN OUT [--blocks N] [--light]` times the parts of the step (with `--light` only the block parts
  and the main thread's waits). Run with the engine folder as the working directory.
- `s07_engine.py THEIRS OUT`: an engine folder with the main checkout's package byte for byte and this branch's
  product files over it, so a remake hits the run's caches.
- `runs/` (rasters, reports `runs/*.json`, logs, the frozen v0.4.0 engine `runs/engine_base`) is not in git.
