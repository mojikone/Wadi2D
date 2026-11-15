# W81 tables memory and parallel build

**Live.** Branch `fix/tables-memory-parallel` off `main` (= `feature/fast-products`, `65ef588`); not merged, nothing pushed.

## What was wrong

1. **Strip tables memory.** On Block 2 at 20 m with the aligned centre mesh (`strips.generator: centres`) at the DEM's
   0.5 m pixel, `strip_tables` read one window under every strip at once: 91,457 x 97,537 pixels, 66.5 GiB of float64,
   refused (`W79 .../runs/try3_run1_aligned_memory/progress.jsonl`). W79 ran on with `terrain.pixel_stride` 2.
2. **One core.** The square tiles, the quadtree tiles and the strip cells were built one after another; inside a tile
   the kernels ran on Numba threads over 32 rows, but the DEM read, the terrain edit and the strip's per-cell and
   per-face Python loops ran on one core. W79's aligned run spent 1,493 s in its tables at 1 m pixels.

## What changed

- **Strip pieces** (`wadi2d/strips/tables.py`, `build.py`): the strip's cells are grouped by the square of 32 lattice cells
  their centroid stands in; each piece reads its own window (its rings, its faces and their sampling reach, the local
  radius's 9 x 16 m = 144 m past a face's ends, plus 4 pixels), applies the terrain edit to that window as a square
  tile does, and finds each pixel's owner among every cell whose box reaches the window, in cell order, so a pixel two
  rings claim goes where it went before. Pixel indices are taken on the whole window's origin, so the floors are the
  same arithmetic. The per-cell and per-face loops are one nogil Numba kernel (`_piece_tables`); face lengths stay
  numpy's `hypot`.
- **Threads** (`wadi2d/tables/parallel.py`, `builder.py`, `quad.py`, `core.py`, `strips`): tiles and strip pieces go to a
  thread pool, each thread with its own handle on the raster (`RasterBed.reopen`), the tile kernels as serial nogil twins
  of the same row body (`tile_tables_serial`, `tile_local_radius_serial`); every tile and piece writes only its own
  slots. Workers: `TABLE_WORKERS` = half the logical CPUs (16 here), `WADI2D_TABLE_WORKERS` overrides, 1 is the old
  path (the prange kernels on the calling thread).

- **Strip pixel ground** (`wadi2d/strips/pixels.py`, products' `strip_ground`): it read one float64 window over the whole
  strip extent with a nodata fill over all of it, then took every strip pixel's node weights at once (tens of bytes of
  temporaries per pixel and node); [Likely] why W79's products process held 87 GB. The owners are now found with the
  strip tables' pieces (`owned_pixels`), each piece's window read alone with the edit on it, and the weights a block of
  4 M pixels at a time. The per-pixel arrays the maxima keep (about 76 bytes a pixel) are unchanged: they are the
  product. `wadi2d/products/ground.py` not touched (W80's).
- **Strip cache** (`wadi2d/io/cache.py`, `run.py`): `prepare_grid` built the aligned mesh and the strip tables before it
  looked at the grid cache, on every start and products remake. They are saved as `strip_<key>.pkl` beside the tables
  with the mask they leave; the key is the grid's own key (DEM, window, objects, table settings, strips section, banks
  file), the domain mask, the job's terrain, grid (not the cache folder), breakline and boundary settings and the code
  of `strips`, `breaklines`, `solver/poly`, `tables`, `terrain`, `grid`. A pickle: the cache's own file, read back by
  the same code, refused on any key or format mismatch.

## Identical tables

The old code (`65ef588`) and the new built the same Block 2 window, 6 x 6 km round Faydh 01 at the 0.5 m pixel with
Faydh's crest and spillway, every array saved and compared with `np.array_equal`:

| Case | Arrays | Result |
|---|---|---|
| squares, 101 tiles, 90,601 cells | 20 | identical, at 1 and 16 workers |
| quadtree, 92 tiles (no objects: crests refuse coarse tiles) | 20 | identical, 16 workers |
| aligned centre mesh, 84,002 squares + 7,818 strip cells | 49 (lattice and strip mesh) | identical, at 1 and 16 workers |

Tests: `tests/strips/test_tables.py` (a 45-degree corridor with gap triangles in pieces of 2 cells from a bed with an edit
equals the one-piece build, both conveyance laws), `tests/tables/test_parallel.py` (uniform grid with a burn edit and a
ragged mask, and the quadtree with interface faces, 1 against 4 workers; the bed handles),
`tests/strips/test_pixels.py` (the strip ground in pieces of 2 cells and weight blocks of 1,000 pixels against the old
whole-window owners and one block), `tests/engine/test_strip_cache.py` (a second `prepare_grid` builds no strip and
matches every lattice, mesh and geometry array; a changed corridor misses). Targeted suite after merging `feature/fast-products` (`bdbb7f5`'s wider rings in the strip pixel maps kept): tests/tables, tests/strips, tests/products, the quad, poly and sub-grid solver tests, the strip, breach, mesh-earthworks, terrain and cache engine tests, 374 passed on 8 workers. The full suite was not run.

One limit, as before for the squares: where a window holds nodata pixels, `RasterBed.read` fills them from the nearest
good pixel inside that window, so a piece's fill can differ from the old whole window's near nodata. The strip lies on
active cells; the 6 km case had none.

## Times and memory

CPU only, no solver, a fresh cache folder each time, `prepare_grid` timed by phase (script in the session scratchpad,
`time_tables.py`); peak is the process's peak working set or commit, whichever is higher.

**The 66.5 GiB case, Block 2's W79 job (`run1_full_2d_aligned`), centre mesh at 20 m, `pixel_stride` 1 (0.5 m), 16
workers: built, peak 13.4 GB.**

| Phase | Seconds |
|---|---|
| domain mask | 37.8 |
| centre mesh (`mask_for_strips`, one core, not touched here; now cached) | 732.4 |
| lattice tables, 3,605 tiles, 2,941,116 cells | 129.3 |
| strip tables, 647,042 cells | 226.5 |
| total | 1,164.3 |

Before: refused at the strip window (66.5 GiB); W79 ran at 1 m pixels (stride 2) and spent 1,493 s in its tables on a
machine shared with GPU runs.

**Block 2's squares at 20 m, 0.5 m pixels, the same job without strips (3,605 tiles, 3,509,086 cells), lattice tables:
old code (`65ef588`, its first Numba compile inside, about 20 s) 325.2 s, peak 10.5 GB; new, 16 workers, 138.9 s, peak
11.0 GB: 2.3 x.** The machine was otherwise idle. The tables are bounded by the DEM reads (Findings), not the kernels.

A 10 km window round Faydh 01 at 0.5 m (257 tiles), lattice tables alone, while the W79 products process ran: 29.8 s
on 1 worker, 17.6 s on 16, 20.8 s on 32.

## Findings

- A DEM tile read does not scale past about 4 threads (LZW, 128 x 128 blocks, GDAL 3.12.1): a 1,857-pixel window
  0.049 s on one thread, 0.017 s on 4, 0.018 s on 8; `GDAL_NUM_THREADS=ALL_CPUS` gives one read 0.016 s by itself;
  a smaller `GDAL_CACHEMAX` (64 MB) scaled better (0.012 s on 8). Measured while the W79 products process held 87 GB and
  ran on the CPU, so the numbers are loose. The reads, not the kernels, now bound the build.
- The local radius reads every tile 288 pixels wider on each side at 0.5 m (1,857 against 1,281 pixels), 2.1 x the
  pixels; reading each pixel once is the next saving, not built.
