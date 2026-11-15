# W91 pre-solver wait

**Live.** Branch `perf/pre-solver` off `feature/fast-products` (`6408033`), six commits, not merged, not pushed.

His order: the fastest stable engine end to end. W79's Block 2 reruns waited 23 to 35 minutes before the solver's
first step (`W79 .../runs/rerun2_*.log`). **A cold start of W79's run 1 now waits 14.5 minutes where it waited 42,
run 3 9 minutes where it waited 26, with the tables, the strip, the pits, the survey and the resolved job the same
to the digit.** What is left is the strip's mesh: 588 of run 1's 870 s.

## Before and after

A cold build each (`scripts/s01_cold_build.py`): W79's own rerun job, the DEM's chunk store already decoded (as it was
for the reruns), no other cache; the tables on the CPU (16 threads), the run stopped at the solver's first step on
the CPU backend (W79's reruns held the GPU, one of them running throughout). Before is `feature/fast-products` as
it was (`git archive` into `runs/code_before`), after is this branch. Seconds:

| Stage | Run 3 before | Run 3 after | Run 1 before | Run 1 after |
|---|---:|---:|---:|---:|
| Edge check (W78), cold outline | 225 | beside the build | 226 | beside the build |
| First build: strip mesh, tables, save | 487 | 497 | 740 | 704 |
| First build: strip tables | 42 | 21 | 164 | 108 |
| Build with the pit fills: tables | 487 | 11 | 739 | 25 |
| Build with the pit fills: strip | 37 | 2 | 166 | 4 |
| Pits, cell grid, survey | 272 | 3 | 463 | 6 |
| Entries, lines, model set-up | 14 | 13 | 25 | 23 |
| **To the solver's first step** | **1,566** | **547** | **2,522** | **870** |
| Peak commit, GB | (not read) | 9.2 | 11.8 | 9.1 |

Run 3: 16 pits, 1.09 M cells, 100,923 strip cells. Run 1: 31 pits, 2.93 M cells, 189,748 strip cells. The edge
check's 225 s overlap the first build at no measurable cost to it (497 against 487 s on run 3, 704 against 740 on
run 1, within what the GPU run beside them moves); a warm outline reads it from its cache in a second, as W79's
reruns did.

Inside run 1's first build (`scripts/s02_stage_split.py`, `runs/final_run1.stages.json`): **the strip's mesh 588 s**
(the centre generator, W46), the domain mask 1.5 s, the tables of 3,588 tiles 50 s, their save 22 s; the strip's
tables 96 s. Before this branch the build with the pit fills made the mesh again (the fills are in the strip's
cache key), which is most of the 739 s.

## Identical

