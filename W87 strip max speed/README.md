# W87 strip max speed

**Live.** Branch `fix/strip-max-speed` off `feature/fast-products` (`40171b7`); not merged, nothing pushed.

**The record is fixed; the cause behind it is a fault in the step, found, measured and NOT changed: his decision.**
On Faydh 01 that fault moves the dam-axis peak by 0.3 % and leaves the squares' depths alone, but it piles water in
about 1 % of the aligned cells: 99 read a highest level over 1 m too high, the worst 16.5 m against 1.5 m.

## What was found on Block 2

Read from the files of `W79 Block 2 four ways/runs` (`block2_record.py`, nothing rerun; `results/block2_*_record.json`).
Block 2 at 20 m, the aligned centre mesh, 48 h, `u_max` 25 m/s, `speed_depth` 0.05 m.

| Run | Mass error | Aligned cells | Over 10 m/s | Over 25 | Over 100 | Largest | Squares over 10 m/s | Largest square |
|---|---|---|---|---|---|---|---|---|
| 1, full 2D | 9e-10 | 542,980 | 4,846 | 932 | 165 | 1.09e7 m/s | 78 of 2.94 M | 1.08e6 m/s |
| 3, hybrid | 2e-8 | 539,195 | 1,513 | 390 | 93 | 7.32e8 m/s | 47 | 2.68e7 m/s |
| 4, hybrid, 2D routing | 7e-8 | 542,980 | 2,626 | 513 | 102 | 7.60e8 m/s | 46 | 2.58e7 m/s |

- **Not mostly the transition polygons.** Run 1: 2,258 of the 189,406 cells aligned along a line (1.2 %) and 2,588 of
  the 353,574 other polygons (0.7 %) read over 10 m/s. Both groups have a median area of 400 m2: these are not
  slivers.
- **Where the saved maps spike the cell is almost empty.** In run 1, 103 of 192 maps hold an aligned cell over
  10 m/s (1,159 cells in the worst map). In those cells the median mean depth is 0.021 m while the level stands 1.5 m
  above the lowest pixel: a deep notch holding little water. Over the run, cells over 10 m/s hold a mean depth of
  0.08 of their level, against 0.16 for wet aligned cells.
- **The squares over 10 m/s** (run 1, 78): 57 are on a join with the strip, with every square over 25 m/s among them;
  6 are within two cells of a join, 5 of them at one deep pool near 417,700 / 2,733,650 (4 to 7 m deep, 10.8 to
  20.2 m/s, beside the join square that reads 1.08e6 m/s); 14 are
  thin flow in steep hill gullies (1 to 2.5 m deep at the lowest pixel, mean depth 2 to 100 mm, 10.0 to 12.7 m/s,
  under the cap, the squares' own face velocities); 1 is a pit 35 m deep at 433,000 / 2,739,675 (11.8 m/s, in all
  three runs, [Likely] a hole in the DEM as W85 found others). So three quarters of them are the same family as the
  strip's, through the join; the rest are what the squares compute on steep ground and in pits.

## Why the record spiked

[Certain, from the code] The strip recorded the length of the **Perot cell vector** `U`: the cell's momentum from its
face discharges, `sum (xf - c) q`, over the cell's volume `h area`, floored at 1e-9 m3 (`perot_velocity`, `poly_sums`),
wherever the level stood over `speed_depth`. The discharge is the one of the step just taken and the volume is what
that step left, so a cell that gave most of its water away reads a discharge over almost nothing.

The squares never read that. Their speed of record (`wadi2d/engine/maxima.py`) is the mean of the two opposite
**face velocities**, and a face velocity is the kernel's own unknown: momentum over the mean wet section, friction
implicit, capped at `numerics.u_max`, zero on a dry face. The strip had those same face velocities and did not use
them for the record.

## What changed: the record only

The strip's speed of record is now read from its faces' velocities, the squares' rule on a polygon.

