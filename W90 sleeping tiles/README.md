# W90 sleeping tiles

Branch `perf/sleeping-tiles` (off `feature/fast-products` at `243ea26`), 2026-11-15. Not merged, not pushed.

**His question (2026-11-15):** in a run where the catchments are lumped and only the routing is 2D, most cells never
get wet; how can the unused cells be inactive without knowing in advance which get wet?

**Answer in one line:** the engine already did that for squares; the aligned strip switched it off, by keeping awake
every tile that holds a square the strip touches. That is fixed, with results equal to the last bit. On Block 2
the gain is 24 % (run 3) and 13 % (run 4) of the stepping time, not more, for two reasons that are not faults:
the water of those runs reaches 59 % and 80 % of the tiles, and the strip, which is stepped whole, is 43 % of a step.

## 1. The cause

[Certain] `Hybrid.__init__` (`wadi2d/strips/hybrid.py`) put every tile that holds a ghost (a square the strip
opens onto) into the stepper's `keep_active` and `pinned`, and `Model.set_source*` put `pinned` back into
`keep_active` at every source window. The stepper wakes a kept tile and its eight neighbours, whatever the water does.
With streams on almost every tile that is the whole model:

| Block 2, 20 m aligned mesh (run 4's own grid and strip) | tiles | with their 8 neighbours |
|---|---|---|
| all | 3,604 | |
| hold a ghost of the strip (104,062 ghosts) | 2,276 | 3,479 |
| hold a boundary cell (6 lines) | 64 | 139 |
| ghost or boundary | 2,311 | **3,487** |
| active at the first step of runs 1, 3 and 4 (`progress.jsonl`) | | **3,487** |

The stepper's own rule applied to those two static sets gives 3,487, the number in all three runs at step 1, with no
water and no rain in the model (`block2/run4_first_step.json`, `scripts/block2_first_step.py`). The rest of the way
to 3,593 and 3,594 is the wet tiles' neighbours.

Nothing else on the list of suspects holds a tile: the rain and lumped masks keep a tile only while its net rate is
not zero; the pit and edge checks do not touch the list; there is no local time stepping in these runs. "A tile
never sleeps again" is true but is not a fault: a tile that was wet keeps a film (a face stops at 0.1 mm over its
invert), so on real ground it never dries. On run 3's frames 1,470 tiles ever carried a flow and 1,473 ever held
water; a rule of "no flow" in place of "no water" would have slept three tiles.

### His hypothesis: the 40 m rim that was rained on

[Certain] It is not the rim. The rim's 14,250 rained squares lie in 358 tiles, 722 with their neighbours; with the
coast strip's 55,379, 417 tiles and 757 with neighbours. The first-step list of 3,487 is static: 2,806 of its
tiles are outside the rain's 757, and the rain adds 76 tiles to it. Run 1, with rain everywhere, shows the same 3,487
at its first step, so the rain woke nothing there either ([Likely] no cell has a net rate at the first step; not
looked at). As to where the rim's water went afterwards, the frames cannot separate it from the lumped inflows: all
the water of run 3 together touched 1,473 tiles (2,133 with neighbours), so the rim's own share is below that, and
all of it is far below 3,487.

## 2. The fix

A tile is asleep while no water and no source can reach its cells before the next check of the active list. Water
moves one cell a step at most, so "can reach" is a count of cells.

- **Squares**: unchanged rule, a wet tile and a tile with a source wake their eight neighbours (a tile is 32 cells
  wide, a check comes every 16 steps).
- **Strip** (new, `wadi2d/strips/watch.py`): a strip is a second way in, its cells need not be the lattice's size, and
  it hands water to squares anywhere inside a tile. So the reach is counted once, at the start, on the model's own
  cells: from every tile's squares outward 18 cells (16 steps between two checks and a margin of 2) through squares,
  strip cells and the joins between them, noting which tiles' squares and which strip cells were met. The strip's
  cells are grouped by the tile their centre lies in (their home tile); at a check the device says which homes hold
  water or a source, and a tile wakes if any tile or home it met does. On Block 2: 0.3 s at the start, 42,933
  entries (`block2/run3_watch.json`). There the strip's cells are about the lattice's size (the largest 808 m2
  against 400) and no reach passes a tile's eight neighbours: the watch is the squares' own rule, with the strip's
  cells counted as water. The count is what keeps it right on a mesh with larger cells.
