# W105 dams end the lumped model

**Live (2026-11-16), branch `feature/dams-end-lumped` off `feature/fast-products` (`7b58a2b`); not merged, nothing
pushed.** His rule of 2026-11-16, on W103's finding: "in run 4 every lumped catchment takes its dam's ARF. The dams are
actually the last point of the lumped model." And, held to exactly: "In Lumped and Hybrid Lumped, the ARF applies to
each point's upstream area. But in Hybrid 2D, the ARF applies to the area upstream of the last point of each basin, like
the dams and the one defined in HAT, since in Hybrid 2D we cannot run the 2D model for each upstream point."

**What it gives** [Certain, the engine's own functions on Block 2, no 2D solver]: with the dock's own way (the lumped
part of the area reduction a curve, the lumped water kept on the network in Hybrid Lumped, no storm area or point
inflow typed) and the last points the five dams plus HAT-J4, every one of the 26 lumped subbasins takes W79's hand-typed
factor (within 3e-6, the 0.005 km2 rounding of the typed areas) in both Hybrids, every hydrograph entering the grid is
W79's (Hybrid Lumped's six: peaks within 0.005 m3/s, volumes within 5e-6; Hybrid 2D's 26: peaks within 0.003 m3/s,
volumes within 3e-6) and enters at the same time. **What it does not give: W79's points.** The five dams' water enters
at the dams, on the edge of the catchments left out of the mesh, 10 to 35 m from the dam lines (Bidah 03 96 m: its entry
lies 15 m from the left-out edge, so [Likely] its HMS polygon reaches about 80 m past the line); W79 put its five hand points 200 m below the spillways' thalwegs by a rule of its
own, so they lie 163 to 240 m (8 to 12 cells) from the automatic ones. HAT-J4 enters where run 3 entered, to the
centimetre. Superseded record: W103's "dock's own way" table (kept as it was, in W103).

## Where things are

| What | Where |
|---|---|
| The engine's rule | `wadi2d/engine/last_points.py`, `entry_area.py` (`read_areas`), `network_entries.py` (`stop_at_last_points`), `left_out.py` (`snap_entries`, `edge`), `run.py` (`_last_point_map`, the hash) |
| The dock | `plugin/wadi2d_qgis/last_point_rows.py`, `sections/last_points_table.py`, Hydrology, `model_doc._to_6` |
| Block 2 against runs 3 and 4 | `scripts/compare_last_points.py`, `results/compare_last_points.json` and its CSVs, `logs/compare_last_points.txt` |
| The real-dock check and what it wrote | `dock_last_points.py`, `logs/log_dock_last_points.txt`, `dock_data/` (the two scenarios of format 6, the two jobs; their paths point into the worktree they were written in) |
| Old jobs before and after | `scripts/old_jobs.py`, `results/old_jobs.json`, `logs/old_jobs_*.txt` |

## The rule, as built

