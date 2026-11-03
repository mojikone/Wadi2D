# W29 conserving routing

**Status (2026-11-02): done on branch `feature/mc-conserving`, cut from `main` at `a783afc`. Not merged, not pushed. The job gains one setting, `hydrology.reach_routing`: `hms` (the default, HEC-HMS 4.12 replicated to the last digit, unchanged) or `conserving`, the mass-conservative, storage-consistent variable-parameter Muskingum-Cunge of Todini (2007) on the same cells, sub-steps and section. It is in the dock and tested through the real dock (29 of 29, `log_dock_routing_block2.txt`). On Block 2's eight reaches with HMS's own 100-yr inflows the conserving variant closes inflow = outflow + storage to round-off (worst 5.6e-9 m3 of 12 Mm3) and out/in to 1.000000 once the tail drains, where the HMS path reads 0.9992 to 1.0002; on the 20-minute floods where the HMS path reads 0.84 to 1.91 x it reads 1.000000. The peaks of the design floods are the HMS path's within 0.14 % and the timings the same; the short floods differ by a factor, and that is the record for his decision, not a pass.**

## [PRESERVE-CHECK]

**KEEP, numbers to the last digit:** the HMS-faithful kernel `route_cells` and every rule in it; `MuskingumCunge.grid()`; the replication tests (`tests/hydrology/test_block2_replication.py`, `test_heldout_replication.py`, `test_replication_rules.py`) pass unchanged; a job without the key keeps its hash, so an old checkpoint resumes; the dock's other rows; the solver.

**CHANGE:** `hydrology.reach_routing` in the schema (default `hms`); `MuskingumCunge.scheme`, a field with the HMS default, dispatching `route()` and a new `route_conserving()` that also returns the end storage; the new kernel module; the scheme threaded through `basin_from_hms`, `load_network`, `engine_basin` and `run._lumped_basin`; `job_hash` drops the key at its default; `normal_depth` of `routing_kernel` made public so both kernels read one section; a `Reach routing` combo in the dock's Hydrology section and the key in `build_job`.

**FILES:** `wadi2d/config/schema.py`, `wadi2d/hydrology/routing.py`, `wadi2d/hydrology/routing_kernel.py` (rename only), new `wadi2d/hydrology/routing_conserving.py`, `wadi2d/hydrology/from_hms.py`, `wadi2d/basin/loader.py`, `wadi2d/basin/job.py`, `wadi2d/run.py`; `plugin/wadi2d_qgis/sections/hydrology.py`, `sections/basin_rows.py`, `job_builder.py`; tests under `tests/hydrology`, `tests/engine/test_handback.py`, `tests/basin/test_model.py`, `tests/plugin`; this folder.

## What was built

**The scheme** (`routing_conserving.py`). Todini's point is that the Muskingum storage equation, discretised with each time level's own parameters on its own side (his eq. 30 and 34),

    2 [k e]' I' + 2 [k(1-e)]' O' - 2 [k e] I - 2 [k(1-e)] O = dt (I' + I) - dt (O' + O)

