# W61 inflow hydrograph lines

**Status (2026-11-14): built on `feature/inflow-lines` (off `feature/fast-products` at `c7c08e3`), not merged, nothing pushed.** The 2D model takes a flow hydrograph across a line, HEC-RAS's "Flow Hydrograph" boundary condition: a boundary of kind `flow`. The second of the RAS-side items of his standing order of 2026-11-14 (dam breach in 2D is the other, not done here).

## What it does

- **Job:** `boundaries: [{kind: flow, coordinates: [...], flow: {file | times_s + flows, record, time_unit, time_format, start, distribution, slope}, name}]`. The file is a CSV (time in minutes from the run's start, or dates with `start`) or a DSS flow record, an HMS run's say, read through the W54 station-record readers (`wadi2d/io/series`); cfs is converted. A table in the job does instead of a file.
- **Cells:** the line picks cells as every boundary does (`cells_along`, `snap_m` 150 m for a line drawn just off the domain, the `min_share` warning). The cells are not boundary cells: they stay in the model, their level is not overwritten, and the edge behind them stays a wall.
- **Entry:** the hydrograph enters as volume through the source vector, refreshed every `run.source_every_s` with the window's exact integral of the piecewise-linear table, as a point inflow does. So the uniform grid, the quadtree and a strip job take it alike, and CPU and GPU from one source (the source vector is built on the host).
- **Sharing across the line**, `distribution`:
  - `normal_depth` (default, HEC-RAS's rule): each refresh, Q and the energy slope `slope` (0.005 by default) give a normal-depth water surface across the line; each cell takes its conveyance under it, `w / n * hbar^(5/3)`, with `w` the length of line inside the cell (a snapped cell its own width), `n` the cell's Manning, `hbar` the cell's own sub-grid mean depth at that level. A cell whose ground stands above the surface takes nothing.
  - `conveyance`: the same weight at each cell's own water level; the normal depth only while the line is dry.
- **Momentum: none.** The water enters with zero momentum, as the point inflows do. A momentum source normal to the line would be a change to three kernels (tiles, polygons, GPU), which the old-numbers rule and this brief's scope argue against; not built.
- **Strips:** the centres generator already keeps squares under every boundary line, so its corridors stop short of a flow line. A line over squares that a W45 corridor replaced is refused by name ("... crosses the cells of an aligned corridor ..."), since its flow would land in the squares beside the corridor.
- **Dock:** the Boundaries table (W18) offers `flow` from the schema, with a fourth column "Hydrograph file" (a file chooser, CSV, TXT or DSS) enabled only on flow rows, or a `file` field in the layer; a flow line with no file stops the run in words; a layer of flow lines only draws a note that nothing can leave the domain.

**HEC-RAS's rule, the source:** the 2D manual states that a flow hydrograph line needs an energy slope, used to compute a normal depth along the line from the flow and the terrain each step, and that the flow is distributed by conveyance among the cells whose terrain lies below that surface. I could not reach the manual itself in this session; the rule is as summarised by Freese and Nichols, [Considerations for HEC-RAS 2D Flow Hydrograph Boundary Conditions](https://www.freese.com/blog/considerations-for-hec-ras-2d-flow-hydrograph-boundary-conditions/), and the HEC-RAS forum ([EG slope for distributing flow along BC line](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/eg-slope-for-distributing-flow-along-bc-line-2d/)). [Likely] that this is the rule; HEC-RAS's exact conveyance (its face tables, not a cell's mean depth) is not published, so the share across a real line will differ in detail from RAS's.

## Tests (CPU, `tests/engine/test_inflow_lines.py`, 10 of 10; plugin 152 of 152)

A plane 400 x 96 m falling 1 % east, walls north and south, 4 m cells, Manning 0.04, a free outlet at the east end, the flow line across the west end.

| Case | Number | Rule |
|---|---|---|
| CSV hydrograph 0-2-2-0 m3/s over 20 min, 1,800 m3 | in 1,799.99997 m3 (-1.7e-8), balance -3.2e-8 | to 1e-6 |
| Steady 20 m3/s, `normal_depth` | mean depth at 250 m 0.2252 m against normal depth 0.2252 m (1.000) | within 3 % |
| Steady 20 m3/s, `conveyance` | 0.2252 m (1.000) | within 3 % |
| Line at 45 degrees across the channel | 0.2259 m (1.003), volume in to 5e-9 | within 3 % |
| Quadtree (8 m coarse, line on fine cells) | volume in to 1e-6, balance under 1e-5 | passes |
| W45 corridor beside the line | volume in to 1e-6, balance under 1e-5 | passes |
| W45 corridor under the line | refused, exit 2, by the line's name | passes |
| Normal-depth share, unit | flat cells share equally; a raised cell takes its conveyance share; Q met to 1e-9 | passes |
| An old job's hash | boundaries hashed without `name` and `flow` | unchanged |

**Old jobs to the digit:** one job with a free and a normal boundary, a point inflow and rain, run on `c7c08e3` and on this branch: the same hash, 1,289 steps each, the line series file byte for byte and all five maxima arrays identical. The existing forcing, run, physics, strip-run, transmission, contract, boundary-row and job-builder tests pass; the contract's frozen schema sample is regenerated and its kind list gains `flow`.

**Through the real dock** (`dock_flow_line.py`, QGIS 3.44.8, throwaway profile, Bidah ground at 20 m, 1 h), 14 of 14 (`log_dock_flow_line.txt`): the table offers `flow` from the engine's schema with its file column, the file chooser is live only on a flow row and the value box is not; a CSV of 0-20-20-0 m3/s over 40 min reaches `job.json` and the engine, and 35,999.9996 of 36,000 m3 entered, balance -4.2e-9. Run with `powershell -File tests\dock\run_check.ps1 "W61 inflow hydrograph lines\dock_flow_line.py" <throwaway folder>`; the harness needs `.venv` in the checkout (a junction to the main one in a worktree).

Found on the way: the first dock run made the flow line the whole of Bidah's second outlet, which meets the first in a cell, and the engine refused it in words ("1 of its cells are cells of another open boundary"); the scenario now uses the middle half of that outlet. The flow line drawn on the domain's edge leaves water 4.3 m deep against the wall beside it, which the run's edge-ponding warning names: an inflow line wants a wall-free edge or a line a cell inside it.

## Not done

- Momentum along the line's normal (above).
- No series of the line's own inflow or of the normal-depth level is written; the volume is in the run's balance (`inflow_m3`) with the point inflows.
- The dock sets only the file; `distribution`, `slope`, `record`, `start` and units are job fields with their defaults.
- Not raced against a HEC-RAS 6.6 run with the same line; not run on the GPU (the path is host-side and shared, so the GPU sees the same source vector).
