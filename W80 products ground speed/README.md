# W80 products ground speed

Two fixes found on `W79 Block 2 four ways` (Block 2 at 20 m, aligned centre mesh, `terrain.pixel_stride` 2, dam crest
lines and spillways). Branch `fix/products-ground-speed` off `main`; not merged, nothing pushed. CPU only: the GPU was
busy with W79.

## 1. The products' ground stage: 40 s a strip of tiles

**Cause [Certain, profiled]: GDAL's decimated read.** At `pixel_stride` 2 every window of the kept cells' ground is read
through `RasterBed._window`, a rasterio read with `out_shape` half the window and nearest resampling. GDAL takes that
path pixel by pixel. The DEM (`GGC_2_MERGE_HDSM.tif`, 131,136 x 128,660, LZW, 128 x 128 tiles) has no overviews, so
it reads the same blocks a whole read does and then picks from them slowly. cProfile on strips 20 and 21 put 18.6 of
19.4 s in `_window`, spread over the 16 reading threads. The edited ground was not the cause: crest lines and
spillways make no pixel edit, so the threaded tile reader of W50 ran on every strip. The aligned cells were not the
cause either: the strip's pixels are a separate step with no ground ticks. W50's 72 s was measured at stride 1, where
the decimation never runs.

**Fix:** `wadi2d/products/ground.py` reads the window whole and slices it, `[s // 2 :: s, s // 2 :: s]`, at any stride
above 1 (`_strided_window`). This gives the same pixels: GDAL's nearest decimation by a whole factor takes the pixel at
`s // 2` of each block of `s`. The same clipping and holes are kept. The whole-strip path (terrain objects with a pixel
edit, holes whose fill needs the strip) reads through the same reader (`_read`) with `RasterBed.read`'s own fill.
`terrain/dem.py` is unchanged, because it is hashed into every grid cache key. Stride 1 is untouched.

| Block 2 at 20 m, stride 2, all 74 strips (524,960 cells) | Ground stage |
|---|---|
| Before (main's `ground.py`), this PC with W79's products running beside it | 802.0 s |
| After | 27.0 s |
| In the W79 run itself, before | about 40 s a strip, about 50 min |

**The same numbers:** the whole stage's ground array was compared before against after, 209,984,000 pixels of 524,960
cells, rows, columns, k, pixel and datum: identical to the byte. The rasters are computed from that array and the saved
maps alone, so they are identical by construction. I did not rerun a whole Block 2 products remake and compare its
rasters, because the coordinator forbade it while W79's own remake held 87 GB of RAM. That rerun is the remaining
check.

Before the change, 199 random windows that hold data, at strides 2 to 4 on the Block 2 DEM, read the same through the
decimated read as through the whole read sliced. The decimated read took 6.5 s and the whole read 1.4 s. The test
`tests/products/test_ground_read.py::test_a_strided_window_read_whole_and_sliced_is_gdals_decimated_read` checks the
same at strides 2, 3 and 4 on a DEM with holes: windows inside, across and past the raster, and the filled and unfilled
reads.

## 2. The after-run edge check on aligned meshes

**Cause [Certain]:** W78's pool check, and the older deepest-cell warning it replaces, took the domain edge as every
active cell beside an inactive one. On a strip run the squares an aligned corridor replaced are inactive, so every
square beside a corridor was an edge. That produced 338 false pools on Block 2 (W79 README).

**Fix:** `wadi2d/run.py` `domain_cells(tables)`: the active cells plus the squares the strip replaced
(`tables.strip.strip.masked`). `edge_pools` and `edge_ponding` erode that to find the outline. A run without strips
passes the mask itself, so its result is unchanged.

**Tests** (`tests/engine/test_edge_valleys.py`):
- A grid with a corridor block masked out and deep water either side names no pool, and the outline is still checked.
- A synthetic strip job, a corridor across a rained plane with `edge_depth` 0.001 m, names no pool at its joins. With
  the fix switched off it named one at (400166, 2699954), on a join.
- The W78 tests and the two `edge_ponding` tests still pass.

## 3. Found on the way, not changed

- **Why a products remake of the aligned run holds 87 GB** [Likely, from the code, not measured]. `strip_ground`
  (`wadi2d/strips/pixels.py`) reads one window over the bounding box of the whole strip geometry: on Block 2 that is
  close to the whole block at the 1 m pixel. The window is float64, with the fill's distance transform of the whole
  box, whose index arrays are two int64 values a pixel. Every strip pixel then carries four weights and four
  incidences, plus label and scatter arrays. On squares, W50 reads only tile boxes of kept cells, so it never holds a
  block-wide window. The cure is to read the strip's ground per tile box as the squares do. It is not built here. That
  read is also still GDAL's decimated read at stride 2, so the strip step is slow for the same reason as section 1.
- **Every products remake rebuilds the aligned mesh** [Certain, stack dump]. `prepare_grid` runs `mask_for_strips`,
  meaning the centre generator with its coarse DEM read, and then `strip_tables`, before it looks at the grid cache.
  Only the lattice tables are cached ("seconds", says its comment). On Block 2 the first stack dumps sat in
  `read_coarse` under `centre_mesh_of` for more than 3 minutes, beside W79's process. A remake could read the run's
  own strip from its run folder, or cache the strip beside the grid. Not built.

Scripts: the profiling and comparison scripts were run from the session scratchpad, not kept.