telescopes over a flood: every term but the two end storages cancels, so the routed volume equals the inflow volume less what the reach still holds, whatever the parameters do from step to step. The kernel solves that equation for O' directly, in the storage form, rather than the coefficient form, so the identity is exact by construction and the test asserts it. The parameters are the corrected ones of his eq. 44 and 49-51: the travel time of a cell is k* = dx / v, the parcel speed, not dx / c, so the steady storage of a cell is the section's A dx; and D* = D / beta with beta = c / v, so the diffusion dt D / C is what it was. The reference flow at the new level is (I' + O')/2 from the first guess O + (I' - I), iterated to the HMS path's own relative tolerance of 1e-3 and capped at the same `Maximum Route Step Iterations`; Todini says twice. Nothing is clipped: a clipped ordinate would break the identity. [Certain, read in the paper's section 3 to 5 and tested here.] One note for a reader of the paper: eq. 52 as printed carries the old level in the numerator of C1; eq. 36 and 37, which it rewrites, carry the new one, and the storage form does not meet the question.

**Same grid, same hydraulics.** Cells, sub-steps and the trapezoid are `MuskingumCunge.grid()` and `normal_depth`, shared with the HMS path. D* reads the top width, as the HMS path's D does.

**Two guards, both keeping the identity**, and both his to re-open. The paper's test channels are mild (S0 1e-4 to 2e-3) and never dry (a 100 m3/s base flow). A Block 2 wadi is steep and starts from nothing, and the raw scheme on HMS's grid (dx = c_index dt, so C* runs from 0.02 at a trickle to 2 at the peak) did two things the paper does not meet (`proto_mct.py`, the prototype that found them, is kept in this folder):

1. **A dip of -97 m3/s, 9 % of R1's peak**, from the weight of the new inflow going negative at low flow (C* + D* < 1), compounding over 57 cells, and -3.4 on an 8 m3/s flood. The HMS path meets the same thing and zeroes that weight, splitting it between the other two, which is one of the two rules that break its continuity (W25). The conserving counterpart here holds D* at or above 1 - C* (`storage_weights`): the new inflow's weight is then never negative, the identity holds because the parameters still sit on their own time levels, and the storage of a cell is untouched, since k* = dx / v is kept. It acts where C* < 1 - D*, which on R1 is below about 250 m3/s; at the design peak (C* 1.4 to 2.0) it does nothing. Rejected first: capping k* at dt / (1 - D*) instead, which zeroes the same weight but changes the storage; it made R4's peak 516 m3/s from a 387 inflow, a shock where the capped and free regimes meet in the rising limb.
2. **A tail that never drains.** With k* = dx / v the storage of a trickle in a 60 m bed is honest and enormous: at 0.01 m3/s a cell of R1 holds its water 3.8 h, and the reach drains as t^-2.5, so after 16 h of dry tail R1 still held 0.15 % of a 16 Mm3 flood and 55 % of a 4,800 m3 one, and the hand-back's drain (`LiveNetwork.settle`, up to 8,192 steps) would book the rest as a defect. The guard is a floor on the parcel speed, `CONSERVING_MIN_VELOCITY` 0.1 m/s, which on R1 engages below about 0.2 m3/s; above it nothing changes. With it R1 drains to 1e-6 m3/s in 153 h at the 5-minute step, inside the drain's reach. The hydraulics are read at no less than `CONSERVING_FLOW_FLOOR`, HMS's own 0.01 m3/s, where the celerity and beta are otherwise 0 / 0.

**Plumbing.** `hydrology.reach_routing` is the one source; `basin_from_hms(..., reach_routing)`, `load_network(..., reach_routing)` and `engine_basin(..., reach_routing)` carry it to `MuskingumCunge.scheme`; `run._lumped_basin` passes `cfg.hydrology.reach_routing` on both the HMS and the generated route. The replication module calls `basin_from_hms` with the default and stays HMS. `job_hash` drops the key when it is `hms`, so a checkpoint made before the setting existed still resumes.

**The dock.** A `Reach routing` combo in section 3, between the subbasin table and the hand-back lines, filled from the schema's enum, words from `ROUTING_WORDS` in `basin_rows.py`, tooltip from the schema's description, default from the schema. The dock writes `hydrology.reach_routing` with whichever is chosen, so the run folder's job says which, and it survives `merge_hms`; a job written by hand without the key runs HMS-faithful.

## Block 2's eight reaches, HMS's own inflows (`block2_reaches.py`, `block2_reaches.txt`, `block2_reaches.json`)

The 100-yr inflow of each reach from `DA_100yr_B1.dss`, 5-minute step, a 160 h dry tail so the conserving tail drains. Identity is inflow volume - outflow volume - storage left, the kernel's own number; drained is the hour after which the outflow stays below 1e-6 m3/s.

| Reach | Cells | Inflow peak, m3/s at h | HMS peak at h | HMS out/in | Conserving peak at h | Conserving out/in | Identity, m3 | Drained, h |
|---|---|---|---|---|---|---|---|---|
| R1 | 57 | 1089.6 at 13.75 | 1080.8 at 15.25 | 0.9992 | 1080.9 at 15.25 | 1.000000 | -3.5e-13 | 153.4 |
| R2 | 19 | 1646.1 at 15.17 | 1640.4 at 15.67 | 0.9996 | 1640.5 at 15.67 | 1.000000 | -4.0e-36 | 94.8 |
| R3 | 32 | 711.8 at 14.08 | 708.6 at 15.08 | 0.9997 | 708.6 at 15.08 | 1.000000 | 5.6e-09 | 112.3 |
| R4 | 21 | 386.9 at 13.0 | 384.8 at 13.92 | 1.0002 | 385.3 at 13.83 | 1.000000 | -7.3e-37 | 87.8 |
| R5 | 2 | 819.3 at 13.67 | 821.0 at 13.67 | 1.0000 | 821.0 at 13.67 | 1.000000 | -3.6e-83 | 45.1 |
| R6 | 10 | 572.2 at 13.25 | 570.9 at 13.5 | 0.9999 | 571.0 at 13.5 | 1.000000 | 9.3e-10 | 64.8 |
| R7 | 38 | 519.5 at 13.5 | 516.5 at 14.67 | 0.9998 | 516.6 at 14.67 | 1.000000 | 2.8e-09 | 117.9 |
| R8 | 17 | 784.7 at 14.33 | 781.4 at 14.92 | 0.9998 | 781.3 at 14.92 | 1.000000 | -5.6e-09 | 88.2 |

On the design floods the two schemes agree: peaks within 0.14 % (R4, the largest), timings to the step. [Likely] That is because at these flows C* sits near 1 and D* is small, where every Muskingum-Cunge is the same box scheme; the HMS rules act at the front and the tail, where the flows are small. The volume the HMS path loses is 0.02 to 0.08 % of these floods on HMS's own inflows; W25's 0.22 % on R1 was on the hand-back case, the grid's crossing as inflow over a 30 h window.

## The short floods, where the HMS path creates or loses water (W25's table, both schemes)

20-minute triangles from zero to zero, routed alone; the lowest ordinate shows what the guards leave of the dips.

| Flood | HMS peak at h | HMS out/in | Conserving peak at h | Conserving out/in | Lowest ordinate, m3/s | Drained, h |
|---|---|---|---|---|---|---|
| Block 2 R1 peak 8 dt 5 min | 1.3 at 7.0 | 1.571 | 0.1 at 70.08 | 1.000000 | -8.59e-81 | 122.7 |
| Block 2 R1 peak 80 dt 5 min | 25.4 at 5.42 | 1.914 | 0.6 at 26.75 | 1.000000 | -6.87e-76 | 123.5 |
| Block 2 R1 peak 800 dt 5 min | 134.2 at 3.42 | 1.184 | 31.5 at 5.58 | 1.000000 | -1.78e-34 | 123.5 |
| Block 2 R6 peak 8 dt 5 min | 3.6 at 1.17 | 1.338 | 0.2 at 6.92 | 1.000000 | -4.5e-25 | 36.7 |
| Block 2 R6 peak 80 dt 5 min | 73.1 at 0.92 | 1.147 | 8.1 at 1.5 | 1.000000 | -9.73e-19 | 37.1 |
| Block 2 R6 peak 800 dt 5 min | 575.8 at 0.58 | 1.045 | 668.8 at 0.58 | 1.000000 | 0 | 36.8 |
| test reach 3 km peak 8 dt 1 min | 6.4 at 0.57 | 1.044 | 2.8 at 0.73 | 1.000000 | -2.81e-44 | 15.4 |
| test reach 3 km peak 80 dt 1 min | 68.4 at 0.35 | 0.987 | 70.6 at 0.35 | 1.000000 | -1.71e-67 | 15.5 |
| test reach 3 km peak 800 dt 1 min | 667.7 at 0.27 | 0.975 | 669.7 at 0.27 | 1.000000 | -2.5e-83 | 15.5 |

**The uncomfortable part.** On a short flood the two schemes are different models, not the same model with a leak fixed. A 48,000 m3 pulse on R1 comes out of the HMS path as 25 m3/s at 5.4 h with 1.9 x its volume; out of the conserving one as 0.6 m3/s over days, because the storage-consistent scheme spreads 48,000 m3 over 26 km of 60 m bed as 3 cm of water moving at a trickle's speed. [Likely] The second is what a kinematic wave of the section does and the first is an artefact; neither has been checked against a flood in a real wadi, where such a pulse infiltrates before it reaches the end. For the design floods of the project the choice moves nothing but the volume line; for a hand-back route fed by a short burst from the grid, or for `routing_defect` reading zero, it is the conserving one.

## Hand-back and the books (`tests/engine/test_handback.py`, `tests/hydrology/test_live_network.py`)

The W25 closed box, 3 km reach, with `reach_routing: conserving`: the grid closes to 1e-5 as before, the whole closes, and `routing_defect` reads 5.2e-6 m3 of 4,800, which is the drain's own cut at 1e-6 m3/s, not the scheme's; the reach's series in the results file equals the conserving route of the line's inflow by hand to 1e-9. The same reach under the HMS path books -218.5 m3 (W25). On the live network with no grid, a 1.8 Mm3 pulse: defect 7e-8 m3, drained, 2,639 m3 still trickling after 8 h.

## Through the real dock (`checks/dock_routing_block2.py`, `log_dock_routing_block2.txt`, `block2_routing_peaks.json`)

Block 2's HMS project (`Basin_1.basin`, `FM_100yr.met`, `Control_1.control`, 48 h) on the dock at 40 m, every subbasin lumped, the five dam lines as design lines; once with the combo as it opens, once set to `Conserving`; QGIS 3.44.8, a throwaway profile, the engine of this checkout through the venv. **29 of 29.** Checked: the combo holds the engine's two schemes with HMS-faithful first and the schema's tooltip; the first run writes `hms` into `job.json` and `config.resolved.json`, the second `conserving`, and nothing else of the job changes; both runs finish and close their mass; every reach's outflow differs between the runs, never gains volume and never goes negative; the five headwater reaches (R1, R3, R4, R6, R7) take the same inflow in both runs to the last digit, the other three take what the scheme above gave them; every dam's network inflow is within 10 % of the HMS-faithful run's. The combo's words and the dock are in `hydrology_routing.png`.

| Reach | HMS peak, m3/s at h | Conserving peak at h | out/in HMS, 48 h window | out/in conserving, 48 h window |
|---|---|---|---|---|
| R1 | 979.3 at 15.17 | 979.4 at 15.17 | 0.9992 | 0.9953 |
| R2 | 1565.8 at 15.67 | 1565.9 at 15.67 | 0.9996 | 0.9968 |
| R3 | 626.7 at 15.08 | 626.7 at 15.08 | 0.9997 | 0.9980 |
| R4 | 324.8 at 13.83 | 326.8 at 13.83 | 1.0004 | 0.9980 |
| R5 | 710.7 at 13.67 | 720.8 at 13.67 | 1.0000 | 0.9998 |
| R6 | 491.4 at 13.42 | 491.4 at 13.42 | 0.9999 | 1.0000 |
| R7 | 445.6 at 14.58 | 445.6 at 14.58 | 0.9998 | 0.9971 |
| R8 | 688.0 at 14.92 | 688.1 at 14.92 | 0.9997 | 0.9973 |

| Dam, network inflow, m3/s at h | HMS-faithful run | Conserving run | 2D design line, both runs |
|---|---|---|---|
| Faydh 01 | 877.9 at 13.25 | 877.9 at 13.25 | 681.4 / 681.4 |
| Bidah 03 | 302.3 at 12.75 | 302.3 at 12.75 | 0.6 / 0.6 |
| R5A | 801.1 at 14.83 | 802.2 at 14.83 | 680.3 / 680.3 |
| R2A | 1277.3 at 14.33 | 1278.2 at 14.33 | 1049.2 / 1049.2 |
| Z4C | 1605.7 at 15.67 | 1605.9 at 15.58 | 1551.7 / 1551.7 |

Three things to read right. The out/in here is over the run's 48 h window, with the reaches still draining their trickle, so the conserving column reads under 1 (R1 holds 0.5 % at 48 h and drains it by 153 h, table above); the HMS column's 0.9992 is its loss. The storm is the one `hms-import` reads from the met file at the control's window, not the depth-area analysis of the replication, so the peaks are not that table's. And the 2D lines are identical in both runs because on the HMS route every subbasin enters the grid at its own outlet and nothing on the grid sits below a lumped reach: the option reaches the grid only through a hand-back route or an inflow taken from an element below a reach, which the hand-back test covers. R5's +1.4 % is not R5's own: it is not a headwater reach, and takes what R4 and the junction above gave it.

## Tests

`python -m pytest -q --ignore=tests/dock` on the branch with the project venv: **1,752 passed, 0 failed, 0 skipped** (`suite_log.txt`). New: `tests/hydrology/test_conserving_routing.py` (27, no data), `tests/hydrology/test_conserving_block2.py` (10, Block 2 data), one each in `test_live_network.py`, `test_handback.py`, `tests/basin/test_model.py`, `tests/plugin/test_contract.py`, `test_job_builder.py`, and the routing combo in the headless QGIS smoke test. `uvx ruff check` clean.

## What was not tested, and what is weak

- **The guards are mine, not Todini's.** The velocity floor and the diffusion floor are named constants with their reasons, measured on Block 2's sections at HMS's grid; neither has a gauge behind it. A reach much milder than Block 2's (D* near 1) never meets the diffusion floor; a reach with a narrow bed drains without the velocity floor. Both are in `routing.py`, one line each to change.
- **A dip remains where C* > 1 + D*:** the test reach, 800 m3/s falling to zero in two 5-minute steps, reads -0.11 m3/s, 0.014 % of the peak, the region where any Muskingum-Cunge weights the old outflow negatively. The test tolerates 2e-4 of the peak and the Block 2 floods read round-off. A held re-entry would push that into the grid as a negative source; none appeared in the hand-back test.
- **The drain of a long reach is slow:** R1 takes 153 h to 1e-6 m3/s, 1,840 lumped steps, inside `LiveNetwork`'s 8,192 but at the cost of reruns on a series that long. A 1-minute step on a reach like R1 would exceed it and book the trickle as a defect.
- **Not run:** the conserving variant on a generated basin through the dock (only through `load_network` and the engine tests), an ARF study, a resume with the conserving reach in the network, the GPU hand-back case. Run times are not quoted: the card was shared.
- **The dock combo is enabled under a generated basin and an HMS project alike;** `wadi2d basin` receives the key too and ignores it.

## How to rerun

- Tables: `.venv\Scripts\python "W29 conserving routing\block2_reaches.py"` (reads the Block 2 HMS project, writes `block2_reaches.json`).
- Dock: `powershell -File tests\dock\run_check.ps1 "<repo>\W29 conserving routing\checks\dock_routing_block2.py" <throwaway folder> -Copy "<repo>\W29 conserving routing"`; QGIS 3.44.8 with a throwaway profile; the log and `block2_routing_peaks.json` land beside this file.
- Suite: `.venv\Scripts\python -m pytest -q --ignore=tests/dock`, then `git restore "W1 research and design note/validation/hms_replication.md"`.
- The prototype that chose the guards: `.venv\Scripts\python proto_mct.py` with the repo on `PYTHONPATH`; set `CAP` to `"d"`, `"k"` or `None` and `VMIN` to see each.
