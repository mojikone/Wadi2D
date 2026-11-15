# W85 what limits the time step

**Live (2026-11-15).** Branch `perf/step-limiter` off `feature/fast-products` (`a119503`), not merged, not pushed.
Everything here ran on the CPU: the GPU carried W79's reruns the whole time. Nothing in this folder is a GPU timing.

## What was asked

Block 2's 200-yr full 2D run at 20 m (`W79 Block 2 four ways/runs/run1_full_2d`, 3.5 M cells, 715,457 steps, 1,956 s
of loop) steps at 0.196 s from hour 20 to hour 48, on the squares and on the aligned mesh alike. At a Courant number
of 0.45 on 20 m cells that is a wave speed of 46 m/s, which no flood has. Find what sets the step, whether it is
legitimate, what the step would be without it, and what can be done.

## The answer

**One hole in the DEM sets the step for 35 of the 48 hours.** [Certain, read from the run's own frames and
reproduced through the engine on a window]

- **Where:** x 414,791, y 2,722,485, at 1,188 m in the western mountains, at the foot of a cliff. A closed sink
  14.5 m by 33 m in plan (304 m2) whose lowest pixel is 1,064.5 m: **123 m deep**, 12,870 m3 below its spill level of
  1,187.8 m. Depth 7 times its width: [Likely] a blunder of the terrain model and not ground; not checked on
  imagery (`ground/ground_pit.png`).
- **What happens:** rain fills it 40.7 m deep by hour 24 (about 700 m3; it never spills). The hole lies across the
  face between two cells: the west cell is wet over 2.3 % of its plan, the east one over 5.5 %, and the face between
  them has 94 m2 under water. The step rule reads the gravity wave from the face area over the smaller wet plan share,
  g x 94 / (0.023 x 20 m), a hydraulic depth of **205 m** where the water is 25 to 40 m deep: 44.8 to 46.1 m/s,
  **0.195 s**.
- **How many:** three cells hold the hole's water; one face leads. Next in line are three single cells, [Likely]
  blunders too: a 13 m hole against the wall of a building that the DEM keeps (x 438,521, y 2,739,036;
  `ground/ground_second.png`), and two clusters of a dozen low pixels (432,961 / 2,740,036, 4 m below a flat patch at
  94.45 m that reads as a water surface, `ground/ground_third.png`; 451,501 / 2,721,316).
- **The step without them** (the run's last frame): 0.195 s as run; **0.307 s** without the hole; **0.423 s** without
  the four, where the legitimate limit takes over: Faydh 01's pool, 46.6 m deep at the dam (7.1 Mm3, 769 cells deeper
  than 15 m), sqrt(g x 46.6) = 21.4 m/s, and a 45 m deep pond of 43 cells at 432,961 / 2,739,616 with the same
  number. At the flood peak (hours 12 to 13) the flood itself asks for 0.23 to 0.33 s, 116 cells under 0.40 s at
  hour 12: the cells that lead there hold 6 to 14 m of water moving at 4 to 13 m/s and read 17 to 29 m/s of celerity,
  so [Likely] the same rule at work on real ground, a gorge cell beside a wall cell wet over a sliver.
- **Steps over the 48 h**, the run's own step scaled by each frame's ratio (`frames_run1/steps_without.csv`):

| | Steps | Of the run's | Loop on the GPU at the run's 2.73 ms a step |
|---|---|---|---|
| As run | 705,917 (the run counted 715,457) | 1.000 | 1,956 s |
| Without the hole | 487,733 | 0.691 | about 1,350 s, 10 min less |
| Without the four cells | 385,727 | 0.546 | about 1,070 s, 15 min less |
| `numerics.plan_min` 0.05, terrain as it is | 495,018 | 0.701 | about 1,370 s |
| `numerics.plan_min` 0.10, terrain as it is | 373,979 | 0.530 | about 1,040 s |
| `numerics.plan_min` 0.25, terrain as it is | 352,361 | 0.499 | about 980 s |

  The loop times are the step counts times the run's cost per step: [Likely], not measured. The three `plan_min`
  rows are what the frames would allow, and the window test below rejects them: the pit does not survive a raised
  floor. The aligned run (702,373 steps, 2,711 s of loop) reads 0.1965 s through its recession: [Likely] the same
  hole, which lies on a hillside of squares, so the same shares apply to it. Its frames were not read.

**The rule is legitimate; the terrain is not.** The fix published practice supports is to mend the terrain at the cell
the diagnostic names. Nothing was changed in a kernel.

