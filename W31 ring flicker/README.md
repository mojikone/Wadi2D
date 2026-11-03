# W31 ring flicker

**Status (2026-11-02): cause found, not fixed. The flicker of `S5_ring` and `S11_ring` is a self-excited surge of the pond that forms where a lumped hydrograph enters the 40 m grid: S5's 630 m3/s go into two gorge cells, which stand 9 m deep at the peak, and the water in them surges with a period of 11 s at 9 m and 30 to 37 s at 3 m; a line whose faces run between or round those cells reads the surge, swinging up to 300 m3/s in a minute. The refresh split is innocent: the flicker is unchanged with all of the inflow in one cell (`inject_min_depth` 5 m), with a refresh of 10 or 120 s, at half the time step, and on the CPU twin, which surges with the same period and swing; two GPU runs with the same water are bitwise identical, so it is deterministic. The surge is also what parts the CPU twin from the GPU on the hybrid: the twins separate first at the S5 ring, hour 9, and the dam lines stay within 0.16 % on the 15-minute peak. No fix is a few lines: see "What a fix would take". A second finding outranks the first: a ring drawn on a lumped subbasin's edge passes about half its hydrograph (S5 0.50, S11 0.48, S6 0.49, S14 0.00, S1 1.75 x, S2 2.32 x), because the inflow's cells straddle the ring; the hydrograph of record is `series/network_<name>.csv`, not the ring, and not its 15-minute mean.** Branch `feature/ring-flicker`, no engine or plugin code changed.

The finding was recorded in `W20 storm section/README.md` with the guess that the inflow's split among its cells, decided anew at each refresh, was the cause. The guess was wrong.

## The cause, with the evidence

[Certain] **Reproduced without the dock.** `s02_block2_40m.py w20` runs the W20 scenario's job through `run_job`: the validation job `c10_A74_h100` at 40 m with the HMS project imported as the dock merges it, 36 h, series every 5 s. `S5 ring` reads 464.9 m3/s at the minute, 332.6 as a 15-minute mean, and steps by up to 222 m3/s from one minute to the next; `S11 ring` 313.3, 248.5 and 124.3. The other fourteen lines step by at most 34 m3/s on peaks of 300 to 1,600 (W20 through the dock: 480.2, 325 and 106.7 at S5).

[Certain] **Deterministic.** `w20` and `w20_points` carry the same water and differ only in the series they record. At the 28,488 sample times they share, every value of `S5 ring` and of `Z4C` is bitwise the same. The 2.2 % between the two W20 runs is where a one-minute sample lands on an 11-second sawtooth, nothing more.

[Certain] **Not the refresh split.** `lowest_only` sets `inject_min_depth` to 5 m, so every cell counts as dry and the whole hydrograph goes into the one lowest cell at every refresh: S5 ring still reads 439.8 / 323.7 with steps of 199. `refresh_10` and `refresh_120` leave the period at 11.6 and 11.3 s against 11.5. Nothing about the split or its timing reaches the flicker.

[Certain] **Not the time step.** `cfl_half` doubles the steps (464,448 against 234,735): period 11.6 s, swing 327 against 307 m3/s. The surge is a mode the discrete equations hold, not a step artefact.

[Certain] **The shape and where it lives.** At 1-second samples the ring reading is a sawtooth: it climbs from about 230 to 450-500 m3/s over 9 s and drops back in 2 s. Point series at the two cells that take S5's inflow (cell (568, 413) inside the ring, bed 311.24 m; cell (569, 413) outside, bed 310.70 m, the lowest) stand 9.0 m deep at the peak and move against each other (correlation -0.78). The period follows the depth through the hydrograph: 37 s at 2.5 m (hour 10), 17 s at 4.8 m, 11.2 s at 9.0 m (hour 13.5 to 14), back to 30 s at 3 m (hour 19). At S11 the two cells stand 4.5 and 5.1 m deep and the period is 20 s; at S6, 2.7 m deep and steady, the two cells move together (correlation +0.97).

[Likely] **Why there and not elsewhere.** The S5 cells sit in a pocket: the cells either side rise 13 to 25 m to the north and 20 to 50 m to the south, and the thalweg falls only 0.6 m across the three cells before the exit. A hydrograph that enters with no momentum (design note section 8) into a 40 m cell at 630 m3/s raises that cell 0.4 m/s; the pocket holds the water 9 m deep, and the surge between the two cells is what the ring's faces, which run between them, read. S6 takes 327 m3/s in an open mouth, 2.7 m deep, and does not surge. [Guessing] Whether real water in such a pocket surges the same way is not known; the point source without momentum is the model's own construct, and no gauge sits at a gorge mouth.

