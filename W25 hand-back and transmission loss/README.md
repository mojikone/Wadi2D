# W25 hand-back and transmission loss

**Status (2026-11-02): live, on branch `feature/hand-back`, cut from `main` at `0c540e4` (D5 merged). Not merged, not pushed. Engine and tests only; the dock has no rows for either feature yet, by the coordinator's brief.**

**Headline.** The hand-back closes its mass: on a closed box the whole model (grid plus network) closes to 4e-8 of the water that entered, with the network's storage measured by draining it, not taken as the remainder. The link puts exactly one lumped step of lag on the flow, by causality. **The weak point found is not the link: the engine's Muskingum-Cunge, which replicates HEC-HMS 4.12, does not conserve volume on a short flood** (out/in 0.84 to 1.91 on 20-minute floods, routed alone off the grid). The books show this as its own line, `routing_defect`, equal to what the reach gives routed by hand. On Block 2's R1, 26 km, with a real 100-yr flood it is 0.22 % of the volume, and the reach raises the peak 4.6 %. [Likely] HEC-HMS has the same error, since the engine reproduces its reach outputs to 0.0003 m3/s rmse; HMS's own volumes were not checked here. Transmission loss is HEC-HMS's percolation method per cell; on the Fizh basin at 150 mm/h, the top of Lane's clean gravel, applied to every channel cell, the 100-yr peak at the gauge still stands at 2.2 x its Q100, and the beds have taken 60 % of the rain. No defensible bed loss alone closes the 3.4 x.

## [PRESERVE-CHECK]

**KEEP, untouched in behaviour, numbers to the last digit for any job with no hand-back and the loss off:**

- The solver kernels on both backends, CUDA and Numba, the stepper, the level stepper, the mesh. No kernel is edited.
- `hydrographs()`, `preflight()`, `Injection`, `boundary_set()`, `Balance.error`, `Balance.relative`, the `done` event and `results.h5` attributes of an old job.
- A lumped network run once before the 2D run when there is no hand-back; `_check_routes` for those jobs.
- Old checkpoints: format `2`, and their job hash, stay resumable.
- The dock. `plugin/` gains no code; the job fields pass through, `tests/plugin/schema_sample.json` is regenerated.

**CHANGE:**

- `hydrology.handbacks` (new job part): name, line, element. Inside the grid the line is an open sink line with its own tally per step. Volume crossing per lumped step, over the step, is the inflow of the element. The network below it reruns on the series so far during the run, and its outflow goes to the `Injection` where it re-enters, or leaves at the end of the network.
- `LumpedEngine.run` gains `external` and `cut`. Absent, the arithmetic is the old one.
- `Balance` gains fields with default zero. The `done` event and `results.h5` gain them only when the job uses them.
- A checkpoint gains a `handback` group when the job has one, and a `transmission` group when the loss is on.
- `transmission` (new job part, off by default): a rate over the wetted plan of channel cells, limited by the water present and optionally by a total depth per cell, applied through the source refresh, on its own line in the balance.
- `boundary_notes` takes optional labels; `boundary_set` keeps its results and shares one helper, `open_faces`, with the per-line faces.
- The mesh refines along hand-back lines as along boundaries.

**FILES:**

- New: `wadi2d/hydrology/live_network.py`, `wadi2d/engine/handback.py`, `wadi2d/engine/transmission.py`, `tests/hydrology/test_live_network.py`, `tests/engine/test_handback.py`, `tests/engine/test_transmission.py`, this folder.
- Edited: `wadi2d/config/schema.py`, `wadi2d/run.py`, `wadi2d/forcing.py` (small), `wadi2d/engine/monitor.py`, `wadi2d/io/checkpoint.py`, `wadi2d/hydrology/network.py`, `wadi2d/mesh/build.py` (one line), `tests/plugin/schema_sample.json`, `tests/plugin/test_contract.py` (one test added).

The blast radius is several modules but no existing behaviour is removed, and the owner has said not to stop. The proof is `old_jobs_check.py`, below.

## D6c, the hand-back: the design as built

The brief's reading is kept, with two changes, each for a reason.

