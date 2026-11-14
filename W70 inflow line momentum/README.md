# W70 inflow line momentum

**Status (2026-11-14): built on `feature/inflow-momentum` (off `feature/fast-products` at `a48d823`), not merged, nothing pushed.** A `flow` line (W61) now brings its water in moving. `flow.momentum`, on by default. Before this, the water entered as volume at rest. That made the depth next to the line too high, and a jet lost its direction.

## What the published models do

- **HEC-RAS 2D.** A Flow Hydrograph line sits on the 2D area's edge. Its flow is shared by conveyance under a normal-depth surface set by the energy slope. RAS treats the line as a flux boundary: the water crosses the boundary faces, so the face momentum equation sees it moving. Sources: [Freese and Nichols](https://www.freese.com/blog/considerations-for-hec-ras-2d-flow-hydrograph-boundary-conditions/) and the [RAS Solution forum](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/eg-slope-for-distributing-flow-along-bc-line/). [Likely] I could not reach HEC's own manual pages from this session (404), and the face treatment itself is not published.
- **TUFLOW HPC.** A QT line is, "internal to the software", "a HX boundary connected to 1D storage node". That is a level boundary, so the flow enters through faces under the momentum equation. HPC also holds "a uniform total energy level along the boundary", correcting the inflow cells by (v̄² − v²)/2g so the inflow does not recirculate. Its quadtree carries the transverse momentum ("Method B", parallel inertia). An SA region, by contrast, is a volume source with no momentum. Source: [TUFLOW Classic/HPC manual, section 8.2.2](https://docs.tuflow.com/classic-hpc/manual/2026.3/07-Boundaries-and-Initial-Conditions.html) and [8.2 Solver Specific Considerations](https://docs.tuflow.com/classic-hpc/manual/2025.2/BC-Solver-2.html). [Certain] on the quoted words.
- **So:** W61's volume at rest is TUFLOW's SA form. Both models' line boundaries bring the water in with momentum.

## What was built: the form closest to the staggered scheme

Our line's cells stay interior (W61), so there is no boundary face to carry a flux. The equivalent is a momentum source.

- **The source.** Each cell's share `Q_c` brings `Q_c U_c n` of momentum, with:
  - `n` the line's unit normal at the cell;
  - `U_c = Q_c / (w_c hbar_c)`, where `w_c` is the length of line in the cell and `hbar_c` is its sub-grid mean depth at the level that shared the flow (the normal-depth surface, or the cell's own level under `conveyance`);
  - `U_c` capped at `numerics.u_max`.
- **Where it goes.** The source is shared half to each of the cell's two faces in x and in y. That is the scheme's own average of a cell quantity to a face. A face against a wall takes nothing.
- **How it enters the step.** Before every step, `m += dt * S / L`. That is the face update `us = (m - dt*flux/L)/Abar` with the source on its right side. It runs as one indexed add on `mx` and `my` (`wadi2d/solver/momentum.py`), on CPU and GPU alike. The face kernels are untouched.
- **First attempt, rejected.** The whole `Q U` on the downstream face over-drove the cell: the line's column read 0.287 m against 0.390 m downstream, on the steep case below. The scheme's centred discharge at a line cell is already half of Q, so the full source double-counted. The half-and-half share gives a whole `Q U` against a wall, as a boundary face would.
- **Direction.** `flow.direction`: `auto` (default), `left` or `right` of the line as drawn. `auto` looks two cells either side of the line:
  - if one side has clearly more active cells, the water goes there (a line on the domain's edge flows into the domain);
  - otherwise it goes to the lower ground.
- **Refresh.** The source is refreshed with the source vector every `run.source_every_s`, from the same window's shares. A window with no flow brings no momentum.
- **Scope.** Uniform step only. With the quadtree or local time stepping, a tile's step differs from the global one, and faces at a level edge are stepped by other lists.
  - A line that sets `flow.momentum: true` in so many words is refused, by name.
  - A line left at the default runs at rest, as in W61, with a warning.
  - Strip jobs (W45, W46) run the uniform step and take the momentum: the strip keeps squares under every boundary line, so the line's cells are always squares. The strip and polygon kernels are not touched.

## Results (CPU; `study.py`, `study.json`)

**Rows "plane" and "steep": a line across the west edge of a channel with walls north and south, steady flow.** The ratio is the depth of the line's own column over the depth 250 m downstream.

| Case | At rest (W61) | With momentum (W70) | Depth downstream, both |
|---|---|---|---|
| Plane 1 %, 96 m wide, 20 m3/s, Fr 0.62 | 1.130 | 1.0014 | 0.2158 m |
| Steep 3 %, 48 m wide, 50 m3/s, Fr 1.20 | 1.398 | 1.0022 | 0.3899 m |

- The steep case's profile from the line, with momentum: 0.391, 0.390, 0.390, 0.390 m.
- At rest: 0.545, 0.458, 0.413, 0.398 m.
- The bump against the wall at the domain edge is gone. The depth downstream does not move.

**Row "jet": a flat dry plain, 400 x 400 m, 4 m cells, n 0.01.** 8 m3/s enters through a 16 m line on the west edge. At the line that is normal depth 0.102 m at 4.89 m/s, Fr 4.9. The plain is read at 91 s.

The hand estimate:
- A jet's edge cannot spread faster than 2c across a flow running at U. The half-width is therefore at most 8 + x · 2/Fr.
- Friction takes the jet's speed down over an e-folding length h / C_f of about 49 m.

| Measure | At rest | With momentum | Estimate |
|---|---|---|---|
| Discharge east through x = 20 m, share of Q | 0.88 | 0.97 | about 1 |
| RMS half-width of that discharge at 20 m | 18.0 m | 9.2 m | at most 16.2 m |
| Discharge east through x = 40 m, share of Q | 0.73 | 0.91 | |
| RMS half-width at 40 m | 26.8 m | 12.5 m | at most 24.4 m |
| Discharge east through x = 80 m, share of Q | 0.31 | 0.68 | falls past h/C_f, 49 m |
| Front east / front sideways | 102 / 82 m | 134 / 70 m | |

- With momentum, the jet keeps its direction inside the estimate's envelope.
- At rest, the water spreads sideways along the wall beyond the envelope.
- Volume enters to 1e-8 in every run.

**W61's ten tests**, rerun with momentum on by default: 10 of 10.
- A CSV hydrograph enters to 1e-6.
- Steady flow reaches normal depth within 3 % under `normal_depth` and under `conveyance`.
- The 45-degree line passes.
- The quadtree runs at rest with the warning.
- The strip corridor beside the line passes.

**GPU, one short job** (`gpu_check.py`, `gpu_check.json`): the steep case on the GPU gives the CPU's profile to the fourth decimal. The line-over-downstream ratio is 1.00221 on both.

**Old numbers to the digit** (`old_numbers.py`). Two jobs were run on `a48d823` and on this branch, and every array in `results.h5` (27 per job) and every series CSV was hashed with sha256. The two digests are identical (`old_numbers_base_a48d823.json`, `old_numbers_branch.json`):
- **A job with no flow line:** normal and free boundaries, a point inflow and uniform rain.
- **W61's flow line with `momentum: false`:** it gives W61's numbers.

By construction, a job with no flow line never sets a source (`test_a_job_without_flow_lines_sets_no_momentum_source`), and the stepper's one added line is a `None` check. A job hash without flow lines is unchanged (W61's rule). A job with a flow line hashes the two new fields, so a W61 checkpoint of a flow-line job does not resume. That is right, since the water differs.

## Tests (`tests/engine/test_inflow_lines.py`, 15 of 15)

W61's 10, plus 5 new:
- The steep bump at rest (over 1.3) and with momentum (1.00 within 0.01).
- The supercritical jet: over 0.9 of Q east inside the envelope at 20 m, and at least 0.05 more than at rest.
- `momentum: true` on a quadtree refused by name.
- A job without flow lines sets no source.

The contract's frozen schema sample is regenerated with the two new fields.

## Not done

- The quadtree and local time stepping do not take the momentum. They are refused when asked, and run at rest with a warning by default. The kick would have to follow each tile's own step and the level-edge face lists.
- TUFLOW's uniform-energy correction along the line is not built. Our line shares by normal depth, HEC-RAS's way, and carries the momentum of that share.
- Not rerun: W61's Bidah dock case, whose line on the domain edge left 4.3 m of water against the wall. The channel cases above show the mechanism gone, but the Bidah number itself is not remeasured. No dock control for `momentum` or `direction`: they are job fields with their defaults.
- Not raced against HEC-RAS 6.6 on the same line.
