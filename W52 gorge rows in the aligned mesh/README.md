# W52 gorge rows in the aligned mesh (2026-11-13, branch `feature/gorge-rows`, not merged)

**Live.** The aligned (centre) mesh read a deep narrow gorge high in tight bends with the local hydraulic radius, and
refining did not refine across such a channel, since the bank rule leaves exactly two cells across it (W48, W49).
This iteration diagnoses why, builds rows of narrower 4-sided cells across a channel narrower than the pair (a
`strips` setting, off by default), and tests both. Two defects found on the way are recorded first, because they
change what the rows are worth.

Reference answers (W49, `probe_top_fix`, local radius): synthetic gorge (12 m bed, walls 7 m over 1.5 m, 1 %, n 0.05,
300 m3/s), depth on the axis with 2 m squares: straight 5.325 m, tight sine (radius 243 m) 5.379 m, gentle sine
(radius 729 m) run here. Faydh 01 race (rain on grid, dam axis): 5 m squares 1,796.2 m3/s.

## Finding 1: the cell centroids were wrong by metres on map coordinates (fixed)

[Certain, measured] `MeshGeometry.areas_centroids` and the centre generator's `_areas_centroids` took the shoelace
on UTM coordinates themselves (x about 4e5, y about 2.7e6 m). The products cancel: on the tight-sine centre mesh with
four gorge rows, the centroid error was 0.09 m at the median, 1.7 m at the 99th percentile and 4.1 m at worst, and
0.47 m at the median on cells under 100 m2. The centroid sets every face's centre distance `dn` and skew vector, so a
row cell 3.25 m wide met its neighbour at a `dn` of 0.2 m. The fix takes the shoelace from each ring's first node
(`wadi2d/strips/geometry.py`, `wadi2d/strips/centres.py`; test `tests/strips/test_geometry_precision.py`).