| Piece | As built | Why |
|---|---|---|
| Job part | `hydrology.handbacks`: `name`, `coordinates`, `element`, `snap_m`, `min_share` | As briefed |
| The line inside the grid | A **sink**: its cells are held dry, like a `free` boundary, with their own face tally every step, on both steppers | A boundary that follows the level (`normal`) holds water in its cells and passes it on to the cells beyond. That water would miss the reach and nobody would know |
| Inflow of the element | Volume crossed in lumped step k, over the step: a period mean at ordinate k | As briefed: a trapezoid over period-ending ordinates gives the exact volume for a hydrograph from zero to zero, and the drain at the end books the last half step |
| Network below | Reruns on the series so far each lumped step; every routing method here is causal, tested to the last digit | As briefed. No method needed a streaming form, and the series is the whole state |
| Re-entry | **Held**: ordinate k's outflow enters over period k to k + 1, at the same cells an `Injection` uses | **Changed.** A line through the ordinates would add half a step more delay and round the hydrograph. A hold keeps each block of water whole and costs exactly one step |
| Routes | Links into the hand-back's element are cut: the grid carries that water. The link below a re-entry is cut: its water is on the grid again | His double-count rule, made structural rather than checked after the fact |
| Books | `Balance` gains `handback`, `reentry`, `lateral`, `network_out`, `network_storage`, `routing_defect`; `whole_error` = grid error + routing defect | The grid's own `error` is unchanged. Network storage is measured by **draining** the network after the run (the inflow stops, the reaches empty), so the defect is a measured number, not zero by construction |
| Resume | The checkpoint keeps each line's series, tally and last volume; on load the network is rerun, so every reach and pool comes back | A checkpoint without that record is refused: "the water in the reaches would be lost: run without --resume in a new folder" |

**Refused or warned, in words** (all tested): a hand-back's route that runs into another hand-back's element ("it would be lost"); a route through a subbasin; an unknown element; two inflows on one element ("the same water would enter twice"); a 2D subbasin draining into a route ("its rain falls twice"), with or without a re-entry; a re-entry that also carries a lumped subbasin with its own outlet ("enters twice"); a hand-back with no network. Warned: a line that opens less than `min_share` of its length; a line that crosses no face; a re-entry on higher ground than a line.

**One case is allowed on purpose.** A lumped subbasin with its own outlet that joins below the line enters the grid at its outlet and is cut from the reach, so its water is counted once. The old rule would call this "enters twice", but here it does not.

## Proof of the mass balance (`tests/engine/test_handback.py`, through `run_job`)

A closed box: a plane falling east at 1 %, walled all round, 512 x 128 m at 4 m. A 4,800 m3 triangle enters in the west, a line takes it across the middle, the network carries it and it comes back in the east. Lumped step 1 min. Every figure below is from the test run; tolerance on the books 1e-5 of the water that entered.

| Case | Entered | Crossed the line | Came back | Left at the end | In the network | On the grid | Routing defect | Grid error | Whole error |
|---|---|---|---|---|---|---|---|---|---|
| Lag 10 min, re-entry | 4,800.0 | 4,792.0 | 4,789.9 | 0 | 2.1 | 4,797.9 | 0 | -1.9e-8 | -3.8e-8 |
| Lag 30 min, run stopped at 25 min with the flood inside the reach | 4,800.0 | 4,590.1 | 0 | 0 | **4,590.1** | 209.9 | 0 | -1.8e-9 | -1.8e-9 |
| Muskingum-Cunge, 3 km, re-entry | 4,800.0 | 4,795.1 | 5,011.0 | 0 | 2.6 | 5,015.9 | **-218.5** | -2.1e-8 | -4.6e-2 |
| Reservoir, sill 1 m above the floor of a 1,000 m2 pool | 4,800.0 | 4,796.6 | 3,796.5 | 0 | **1,000.1** | 3,799.9 | 2e-13 | -1.8e-8 | -3.2e-8 |
| Lag 10 min, no re-entry: leaves at the end of the network | 4,800.0 | 4,792.0 | 0 | 4,789.9 | 2.1 | 8.0 | 0 | -1.5e-10 | -1.5e-10 |
| Lag 10 min on a mesh, 4 m and 8 m cells | 4,800.0 | 4,792.0 | 4,789.9 | 0 | 2.1 | 4,797.9 | 0 | -2.9e-9 | -5.9e-9 |
| Lag 10 min, GPU | 4,800.0 | 4,792.0 | 4,789.9 | 0 | 2.1 | 4,797.9 | -9e-13 | -2.0e-8 | -4.0e-8 |

m3; errors as a share of the water that entered (`proof_table.py`, `proof_table.json`). How each is known without the model's word for it:

