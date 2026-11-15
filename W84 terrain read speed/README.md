# W84 terrain read speed

**Live.** Branch `perf/dem-reads` off `feature/fast-products` (`5c7c285`); not merged, nothing pushed. CPU only; the
GPU was busy.

His order: the fastest stable engine. W81 left the tables bounded by the DEM read, which stopped scaling at about four
threads; W80 and W50 found the same file slow under the products (`GGC_2_MERGE_HDSM.tif`: 131,136 x 128,660 pixels of
0.5 m, float32, LZW in 128-pixel blocks, no overviews, 27.8 GB).

## What limited the read

Measured on windows of 1,857 pixels (a 20 m tile with the local radius's reach at 0.5 m) inside Block 2's data, on a
lattice of 1,280 pixels as the table build reads them (`scripts/bench_read.py`, `bench_fill.py`, `bench_store_read.py`,
`bench_copy.py`, `profile_tables.py`). Other workers' runs shared the CPU, so single numbers are loose; the order is not.

| What | Measured | Verdict |
|---|---|---|
| LZW decode | 15 ns a pixel: 44.5 ms a window on one thread, 5.5 ms on 16 (8 x) with a handle each | no lock in GDAL: raw reads scale; processes gave 4.6 ms, no better |
| The same blocks decoded again | neighbouring tiles overlap (2.1 x the pixels); each thread's handle keeps its own blocks, so the overlap is decoded once per thread; the domain mask, the tables, the strip tables and the products each decode the ground again | the larger half of the decode was repeats |
| The masked read and its conversions (`RasterBed._window`) | `bed.read` 56.5 ms a window against 25 ms for the raw read on one thread; 28 ms with every block already in GDAL's cache | GDAL's mask pass and six to eight temporaries of 14 to 28 MB a window cost more than the decode |
| Closing the threads' handles | on a 10 km window (257 tiles, 16 threads) the tiles took 6.1 s and `build_tables` 11.8 s: 5.7 s freeing GDAL's block cache as the handles close | W50 met the same in the products |
| Memory | the copy alone, float32 to float64 and mask in private memory, no file: 4.5 ms a window on one thread, 2.0 ms a window at 8, 16 and 32 threads | **this is why a read stops scaling near four threads: it moves 76 MB a window and the memory bus is full**; fresh arrays add the system's page faults on top (a store read 15 ms of a thread alone, 76 ms on 16 threads; into arrays used again 8 and 36 ms) |

So: not a lock in the LZW decoder, not one dataset handle. The decode was done several times over, the Python side of
the read cost more than the decode, and under both sits the memory bus.

## What changed

- **A chunk store** (`wadi2d/demstore/chunks.py`): the raster's pixels in raw chunks of 2,048 x 2,048 (16 MB of float32,
  about a square km at 0.5 m), files `r<row>_c<col>.npy` under `<cache folder>/dem_<key>/`. A chunk is read through GDAL
  the first time any window touches it, written under a name of its own, flushed to disk and renamed into place; from
  then on it is mapped, by every thread and every later process. Only the chunks a job touches are made; a chunk with no
  data is an empty `.void` file. The key is the file's name, size and time (its content when small, as the grid cache
  knows a file), its grid and its type. **Nothing is written beside his file, and his file is only read.** What a chunk
  holds is what GDAL gave: the file's values in the file's type, NaN where GDAL's mask says no data.