[Certain] **No synthetic case surged.** Twenty-four cases on a V valley at 40 and 20 m with a steady 400 m3/s inflow (`s01_smallest_case.py`) are all steady to the last digit, a 1:1 gorge and a gorge with a sill below the inflow included: the surge needs the real pocket, and the smallest case that shows it is the Block 2 job at 40 m. The synthetic cases show the second finding instead: a ring whose edge runs through the four inflow cells reads 201.19 of the 400 m3/s, the share injected inside it; one cell inside, 400; all to the lowest cell, which lies outside, 0; the straight line 1 km below reads 400 in every case.

## The second finding: a ring on a subbasin edge does not read its hydrograph

The rings of the validation job are the simplified polygon edges of the lumped subbasins, and HMS puts each outlet on that edge (0 to 7 m from the ring). The cells within `inject_radius` of the outlet lie on both sides of the ring, so the ring passes only the share injected inside it, plus the surge:

| Subbasin | Lumped peak, m3/s | Ring, 1-min peak | Ring, 15-min peak | Ring volume / lumped volume | Inflow cells inside the ring |
|---|---|---|---|---|---|
| S5 | 629.5 | 464.9 (0.74 x) | 332.6 (0.53 x) | 0.50 | 1 of 2 |
| S11 | 492.7 | 313.3 (0.64 x) | 248.5 (0.50 x) | 0.48 | 2 of 2 |
| S6 | 326.9 | 169.6 (0.52 x) | 161.9 (0.50 x) | 0.49 | 1 of 2 |
| S14 | 447.9 | 2.2 | 2.0 | 0.00 | 0 of 2 |
| S1 | 549.2 | 986.5 (1.80 x) | 984.3 | 1.75 | 0 of 1 (shares J1 with S2) |
| S2 | 441.6 | 986.4 (2.23 x) | 984.3 | 2.32 | 1 of 1 (shares J1 with S1) |

The W20 advice, "a 15-minute mean is the fair number there", is withdrawn: at S5 it reads 0.53 of the hydrograph. The number of record for a lumped subbasin is its series in `series/network_<name>.csv`; a 2D line near an inflow reads the pond, not the hydrograph. The dam lines are unaffected: Z4C 1593.0, R2A 1101.5, R5A 752.3, Faydh 01 699.1 as in W20 within the sampling.

## Experiments

Block 2 hybrid at 40 m, `s02_block2_40m.py`, GPU unless said; the reading is the dock's: 1-minute peak / 15-minute mean peak / largest minute step, m3/s. Z4C and R2A are dam lines.

| Variant | What changed | S5 ring | S11 ring | Z4C | R2A | Period at S5 peak |
|---|---|---|---|---|---|---|
| `w20` | nothing | 464.9 / 332.6 / 222 | 313.3 / 248.5 / 124 | 1593.0 / 1589.7 / 25 | 1101.5 / 1090.0 / 34 | 11.5 s |
| `w20_points` | series every 1 s, points at the inflow cells | 481.4 / 388.6 / 197 | 319.8 / 250.0 / 131 | 1593.0 / 1589.7 / 25 | 1102.3 / 1090.2 / 26 | 11.5 s (bitwise as `w20`) |
| `lowest_only` | `inject_min_depth` 5 m: no split, one cell | 439.8 / 323.7 / 199 | 5.8 / 3.8 / 4 (both cells inside; ring moot) | 1592.9 / 1589.6 / 25 | 1098.3 / 1091.2 / 28 | 11.5 s |
| `refresh_10` | `source_every_s` 10 | 462.9 / 325.4 / 228 | 327.2 / 248.3 / 124 | 1592.8 / 1589.5 / 26 | 1102.9 / 1091.6 / 33 | 11.6 s |
| `refresh_120` | `source_every_s` 120 | 498.2 / 341.3 / 280 | 270.8 / 230.7 / 107 | 1592.8 / 1589.5 / 25 | 1102.5 / 1092.1 / 33 | 11.3 s |
| `cfl_half` | `cfl` 0.225, twice the steps | 485.9 / 339.8 / 229 | 335.0 / 249.1 / 140 | 1593.0 / 1589.9 / 25 | 1103.4 / 1092.5 / 27 | 11.6 s |
| `radius_100` | `inject_radius` 100 m | 549.3 / 342.3 / 311 | 173.2 / 164.9 / 14 | 1612.4 / 1609.1 / 25 | 1250.2 / 1235.0 / 35 | 13.7 s |
| `dx20` | 20 m cells | 201.0 / 166.9 / 62 | 200.7 / 199.8 / 5 | 1607.3 / 1604.2 / 23 | 1217.1 / 1213.6 / 13 | 13.2 s, swing 89 on a mean of 160 |
| `cpu` | the Numba twin, 234,750 steps | 495.7 / 333.3 / 261 | 322.5 / 245.1 / 125 | 1592.8 / 1589.6 / 25 | 1103.5 / 1091.7 / 29 | 11.4 s, swing 307 |