- **Lag**: the reach's outflow equals the line's inflow shifted by 10 ordinates, block for block, to the last bit (`test_a_plain_lag_gives_the_exact_answer_block_by_block`). Re-entry plus network storage equals what crossed to 1e-6.
- **Stopped inside the reach**: what the network holds equals the sum of the line's period inflows, to 1e-9. None of it is on the grid, and none of it is lost.
- **Muskingum-Cunge**: the defect equals, to 1e-3, what the same reach gains on the same inflow routed by hand off the grid. It is the method's own, see below; the link adds nothing.
- **Reservoir**: what stays is the dead storage under the sill, 1,000 m3 from the table, against 1,000.1 measured.
- **Mesh and GPU**: the same books as the uniform CPU run, within 3e-6 of each figure.

Also tested: a stop and a resume end with the same grid storage and line volume as an uninterrupted run, to 1e-3; two lines into one reach are tallied apart; nothing passes a line on the grid, because a section 20 m beyond it reads zero throughout.

**The lag of the link, measured** (`lag_table.py`, the same box, a 10-minute lag reach, sections 8 m before the line and 12 m after the re-entry):

| Lumped step | Link's own lag | Lag measured on the grid, after the reach's 10 min | Peak after / peak before | Whole error |
|---|---|---|---|---|
| 1 min | 60.0 s | 106 s | 0.978 | -3.8e-8 |
| 2 min | 120.0 s | 166 s | 0.976 | -3.5e-8 |
| 5 min | 300.0 s | 344 s | 0.916 | -4.0e-8 |

The link's own lag is one step exactly, at every step. The rest of the total is water moving 20 m on the grid. Holding costs the peak 2 % at 1 and 2 min and 8 % at 5 min on this 20-minute flood. A flood of hours loses far less, and the Block 2 case below measures it.

## Muskingum-Cunge does not conserve volume, and the books say so

Routed alone, with no grid and no link, on triangles from zero to zero (`mc_check.py`, output in `mc_check.txt`; on the grid the test `test_muskingum_cunge_closes_and_its_own_volume_error_is_named_not_hidden` finds the same):

| Reach | Step | Peak 8 | Peak 80 | Peak 800 m3/s |
|---|---|---|---|---|
| Test reach, 3 km | 1 min | 1.044 | 0.987 | 0.975 |
| Test reach, 3 km | 5 min | 1.191 | 1.020 | 1.001 |
| Block 2 R1, 26 km | 5 min | 1.571 | 1.914 | 1.184 |
| Block 2 R6, 4.3 km | 5 min | 1.360 | 1.065 | 1.020 |

out/in by volume, 20-minute triangles. [Likely] The cause is HMS's own handling, which the engine copies to replicate it: a negative new-inflow weight is zeroed and its share split between the other two, and the low-flow rule replaces the coefficients with a mean. Neither keeps continuity. On Block 2's real 24-hour floods the error is smaller; the Block 2 case below gives the number. This is not a hand-back defect. It has been in every lumped run since the HMS replication, which compared against HMS's own series, and those would carry the same error [Likely]. **It needs his decision** (Next steps).

## Block 2 case (`block2_case.py`): a real line above a real lumped reach

S1 and S2 (103.5 km2) run as rain-on-grid, 100-yr storm at 103.5 km2, project CN grid, n 0.04, 20 m, lumped step 5 min, 30 h. The line crosses the wadi 400 m down R1 from its head, 1.4 km long, ends 20 m above the thalweg. R1 is HMS's own reach: Muskingum-Cunge, 26.0 km, n 0.1. Its outflow re-enters 300 m above R1's end, and section J2 sits 150 m above the end. In the second run the same flood runs the whole of R1 on the grid. **S3, the subbasin R1 runs through, is masked in both runs** (lumped, with a table inflow of zeros under its own name), so the difference is the reach alone. That device belongs to this comparison only.

| | Peak, m3/s | At, h | Volume, Mm3 |
|---|---|---|---|
| Crossed at the line, period means | 1,855 | 12.38 | 16.256 |
| Full 2D run, section at the line's place | 1,846 | 12.53 | 16.253 |
| R1 lumped, as the network gave it | 1,940 | 13.83 | 15.795 |
| R1 routed by hand on the same inflow | 1,940 | 13.83 | 15.795 |
| **J2, hand-back run** | **1,923** | **13.91** | 15.789 |
| **J2, full 2D run** | **1,832** | **13.33** | 15.990 |

Books of the hand-back run: rain 16.933 Mm3; crossed the line 16.256; came back 15.782; still in R1 after 30 h 0.439 (measured by draining it); routing defect **35,564 m3, 0.22 % of what crossed**; grid error -1.3e-8; whole error 2.1e-3, which is the defect.