- **A bed on the store** (`demstore/bed.py`, `StoredBed`): a `RasterBed` whose windows come from the store, with the same
  clipping, the same pixels and the same mask at every stride (a stride takes the pixel at `stride // 2` of every block,
  as GDAL's decimated read does, W80). The conversion is one kernel free of the interpreter lock. A raster with
  overviews keeps GDAL's decimated read, because GDAL answers that from the overviews. Without a cache folder, with
  `WADI2D_DEM_STORE=0`, or on a raster that is not float, it is a plain `RasterBed`.
- **Window arrays used again** (`demstore/scratch.py`): a thread's last window and mask are given out again when nobody
  holds them. That is counted, not assumed: the interpreter's reference count on the arrays, checked at import against
  arrays held the same way with and without a view; a reader that keeps a window, a slice of it or its mask keeps it,
  and the next read takes fresh arrays as before.
- **Wiring**, outside the files a cache key hashes: `prepare_grid` (squares, quadtree, strip tables), the domain mask,
  the products' ground (`products/ground.py`, `step.py`, `mesh.py`) and the time slider's ground (`render/`). The domain
  mask asks for the ground of the cells inside the outline alone (`StoredBed.active_cells`), so a first run decodes what
  its tables then read, once, on every core.
- **The products' pick** (`products/ground.py`): with the read down to a few seconds the ground stage still took 19 s,
  because every tile's pixels were picked with index arrays under the interpreter lock and placed by the calling thread,
  and one strip's slowest tile held the other threads idle. A kernel now writes each cell's pixels into its row of the
  ground array from the reading thread, and four strips of tiles are with the readers at once.

`terrain/dem.py`, `tables/` and `strips/` are untouched.

## Old caches

**Kept valid.** No file under `tables/`, `terrain/`, `grid/`, `strips/`, `breaklines/`, `solver/poly/` or
`solver/layout.py` changed, and no field was added to the job: the hashes in every grid, mask and strip key are the old
ones (`scripts/cache_identity.py`: builder `a669f2175304a984285a6beb`, strip `a9964450baa3797ec3f76200` on `5c7c285` and
here), and the old code loaded tables this branch had built. The store's own code is therefore outside the grid cache
key, as GDAL is: it may only ever return the file's pixels, and `tests/demstore` hold it to that against `RasterBed`.

## Identical numbers

Old code is `5c7c285` (`git archive`, run from its own folder); new is this branch. Compared by SHA-256 of every array
(`scripts/time_tables.py --hash`, `compare_hashes.py`), or byte for byte where the arrays were saved.

| Case | What was compared | Result |
|---|---|---|
| Block 2 whole, squares at 20 m and 0.5 m, 3,605 tiles, 3,509,086 cells, dam crests and spillways | 21 arrays, 1.40 GB: every table and the mask | identical, twice, each on a first run with the store being made |
| Block 2 whole, aligned centre mesh, 2,941,116 squares + 647,042 strip cells | 52 arrays, 2.01 GB: lattice tables, strip tables, strip mesh and geometry | identical, twice, on a made store |
| 6 km round Faydh 01 with its crest and spillway (W81's case), squares | 21 arrays saved and compared with `compare_npz.py` | identical |
| The products' ground, W79's squares run (`run1_full_2d`), 821,602 cells kept | rows, columns and 1,314,563,200 pixels of ground | one SHA-256 from nine runs: old code at 1, 4, 8 and 16 threads, new at the same on a made store, new on a fresh store |
| Cache keys | the old code run on a cache folder this branch had filled | it loaded the tables (a hit): same keys |

Not compared: a whole products remake raster by raster (it needs the GPU, which was busy); the rasters are computed
from the ground array above and the run's saved maps alone. Nor the quadtree's tables on Block 2: they read through
the same bed, whose pixels the tests hold to `RasterBed`'s.

## Times

Block 2, W79's job: 20 m cells on the 0.5 m DEM, 3,605 tiles, 3,509,086 cells. `scripts/run_series.py`, every case in
a fresh process, grid cache emptied before each; all numbers in `series_2026-11-15.txt`. Other workers' runs were on
the machine at times (a rerun of one case moved by up to 15 %), so read the table for its size, not its last digit.
"Store made" is every later start on the same cache folder; "first run" is a fresh cache folder, the store being made.

**Lattice tables (`build_tables`), s**

| Threads (`WADI2D_TABLE_WORKERS`) | Before | After, store made | After, first run |
|---|---|---|---|
| 1 (one reader, the kernels on every core, the path before W81) | 440.0 | 168.3 | 148.7 |
| 4 | 321.0 | 203.4 | 189.0 |
| 8 | 174.9 | 101.9 | 129.0 |
| 16 (the default) | 128.8 | **54.6** | 58.5 |
| 32 | not run | 39.0 | not run |

After, the build goes as the threads go (203, 102, 55 s): it is bounded by the table kernels, no longer by the read.
Peak memory of the process at 16 threads: 9.3 GB working set (11.1 GB committed) before, 4.0 GB (4.5 GB) after; GDAL's
block cache is gone from it.

**Domain mask, s** (it is kept as `mask_<key>.npz`, so this is a first start on a domain)

| Threads | Before | After, first run (this decodes the domain into the store) | After, store made |
|---|---|---|---|
| 1 | 192.4 | 122.9 | 1.4 |
| 4 | 88.5 | 38.1 | 1.8 |
| 8 | 52.0 | 30.6 | 1.9 |
| 16 | 41.9 | 28.6 | 1.3 |

The first run wrote 23.3 GB of chunks in 28.6 s to the scratch disk (C:, the slower of the two NVMe drives): about
0.8 GB/s, the disk and the masked decode (270 to 300 M pixels a second from 8 threads up, `bench_fill.py`) together.

**The whole of `prepare_grid`, squares, 16 threads** (mask, tables, and 22 to 25 s saving the tables): 194.5 s before,
110.9 s on a first run, 80.0 s with the store made.

**Products' ground stage (`read_cells`), s**: W79's squares run, 821,602 cells kept, 1.31 G pixels

| Threads (`READ_WORKERS`) | Before | After, store made |
|---|---|---|
| 1 | 205.0 | 39.1 |
| 4 | 61.0 | 15.0 |
| 8 | 45.6 | 11.5 |
| 16 (the default) | 41.8 | **14.8** (10.2 in another run) |

On a fresh store, 16 threads: 34.5 s. From 4 threads on the stage does not gain: it is at the memory floor of the copy.

**Strip tables, aligned centre mesh, 16 threads** (W81's harness, the mesh of `mask_for_strips` kept in a pickle
between runs: 720 s on one core, the mesher's, not touched here)

| Phase | Before | After, store made |
|---|---|---|
| lattice tables, 2,941,116 cells | 117.5 s | 60.2 s |
| strip tables, 647,042 cells | 200.1 s | **135.7 s** |
| peak working set (committed) | 11.4 GB (13.0 GB) | 6.1 GB (6.6 GB) |

The strip tables gain least: what is left is their own work on each piece, not the read (not profiled further).

## What it costs

- **Disk: 16 MB a square km at 0.5 m.** Block 2's domain (1,404 km2 of cells) makes a store of 23.3 GB in the cache
  folder. The dock gives a project's runs one cache folder; a job run from the command line with no `grid.cache_dir`
  keeps its cache, and so its store, in its own run folder. `source.json` in the store says what it is; deleting the
  folder is safe, it is made again. `WADI2D_DEM_STORE=0` switches the store off.
- **A store is not cleared when the DEM changes**: a changed file gets a new key and a new folder, the old one stays
  until someone deletes it.
- Mapped chunks hold their files open: on Windows a store in use cannot be deleted.

## Findings

- **The tables are bounded by their kernels now.** Block 2 on 16 threads, a quiet machine, the threads' seconds
  (`profile_tables.py`): 448 in the local-radius kernel, 255 in the cell and face tables, 205 in the read, 15 in the
  centre beds; that was before the window arrays were used again, which halves the read's share. On 32 threads the build takes 39.0 s against 54.6 s on
  16: the kernels gain from a core's second thread, where the old read did not (W81 chose 16 for that).
  `TABLE_WORKERS` is in `tables/parallel.py`, a file in every cache key, so it is not changed here.
  `WADI2D_TABLE_WORKERS=32` gives the 39 s today; making it the default is one line and rebuilds every cache once.
  His call.
- **Saving the tables takes 22 to 25 s** of every build, one core of gzip over 1.4 GB (`io/cache.py`): 30 % of a build
  with the store made. Not touched.
- **The aligned mesh reads the DEM twice more, 285 s of its 720 s, and W84 does not reach it.** `read_window` in
  `breaklines/window.py` takes a domain mask of its own through a plain bed (44 s) and `read_coarse`
  (`mesh/streams.py`), GDAL's average of the whole window down to the 5 m analysis pixel on one core (240 s;
  `scripts/time_coarse.py`, measured with tests running beside it). Both files are the mesher's, which another worker
  holds, and both are in the strip cache key. The mask is one line, a bed from `open_bed`. The average is not: GDAL
  sums in an order of its own, and a block mean that differs in the last bit moves the mesh. It needs a kernel proved
  equal to GDAL's on this DEM, or his word that the analysis raster may change in its last place. The edge check and
  the basin delineation read the same way.
- **The strip's pixel ground** (`strips/pixels.py`, the products of an aligned run) still opens a plain bed: one line,
  in a file of the strip cache key. The breach control, result lines, terrain preview and estimate keep plain beds
  too; their reads are small.
- **Processes instead of threads: no gain.** 16 processes read a window in 4.6 ms against 5.5 ms on 16 threads from
  the file, and 4.6 against 4.7 ms from the store. The bound is memory, and processes share it.
- **GDAL's settings do not help.** On a busy machine, raw reads on 16 threads: 7.4 ms a window with the default block
  cache, 6.1 ms with `GDAL_CACHEMAX` 64 MB, 5.8 ms with none; through `bed.read` the cache size changes nothing (19.4
  and 22.4 ms). `GDAL_NUM_THREADS=ALL_CPUS` halves one thread's read (20 against 42 ms) and ruins 16 threads' (43 ms a
  window against 7.4): GDAL's own threads fight the readers.
- **Overviews were not built.** Nothing here could read them and give the same numbers: the mask wants a cell's
  centre pixel, the mesher GDAL's average of the full pixels.
- **A store that has left the system's file cache reads slower, not slowly.** Put out of the cache
  (`evict_store.py`), the whole block's 3,583 windows on 16 threads took 14.7 s against 9.6 s from the cache
  (`bench_store_read.py reuse`), 1.6 GB/s off the scratch disk. Asking the system for a window's rows ahead
  (PrefetchVirtualMemory, `ahead`) gave 12.4 s cold and cost 11.4 s warm: not built. The domain mask from a made store
  took 25.8 s once, right after the series had written and deleted 90 GB of chunks, and 29 s beside a process holding
  83 GB; 1.3 s otherwise. The mask is kept in a file of its own, so that is met only on a new domain or cell size.
- **Chunks kept mapped: 96 is enough.** With 4,096 mapped the threads' read seconds fell by a quarter at 1 m pixels and
  the build by under a second in 23; with 256 nothing changed. Mapping more is address space and working set for
  little.
- **What a read costs now is memory.** A window is float32 in the file and float64 in every reader's hands, twice the
  bytes; readers that took float32 would halve the floor, and that is a change to the kernels.

## Tests

`tests/demstore` (41 tests):

- `test_store.py`: a stored bed against `RasterBed` on an LZW DEM with scattered holes, a patch of holes wider than
  a chunk, a hole border, infinite and absurd values, in chunks of 64 pixels: windows inside, across, past and off the
  raster at strides 1 to 4, filled and unfilled; the active mask at four cell sizes and three strides on snapped and
  unsnapped windows; cells not wanted are not read; a chunk is decoded once and found by the next process; eight
  threads share it and make no chunk twice; a chunk cut short is made again; a changed file gets a new store; no
  cache folder or `WADI2D_DEM_STORE=0` reads through GDAL; a raster with overviews keeps GDAL's decimated read; a dead
  writer's half chunk is cleared.
- `test_scratch.py`: free arrays come again and held ones do not (the array, a slice, the mask alone); a small window
  takes no large one; an interpreter that does not count reuses nothing; windows kept by the reader keep their pixels;
  a used window reads as a fresh one past the edge, over holes and over ground; threads on one bed.
- `test_wiring.py`: `prepare_grid` with a slanted domain outline, both conveyance laws, strides 1 and 2: every table,
  the mask and the cache file names with the store and without; the domain mask reads only under the outline.
- `test_products.py`: the kept cells' ground at the DEM's pixel and at strides 2 and 3, with holes, with the store
  and without; a stop from the tick ends the read.

Targeted suite on the last code: `tests/demstore`, `tables`, `strips`, `products`, `render`, `terrain`, `breaklines`
and the engine's run, io, strip cache, terrain, edge valley, mesh, strip run, breach, earthworks, levels, line check,
review and resume tests: **719 passed** (23 min beside other workers' jobs). The full suite was not run.

## What was kept and what changed

- KEEP: every table, mask and product number; `terrain/dem.py`, `tables/`, `strips/`, `breaklines/`, `mesh/` and the
  job schema, untouched; a run with no cache folder or with `WADI2D_DEM_STORE=0` reads as before.
- CHANGE: `wadi2d/demstore/` (new); `run.py` `prepare_grid` and `domain_mask` (the bed from `open_bed`; the outline
  rasterised before the mask is read); `products/ground.py` (`read_cells` takes the cache folder, `_ThreadBeds` reopens
  the bed it is given, the pick is a kernel and `_picked` is gone, four strips ahead), `products/step.py` and
  `mesh.py` (the cache folder passed on); `render/ground_store.py` and `renderer.py` (the same).
- New on disk: `dem_<key>/` in the cache folder.

## Scripts

`scripts/`: `bench_read.py` and `bench_all.py` (threads, processes, GDAL's cache, the plain and the stored bed),
`bench_fill.py` (what a chunk costs to make), `bench_store_read.py` (mapped chunks, file reads, arrays used again, the
system asked ahead), `bench_copy.py` (the memory floor), `evict_store.py`, `profile_tables.py`, `profile_ground.py`,
`time_tables.py` (W81's harness, with hashes), `time_ground.py`, `time_coarse.py`, `run_series.py` (the tables above),
`compare_npz.py`, `compare_hashes.py`, `cache_identity.py`. The old code for "before" is `git archive 5c7c285 wadi2d`
unpacked beside them, run with `PYTHONPATH` on it. `series_2026-11-15.txt` holds the series' own lines.