- `PolyMesh.speed_weights` (`wadi2d/solver/poly/mesh.py`): per face and side, `(xf - c) L / A` with the outward sign,
  Perot's reconstruction of a cell vector from normal components. It is exact for a uniform velocity on any closed
  polygon, and on a square it is the mean of the two opposite faces, the lattice's rule. The lever arms are differenced
  in double precision before the cast (a float32 holds Block 2's northing to 0.25 m).
- `kernel.cell_speed` (`wadi2d/solver/poly/kernel.py`) and its twin `cell_speed` in `poly.cu`, used by
  `poly_cell_maxima` and the new `poly_cell_speed`: the same sum in the same face order on both backends.
- **A cap** at `kernel.SPEED_CAP` x `numerics.u_max` = sqrt(2) x 25 = 35.4 m/s: what a square's centre reads with its
  four faces at the velocity cap. No polygon can record more than a square can. It bites only where face velocities
  fit no uniform flow on a badly shaped cell (a 50 to 1 sliver would read 50 times the cap).
- Thresholds from the central configuration, unchanged: `outputs.speed_depth` for the maxima, as the squares; the
  saved maps carry no threshold, as the squares' maps carry none.
- Three things read it (`wadi2d/strips/hybrid.py`, `hybrid_gpu.py`): the run maxima `strip_speed` and `strip_hazard`
  (depth x speed), and `strip_speed` in every saved map, which feeds the pixel maps, the time slider and Make map.

Not changed: every step kernel, the join, the time step, the squares' `Maxima`, the depth and discharge maxima, the
checkpoint's names and the map field names.

## Tests

`tests/strips/test_speed_record.py`: on the CPU 6 passed and 1 expected failure (the fault in the step, below); on the
GPU 2 passed (the job below within the cap, and the device reading the CPU's speed to 2e-5 and holding its maxima).

- On a strip of squares the speed of record is the lattice's mean of opposite faces, and reading it writes no state.
- A uniform velocity is read exactly on a square, a pentagon and a 50 to 1 sliver triangle at map coordinates.
- Face velocities no uniform flow could give stop at the cap; a square with four faces at `u_max` reads the cap.
- **The job**: 200 x 96 m at 0.5 m pixels falling 10 %, rough to 0.3 m, a gully 1 m deep weaving 16 m either side of
  a corridor's axis, in and out through its gap triangles; two floods of 3 m3/s over the dry bed. No recorded speed
  above the cap, in the maxima and in 30 saved maps; hazard no more than depth x speed.

Existing tests, one file at a time on the CPU (`-m "not gpu"`), 147 passed in 17 files: `tests/solver/test_poly.py`
(5), `tests/strips/` `test_hybrid` (4), `test_centres` (11), `test_pixels` (5), `test_tables` (6), `test_mesher` (16),
`test_objects` (5), `test_banks` (10), `test_gorge` (7), `test_geometry_precision` (1), `tests/engine/`
`test_strips_run` (13), `test_breach_strips` (6), `test_strip_cache` (2), `test_edge_valleys` (15), `test_io` (11),
`tests/render/test_renderer.py` (16), `tests/products/test_mesh_pixels.py` (14). Their 4 GPU cases and
`tests/strips/test_hybrid_gpu.py` (3) were not run.

## The water is unchanged, to the digit

`run_front.py` runs the test's job on the code before (`feature/fast-products`, exported) and after;
`compare_runs.py` compares (`results/gully_before_after.json`): the line series byte for byte, depth, mean depth and
face discharges of squares and strip in all 30 maps bit for bit, the maxima of depth, mean depth and arrival, 4,241
steps, the books. Identical. The squares' speed and hazard maxima are identical too: the squares' record was not
touched.

| Test job, aligned cells (256, 217 wet) | Before | After |
|---|---|---|
| Largest speed of record | 1.59e7 m/s | 29.6 m/s |
| Cells over 35.4 / 100 m/s | 13 / 6 | 0 / 0 |
| Cells over 10 m/s | 31 | 39 |
| Median over wet cells | 2.78 m/s | 1.79 m/s |
| Largest hazard | 9.16e6 m2/s | 31.0 m2/s |
| Largest in the saved maps | 9.9 m/s | 2.9 m/s |

**Faydh 01 on real ground, the same comparison** (`faydh_job.py`, `faydh_report.py`, `results/faydh_report.json`):
W46's job at 20 m with the aligned centre mesh, 16 h, CPU, 25,226 aligned cells and 162,528 squares, 97,032 steps
either way. Both line series byte for byte, all 16 hourly maps and the depth maxima bit for bit, steps, outflow and
storage identical. The rain total differs in its 16th digit (2.6e-15): the monitor credits each rain window in shares
cut at its progress ticks, which come by the wall clock (`Monitor.settle`), so any two runs sum it in different
pieces. That is in the books' last bit on every run and not from this change.

| Faydh 01, aligned cells (25,226) | Before | After |
|---|---|---|
| Largest speed of record | 150,875 m/s | 30.8 m/s |
| Cells over 35.4 / 100 m/s | 79 / 42 | 0 / 0 |
| Cells over 10 / 25 m/s | 312 / 107 | 110 / 29 |
| Median | 1.71 m/s | 1.84 m/s |
| Largest hazard | 20,898 m2/s | 419 m2/s |
| Largest in the hourly maps | 42,973 m/s | 26.7 m/s |

The squares of this job top at 17.1 m/s, 9 over 10 m/s, before and after alike.

## What the change does not cure: a fault in the step

**The record is now honest, and what it shows is not right yet.** In the test job 39 aligned cells still read over
10 m/s and 16 over 25 m/s, where the same job on squares alone tops at 3.4 m/s. Those are the kernel's own face
velocities, kicked to `u_max`. The brief's premise, that only the record was wrong and not the flow, does not hold.

[Certain, from the code] Two velocities the step itself reads divide a discharge by a vanishing volume:

1. **The join.** After each step the strip writes a velocity into the squares' closed face on the join, for the
   squares' advection stencil: `q / (max(h, 1e-6) dx)`, with `h` the ghost square's mean depth before the step
   (`HybridCpu.after_update`, `poly_edges`). On a front entering a dry square that is 1 m3/s over 2e-5 m2. It is the
   one face velocity in the model with no cap: 33,971 m/s in the test job, 1.08e6 to 2.68e7 m/s on Block 2. The
   squares' speed of record reads it too, which is the 57 squares above.
2. **The cell vector.** `U` as described above, for the strip's cells and for a ghost (`perot_velocity`, `poly_sums`,
   `ghost_rates`). The strip's advection, its friction speed and the crest's energy head read it.

[Likely, shown by test] On a front over a dry join each feeds the other: the join velocity kicks the squares' faces,
their discharges make the ghost's vector, the vector kicks the strip's faces, their discharge makes the next join
velocity. Friction and the `u_max` clamp bound the kicks at 25 m/s; nothing removes them.

`kernel_probe.py` bounds each at `u_max` **in memory, never in the source**, and reruns the test job on the CPU
(`results/gully_kernel_probe.json`). The inflow is a steady 3.000 m3/s; the line crosses the corridor 40 m below it.

| Test job | Line peak, m3/s | Largest aligned speed | Aligned cells over 10 m/s | Largest square speed | Steps |
|---|---|---|---|---|---|
| Squares alone | 3.000 | | | 3.4 m/s | 4,205 |
| Aligned cells, as the step stands | **3.655 (+21.8 %)** | 29.6 m/s | 39 | 33,971 m/s | 4,241 |
| Cell vector bounded | 3.000 | 3.0 m/s | 0 | 9.7 m/s | 4,201 |
| Join velocity bounded | 3.000 | 3.0 m/s | 0 | 8.6 m/s | 4,201 |
| Both bounded | 3.000 | 3.0 m/s | 0 | 9.7 m/s | 4,201 |

- **The water moves.** The books close in every row (mass error under 3e-8): the fault is in momentum, not in volume,
  which is why the mass error never showed it. The line's peak is 22 % over the inflow, and the deepest aligned cell
  reads 1.35 m against 1.04 m.
- **Either bound cures this job**, because either cuts the loop. With the join bounded, the record as it was before
  W87 tops at 8.9 m/s: on this job the cell vector spikes only through the loop.
- **The bound is a diagnosis, not the cure.** With it the squares beside the join still read 8.6 to 9.7 m/s against
  3.4 m/s on squares alone: a join velocity clamped at 25 m/s is still not the velocity of the water.
- The same statements are in `poly.cu` (`poly_edges`, `poly_sums`), so the GPU runs of W79 carry the fault.

**On real ground**, the Faydh 01 job above run a third time with both bounded (`run_bounded.py`):

| Faydh 01 at 20 m | As the step stands | Both bounded | Bounded over as it stands |
|---|---|---|---|
| Dam-axis peak | 1,870.1 m3/s at 12.24 h | 1,876.2 m3/s at 12.24 h | +0.32 % |
| The job's second line (`box_mid`, 540 m east of the axis), peak | 1,875.2 m3/s | 1,866.9 m3/s | -0.45 % |
| Volume through the axis | 9.803 Mm3 | 9.816 Mm3 | +0.13 % |
| Steps | 97,032 | 96,801 | -0.24 % |
| Mass error | 1.1e-8 | 1.2e-8 | |
| Aligned cells over 10 / 25 m/s | 110 / 29 | 2 / 0 | |
| Largest aligned speed | 30.8 m/s | 10.3 m/s | |
| Largest aligned hazard | 419 m2/s | 69.9 m2/s | |
| Deepest aligned cell, level over its lowest pixel | 16.55 m | 11.00 m | |
| Squares, largest speed | 17.08 m/s | 17.10 m/s | |

- **The design discharge barely moves**: 0.3 % at the dam axis, 0.5 % on the second line.
- **The maxima of the aligned cells do.** As the step stands, 260 of the 25,226 aligned cells record a highest level
  more than 0.1 m above the bounded run's, 146 more than 0.5 m, 99 more than 1 m, 22 more than 5 m; 4 read more than
  0.1 m lower. The worst cell reads 16.46 m against 1.52 m, and it is water, not a level on nothing: its largest mean
  depth is 3.32 m against 0.016 m, 1,300 m3 thrown into a 400 m2 cell for a moment. 237 cells hold a largest mean
  depth over 0.05 m above the bounded run's.
- **The squares do not move**: their depth maxima differ by -0.05 to +0.08 m over the whole model.
- So the depth, level, speed and hazard maps of an aligned run carry spikes in about 1 % of its aligned cells, and its
  hydrographs are sound. [Likely] the same on Block 2; not run.

**The time step.** The step search reads face velocities and the wave speed on faces whose upwind level is over
`h_cfl`; it never reads the cell vector, and the join velocity sits on a closed face, which the search skips. So the
artefacts do not enter it directly. They do through the kicks: a face at 25 m/s is read as it is. Test job: 4,241
steps as the step stands against 4,201 bounded, 1.0 % more; Faydh 01: 97,032 against 96,801, 0.24 % more. The step
is not collapsed by them, as W79's reruns showed; W85's holes in the DEM are what set Block 2's step.

**For his decision.** A change to both kernels, CPU and GPU, that moves the water of every aligned-mesh run:
- what the join face should carry: its own strip faces' velocity (bounded by construction), or a clamp at `u_max`;
- how the cell vector is desingularised where the volume vanishes (a clamp at `u_max`, or the Kurganov and Petrova
  form the tile design names in decision 18 c);
- published practice first, his standing order; then the aligned runs whose maps are quoted are rerun (W79's four
  ways).
- **It is not the Faydh race's excess.** The race (W46, W52, W56) was closed as coarse-cell error with this fault
  inside every run. Bounded, the dam-axis peak rises 0.3 %; it does not fall. The excess of the aligned cells over
  the squares at 20 m stands as it was read.

## Not done

- **The GPU twin passed its own two tests and no other GPU test was run.** The card held other sessions' jobs almost
  all through (W86's products runs), and the rule was no second CUDA job. `compile_poly.py` compiled `poly.cu` with
  NVRTC on the host, no device context, while it was busy. The two new GPU tests then ran for 7 s when `nvidia-smi`
  showed no Python job; W86's next products run took the card in the same moment, so the two overlapped. Both
  finished, no driver fault seen. After that the card stayed busy: `tests/strips/test_hybrid_gpu.py` (3) and the GPU
  cases of `tests/engine/test_strips_run.py` (2), `test_breach_strips.py` (1) and `tests/render/test_renderer.py`
  (1) are not run on this branch and must pass before a merge.
- **Block 2 is not rerun.** The W79 runs' strip speed and hazard cannot be repaired from their files: the face
  velocities were not saved. Their strip speed and hazard maps stay wrong until a rerun; depth, level, discharge and
  the dam lines' series are untouched by the record.
- **The squares' record on the join** still reads the join velocity. That is the kernel's number, and it goes with
  the kernel decision.
- The kernel holds face midpoints and centroids as float32 map coordinates: at Block 2's northing a midpoint is
  rounded to 0.25 m, under 1 % on a 20 m cell's vector. Noted, not changed.
- The full suite was not run: the files above only, as the brief said.

## Files

| File | What it is |
|---|---|
| `block2_record.py` | Reads a finished run's record from its files; `results/block2_*_record.json` |
| `run_front.py`, `compare_runs.py` | The test job on the code before and after; water and record compared |
| `kernel_probe.py` | The step's two velocities bounded in memory, the test job rerun |
| `run_bounded.py` | Any job on the CPU with those bounds, for real ground |
| `faydh_job.py`, `faydh_report.py` | Faydh 01's job for the three runs, and their comparison |
| `compile_poly.py` | `poly.cu` through NVRTC with no device |
| `results/` | The JSON behind every number above |