- **The link does what HMS does.** The network's R1 equals R1 routed by hand on the same inflow to the last bit (max difference 0.0 m3/s).
- **The sink does not disturb the flow above it.** At the line's place the crossing and the full 2D section agree to 0.5 % at the peak and 0.02 % in volume. The crossing's peak sits 9 min earlier, an artefact of reading period means at the middle of their 5-minute period, plus some draw-down toward the dry line [Likely].
- **Difference of method, not tuned.** HMS's R1 makes J2's peak **5.0 % higher and 35 min later** than the same 26 km on the grid. Over R1 the lumped reach **raises** the peak from 1,855 to 1,940 m3/s (+4.6 %), where the grid lowers it from 1,846 to 1,832 (-0.8 %). [Likely] The rise is the same handling that breaks continuity in the table below, a clipped negative weight; a plain Muskingum-Cunge attenuates. Of the 35 min, 5 are the link's step.
- **Where it fails.** The case closes its mass and agrees with the reach routed by hand, so nothing failed in the link. What it exposed is in the method: the reach does not conserve volume and lifts the peak, and that reaches every lumped run of the project, not only hand-backs.

## D6d, dry-bed transmission loss

**Method.** HEC-HMS's percolation channel loss (a constant rate over the wetted area), taken per cell. The wetted share of the cell plan comes from the sub-grid tables, so a thread 8 m wide in a 20 m cell loses over 8 m, not 20. A cell is a channel cell when its level stands `min_depth_m` (default 0.1 m) above its lowest point. Thinner sheet flow keeps its CN loss and nothing more. An optional total per square metre of bed, `max_depth_mm`, stands for the alluvium's storage above rock or the water table. Rates are read from Lane's bed-material table, NEH Part 630 chapter 19 (USDA NRCS, 2007), table 19-1, effective hydraulic conductivity [Certain, read from the chapter]:

| Lane's group | Bed | K, in/h | mm/h |
|---|---|---|---|
| 1 | Very clean gravel and large sand | over 5 | over 127 |
| 2 | Clean sand and gravel, field conditions | 2 to 5 | 51 to 127 |
| 3 | Sand and gravel, low silt-clay | 1 to 3 | 25 to 76 |
| 4 | Sand and gravel, high silt-clay | 0.25 to 1 | 6 to 25 |
| 5 | Consolidated bed, high silt-clay | 0.001 to 0.1 | 0.03 to 2.5 |

Lane's K feeds a volume-and-distance model, not a rate; using it as a rate over the wetted bed is the HMS percolation reading of it, and an approximation [Likely].

**Where it runs, and why.** On the Python side, through the existing source refresh, not in the kernels. It is honest about the time scale: the rate is held for one window of `run.source_every_s`. At 100 mm/h a 30 s window takes 0.8 mm from a cell that holds at least 100 mm of level, so the state does not move under it. And no kernel changed, so off leaves every number as it was without a second proof on two backends. What it gives up: a cell can drain between refreshes and be overdrawn. `water_share` (0.5) makes that rare, and the kernels floor such a cell at zero, which shows in the balance as error, never as a loss that did not happen.

**Tests** (`tests/engine/test_transmission.py`): still water, 36 mm/h for an hour, takes 36 mm everywhere to 1e-5; the cap stops at 10 mm; 2,000 mm/h on 20 mm of water takes less than the water and closes to 1e-6; thin water below the channel depth keeps its water; only the given area loses; **a dry rectangular channel 8 m wide carrying 2 m3/s loses rate x wetted bed by hand within 3 %**; a stop and a resume keep the cap; the GPU takes the same. Off: nothing taken, and no new key in the done event.

## Fizh as a sensitivity, not a calibration (`fizh_sensitivity.py`)

The W11 job as it stood: 100-yr Block 2 storm at the gauge's 262 km2, project CN, n 0.05, 20 m, 36 h, rerun on this branch with the loss off, then at rates across Lane's groups. The loss acts on every channel cell, mountain wadis included, which is an upper bound: bedrock wadis lose little. The gauge's Q100 of 770 m3/s is read against the results, not used to choose a rate.

| Bed rate, mm/h | Lane's group | Peak at the gauge, m3/s | / Q100 770 | Peak at, h | Volume past the gauge, Mm3 | Taken by beds, share of the rain | Grid error |
|---|---|---|---|---|---|---|---|
| 0 | off | 2,582 | 3.35 | 14.0 | 36.9 | 0% | 2.9e-08 |
| 25 | 3 to 4 | 2,432 | 3.16 | 14.1 | 31.2 | 17% | 1.5e-08 |
| 75 | 2 to 3 | 2,144 | 2.78 | 14.1 | 22.7 | 41% | -9.6e-09 |
| 150 | 1 | 1,723 | 2.24 | 14.3 | 15.6 | 60% | -1.3e-08 |
| 300 | past 1 | 1,025 | 1.33 | 14.5 | 8.0 | 80% | -1.3e-08 |