`radius_100` is not a fix: cells 100 m from an outlet lie across divides and in other wadis, so R2A rises 13 %, R5A 10 %, Faydh 01 6 %, and the S1 ring falls to 241. A fix must follow the channel, not a circle.

At 20 m the S5 pond still surges, with a period of 13 s and a swing of 89 m3/s on a ring mean of 160; S11 is steady there. The rings pass different shares at 20 m (S5 ring 201 on 630, S6 ring 48 on 327) because the cells within 30 m of the outlet are other cells: one more sign that a ring on a subbasin edge reads the footprint of the injection, not the hydrograph. The dam lines move between 40 and 20 m as the hybrid always has (R2A +10.5 %, R5A +4.4 %, Z4C +0.9 %, Faydh 01 -3.1 %); that is the cell size, not this finding, and design points run at 10 m by the standing rule.

Smallest case, `s01_smallest_case.py`, CPU, a V valley at 40 m, a steady 400 m3/s inflow at a lattice corner so four cells share it, a closed ring whose east edge runs through those four cells, a straight line 1 km below; readings after the valley has filled.

| Case | What changed | Ring | Straight line | Any step |
|---|---|---|---|---|
| `base`, `base_again` | nothing; bitwise identical twice | 201.19 | 400.00 | none |
| `two_cells`, `one_cell` | inflow at a face, at a cell centre inside | 201.68, 400.00 | 400.00 | none |
| `ring_below` | ring 3 cells below the inflow | 400.00 | 400.00 | none |
| `refresh_10`, `_60`, `_120` | `source_every_s` | 201.19 | 400.00 | none |
| `lowest_only` | `inject_min_depth` 5 m; the lowest cell lies outside | 0.00 | 400.00 | none |
| `no_mirror` | `mirror_dry_faces` off | 201.20 | 400.00 | none |
| `dx20` | 20 m | 205.94 | 400.00 | none |
| `thalweg_off`, `steep_bank`, `steep_bank_lowest`, `steep_bank_refresh_10` | thalweg 10 m off the corner, banks 10 % | 201.12, 203.51, 0.00, 203.51 | 400.00 | none |
| `gorge`, `gorge_lowest`, `gorge_refresh_120`, `gorge_cfl_half`, `gorge_ring_below`, `gorge_dx20` | 1:1 banks, about 9 m deep | 206.79; ring below 400.00; 20 m 208.19 | 400.00 | none |
| `pocket`, `pocket_cfl_half`, `pocket_one_cell` | the gorge with a 3 m sill two cells below the inflow | 199.38, 199.32, 400.00 | 400.00 | 0.03 at most |

In `gorge_lowest` the water stands deeper than 5 m, so every cell counts as wet and the split is back; the case tells nothing beyond `gorge`. The smallest case that shows the surge is therefore the Block 2 job itself at 40 m: a prismatic gorge, with or without a sill, does not surge, so the surge needs the real pocket's sub-grid tables, which a plane and a sill do not give.

## What a fix would take

None of these is a few lines, and none leaves other runs unchanged, so nothing is built:

1. **A momentum source.** Inject the hydrograph with the velocity it would have along the thalweg, so the water leaves the cell instead of ponding. Needs a direction per inflow (from the HMS reach, the basin model or the accumulation grid), a face momentum term in both kernels, the forcing, the schema and tests, and a validation case of its own, since no case today checks momentum at an inflow. Days of work; every hybrid peak near an outlet would move.
2. **Spread the inflow along the channel.** Put the hydrograph into the N cells upstream of the outlet along the thalweg, so each cell takes a share small enough not to pond. Needs the stream line through the outlet (the basin model's reaches or `W26`'s stream finder); a circle does not do it (`radius_100`). Peaks at the outlets would change by an amount only a run can tell.
3. **Read it right instead.** Warn at preflight when a line's faces touch an inflow's cells, naming the line and the inflow, and have the dock show `series/network_<name>.csv` as the hydrograph of a lumped subbasin. About twenty lines and a test; no number changes. This does not stop the surge; it stops the wrong reading.