- **A tile that wakes** is made what it would be had it never slept: its wet share (`om`) written by the kernel's
  own arithmetic (a new kernel `plan` on both backends; asleep it kept the host's float64 value) and the halos of
  the list filled. Without the margin and this pass a waking tile reads stale halo cells of its neighbour.
- **A tile sleeps again** after two checks in a row that did not want it (`SLEEP_CHECKS`, at least 16 steps dry): by
  then both of its face buffers and its wave speed are a dry tile's. A change of source never drops a tile, only a
  check does.
- **The reference**: `stepper.adaptive_active = False` now steps every tile at every step; the tests compare with it.
- A quadtree keeps the old rule for its ghost tiles (the watch counts cells on the uniform lattice only).
- The CPU backend now zeroes its wave array at a refresh, as the GPU always did: a tile off the list has no wave.

**The strip itself is still stepped whole** (section 4).

### [PRESERVE-CHECK]

- KEEP: every kernel that steps water (`faces`, `limit`, `update`, the strip's `poly.cu` and `poly/kernel.py`: not
  touched); the rule for squares; the level stepper's levels and plans; checkpoints (format, saved arrays); the job
  schema and every hash (no new setting); a quadtree's ghost tiles.
- CHANGE: ghost tiles are no longer kept awake on a uniform grid (they wake by the watch); `Model.set_source*` no
  longer puts `pinned` tiles into `keep_active`; a tile leaves the list after two unwanted checks, not one; a waking
  tile gets the `plan` and halo pass; `adaptive_active = False` means all tiles (it was unused); the CPU wave array
  is zeroed at a refresh; setting the strip's depth or source rebuilds the list.
- FILES: `wadi2d/solver/stepper.py`, `level_stepper.py`, `model.py`, `cpu/backend.py`, `cpu/kernels.py` (new
  kernel `plan` only), `gpu/backend.py`, `gpu/kernels/cells.cu` (new kernel `plan` only);
  `wadi2d/strips/watch.py` (new), `hybrid.py`, `hybrid_gpu.py`; tests `tests/strips/valley.py`,
  `tests/solver/test_sleeping.py`, `tests/strips/test_sleeping.py`, `tests/engine/test_sleeping_run.py` (all new).
- For the merge with `fix/strip-max-speed`: `poly.cu`, `solver/poly/*.py` are untouched. In `hybrid.py` the edits are
  the module docstring, `Hybrid.__init__` (the last ten lines), four new methods after `make_state`
  (`_ghost_tiles`, `tiles_to_wake`, `strip_flags`, `strip_changed`), one comment in `load`, and in `HybridCpu`
  a new `strip_flags` and one line at the end of `set_strip_depth` and `set_strip_source`; in `hybrid_gpu.py` the
  same three in `HybridGpu`. `before_update`, `after_update`, `_book` and the ghost kernels are untouched.

## 3. Identical results

The sleeping run against the run that steps every tile, same calls, compared to the last bit: `h`, `d`, `u`, `v`,
`mx`, `my`, `qx`, `qy`, `res` on every own cell, the strip's `h`, `d`, `u`, `m`, `q`, `res`, the step count, the time
and the time step, at several times through each case. One differing entry fails.

| Case | File | Backend |
|---|---|---|
| still water in one corner, the rest asleep | `tests/solver/test_sleeping.py` | CPU |
| a front crossing tile borders north, south, west and east | same | CPU |
| rain starting later on a tile that slept | same | CPU |
| a lumped inflow at the head, an open (free) end | same | CPU, GPU |
| a tile that dries, sleeps again, and is rained on again | same | CPU |
| a dry strip holds no tile awake (was all 16) | `tests/strips/test_sleeping.py` | CPU |
| a flood down a strip wakes the tiles ahead of it | same | CPU, GPU |
| three strips, water in one: the dry ones hold nothing awake (was all 24, now 20) | same | CPU |
| still water across the join, dry tiles beyond | same | CPU |
| rain on a strip that slept, running down it and out of its end into squares that slept | same | CPU, GPU |
| water from the squares into the strip and down it | same | CPU |
| the watch's reach is a count of cells | same | CPU |

15 tests, 12 on the CPU and 3 on the GPU, all pass. The same is true of the 240-tile timing case below (5,339 steps,
0 entries differ under the old rule and the new).

Those strips are squares. On a real corridor (the mesher's aligned rows and the polygons round them) the same is
shown through `run_job`: `tests/engine/test_sleeping_run.py`, 36 tiles, 2 m3/s into the corridor's head on dry
ground, no rain. The series files are equal as text, the strip's depths, the balance and the maximum maps equal
exactly, the step count the same, against the same job with every tile stepped.

**Do the tests see a broken rule?** (`scripts/mutations.py`, the strip-end case): with no wake rule for the strip the
run differs at t = 1,800 s and is 404 m3 short (the strip's end pours into a tile that is not stepped). With a reach
of 2 or 6 cells in place of 18, and with the wake pass removed, this case still passes: its front moves under half
a cell a step. [Likely] Those two guard the worst case (a front at one cell a step), which no test here produces;
they rest on the count, not on a failing example.

**Local time stepping** is not in this claim: with it the cycle's length depends on which tiles are on the list, so
a sleeping run and an all-tiles run take different sub-steps by design, as they always have. Its own tests pass.

Existing tests, one file at a time: 31 files, 373 passed, 0 failed (section 8).

## 4. The gain

### The made-up case (CPU, `scripts/valley_gain.py`, `valley/*.json`)

A valley of 10 x 24 tiles (245,000 cells), 40 m3/s at its head for 3 h, a strip on the axis and an open end; then the
same with two more strips on the hillsides that stay dry, which is Block 2's case.

| | awake tiles (mean) | ms a step | strip, ms |
|---|---|---|---|
| one strip: every tile | 240 | 5.76 | 0.58 |
| one strip: rule before W90 | 108 | 2.90 | 0.46 |
| one strip: W90 | 76.5 (32 at the start, 108 when the flood is at the end) | 2.41 | 0.50 |
| three strips: every tile | 240 | 6.07 | 0.90 |
| three strips: rule before W90 | **240** | **6.35** | 0.77 |
| three strips: W90 | **76.5** | **3.44** | 0.76 |

With dry streams about, the old rule stepped everything and W90 steps a third: 46 % less time, the remaining strip
(6,750 cells, stepped whole) 22 % of the step.

### Block 2 itself (GPU, `scripts/block2_step_time.py`, `block2/run3_step_time_gpu.json`)

Run 3's own tables and strip, the water of two of its saved frames put back (depths, no velocities), 320 steps each:

| Water of the frame at | every tile | rule before W90 | W90 | W90's tiles with no strip |
|---|---|---|---|---|
| 4 h, awake tiles | 3,604 | 3,572 | 1,126 | 1,133 |
| 4 h, ms a step | 2.556 | 2.558 | **1.653** | 0.470 |
| 16 h, awake tiles | 3,604 | 3,593 | 1,964 | 1,964 |
| 16 h, ms a step | 2.539 | 2.561 | **1.912** | 0.914 |

[Certain] The squares cost 0.44 ms per 1,000 awake tiles; the strip (539,195 cells, 1.28 M faces) costs 1.0 to
1.2 ms a step whatever is awake, 43 % of the old step and more than half of the new one. A strip cell costs about
five times a square.

### Runs 3 and 4, estimated from their frames (`scripts/block2_tiles.py`, `block2_estimate.py`, `block2/*.json`)

Nothing was rerun. A tile is "needed" in a frame when it or a neighbour holds water (squares, or strip cells whose
centre lies in it); steps per frame from `progress.jsonl`; step times from the table above.

| | run 3 (hybrid) | run 4 (2D routing) |
|---|---|---|
| tiles that ever held water, of 3,604 | 1,473 (41 %) | 1,861 (52 %) |
| tiles ever needed (with neighbours) | 2,133 (59 %) | 2,885 (80 %) |
| wet squares, share of cell-steps | 11.6 % | 11.5 % |
| tile-steps needed | 56 % | 77 % |
| tile-steps saved by W90 | 46 % | 26 % |
| stepping, ms a step: before, after | 2.56, 1.94 (-24 %) | 2.56, 2.22 (-13 %) |
| seconds saved of the saved run's loop | 237 of 1,648 (14 %) | 146 of 1,843 (8 %) |
| strip cell-steps needed | 58 % | 83 % |
| if the strip slept too, ms a step | 1.49 (-42 %) | 2.03 (-21 %) |

[Certain] The share of the whole loop is smaller than the share of the stepping: the saved runs spent 4.3 ms a step
in their loop, and the stepping measured here is 2.56. [Guessing] The rest is the 192 maps written inside the loop,
the per-step books and the strip's sub-steps; what of it shrinks with the awake tiles (the maxima kernel runs on
them) was not measured, so the 14 and 8 % are a floor.

**Why not more.** [Certain] In these two runs the water is not in a few wadis: the 86 subbasins that drain to no
dam each enter at their own wadi outlet (W79), and the strip runs through 2,216 tiles. Wet squares are 12 % of the
cells but lie in 41 to 52 % of the tiles, and each wet tile wakes its neighbours. The unit that sleeps is 640 m wide.

## 5. What is possible next (not built; his call)

1. **The strip in groups** (the larger gain left). The groups exist now (the home tiles of `watch.py`) and so does
   the reach count. What is missing is in the strip's kernels: all 15 of `poly.cu` and their CPU twins loop over
   every cell or face. Give each a list of awake cells and awake faces (`i = list[n]` in place of `i = n`, no change
   to any formula), rebuilt at each check from the awake homes; a home is awake when water can reach its cells within
   the same 18 cells (the same count, started from strip cells). Expected: the strip's 1.09 ms in proportion to its
   needed cells, run 3 to 1.49 ms a step (-42 % in all), run 4 to 2.03 (-21 %). Not done here because it edits every
   kernel signature of `poly.cu` while `fix/strip-max-speed` is in the same file.
2. **Wake a neighbour only when water is near the shared edge** (within 18 cells of it), not every neighbour of a
   wet tile: tile-steps 56 to 50 % on run 3 and 77 to 67 % on run 4 (`band_rule_tile_steps_share`). Needs four more
   flags per tile from the update kernel and the same in the watch. A small gain for a kernel change.
3. **A smaller unit.** [Guessing] With 16-cell tiles the awake share would move toward the 12 % of wet cells; the
   tile size is in every kernel and table (`layout.TILE`), so this is a study, not a patch.
4. **Fewer strip cells.** 351,370 of the strip's 539,195 cells are the transition polygons round the corridors, at
   five times a square each.

## 6. Files

- `scripts/read_progress.py`, `h5_layout.py`, `npz_layout.py`: what the saved runs hold (read only).
- `scripts/block2_first_step.py` -> `block2/run4_first_step.json`: the cause, and the rim test.
- `scripts/block2_tiles.py` -> `block2/run3_tiles.json`, `run4_tiles.json`: per frame the wet, needed and flowing tiles.
- `scripts/block2_step_time.py` -> `block2/run3_step_time_gpu.json`: step times on Block 2's own mesh.
- `scripts/block2_estimate.py` -> `block2/estimate.json`: the table of section 4.
- `scripts/valley_gain.py` -> `valley/valley_10x24_cpu.json`, `valley_10x24_dry_strips_cpu.json`.
- `scripts/block2_watch.py` -> `block2/run3_watch.json`: the watch on Block 2's strip.
- `scripts/mutations.py` -> `logs/mutations.txt`: broken rules against the identity comparison.
- `scripts/run_tests.sh` -> `logs/tests_after_w90.log`.

W79's run folders were read, never written.

## 7. Not done

- The strip is stepped whole (section 5.1).
- No Block 2 run was made with the fix: the gain there is an estimate from frames and a 320-step timing.
- The full suite was not run (one file at a time, the files that touch the change: table below).
- Not through the dock: nothing in the plugin changes, and `active_tiles` in the progress line is the only place a
  user sees it.
- A quadtree with a strip keeps the old rule.

## 8. Existing tests after the change

One file at a time, CPU and GPU (`logs/tests_sleeping_final.log`, `logs/tests_after_w90.log`). The five files that
build a strip were run again on the last commit of the code and pass the same (`logs/tests_strips_final.log`).
The full suite was not run:

| File | passed | failed |
|---|---|---|
| `tests/solver/test_sleeping.py` | 6 | 0 |
| `tests/strips/test_sleeping.py` | 9 | 0 |
| `tests/engine/test_sleeping_run.py` | 1 | 0 |
| `tests/solver/test_levels.py` | 29 | 0 |
| `tests/solver/test_quad.py` | 28 | 0 |
| `tests/solver/test_analytic.py` | 14 | 0 |
| `tests/solver/test_steady.py` | 3 | 0 |
| `tests/solver/test_subgrid.py` | 9 | 0 |
| `tests/solver/test_dry_faces.py` | 2 | 0 |
| `tests/solver/test_face_level.py` | 2 | 0 |
| `tests/solver/test_limiter.py` | 10 | 0 |
| `tests/solver/test_poly.py` | 5 | 0 |
| `tests/solver/test_review_regressions.py` | 18 | 0 |
| `tests/strips/test_hybrid.py` | 4 | 0 |
| `tests/strips/test_hybrid_gpu.py` | 4 | 0 |
| `tests/engine/test_strips_run.py` | 15 | 0 |
| `tests/engine/test_resume_exact.py` | 2 | 0 |
| `tests/engine/test_strip_cache.py` | 2 | 0 |
| `tests/engine/test_breach_strips.py` | 7 | 0 |
| `tests/engine/test_levels_run.py` | 3 | 0 |
| `tests/engine/test_run.py` | 15 | 0 |
| `tests/engine/test_rain_run.py` | 15 | 0 |
| `tests/engine/test_handback.py` | 28 | 0 |
| `tests/engine/test_inflow_lines.py` | 15 | 0 |
| `tests/engine/test_transmission.py` | 9 | 0 |
| `tests/engine/test_breach.py` | 15 | 0 |
| `tests/engine/test_breach_quad.py` | 6 | 0 |
| `tests/engine/test_mesh.py` | 24 | 0 |
| `tests/engine/test_review.py` | 48 | 0 |
| `tests/engine/test_basin_run.py` | 10 | 0 |
| `tests/engine/test_edge_valleys.py` | 15 | 0 |
| **31 files** | **373** | **0** |