Rain over the domain: 38.9 Mm3 in every run. The run with the loss off gives 2,582 m3/s, W11's figure to the unit, so W11's finding stands on this branch.

**What it says.** No rate inside Lane's table closes the factor. At 150 mm/h, the top of clean gravel and applied to every channel cell, the peak is still 2.2 x Q100, and the beds have taken 60 % of the rain. Reaching 770 would take about 350 mm/h by extrapolation (not run), with the beds taking more than 80 % of the rain, on bedrock wadis as well as gravel. [Likely] Transmission loss is a real part of the answer on the fan, where Hatta halves between Ajib and Shinas. But a loss large enough to explain 3.4 x would have to take most of the flood, which no measured Batinah bed supports. The storm, the CN grid or the gauge's rating is still where most of the gap must be. This is a sensitivity of an uncalibrated model, and it fits nothing.

## Old jobs give their numbers to the last digit (`old_jobs_check.py`)

Every dataset and numeric attribute of `results.h5`, every GeoTIFF band, every series CSV and the numbers of the done event, hashed one by one. The jobs ran on `main` at `0c540e4` (exported, so it could not move) and on this branch. Run times are left out; nothing else is.

| Job | Backend | What it uses | Items hashed | Identical to `main` |
|---|---|---|---|---|
| Valley, uniform storm, CN, free boundary, points and lines, pixel maps | CPU | rain-on-grid, the products after the run | 65 | **65** |
| The same | GPU | | 65 | **65** |
| The same with a hyetograph and local time stepping | GPU | D5's storm, the level stepper | 65 | **65** |
| Plane, table inflow, stage boundary, initial level | CPU | injection, fixed level, initial water | 40 | **40** |
| Mesh, HMS basin, lumped subbasin at its outlet | CPU | quadtree, lumped network before the run | 40 | **40** |
| **Block 2 hybrid, all 18 subbasins lumped, 40 m, 6 h** | GPU | the real HMS basin, CN raster, ARF storm, 3 boundaries, 5 dams' lines | 96 | **96** |

**311 of 311 items identical, every one to the last bit** (`old_jobs_compare.txt`; `old_jobs_base.json`, `old_jobs_branch.json`). One thing needs saying, because it would otherwise look like a failure. Run twice, `main` itself does not repeat the last digit of `rain_m3` on the mesh job (1391.360015468672 against 1391.3600154686721, `old_jobs_base_again.json`). The monitor credits a window's rain at progress ticks, and the wall clock times those ticks, so the number of partial sums varies from run to run [Certain, read in `Monitor.settle` and `_tick`]. The branch matched the first base run on that item too. Every array, map and series repeats exactly.

## What was not tested, and what is weak

- **The dock.** No rows for either feature; the coordinator wires them. `map_notes` says "from the lumped hills" for the whole of `inflow_m3`, and with a hand-back that includes the re-entry: the note should use `inflow_m3 - reentry_m3`.
- **A line that does not span the flow.** Water that passes round its end stays on the grid and the books still close. Only the open-share warning and the drawing can show it.
- **The sink draws the water down near the line**, as a free overfall does; on Block 2 compare the line crossing with the full 2D section at the same place (table above).
- **Hand-back from D6a's `basin.json`.** Only an HMS basin is read today. The seam is `_network` in `run.py`.
- **A re-entry that runs back to its line** is only warned, by ground level; a loop is not detected.
- **The rerun cost** grows with the square of the lumped steps. Fine at Block 2's 360 steps; a 1-minute step over several days was not timed (the card is shared, so no timings are quoted).
- **Transmission loss**: no "first wetting" memory beyond the cap, no map of what each bed took, no loss in lumped reaches (HMS's own channel-loss options are still refused on import).
- **ruff**: clean, except one I001 import-order hit in `tests/plugin/test_contract.py` that `main`'s own copy gives inside a worktree and not in the main checkout; untouched.

## Next steps (his)

1. Muskingum-Cunge's volume error, inherited from HMS: keep it, to replicate HMS, or add a conserving variant for hand-back routes and design flows.
2. Which bed groups the Batinah wadis and fans belong to, and whether the loss belongs in design runs at all (W11 asked the same question).