## How the step is chosen

- `wadi2d/solver/stepper.py`: every `numerics.dt_every` (8) steps, `dt = cfl x dx / max(w, wave_floor)`, capped at
  `dt_max`; `w` is the largest wave speed any face reported in that step. `cfl` 0.45, `wave_floor` 3 m/s, so dry
  ground steps at 3 s on 20 m cells.
- `face_step` in `wadi2d/solver/cpu/kernels.py` and `gpu/kernels/faces.cu` (the same statements): a face reports
  `|u| + min(lead x |u_new - u|, 2c) + c`, with `c = sqrt(g x A x rho / (max(plan, plan_min) x dx))`. `A` is the
  face's flow area, `plan` the wet share of the upwind cell's plan, or the smaller of the two cells' when both stand
  above `h_cfl` (0.01 m); `plan_min` is 0.02. A face whose upwind cell is under `h_cfl` reports nothing.
- So thin cells are out of the search, as decision 18(c) asks, and the velocity is capped at `u_max`. **The hole is not
  a thin cell.** It is deep water on a sliver of two cells behind a large face, and the rule multiplies that.

## Is the rule legitimate

[Likely: my own linear analysis of the scheme, from no paper; the window runs below test it] On the staggered scheme a face of area `A`
between two cells of wet plan area `S1` and `S2` a distance `dx` apart has an exchange mode of frequency
`w2 = g A (1/S1 + 1/S2) / dx`, and the explicit update is stable for `w dt <= 2`. That is the scheme's own limit, and
on a uniform flooded grid it is the familiar `dt <= dx / (sqrt(2) c)`, which is why `cfl` is capped at 0.7. The
kernel's `c` is this limit written as a wave speed, with the smaller storage standing for both: it keeps
`w dt <= sqrt(2) x cfl` on a single stiff face and `w dt <= 2 x cfl` when all four faces of a sliver cell are stiff.
So **the storage term is not a bug and not an artefact of the rule**: water 40 m deep in 9 m2 of one cell and 22 m2 of
the next, joined through 94 m2, does slosh at 2.7 rad/s on this scheme, and a step over 0.75 s would break it.

**And the linear limit is not the whole of it.** For one stiff pair the rule stands 3.1 to 4.4 times inside that limit
(3.7 at the hole: 0.20 s against 0.75 s), which reads like room to spare. It is not: the window runs below break at
0.28 to 0.35 s, under half the linear limit. [Likely] why: a face's momentum is carried on the mean depth of its two cells (14 m2
here) while its discharge is taken on the face area (95 m2), so in a sliver cell momentum is advected 7 times faster
than the face velocity, and the three cells of the pit share faces. The margin in the rule is paying for that. **A
mistake of mine on record:** from the linear figure I expected `plan_min` 0.10 to be safe at the hole and wrote it up
as the cheap fix before the window run came back; the run says otherwise and the run stands.

## Published practice

- **TUFLOW HPC** (explicit; decision 19 took its scheme as the model for these kernels): the step is the smallest of three control numbers,
  Courant, shallow-wave celerity and diffusion; it writes a minimum-dt map "to identify the specific location that is
  requiring the minimum timestep", and its manual reads an excessively small step as a symptom of "input topography or
  boundary condition errors": the modeller mends the input at that cell. No rule skips or softens the cell.
  [Likely exact: the TUFLOW Classic/HPC manual 2025.2, section 16.1.2, and the wiki page HPC Adaptive Timestepping,
  both read through a page summary and not by eye. Which depth the celerity number reads under sub-grid sampling is
  not documented there.]
- **HEC-RAS 2D**: implicit, so no gravity-wave limit; the step is chosen or adapted on the velocity Courant number, and
  a hole only stores water. [Likely, from HEC's guidance as summarised in practitioner notes, not from the manual
  itself.] It has no treatment to borrow: its answer is the implicit solve.
- **SFINCS** (explicit, sub-grid): a Courant step on the water depth with a factor `alpha` of 0.5, and since v2.2 a
  "wiggle suppression" limiter on the flux where the water level accelerates hard and oppositely in two neighbours,
  sub-grid mode only. [Likely, from its parameter documentation; the source was not read.] That is a published limiter
  on this two-cell mode, in a local-inertial code; nothing like it is in a full-momentum flood code that I found.

So published practice backs two things, both built or shown here: **a reading of which cell sets the step**, and
**mending the terrain there**. It backs no change to the kernel's rule, and none was made.