Rule 9 of his standing instructions applies: these alter or add engine behaviour, so they wait for his word.

## The CPU twin against the GPU, a lead for the combinations test

The combinations test found the Block 2 hybrid at 80 m diverging between the twins (101,421 against 101,432 steps, Faydh 01 -2.5 %, a ring -23 %), each repeating itself to the digit, while 13 Bidah runs, which have no lumped inflow, match step for step. The guess there was the inflow's wet-cell test. What this iteration says:

- [Certain] The inflow path runs on the host in both twins and is the same code: `Forcing.rate` reads the backend's `d` at the inflow cells as float32 numpy, tests `depth >= inject_min_depth` on that array, weights in float64, divides by a float64 sum, casts the rate to float32 and hands the same `src` vector to either backend (`wadi2d/forcing.py`, `Injection.share`, `Forcing.rate`; `Model.set_source_cells`). No reduction order and no cast differs between the backends; the only backend-dependent input is the state `d` it reads.
- [Certain] With an inflow and no surge the twins agree: `base` against `base_gpu` (four inflow cells, 400 m3/s) 3,690 against 3,691 steps, ring and straight line equal at every sample to the 0.001 m3/s the CSV prints; `gorge` against `gorge_gpu` (9 m deep) 7,777 steps both, equal to the same print. The inflow path is not what separates the twins.
- [Likely] What separates them is the surge: a self-excited oscillation amplifies the rounding that already differs between the backends (the GPU kernels compile with `--use_fast_math`, `wadi2d/solver/gpu/backend.py` line 82: fused multiply-add, approximate division and square root, denormals flushed; Numba has none of it), so the pond's phase drifts apart and a line near it reads a different point of the sawtooth; a dam line far below reads the same hydrograph within the sampling. Bidah has no inflow pond and stays matched.
- [Certain] The 40 m hybrid on the CPU twin (`cpu`) bears this out. The surge is there with the same period, 11.4 s at S5 and 20.4 s at S11, and the same swing, 307 m3/s; the twin takes 234,750 steps against the GPU's 234,735. The twins part first at the S5 ring, at hour 9.0, when the pond begins to surge at 20 m3/s, and by more than 1 m3/s from hour 10.2; Z4C first differs by 0.01 m3/s at hour 13.8 and never by more than 0.47, R2A never by more than 1.7. The 15-minute peaks agree at every dam line within 0.16 % (Z4C 0.9999, R2A 1.0016, R5A 1.0001, Faydh 01 0.9987, S1 ring 1.0001), while the one-minute peaks at the surging rings differ by 6.6 % at S5 and 2.9 % at S11: the sawtooth's phase. So the 80 m divergence is the same thing: a deterministic surge at the inflow ponds, present on both twins, whose phase takes the backends' rounding apart; it is not an operation in the inflow path, and nothing there needs a cast or a reduction order changed.

## Not tested

- Whether the pocket at S5 holds 9 m of water in HEC-RAS on the same ground and inflow, which would say whether the pond is the terrain's or the point source's.
- A line through an inflow on a generated basin (`W27`), where the outlets sit at junctions found from the DEM, not on polygon edges.
- The frames run of W20 (gridded rain): the water is the same, as W20 showed, and nothing here depends on the rain.
- The dock itself: everything ran through `run_job`; the readings use the dock's own rule (`W20 storm section/dock_storm.py`, `roughness`).

## Rerun

From the repository root, with the project venv:

```
"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" "W31 ring flicker\s01_smallest_case.py"            # every synthetic case, CPU, results_s01.json
"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" "W31 ring flicker\s02_block2_40m.py" w20 w20_points lowest_only refresh_10 refresh_120 cfl_half radius_100 dx20 cpu
"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" "W31 ring flicker\s03_injection_cells.py"           # the inflow cells against each ring, needs the s02 grid cache
"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" "W31 ring flicker\s04_waveform.py" w20_points 0.5    # period, depths and their correlation, half an hour round the peak
"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" "W31 ring flicker\s05_terrain_probe.py"             # the bed round the S5, S11 and S6 inflow cells
```

`s02` needs the Block 2 folder and its HMS project (read-only). The run folders under `runs/` are not in git; the series of every line and the result files beside the scripts are. The GPU was shared with other agents throughout, so no run time here is a finding.