| Model | A lumped subbasin is read on the curve at | An element is reported at | The lumped water enters the grid |
|---|---|---|---|
| Lumped | each element's own drainage area (HMS depth-area), unchanged | its own area | nowhere: no grid |
| Hybrid Lumped | the drainage area of the element where it enters the grid: its last point (W98's rule, unchanged) | its own area; the grid takes the last point's own hydrograph (W98) | **at the lowest last point on its way**, at the pour point of the catchments it brings in (new) |
| Hybrid 2D | **the drainage area of the first last point at or below it, one factor per dam** (new; W98 read its own area) | what entered: the dam's factor (no rerun) | at its own outlet, unchanged |

- **The last points** (`hydrology.last_points`): None, the default, is every dam of the lumped network (an HMS
  reservoir, a generated basin's dam); a list names them all (dams and junctions alike); `[]` none, which is W98's rule
  everywhere. `wadi2d/engine/last_points.py`.
- **Hybrid Lumped** (`hydrology.lumped_entry: network`, `wadi2d/engine/network_entries.py`): a last point lumped all the
  way whose water reaches no other last point on lumped elements is an *entering* last point, and every element below it
  leaves the lumped network: the water stops there. A dam above a dam passes its water on, lumped, to the lower one (his
  words name no case of dams in series; this is my reading: the lower dam's own hydrograph, at its own area, is what HMS's
  depth-area analysis gives there). Its inflow is written at its HMS icon with the new entry rule **`edge`**: with the
  catchments left out of the mesh it enters at their pour point, the lowest cell on their whole edge
  (`wadi2d/engine/left_out.py`), wherever the icon lies. The first form searched within `entry_snap_m` (500 m) of the
  icon, W88's rule, and put R2A's water on the dam's second chute, 740 m from the main one, because R2A's HMS icon lies
  884 m from the main chute's exit, beyond the 500 m; the whole edge's lowest cell is 35 m from the main chute. The other
  five points are the same either way. Measured, then changed.
- **Hybrid 2D** (`wadi2d/engine/entry_area.py`, `read_areas`): a subbasin that enters at its own outlet reads the area
  of the first last point at or below it; one carried by the network to an entry reads that entry's (W98); with no last
  point below, its own. A subbasin's own `storm_area_km2` still wins. With dams in series a subbasin above the upper dam
  takes the upper dam's area (the first one its water reaches); his words do not settle that case either.
- **Job hash**: `last_points` enters it only where it can change the water (a lumped curve, or the network entry), so a
  checkpoint made under W98's rule is not resumed under this one; every other job keeps its hash.

## Block 2 against runs 3 and 4 (`scripts/compare_last_points.py`, `results/`)

The jobs the real dock wrote (`dock_last_points.py`, below) from W103's two dock-way scenarios with HAT-J4 added to the
five dams; W79's `rerun2_run3_hybrid_aligned.json` and `rerun2_run4_hybrid_2d_routing_aligned.json`. For the points,
run 3's own mesh: the grid and aligned strip run 3 cached on 15 Nov (`runs/cache`, read only), with the engine's
`snap_entries`; W79's own job on it gives the point run 3 recorded for HAT-J4 to 0.0 m, so it is the mesh run 3 ran on.

### Factors (`factors_*.csv`)

| | Hybrid Lumped | Hybrid 2D |
|---|---|---|
| 26 subbasins, dock way minus W79's hand areas | -3e-6 to +2e-6 | -3e-6 to +2e-6 |
| W103 (before), the same | -3e-6 to +2e-6 | **0 to +0.130** |
| The dams alone, HAT-J4 not added | the same | HAT-S1 to HAT-S8 at their own areas, 0.940 to 0.976 against 0.846 |

### Hybrid Lumped's entries (`entries_Hybrid_Lumped.csv`)

| Last point | Peak m3/s, run 3 / dock way | Volume Mm3, run 3 / dock way | Peak time, h | From W79's point, m | From the dam line, m (W79's) | From the left-out edge, m (W79's) |
|---|---|---|---|---|---|---|
| Bidah 03 Reservoir | 0 / 0 (the dam does not spill) | 0 / 0 | | 163 | 96 (248) | 15 (166) |
| Faydh 01 Reservoir | 0 / 0 (the dam does not spill) | 0 / 0 | | 234 | 13 (246) | 24 (251) |
| R5A Reservoir | 753.761 / 753.756 | 13.45795 / 13.45788 | 15.92 / 15.92 | 181 | 24 (203) | 20 (198) |
| R2A Reservoir | 818.424 / 818.428 | 17.87668 / 17.87675 | 16.50 / 16.50 | 208 | 35 (236) | 34 (234) |
| Z4C Reservoir | 2,024.975 / 2,024.979 | 34.61023 / 34.61031 | 15.83 / 15.83 | 240 | 10 (250) | 3 (243) |
| HAT-J4 | 2,471.988 / 2,471.992 | 47.07086 / 47.07093 | 15.75 / 15.75 | 0 | | 28 (28) |

W103 had these six entering 5.1 to 12.1 km down the reaches, peaks 0.3 to 6.8 % lower and 1.0 to 1.5 h late. The
remaining 0.004 m3/s is the 0.005 km2 rounding of W79's typed areas. **The brief's test "each entry within one cell of
W79's hand point" fails for the five dams by 8 to 12 cells, and it cannot pass with a rule that enters at the dam:**
W79 placed them 200 m perpendicular from the spillway's midpoint, then down the steepest 5 m pixel for at most 60 m
(`W79 .../scripts/s01_inputs.py`, `entry_point`), using the dam team's spillway lines, which run 3's job does not
carry. [Likely] Entering at the dam is the better reading of "the dams are the last point": the 200 m of wadi below
each dam is then on the grid. His call whether 200 m below is wanted; it would be a walk down the steepest path from the
pour point, not built.

### Hybrid 2D's entries (`entries_Hybrid_2D.csv`)

All 26 at their outlets as run 4, peaks within 0.003 m3/s and volumes within 3e-6 of run 4's; W103 had them 1.00 to 1.17
x run 4's peaks and the 26 together 10.4 % more water.

### Each point's own area against its dam's (`own_area_and_dam_factor.csv`)

The elements above a dam that Hybrid Lumped reports at their own drainage area (its series of record, a lumped rerun;
what entered the grid is kept beside as `entry_area_<element>`), and the same subbasins in Hybrid 2D at their dam's:

| Element | Its own area, km2 | Hybrid Lumped: own factor, peak m3/s | Last point (area, km2) | Hybrid 2D: dam's factor, peak m3/s |
|---|---|---|---|---|
| S1 | 59.08 | 0.9416, 783.0 | Z4C (211.09) | 0.8607, 710.1 |
| S3 | 87.60 | 0.9217, 886.1 | Z4C (211.09) | 0.8607, 821.5 |
| J2 (S1 to S3) | 191.07 | 0.8684, 2,070.8 | Z4C | not lumped: the grid routes it |
| S5 | 73.87 | 0.9313, 887.0 | R2A (175.87) | 0.8758, 829.7 |
| S11 | 41.47 | 0.9548, 711.6 | Faydh 01 (74.30) | 0.9310, 692.5 |
| S14 | 42.30 | 0.9542, 645.9 | R5A (117.10) | 0.9046, 609.8 |
| HAT-S8 | 62.11 | 0.9395, 862.6 | HAT-J4 (260.97) | 0.8461, 765.8 |
| HAT-J3 | 166.04 | 0.8806, 2,230.7 | HAT-J4 | not lumped |

All 48 rows in the file. S13, alone above Bidah 03 (20.97 km2 against its own 20.97), is the one subbasin whose two
factors agree.

## The dock (`plugin/wadi2d_qgis/last_point_rows.py`, `sections/last_points_table.py`)

- Hydrology, under the point inflows: **Last points of the lumped model**, the dams the basin holds (an HMS project's
  reservoirs, a generated basin's dams), each ticked; **Add a junction** from the basin's junctions, **Pick on the map**
  (the junction whose icon lies nearest the click), **Remove junction**; a dam is unticked, never removed. Hidden in a
  2D model, which drops it from the job.
- Written only off the engine's default: every dam ticked and no junction writes nothing, so every older model writes
  the job it wrote; else every ticked name, in order (`hydrology.last_points`).
- Saved with the model: **format 6** (`model_doc._to_6`): a format 5 model comes up with every dam ticked; where that
  changes what its job gives (a lumped curve with subbasins at their outlets, or the water kept on the network) it says
  so in words; a Lumped or 2D model is told nothing.
- Read back by Import a job (`job_states._last_point_rows`): the job's list over its basin's dams, the rest as junctions.
- The status line: "the lumped model ends at 5 dams + HAT-J4"; a junction the basin does not hold is Missing in words,
  and Run refuses it in the same words. Area reduction (4b) reads "A curve: each lumped subbasin read at its dam's (last
  point's) drainage area", with the three models' rule in its note.
- The inflow table takes the new entry rule `edge` ("At the edge of the catchments left out") so an imported job with
  one keeps it.

## Old jobs (`scripts/old_jobs.py`, `results/old_jobs.json`)

Every tracked job file with a lumped network, 90, read by the base (`7b58a2b`, a frozen copy) and by this branch: its
hash, the job as the engine resolves it, each lumped subbasin's rain over the event, each hydrograph entering the grid.
**67 read: all 67 the same** (W79's five with storm areas or inflows of their own among them); **23 cannot be read on
this machine**, with the same error before and after (22 point at files in deleted temporary folders and worktrees, one
is refused by today's schema). No tracked job uses a lumped curve or the network entry, so none moves. Jobs that move,
by design, untracked: W103's two dock-way jobs (the table above is what they give now); any model whose lumped part is a
curve with subbasins entering at their outlets near a dam, or whose lumped water is kept on the network.

## Tests

- `tests/engine/test_last_points.py` (7): two dams in series, a junction named, a subbasin with no last point below; the
  default, `[]` and a list; Hybrid 2D one factor per first last point and no rerun; Hybrid Lumped's water stopping at
  the lowest last point (the dam above passing on), the last point's own hydrograph, the upper dam reported at its own
  area; an `edge` inflow at the pour point from 10 cells below and from beyond `entry_snap_m`, a `point` one not moved,
  a full CPU run with its `entries.json`; the hash.
- `tests/plugin/test_last_point_rows.py` (14): the basin's dams, junctions and icons; written only off the default;
  a job's list read back and written again; words, problems, the nearest junction; format 6 and its words; Block 2's
  five dams and HAT-J4 taken by the engine's schema.
- Real dock, QGIS 3.44.8, throwaway profile (`dock_last_points.py`, `logs/log_dock_last_points.txt`): **40 of 40**.
  W103's two dock-way scenarios (format 5) open with the migration's words and Basin 3's five dams listed and ticked,
  nothing written; Add a junction, Remove junction and Pick on the map (a click 50 m from HAT-J4's icon) each do what
  they say and give the map tool back; the status line reads "the lumped model ends at 5 dams + HAT-J4"; saved as
  format 6 (`dock_data/scenarios/`) and opened again, the same hydrology; the job (`dock_data/rebuilt/`) holds the five
  dams in Basin 3's file order and HAT-J4 and in its hydrology differs from W103's job in that field alone; a dam
  unticked writes the other four and HAT-J4; a 2D model none.
- Plugin tests that need no QGIS window, every file of `tests/plugin` alone: **742 passed of 742** (53 files);
  `test_entry_rows.py` and `test_simulation_rows.py` now name format 6 (`logs/plugin_tests.txt`).
- Engine tests that reach the lumped network, the entries, the area reduction or the job hash, each file alone on the
  CPU (`CUDA_VISIBLE_DEVICES=-1`: no GPU, another worker held it): **567 passed of 567 in 44 files**, 5 GPU tests
  deselected (`logs/engine_tests.txt`); W98's `test_entry_area.py` unchanged and passing, since W98's carried subbasins
  keep its rule.

## Not done

- W79's 200 m below the dams (above): not built; his call.
- Dams in series: no Block 2 case; the two choices above are mine, his to confirm.
- A generated basin's reservoir without a rating runs as a junction in the engine, so it is no default last point there,
  while the dock lists it as a dam (found, not changed).
- The depth-area study (`wadi2d arf`) turns a lumped curve into one storm area per run, as before (W98): a study of a
  Hybrid 2D model reads its lumped subbasins at each run's area, not at their dams'.
- The older switch `hydrology.arf_by_element` (the HMS storm's tick) is left as it was: every element at its own area.
- No 2D run of either Hybrid (none asked); the full suite not run (left to the merge).
