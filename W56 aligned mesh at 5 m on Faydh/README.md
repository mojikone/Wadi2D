# W56 aligned mesh at 5 m on Faydh

**Question:** at 20 m and 10 m the centre mesh (`strips.generator: centres`) reads above the converged Faydh 01 peak at the dam axis. Does 5 m bring it down to the converged peak (ordinary mesh error), or does it stay about 2 % high (a bias)? Before W52's centroid fix the tiling guard refused the 5 m centre mesh, so it had never run.

**Answer: it converges.** The 5 m centre mesh ran with no guard refusal and reads -0.6 % against the 5 m squares. The error goes +3.5 %, then +2.1 %, then -0.6 %: refinement removes it, and no 2 % bias is left.

## Set-up

- Engine: commit `7f2fb3e` (tip of `feature/fast-products`), branch `check/faydh-centres-5m`, run as `python -m wadi2d.engine.cli` from this worktree, GPU, one job at a time.
- Jobs: W47's race jobs (`depth_carry/race/ce20`, `ce10`, `sq5`) copied with `tables.face_conveyance: local_radius` (the default on this branch), as W49's `race_local_radius.py` did, each with its own cache. `ce5` is `ce10` with `grid.dx` 5 and `strips.along` 5, nothing else changed. Script: `race_5m.py`. Jobs and the result table are in `runs/` (`ce*.json`, `sq5.json`, `race_5m.json`).
- Rain on grid, 163.1 mm over 24 h, 16 h simulated, Manning 0.05. The peak is the largest absolute discharge in `series/line_axis.csv` (2-minute series).

## Results

| Run | Cells | Dam-axis peak (m3/s) | Against 5 m squares | Tables (s) | Solver loop (s) | Wall (s) |
|---|---|---|---|---|---|---|
| Centres 20 m | 165,249 | 1,859.6 | +3.53 % | 87 | 57 | 146 |
| Centres 10 m | 706,387 | 1,833.3 | +2.06 % | 110 | 241 | 354 |
| **Centres 5 m** | 2,920,100 | **1,785.1** | **-0.62 %** | 206 | 809 | 1,023 |
| Squares 5 m (reference) | 3,021,024 | 1,796.2 | 0 | 69 | 892 | 965 |

- The 5 m squares give W49's 1,796.2 m3/s (`race_faydh_top_fix/sq5`) to the digit, so all four runs sit on the same engine as W49's reference. The 20 m and 10 m centres match W52's +3.5 % and about +2 %.
- At 5 m the centre mesh has 21 corridors, 27,633 aligned cells and 68,639 transition polygons. It ran without a tiling-guard refusal. Mass error in every run is between 1.4e-8 and 2.0e-8.
- Hydrograph volume through the axis is 9.76 to 9.81 Mm3 in all four runs.

## Verdict

[Certain] By the stated test, the centre mesh converges on Faydh 01. At 5 m it lands 0.6 % from the 5 m squares, inside 1 %, after +3.5 % at 20 m and +2.1 % at 10 m. The excess at 20 m and 10 m is coarse-cell error that refinement removes, not a bias that stays.

[Likely] The two 5 m meshes now bracket the answer. The squares converge from below (W46/W49) and the centres have crossed from above to 0.6 % under them, so the converged peak lies near 1,785 to 1,800 m3/s. The sign change rules out a Richardson extrapolation from the centre sequence.

## Also seen

Every run gives the same warning: water stood 8.5 to 12.3 m deep against the domain edge near 424,370 / 2,726,845. The edge is a wall, and the warning comes from the domain polygon, not from the mesh. It is far upstream of the dam axis and was not looked at further.