- **This was the broken 5 m centre mesh (W48's finding).** Faydh's main-stem reach at 5 m, refused by the tiling
  guard for 233 m2 (660,857.8 against 660,625.0 m2; reproduced to the m2 with the old centroids), now builds exactly
  (`faydh_mesh5.py`). The relaxation moves the band's centres to centroids, so the wrong centroids moved the diagram.
  On the tight sine the 5 m centre mesh now reads **+0.067 m, +1.5 % water** against the 2 m squares (W48: +0.65 m,
  +59 % on the strips law): the aligned mesh converges, 20 m +0.167, 10 m +0.131, 5 m +0.067 m.
- At 20 and 10 m the fix moves little: tight sine +0.169 to +0.167 m (20 m), +0.120 to +0.131 m (10 m); Faydh's race
  at 20 m 1,865.5 to 1,859.6 m3/s (+3.9 to +3.5 %), at 10 m 1,839.2 to 1,833.3 (+2.4 to +2.1 %); the smallest step grows (0.13 to 0.19 s at 20 m on the sine).
  **It changes every strip run's numbers a little, with the setting off: a default-path change, his to accept.**

## Finding 2: why the pair reads high in a tight bend (diagnosis)

One candidate at a time, at a depth of 5.3 m, on the centre mesh (`pair_tables.py`, `pair_depth.py`,
`step_limit.py`, `mean_face_engine.py`):

| Candidate | Test | Result |
|---|---|---|
| The along-thalweg faces' local-radius window reaching the outer wall in a bend | K per m of the thalweg faces, sine against straight | 1.0007: not it |
| The pair cells' storage tables | water held at the mid-cell bed, sine against straight | 1.002: not it |
| The cross faces cutting the bank obliquely | spoke angle off the true section; spokes shorter than the water | median 0.1 degree, 95 % 2.4; 0 % at 20 m, 2 % at 10 m: not it |
| The cross faces' tables in a bend | area of each spoke face at 5.3 m: table against the DEM read at 0.05 m and against the analytic section | **table 1.4 % small in the sine (34.29 against 34.77 m2), exact on the straight**; K 2.0 % small with the local radius, 1.4 % with the strips sum; normal depth by the tables alone +0.072 m (20 m), +0.074 m (10 m) |
| Two cells across missing the cross-channel redistribution | gorge rows (below) | at 20 m the rows halve the excess; at 10 m they barely move it |

[Certain, measured] **The cross faces' tables under-read a face oblique to the pixel grid.** A polygon face reads its
ground as the higher of the two pixels either side of its line (`face_profile`, `face_line`; the lattice's rule,
where a face lies on a pixel edge). On a face crossing a steep wall at an angle to the grid the two pixels sit at
different distances from the axis, and the higher of two jittered samples puts the wall nearer the axis: the section
reads 1.4 % small. Grid-aligned faces (the straight gorge) are exact. A run with the mean of the two pixels instead
(`mean_face_engine.py`, a diagnosis wrapper; the engine is unchanged):

| Tight sine, against the 2 m squares | Higher of two (engine) | Mean of two (diagnosis) |
|---|---|---|
| Centres 20 m | +0.167 m, +3.5 % water | +0.107 m, +2.2 % |
| Centres 20 m, 2 gorge rows | +0.080 m, +1.7 % | **+0.011 m, +0.3 %** |
| Centres 10 m | +0.131 m, +2.7 % | +0.065 m, +1.4 % |
| Straight, centres 20 m | -0.049 m, +0.01 % | -0.049 m, +0.01 % (unchanged) |

[Likely] So the pair's bend excess has two parts of about equal size at 20 m: the face rule on oblique faces
(0.06 m at every cell size) and two cells across that do not fit the bed (0.07 to 0.09 m at 20 m, little at 10 m).
Why the sign flipped from W49's strips sum (-0.24 m) to the local radius (+0.17 m): the pair's own rise from straight
to tight sine is about the same under both laws (+0.16 / +0.13 m strips, +0.21 / +0.16 m local radius, 20 / 10 m);
what moved is the converged answer's, +0.40 m with the strips sum and +0.05 m with the local radius. [Guessing] With
no wall shear the fine squares concentrate velocity on the outer wall, which adds bend resistance the coarse pair
cannot; with the walls carrying shear that redistribution matters less. Caveat: the 2 m squares read their lattice
faces by the same higher-of-two rule, on walls oblique to the grid, so the converged answer carries some of the same
bias, smaller at 2 m; not measured.

**Not changed: the face rule.** The higher of two is how a face sees a one-pixel ridge (a dyke, a road crest); the
mean would let a thin diagonal ridge leak. A rule unbiased on smooth walls and still watertight for ridges is a
table-builder change for his decision, after the published-practice check his rule of 2026-11-08 asks for.

## The gorge rows (`strips.gorge_rows`, `gorge_wall_m`, `gorge_cell_min_m`; `wadi2d/strips/gorge.py`)

After the centre mesh is made: along each stream's chain of faces, at every vertex of the line, the ground is read on
the DEM's pixels along the two spokes (the faces leaving the line, one per side); the wall on a side is where the
ground first stands `gorge_wall_m` (3 m) above the lower of the two spokes' lowest pixels, two samples running. Where
both walls stand inside the pair's cell along at least three vertices running, the pair cells of that reach are cut
along the flow into rows between the line and the wall, half of `gorge_rows` each side, no narrower than
`gorge_cell_min_m` (2 m), plus one cell beyond each wall holding the rest of the pair's cell. The row count of a reach
is set at the tenth percentile of its wall distances (where a bed is narrower still the cut moves up the wall, so no
row is under the floor); W52's first rule took the minimum, which on the tight sine let one station hold 6 rows to 4
(`runs_count_by_min/`). The line stays a chain of faces, every row cell has four sides, the strip's outline and the
join to the squares do not change, and the area is checked to 1e-6. A cell at a reach's end keeps its place and
carries the cut nodes on its ring (a polygon of 5 to 7 sides, no triangle). Faces between gorge cells keep their own
centre distance down to 0.15 of `gorge_cell_min_m` (the lattice's floor, 0.15 dx, would be 3 m at 20 m), and a face's
inflow edge on a cut edge is its lowest piece (`opposite_drops`, W47's drop). Hard lines get no rows. Off (0) by
default: no code path changes and the cells are today's. The walls are read on the raw DEM, not on the terrain
objects' modified ground [Likely immaterial: objects rarely sit in a gorge's bed].

`gorge_rows: 2` keeps two cells across the bed, fitted to the walls, with the walls in the cells beyond.

## Results (`run_gorges.py`, `gorge_rows.json`; `race_rows.py`, `race/race_rows.json`)

Level on the axis against the 2 m squares (W48's reading: the level 3 m either side of the axis, the median
between 1 and 8 km), and steps against the same mesh with no rows. All with the centroid fix and the local radius.
`gorge_rows` 2, 4, 6 put 1, 2, 3 rows each side between the line and the wall (3 at 20 m on the sine since the
percentile rule; the minimum rule gave 2).

| Gorge, centres | No rows | 2 rows | 4 rows | 6 rows | Steps, 2 / 4 / 6 rows |
|---|---|---|---|---|---|
| Straight, 20 m | -0.049 m | -0.052 | -0.048 | -0.044 | 1.43 / 1.87 / 2.87 x |
| Straight, 10 m | -0.039 m | -0.042 | -0.039 | -0.033 | 1.01 / 1.06 / 1.28 x |
| Gentle sine (729 m), 20 m | +0.071 m | **-0.001** | +0.002 | +0.011 | 1.28 / 1.54 / 2.32 x |
| Gentle sine, 10 m | +0.045 m | +0.017 | +0.017 | +0.023 | 1.28 / 1.53 / 1.67 x |
| Tight sine (243 m), 20 m | +0.167 m | **+0.080** | +0.085 | +0.084 | 1.53 / 2.10 / 3.12 x |
| Tight sine, 10 m | +0.131 m | +0.108 | +0.111 | +0.110 | 1.10 / 1.32 / 1.47 x |

(The straight gorge's -0.04 to -0.05 m is the reading's own offset, W49's too: its depth on the axis is 5.323 to
5.331 m on every mesh against 5.325 m.) The 5 m centre mesh with no rows, for scale: gentle -0.033 m, tight +0.067 m.

| Faydh 01 race, dam axis | No rows | 2 rows | 4 rows | Steps, 2 / 4 rows |
|---|---|---|---|---|
| Centres 20 m | 1,859.6 m3/s, +3.5 % | 1,866.3, +3.9 % | 1,851.8, +3.1 % | 1.61 / 3.04 x |
| Centres 10 m | 1,833.3, +2.1 % | 1,833.4, +2.1 % | 1,832.5, +2.0 % | 1.21 / 1.60 x |
| Centres 20 m, mean-of-two faces (diagnosis) | 1,892.4, +5.4 % | 1,879.5, +4.6 % | | |

Against 1,796.2 m3/s, the 5 m squares (W49). On Faydh the rows cover 1,475 of 2,983 line vertices in 193 reaches
(the main stem 513 of 1,083, rows of 4.7 m median at 20 m).

[Certain, measured] Four things:

1. **The rows fix the synthetic bends at 20 m, and two rows do it.** Two cells across the bed fitted to the walls,
   with the walls in the cells beyond, take the tight sine from +0.167 to +0.080 m and the gentle one from +0.071 to
   -0.001 m; four or six rows add nothing. So the gain is in fitting the cells to the bed, not in more cells across.
   At 10 m the gain is small (tight +0.131 to +0.108 m), and what remains there is mostly the face rule (Finding 2).
2. **They do nothing for the Faydh race**: +3.5, +3.9, +3.1 % at 20 m, +2.1, +2.1, +2.0 % at 10 m. W48 put the race's
   excess in the pair at tight bends of a narrow gorge; the rows mend that construction on the synthetic gorge and the
   race does not move, and the mean-of-two face rule that mends the rest of the synthetic bend makes the race worse
   (+5.4 %). [Likely] The race's excess is not the steady narrow-bend mechanism of W48; its cause is open.
3. **The straight gorge is untouched by the rows** (within 0.006 m), so they add no error of their own.
4. **The cost is the explicit step**: rows 3 to 6 m wide are the narrowest cells of the run, and the strip runs as
   the finest class of the local stepping (W45), so the whole model takes the smaller step. At 20 m, 2 rows cost 1.3
   to 1.6 x the steps, 4 rows 1.5 to 3.0 x, 6 rows 2.3 to 3.1 x; at 10 m 1.0 to 1.3, 1.1 to 1.6 and 1.3 to 1.7 x.

Run times are under shared load (other workers on the GPU and CPU); steps are load-free and are the cost measure.

## Recommendation (his decision)

- **Keep `gorge_rows` at 0 (off).** It mends the synthetic gorge at 20 m and not the race it was built for, at 1.3 to
  3 x the steps. If he wants it for 20 m work in narrow bending gorges, 2 is the setting: 4 and 6 cost more and gain
  nothing.
- **Merge the centroid fix** (Finding 1) on its own: it is a defect, it makes the 5 m centre mesh usable, and it moves
  20 and 10 m results by tenths of a per cent to half a per cent (Faydh's race 20 m +3.9 to +3.5 %, 10 m +2.4 to
  +2.1 %). It changes every strip run's numbers, so it is his call.
- **The face rule on oblique faces** (Finding 2) is the larger lever on the synthetic gorge, but not on the race; a
  research pass before any change, as his rule of 2026-11-08 asks.
- **The race's remaining excess** at 20 m (+3.5 % with the fix) is unexplained; at 10 m the centres read +2.1 %, the
  squares -1.0 % (W49): 10 m stays the size for design lines.

## Tests

`tests/strips/test_gorge.py` (7): the pair cut into two rows each side between the walls with the rest beyond, every
row cell 4-sided, the outline, the area and the line's chain unchanged; the row count limited by the floor on the
width (2, 6 and 12 rows on a narrow bed give 1, 3 and 3 each side); a reach's ends carry the cut nodes with no
triangle; no wall inside the pair (flat ground, or a channel wider than the pair) leaves the geometry object itself
untouched; the setting off by default and even. `tests/strips/test_geometry_precision.py` (1): a 3.25 by 20 m cell
at UTM coordinates has its true area and centroid in both copies of the shoelace (it failed before the fix).
`tests/strips` 64 of 64 (in the combined run, `pytest_strips_solver_tables.log`, stopped after them), `tests/solver` and `tests/tables` without `test_analytic.py` 104 of 104 with the precision test (`pytest_solver_tables_rest.log`), `test_analytic.py`: Stoker and Ritter 6 of 6 and the four still-water cases 4 of 4 (`pytest_analytic.log`, `pytest_analytic_last.log`); the four Thacker cases were still running on the shared CPU when this was written, over an hour each. The analytic cases run on the lattice, which neither change touches. `tests/plugin/test_contract.py` 81 of 81 with the schema sample
regenerated.

## Not done

- The face rule on oblique faces (Finding 2): published practice first, then his go.
- The rows on Block 2 or Bidah through the dock; the dock has no control for them.
- Why the 20 m rows help on the synthetic gorge and not on Faydh's race; what the race's excess is.
- The 5 m centre mesh in the Faydh race (it builds now; not run), and on Block 2.
- The full suite with the centroid fix (only `tests/strips`, `tests/solver`, `tests/tables` and the plugin contract
  were run here).

## Files

Scripts (in git): `gorges.py` (jobs, runs and W48's reading from this worktree), `run_gorges.py`, `race_rows.py`,
`pair_tables.py`, `pair_depth.py`, `step_limit.py`, `mesh5_check.py`, `faydh_mesh5.py`, `mean_face_engine.py`,
`run_mean_face.py`, `read_mean_face.py`. Results: `*.json`, `*.log`. Runs and caches (`runs/`, `race/`, `cache/`,
`runs_centroid_bug/`, `race_centroid_bug/`, `runs_count_by_min/`) stay out of git. `runs_centroid_bug/` and
`race_centroid_bug/` hold the first runs, made before the centroid fix: superseded, kept as the record.