## The step through the engine, on a window

`scripts/s05_window.py`: 1.2 km square round the hole on the W79 lattice (60 by 60 cells of 20 m), W79's storm, losses
and roughness, every edge a free outfall, 30 h, CPU, `outputs.step_limiter: layer`. The pit is mended in a copy of the
DEM window (`filled`: the sink filled to its spill level, 305 m2 raised, nothing else touched) and with a tool the dock
has (`bank`: an embankment object over the sink, top at 1,187.84 m).

| Variant | Steps in 30 h | Of the base | Step at 12 / 18 / 24 / 30 h, s | The pit's water after the rain (hours 24 to 30) |
|---|---|---|---|---|
| `base`, as W79 ran it | 332,919 | 1.000 | 0.286 / 0.226 / 0.200 / 0.199 | at rest: 40.5 m deep, level 1,105.04 m in both cells, no jump over 0.11 m between samples 10 s apart |
| `filled`, the sink filled in the DEM copy | 101,749 | 0.306 | 0.747 / 0.837 / 0.861 / 0.818 | no pit |
| `bank`, an embankment object over the sink | 101,804 | 0.306 | 0.701 / 0.857 / 0.836 / 0.821 | no pit; stored and outflow volumes equal `filled` to the cubic metre |
| `plan10`, `plan_min` 0.10 | 206,991 | 0.622 | 0.348 / 0.348 / 0.283 / 0.348 | **never rests**: 80 % of samples jump over 1 m, the largest 46 m |
| `plan25`, `plan_min` 0.25 | 170,649 | 0.513 | 0.500 / 0.420 / 0.329 / 0.630 | never rests: 88 %, the largest 51 m |
| `plan100`, `plan_min` 1.0 | 100,989 | 0.303 | 1.106 / 0.452 / 1.263 / 1.704 | never rests: 86 %, the largest 51 m; balance error 2.8e-7 against 4e-10 |
| `lts`, local time stepping | 340,249 | 1.022 | 0.281 / 0.222 / 0.200 / 0.199 | as `base`; all four tiles step together (they are the pit tile's neighbours), so this window cannot show its gain |

Read from `window/window_table.json` (`scripts/s07_window_table.py`), four CPU threads.

- **The engine names the hole itself.** `base` ends with: "one cell set the time step at 130 of 141 progress events:
  (414781, 2722476), water 25.9 m deep over 2.3 % of the cell beside a face with 96 m2 under water, which the step
  rule reads as 207 m of depth: a step of 0.199 s where the next tile would give 0.823 s."
- **Mended, the window takes 0.31 of the steps**, by either route. The pit held 694 m3 of the window's 198,810 m3 of
  runoff back (0.35 %); nothing else moves.
- **Raising `plan_min` is not a fix.** With the floor at 0.10 the two cells of the pit throw their water back and forth
  for the rest of the run, 15 to 45 m of level between samples, in water that the default brings to rest. The window's
  outflow moves by 4 to 16 m3 of 194,968, so the damage stays in the pit here; nothing says it would in a sliver cell
  with a flood through it. The frames' promise for it (0.53 of the steps) is therefore not on offer.
- During the storm the pit is not quiet under the default either: 16 % of samples between hours 12 and 24 jump over
  1 m, the largest 7.4 m, while runoff falls in. It settles when the rain stops.

## What was built

1. **`outputs.step_limiter`** (`off` by default, `progress`, `layer`), commit `790f92d`. At every progress event a
   `limiter` line beside the `step` line: the cell (x, y, row, column), its depth, mean depth, wet share, bed and
   water level, the face's speed, the three parts of the kernel's sum, the hydraulic depth and face area the rule read,
   the step it gives and **the step without its tile**. `layer` also writes `step_limiter.gpkg`, one point per cell
   named, with how often and when it led. One source for both backends (`wadi2d/solver/limiter.py`): the leading
   tile's block is copied to the host and the CPU twin's own `face_step` reads it, so there is no second copy of the
   rule and no kernel changed. The water is unchanged to the digit and the job hash is unchanged (tests). On a
   quadtree the faces inside a tile are read at the tile's cell size, interface faces are not; a strip that leads is
   named, not located.
2. **A warning in words** at the end of such a run (commits `1a7743d`, `1df2586`) when one cell led half the progress
   events or more, the hydraulic depth the rule read is three times the water's own depth, and the next tile would
   step half as long again: where, what the rule read, the two steps, "a hole in the DEM reads like this".
3. Tests: `tests/solver/test_limiter.py` (10, of which 3 on the GPU), `tests/engine/test_step_limiter.py` (5); the
   frozen schema sample takes the one new field.

Not in the dock: `step_limiter` is a job field only. By his rule it is not a finished feature until a dock control
sets it and the layer loads there.

## A fault of this session, and the builder fix it led to

**My first targeted test run took the machine down to 0 GB free and made the owner's Block 2 products run fail**
("Unable to allocate 191 MiB"). I had started `tests/solver` whole, in the background, with no limit. The coordinator
stopped it at 325 GB of commit.

- **What allocated it:** not the limiter. `test_thacker_moving_shoreline` builds tables for 2 cm cells on 5 mm pixels.
  The local-radius reach (W49) is `beta x face_depth_max` = 144 m whatever the pixel, so each tile's window was
  28,800 px of margin a side: `ArrayBed.read` made a 57,729 x 57,729 float64 array, **24.8 GiB**, copied once more by
  its `astype`, and since W81 sixteen threads do that at once. Before W81 the same test took about 50 GB for a moment
  and nobody saw it. Found by rerunning the one test inside a Windows job object capped at 8 GB
  (`scripts/capped_pytest.py`): the allocation fails at its own line, `builder.py:50` from `builder.py:170`.
- **The fix** (commit `c852e5a`, on the coordinator's go; the builder is W49's and W81's code, outside this task):
  the reach is capped at `ArrayBed.span`, the bed's longer side in pixels, and the read drops its second copy.
  Nothing else in the builder changed. `tables/quad.py:131` and `strips/tables.py:336` carry the same formula and
  were not touched.
- **What it changes in the tables** (`scripts/s08_builder_margin.py`, `builder_margin/`):
  - a raster bed has no `span`: a real DEM builds as before. The Block 2 window's tables rebuilt with the new builder
    against the old builder's cache file: **all 20 arrays equal to the digit**;
  - a bed in memory at least 144 m long (320 m at 1 m pixels): all 20 arrays equal to the digit;
  - a flat bed 40 m long: all equal (on a flat bed the local radius is the strips sum whatever the window);
  - a sloping valley 40 m long: equal but for the face tables' rows 5.12 m or more above the face invert, which
    differ by up to 3.5 % (x faces) and 0.16 % (y faces). In general: rows deeper than a ninth of the bed's length
    read fewer repeats of the bed's edge pixel. Those repeats were never ground.
- **The cache key moves.** `builder_identity` hashes `tables/*.py`, and so does the strip key: after a merge every
  grid and strip cache rebuilds once (the window's key went from `66884a1b...` to `65df91ae...` with equal arrays).
  W79's aligned run spent 1,493 s on its tables (`tables_s`), so merge after the reruns, as the coordinator said.
- **Tests since then**: one file at a time, CPU, four threads, each in its own process under the 8 GB cap
  (`scripts/capped_files.py`, `pytest_capped.log`): 18 files, **216 passed, none failed**, with the builder fix in: `tests/tables` (14), `tests/solver` all nine files and the limiter's (74: Stoker, Ritter, Thacker, still water, MacDonald's steady profiles, the 45-degree channel, the quadtree, local stepping, polygons), the engine's run, physics, resume, io and limiter files (36), the plugin contract (92). The Thacker tests pass with their own assertions under the cap, 36 s and 9 s.

## What was not built, and the options

No fix was built into the engine: the limiter is the terrain, and the published remedy is the modeller's. His call:

| | What | For | Against |
|---|---|---|---|
| A | **Mend the four cells in the Block 2 jobs** with terrain objects (an embankment over each hole, top at its spill level; `bank` above shows it on the first) | published practice; no engine change; DEM file untouched; -31 % steps for the hole, -45 % for the four | by hand, per job; an embankment is a fill by another name: a `fill` object (a polygon whose sinks are filled) would say what it is, not built |
| B | **`numerics.plan_min` 0.10 in the job**, terrain as it is | an existing setting; -47 % steps by the frames | **rejected by test**: the pit never comes to rest on the window (table above). Leave it at 0.02 |
| C | **An automatic filter for blunder sinks** when the tables are built, off by default: fill a closed sink deeper than its own width (the hole: 123 m deep, 17 m across; a quarry is the other way round) and list what it filled | no hand work on the next DEM | my rule and my numbers; real shafts and wells; it changes the table builder, so every cache rebuilds once |
| D | **Local time stepping** (exists, `numerics.local_time_stepping`): the hole's tile on its own step | published (PARFLOOD); also lifts the 0.42 s the deep pools set, which nothing else here does | W10 found no gain on a uniform grid of 2 M cells; a GPU test on Block 2 is needed, not run |
| E | **A kernel change**: a local implicit pressure term or scaled inertia on stiff faces | removes the class of problem | unpublished for flood codes; a research pass and his go first |

My order: A now for Block 2 (it is the truth about the ground, and the dock already has the tool), then D measured on
the GPU when it is free, because after A the floor is the pools. C only if holes like these turn up in every DEM he
is given. Not B. E is a study, not a fix.

Faydh 01 (`scripts/s06_faydh_plan_min.py`): only the default was run before B was dropped. On the CPU the race's 20 m
squares read 1,737.54 m3/s at the dam axis in 89,222 steps, against 1,737.29 m3/s in 89,239 on the GPU in W49: the
kernels are unchanged, and the limiter reading was on for that run.

## What it would save on Block 2

- A on the hole alone: about 10 of the 32.6 min of solver loop of the full 2D run on the squares; A on the four: about
  15 min; the aligned run in proportion (about 14 and 20 of its 45 min). [Likely: step counts from the frames times the
  run's cost per step. Not rerun on the GPU.]
- After that the step is 0.42 s through the recession and nothing but D lifts it: two pools 45 to 47 m deep.
- Why the 2026-11-01 run stepped at 0.39 s: [Likely] its 2.03 M cells did not reach the western mountains where the
  hole is; 0.39 s is the pools' number. Not checked against that run's domain.

## Not done, not verified

- No GPU run: not the Block 2 rerun with the holes mended, not the limiter's GPU path on a real job (its three GPU
  tests passed once, run by mistake while the W79 rerun was on the card; the rerun went on undisturbed).
- The dock control for `step_limiter`.
- The three single cells were read on the DEM and in the frames, not run on a window.
- Whether the aligned rerun's 0.23 s in its recession is the same hole with less water in it: [Likely], not read.
- The full suite was not run: targeted files only, as asked, listed above. The GPU-marked tests were deselected.

## Files

- `scripts/s01_frame_waves.py`: the wave speed of every face from a saved frame, through the engine's own kernel.
- `scripts/s02_ground.py`, `ground/*.png`: the DEM under the cells named.
- `scripts/s03_deep_water.py`: the patches of deep standing water in a frame.
- `scripts/s04_steps_without.py`, `frames_run1/steps_without.csv`, `.log`: the step per frame, all scenarios.
- `scripts/s05_window.py`, `window/`: the window runs; `window/dem/fill_report.json`.
- `scripts/s06_faydh_plan_min.py`, `faydh/faydh_plan_min.json`: Faydh 01 on the CPU, the default only.
- `scripts/s07_window_table.py`, `window/window_table.json`: the window runs side by side.
- `scripts/s08_builder_margin.py`, `builder_margin/`: the tables before and after the reach is capped.
- `scripts/capped_pytest.py`, `scripts/capped_files.py`, `pytest_capped.log`: tests under a hard cap on commit.
- The per-face wave maps (70 MB a frame) and the DEM windows are not in git; the scripts remake them.

## [PRESERVE-CHECK]

- KEEP: every kernel, the step rule, `plan_min` 0.02 and all defaults; every existing output; job hashes and
  checkpoints of existing jobs.
- CHANGE: new `outputs.step_limiter` (off), new modules `wadi2d/solver/limiter.py` and
  `wadi2d/engine/step_limiter.py`; a `limiter` progress event, a `warn` and `step_limiter.gpkg` only when asked.
  Separately, on the coordinator's go: the builder's local-radius reach capped at the length of a bed in memory, and
  `ArrayBed.read` without its second copy; face-table rows deeper than a ninth of a short sloping bed change, and
  every table cache key moves.
- FILES: `wadi2d/config/schema.py` (one field), `wadi2d/engine/monitor.py` (create and tick), `wadi2d/run.py` (the
  `NOT_WATER` entry, writing the layer and the warning), `tests/plugin/schema_sample.json`, the two new test files;
  `wadi2d/tables/builder.py` (`ArrayBed.read`, `ArrayBed.span`, one line of `build_tables`),
  `tests/tables/test_local_radius.py` (two tests).
