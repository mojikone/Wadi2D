# W92 centre mesh speed

**Live.** Branch `perf/centre-mesh` off `main` (`69473b1`, v0.4.0); not merged, nothing pushed. CPU only.

His order: the fastest stable engine. After W91 the centre generator (W46) was the largest wait before the solver:
588 of the 870 s of W79 run 1's cold start. **Block 2's aligned mesh (W79 run 1) now takes 87 s against 615 s, run 3
49 s against 433 s, and every array, polygon, note and rule of the mesh is the old code's to the bit.** Peak memory
of the build 7.6 GB working set (9.1 GB committed) to 3.8 GB (4.3 GB).

## Where the time went

`scripts/s01_mesh.py` builds the mesh alone as `prepare_grid` reaches it (the DEM on W79's chunk store, hard-linked
into `runs/cache`, the domain mask from the cache, the left-out catchments, then `mask_for_strips`), with the
mesher's own functions wrapped to sum their seconds; `--profile` adds cProfile. "Before" is `git archive 69473b1
wadi2d` unpacked in `runs/old` and run from there. Seconds; other workers' jobs shared the machine at times (the
same build moved by up to 15 %).

| Stage | Run 1 before | Run 1 after | Run 3 before | Run 3 after |
|---|---|---|---|---|
| The floor rule's ground (`read_window`) | 257.5 | 12.2 | 253.0 | 10.8 |
| of which the second domain mask | 43.4 | 0 | 42.8 | 0 |
| of which GDAL's block average (`read_coarse`) | 213.7 | 12.2 (the store's) | 209.8 | 10.8 |
| Floors of the lines (393 calls) | 0.8 | 0.7 | 0.9 | 0.7 |
| Placing the centres (`place_centres`) | 86.8 | 9.9 | 50.4 | 5.8 |
| Lattice centres | 7.5 | 0.8 | 4.2 | 0.4 |
| Five Voronoi diagrams (`_rings_of`) | 103.7 | 44.7 | 48.6 | 19.7 |
| of which qhull itself | not wrapped | 37.0 | 15.9 | 15.9 |
| Clipping to the domain's edge | 3.7 | 3.4 | 1.8 | 1.9 |
| Short faces merged | 68.1 | 2.6 | 32.6 | 1.3 |
| Areas and centroids | 56.5 | 1.3 | 26.7 | 0.6 |
| The mesh's faces (`from_rings`) | 7.4 | 0.5 | 2.2 | 0.2 |
| **The whole mesh (`mask_for_strips`)** | **615.2** (633.3 on a rerun) | **87.3** | **432.7** | **48.8** |
| Peak working set / committed, GB | 7.6 / 9.1 | 3.8 / 4.3 | 7.6 / 9.1 | 3.9 / 4.3 |

Run 1: 544,221 strip cells, 1,294,606 faces, 569,255 squares replaced. Run 3 (HMS above the dams, left out of the
mesh): 244,938 cells. On a store the domain mask had made and the window's other chunks not yet (`W92_CACHE=cache_fresh`,
as on a job's first start after its grid build) run 1 took 128.4 s, `read_window` 21.9 s, decoding the window's
chunks outside the outline (the store grew from 1,497 to 1,723 chunks with data, 24 to 27 GB, and 534 empty ones).
The Voronoi seconds of that run (52 s against 37) show the machine was shared.

Not measured end to end: a whole cold start of run 1. With the mesh 528 s shorter it should be near 340 to 370 s
against W91's 870 [Likely].

## What changed

1. **The floor rule's ground from the chunk store** (`wadi2d/demstore/coarse.py`, `breaklines/window.py`). The
   mesher's analysis raster is GDAL's average of every 10 x 10 block of 0.5 m pixels over the whole grid window
   (9,360 x 9,768 at 5 m, 36.6 GB of float32): 214 s of GDAL decoding on one core. The same means now come from the
   W84 store on 16 threads, and they are GDAL's to the bit. That took finding how GDAL 3.12 averages
   (`gcore/overview.cpp`, `rasterio.cpp`): a chunk of its own whose mask is all valid takes every pixel times 1/100,
   sums rows, then `100 * (total / 100)`; a chunk holding a masked pixel sums the valid pixels and divides by their
   count. About one block in a hundred is a tie between two float32 values and the two paths round it apart
   (63 of 40,000 on a plain piece), so the store's average reproduces GDAL's chunk partition (output halved until a
   chunk is under 1024 x 1024 DEM pixels, its mask read with one more row and column) and takes each block by the
   path its chunk took. NaN alone is no data, as in GDAL's mask; a value over 1e30 counts and its mean is dropped
   after, as `read_coarse` does. A window past the raster's edge, a non-float raster, a stride or no store: GDAL, as
   before. Mutation check: forcing either path alone fails the tests.
2. **No second domain mask.** `read_window` read the domain mask again through a plain bed (43 s); `prepare_grid`
   hands it the mask it made a moment before (the one before any catchment is left out, as the old read gave) and
   the store's folder, through `mask_for_strips(domain_mask=, cache_dir=)` and `centre_mesh_of`.
3. **The placing walk compiled** (`strips/placing.py`). Beyond each pair, every centre was tested in Python against
   a tree of the higher lines' centres, the active squares and a tree of the line's own centres built anew for every
   centre (90 s of `np.vstack` and `cKDTree`). The same walk in the same order with the same tests, strict and
   closed as before, against centres binned on 40 m squares by the tree's own distance (the square root of the sum
   of the squared differences).
4. **The diagram's rings on whole arrays** (`strips/diagram.py`). Rings, orientation, areas and centroids of all
   rings of one length at once: numpy's sum of a row is its sum of that row as a 1-D array, bit for bit (checked on
   random rows of every length 1 to 39 before use). The merge of short faces, each step depending on the one before,
   runs in its own order compiled (numba's `hypot` checked equal to numpy's on 25 M pairs). The shared faces are made
   only for the diagrams a merge round reads (two of five).
5. **On whole arrays or every core elsewhere**: `MeshGeometry.from_rings` (faces by first appearance from sorted edge
   codes, held to the old dict on random rings and on Block 2's), `resample` (one vectorised GEOS call; Z kept), the
   lattice query (`cKDTree.query(workers=-1)`), each line's outline (a GEOS union per line on its own thread, gathered
   in line order), a line's stations made once for the floor rule and the placing.

**What is not parallel, and why.** The five Voronoi diagrams (qhull, 37 s of the 87) are global and single-threaded:
split by region, qhull's scaling of the paraboloid (`Qbb`) follows the whole point set's bounds and its vertex
arithmetic the facets' history, so the nodes would move in their last bits and the mesh would not be the same mesh.
Each diagram needs the one before it. The placing is in rank order by rule (a lower line gives way to what the
higher ones placed), so it is compiled rather than split. The work that is independent runs on every core: the
ground read (16 threads), the lattice query, the outlines.

## Identical

| Case | Compared | Result |
|---|---|---|
| Block 2 run 1, the aligned mesh | the mask the strip leaves, the replaced squares, corridor and row of every cell, the six geometry arrays, breakline edges, every line's polygon by WKB, notes, rules (`scripts/s02_compare.py`) | identical at every step along the branch and on the final code, store made and store fresh |
| Block 2 run 3 (left-out catchments) | the same | identical |
| Block 2's floor ground | `read_window`'s z (9,360 x 9,768) and inside, against the old code's (`scripts/e03_window_equal.py`) | identical |
| Every mesh the W46 and W52 tests build (16 meshes) | the s01 digest, old generator with its own `geometry.py` and `resample` against the new (`scripts/e06_w46_tests_equal.py`) | identical |
| `from_rings` and `resample` | 300 random ring sets, 800 random lines with and without Z, and Block 2's rings (`scripts/e05_pieces_equal.py`) | identical |
| GDAL's average | a 1,500 x 1,700 raster of float32 ties, holes and infinities, five windows, against `read_coarse` (`tests/demstore/test_coarse.py`) | identical |

## Tests

28 test files the branch reaches, one at a time under a 10 GB cap (`scripts/s03_tests.ps1`, W85's
`capped_pytest.py`): 263 passed, none failed (`runs/tests.txt`): demstore 4, strips 10, breaklines 2, engine 9
(strips run, strip cache, left-out, breaches on the strip, edge valleys, pit rebuild, inflow lines, sleeping run),
solver poly, plugin suggest and breach rows. The full suite was not run.

## Caches

`strips/*.py` and `breaklines/*.py` are hashed into every strip cache key (W81), so **every cached strip, centre or
corridor, rebuilds once on this branch** (on Block 2 run 1 the mesh is now 87 s of that). Grid caches, domain masks
and the DEM store are kept: `run.py` and `demstore/` are outside the keys, and the lattice tables depend on the
strip's cells, which are the same. The store now also holds the chunks of the grid window outside the domain's
outline once the mesh has read them (3 GB more on Block 2).

## Scripts

`s01_mesh.py` (the build alone, stages, peak memory, digests, the mesh pickled), `s02_compare.py` (two runs field by
field), `s03_tests.ps1`, `e01_coarse_equal.py` (store against GDAL on pieces or the whole window), `e02_gdal_order.py`
(the summation variants that found GDAL's paths), `e03_window_equal.py`, `e04_coarse_time.py` (the read's parts),
`e05_pieces_equal.py`, `e06_w46_tests_equal.py`. Runs, the old code and the cache under `runs/` (not in git).