`scripts/s03_compare.py` on before against after (`runs/compare_*.json`), both runs, the first commits alone
(`after_run*`) and the whole branch (`final_run*`): **every one of the 21 arrays of both grid caches (the job as given
and the job with its fills), every array and field of both strip pickles, the 16 and 31 pits row for row,
`volumes.csv` and `volumes_by_station.csv` byte for byte, and `config.resolved.json` equal.** (W79's session reworded
run 3's job description between the before and after runs; that one text field is left out of the compare.)

Tests, one file at a time under the 10 GB cap (`scripts/s05_tests.ps1`, `runs/tests.log`): 33 files, all pass
(the pit fills, pits, volumes, local radius, parallel tables, strip cache and runs, earthworks on the mesh, terrain,
edge valleys, left-out catchments, strip breaches, the step limiter, the DEM store, every strip test but the GPU one,
every terrain test, `test_run`). New: `tests/engine/test_pit_rebuild.py` (the partial grid build against a whole one
with pits on and across tile edges and tiles left untouched, the same through the cache; a cached base falling back
to a whole build; the pit step handing its rebuild the tables before; the strip kept whole only far from every fill;
the strip's pieces rebuilt against a whole strip build with a crest across it; the geometry's kept areas) and
`tests/terrain/test_survey_boxes.py` (fills, burn lines and an embankment against the old survey, to the digit).

## What was slow, and what changed (one commit each)

1. **The build with the pit fills was a whole second build** (W85): the strip's mesh, every tile, the strip's tables,
   again. Now a build whose fills are still to come keeps its raw face arrays (`RawFaces`: mean bed, the two face
   inverts, the two centre-line beds, five arrays of the grid's size, dropped once the pits are resolved); the build
   with the fills copies the first's slots, builds only the tiles whose pixel window (with the local radius's
   margin) holds a filled pixel, and closes every face on the whole grid as a whole build does
   (`build_tables(base=, only=)`, `wadi2d/engine/pit_rebuild.py`). The strip's mesh is taken from the first build: a
   fill shapes no mesh (its lines are the crests, walls and thalwegs, its floors the raw DEM). A first build read
   from the cache has no raw arrays, and the second build is then whole, as before.
2. **The survey** read the raw GeoTIFF through GDAL, read the whole DEM decimated for `bed.levels()`, and ran every
   object's edit and a whole-tile compare on every tile any object reached; an unshaped object reaches every tile
   within 640 m, and each pit cell is an object. It now reads the chunk store (the tables' pixels), reads the levels
   only for a shaped object, and leaves a fill or a burn line out of the tiles it cannot reach, reading its change in
   its own box. Every other kind still walks every tile any object reaches: its reach is a margin, not a bound, and
   the old numbers depend on that (an embankment's 0.00004 m3 of cut on a tile outside its reach, in the test).
3. **The edge check** on an outline its cache has not seen (a GDAL average of the whole DEM under the domain at 20 m,
   then D8) runs on a thread of its own while the tables are built (`_EdgeCheckBeside` in `run.py`); its events are
   held and written after the first build, in their own order. With tables handed in (a depth-area study's runs) it
   runs where it stood. Its lines now come after the first `grid_cache_saved` in `progress.jsonl`, not before.
4. **The strip's tables after the fills** rebuild only the pieces (W81's squares of 32 cells) whose window holds a
   filled pixel, from the first build's piece tables (`PieceTables`, held on the grid tables, never in the strip
   cache), then join the ghosts from the new grid tables and finish the mesh whole (`build_poly_tables(base=,
   boxes=)`). Pits lie in the wadis, beside the strip, so "is any fill near the strip" was always yes.
5. **The strip geometry measures its rings once**: `areas_centroids`, a Python loop of 18 s on run 1's 190,000 cells,
   was asked four times per strip build; it is kept on the geometry for the bytes of its nodes and rings (an edit in
   place is measured again), handed out as copies, and kept out of the pickle.
6. **The strip's crest faces after the fills** (`faces_from_objects`, about 73 s on run 1) are the first build's: a
   fill is no line.

`run.py`, for the branches beside this one (`feature/hms-dock-and-lumped` edits `run.py` too): `prepare_grid` (a
`base` argument; the strip mesh, tile and strip-piece reuse), `survey_terrain` (a `cache_dir` argument, read through
`open_bed`), `_run` (the rebuild closure takes the tables before; the edge check started before `prepare_grid` and
reported after it), and the new `_EdgeCheckBeside` beside `_edge_streams`. Also `arf.py` (its rebuild lambda),
`engine/pit_step.py`, `tables/builder.py`, `terrain/report.py`, `strips/build.py`, `strips/tables.py`,
`strips/geometry.py`.

## Caches

The code of `tables/`, `terrain/`, `grid/` and `strips/` is hashed into every grid and strip cache key, so **every
cached grid and every cached strip rebuilds once** on this branch, whatever the job (about 12 minutes for run 1).
The DEM chunk stores, domain masks and edge-check caches are kept. A strip pickle holds what it held before.

## Not done

- **The strip's mesh, 588 s of run 1's cold start** (the centre generator): the biggest wait left before the solver,
  paid once per mesh (the strip cache holds it after). Its profile is the next step; nothing here touched the mesher.
- The strip's first tables, 96 to 108 s on run 1: `faces_from_objects` and the pieces; not looked at beyond the
  profile in `runs/after_run1.strip_split.txt` (`scripts/s04_strip_split.py`).
- The edge check's own read could come from the chunk store; it is hidden behind the build, and making it equal to
  GDAL's average to the digit was not tried.
- No GPU run: the solver's first step was taken on the CPU backend, so the model set-up times are the CPU's.

## Files

- `scripts/s01_cold_build.py`: a W79 job's pre-solver stretch, cold, stopped at the solver's first step;
  `--code runs/code_before` runs `feature/fast-products` as it was. `scripts/capped_engine.py`: the engine under W85's
  20 GB commit cap, writing its own peak memory.
- `scripts/s02_stage_split.py`: the first build's stages, each alone. `scripts/s03_compare.py`: before against after,
  to the digit. `scripts/s04_strip_split.py`: a whole strip build under cProfile. `scripts/s05_tests.ps1`: the tests.
- `runs/` (out of git): the logs (each line stamped with the seconds since the start), the result and peak files,
  the caches, the comparisons, `tests.log`.
