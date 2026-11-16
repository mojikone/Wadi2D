# W103 Block 2 scenarios complete

**Live (2026-11-16), branch `feature/hybrid-scenarios` off `feature/fast-products` (`b126c09`); not merged, nothing
pushed.** W102 found the dock could not hold two things the Block 2 Hybrid jobs of W79 carry: each subbasin's own storm
area (its dam's or HAT-J4's drainage area, 20.97 to 260.97 km2) and the six point inflows of Hybrid Lumped with the
subbasins' entry and outlet edits. The dock now holds them; the four W79 jobs were imported again and saved as
scenarios, and each job the dock writes equals its original field by field but for three small fields W102 also listed.
**Use these scenarios, not W102's, for the Hybrids.**

**The uncomfortable part: the dock's own way does not give run 3 or run 4.** [Certain, the engine's own functions, no 2D
solver] On Hybrid Lumped the curve-form reduction gives the same factors as the hand-typed areas (to 3e-6), but the
automatic entries of the lumped network (W88) do not stop at the dams: they go on down a reach to where rain-on-grid water
first joins, 5.1 to 12.1 km below the hand-placed points, with that reach routed lumped (peaks 0.3 to 6.8 % lower, 1.0 to
1.5 h later). On Hybrid 2D the curve reads each subbasin at its own area (each enters at itself, W98's rule), not at its
dam's, so the lumped water entering the grid is 10.4 % more by volume and single peaks 0 to 16.9 % higher (all but S13
2.8 % at least). To reproduce
runs 3 and 4, the hand-typed storm areas and the six hand-placed inflows, now held by the dock, are needed.

## Where things are

The scenarios and the data are in the main checkout's folder `D:\Mojtaba\Renardet\Wadi2D\W103 Block 2 scenarios complete`
(not in git, as W102's); the record and the code that made them are in the branch, in this folder.

| What | Where |
|---|---|
| The six scenarios: `2D`, `Lumped`, `Hybrid Lumped`, `Hybrid 2D`, `Hybrid Lumped, dock way`, `Hybrid 2D, dock way` | data folder, `scenarios/*.wadi2d.json` (open with Open scenario; output folder: the data folder) |
| The layers the jobs held inline | data folder, `rerun2_run*_imported_inputs.gpkg` |
| The job the dock writes from each scenario, as Run writes it (the HMS import included) | data folder, `rebuilt/<job or scenario>/job.json` |
| Per scenario: the import's words, the dock's and the engine's comparison, each section's status | data folder, `report.json` |
| The real-dock check that made them | `dock_block2_complete.py`, log `logs/log_dock_block2_complete.txt` |
| The engine comparison of the dock's own way | `scripts/compare_dock_way.py`, `results/`, log `logs/compare_dock_way.txt` |
| The older scenarios, base and branch | `scripts/run_old_batch.ps1`, `old_scenarios/` |

## What the dock now holds

- **Hydrology's subbasin table**, on an HMS project, three more columns: **Storm area, km2** (`storm_area_km2`, empty is the
  storm's), **Enters** (as the basin gives, the wadi outlet of its polygon, its outlet point: `entry`), **Outlet x, y**
  (empty is the HMS import's, `none` takes it away, as a subbasin whose water an inflow below carries needs: `outlet`).
  Hidden on a generated basin: the engine's resolve of a generated basin keeps a subbasin's outlet but drops its `entry`
  and `storm_area_km2` (`wadi2d/basin/job.py`, `resolve`), so the dock offers neither there (found, not changed).
- **Point inflows of lumped elements**, a table under it: name, element (the basin's reservoirs, junctions and reaches, or
  typed), x and y in the DEM's coordinates, entry (`point` or `wadi`), and whether the water enters the grid (`enters`;
  unticked it leaves the model there, as at an HMS sink). Add row, Remove row, **Click on the map**. A table hydrograph at
  a point (`times_s`, `flows`) is not held: the flow lines carry hydrographs.
- **Written only when set** (`entry_rows.apply_edits`, `inflow_jobs`): a model with none, and every older model, writes
  the job it wrote. Entry and `enters` are written only off the engine's defaults.
- **Saved with the model**: format 5 (`model_doc._to_5`, which sets nothing and says nothing: a format 4 model comes up
  with no edit and no inflow). The edits ride in Hydrology's saved state beside the modes; the inflow table is saved as
  the other tables are.
- **Read back by Import a job** (`job_states._hydrology`): on an HMS job every subbasin's storm area, entry (the
  engine's default `point` where the job leaves it out) and outlet (`none` where it has none) are pinned as the job holds
  them, whatever the HMS file's icons say now; a job's element inflows fill the table. A generated basin's job brings no
  edit, as before.
- **Refused in words** (`entry_rows.edit_problems`, `inflow_problems`, `job_builder._entry_problems`): an outlet that is
  no point; a storm area on a 2D subbasin; storm areas where the area reduction reads no table at an area of its own
  (the engine reads them only on the single-storm form at one area or a lumped curve, `reduction_rows.lumped_form`);
  an inflow with no name, no element or no point, or a name twice; inflows with no lumped network.
- **The status line** of Hydrology counts them: "26 at a storm area of their own · 104 entries set by subbasin · 6 point
  inflows". A 2D model carries neither (`model_types.apply_type`).

## The four scenarios, field by field

Each job the dock writes, as Run writes it, against W79's, both read through the engine's schema (defaults written out),
the terrain objects in the order the engine applies them (W101's method). Real dock, QGIS 3.44.8, throwaway profile:
**59 of 59** (`logs/log_dock_block2_complete.txt`).

| Scenario | Model type | Differs from the original job |
|---|---|---|
| 2D | 2D | `hydrology.curve_number`, `outputs.live_every_s`, `run.checkpoint_every_s` |
| Lumped | Lumped | the same three, and `run.lumped_only` (the dock's Lumped type writes it; the job names no lumped run: W79 ran it lumped by a script) |
| Hybrid Lumped | Hybrid Lumped | **the same three only**: the 26 storm areas, the 104 subbasins' entries and outlets (the 26 carried without an outlet) and the six inflows are held |
| Hybrid 2D | Hybrid 2D | **the same three only**: the 26 storm areas and the 104 entries and outlets are held |

What is not listed is identical, as in W102 (DEM, cell, domain, Manning, pit fill, the aligned centre mesh, the outflow
lines, crest lines and spillways, result lines, the 251 mm storm and its pattern, the reduction at 100 km2, the HMS
basin and every subbasin's mode, the catchments left out in Hybrid Lumped). **Still not held** (not in this brief):
`hydrology.curve_number` 88 beside the CN grid (the dock writes the grid alone; [Likely] it matters only where the grid
has no value), and `outputs.live_every_s` 0 and `run.checkpoint_every_s` 0 (no controls; the engine's defaults are
written). [Certain] With those, the lumped network's factors and entry hydrographs of the rebuilt Hybrid jobs equal
W79's to the digit (`results/compare_dock_way.json`, "faithful").

Also through the dock: a scenario saved and opened again writes the same hydrology; the status line; S13 reads Bidah
03's 20.97 km2; an outlet typed as "below the dam" is Missing in words and Run refuses it in the same words, written back
Ready; Click on the map adds a row at the clicked point and gives the map tool back; Remove row; a 2D model carries no
inflow and no edit.

## The dock's own way against runs 3 and 4 (c)

Two more scenarios, made in the dock from the faithful ones: the lumped part of the area reduction **a curve** (W98: each
lumped subbasin read at the drainage area of the element where its water enters the grid) in place of the hand-typed
storm areas, the 2D part at 100 km2 as before; for Hybrid Lumped also **the lumped water kept on the network**
(`hydrology.lumped_entry: network`, W88, with the catchments left out of the mesh) in place of the six hand-placed
inflows. The engine's own functions on each job (`R._resolved`, `_lumped_rain`, `_network`, `left_out_of`), no grid, no
solver; the lumped network runs in 0.1 to 0.4 s.

### Hybrid Lumped

- **Factors** [Certain]: within 3e-6 of the hand-typed areas' for all 26 subbasins. The entry element below each dam is a
  reach that carries only that dam's water, so its drainage area is the dam's (W98's 0.005 km2 again).
- **Entries** [Certain]: the network does not stop at the dams. Its rule (W88) keeps lumped water on the network while
  only lumped subbasins drain to an element, so each dam's outflow goes on down the reach below it, routed lumped, and
  enters at that reach's downstream end, where rain-on-grid water first joins:

| Hand-placed (W79 run 3) | Dock's own entry | Distance, km | Peak, m3/s, W79 / dock way | Volume, Mm3, W79 / dock way | Peak later by, h |
|---|---|---|---|---|---|
| Bidah 03 Reservoir | reach BID-R1 | 6.08 | 0 / 0 (the dam does not spill) | 0 / 0 | |
| Faydh 01 Reservoir | reach FAY-R1 | 12.14 | 0 / 0 (the dam does not spill) | 0 / 0 | |
| R5A Reservoir | reach RIJ-R2 | 5.12 | 753.8 / 750.1 (-0.5 %) | 13.458 / 13.502 (+0.3 %) | 1.0 |
| R2A Reservoir | reach RIJ-R1 | 6.22 | 818.4 / 815.6 (-0.3 %) | 17.877 / 17.938 (+0.3 %) | 1.3 |
| Z4C Reservoir | reach FIZ-R1 | 8.69 | 2,025.0 / 2,007.2 (-0.9 %) | 34.610 / 34.744 (+0.4 %) | 1.5 |
| HAT-J4 | reach HAT-R4 | 7.02 | 2,472.0 / 2,304.2 (-6.8 %) | 47.071 / 47.051 (0.0 %) | 1.4 |

  RIJ-R1 and RIJ-R2 end at one point, so R5A's and R2A's water enter together. Every automatic entry lies 5.2 to 11.7 km
  from the left-out catchments, so none is moved by the snap of W88 [Certain: the snap moves only a point in a left-out
  cell]. The volumes rise 0.3 to 0.4 % on the reaches because HMS-faithful Muskingum-Cunge does not conserve volume (W25,
  W29). In run 3 the five dam points entered where typed and HAT-J4 34 m away (W79's `entries.json`). **So the dock's
  own way replaces 5 to 12 km of 2D routing below each dam with lumped routing, and that is not run 3.** [Likely] For
  the dams the difference at the entry is small (under 1 % of the peak); for HAT-J4 it is 6.8 %, and the 2D flood between
  the dams and the reach ends is missing from the maps either way.

### Hybrid 2D

- **Entries** [Certain]: the same 26 points and rule as run 4 (each lumped subbasin at the wadi outlet of its polygon; the
  HMS import's outlets, which run 4 kept): distance 0.
- **Factors** [Certain]: in Hybrid 2D every lumped subbasin enters at its own outlet, so W98's curve reads each at its own
  drainage area, not at its dam's: factors 0.024 to 0.130 higher (S11 0.931 to 0.955, HAT-S2 0.846 to 0.976; S13, alone
  above Bidah 03, the same). His rule for run 4 ("ARF at elements": every subbasin draining to a dam at that dam's area) is not what the
  curve does there.
- **Entry hydrographs**: peaks 1.00 to 1.17 x run 4's, volumes 1.00 to 1.18 x; all 26 together 161.6 to 178.5 Mm3
  (+10.4 %). Per subbasin in `results/entries_Hybrid_2D.csv` and `factors_Hybrid_2D.csv`.

**What would make the dock's own way equal runs 3 and 4** (not built, his call): for Hybrid Lumped, an option for the
network to enter at the dams (the reservoirs) rather than at the first rain-on-grid join; for Hybrid 2D, the lumped
curve read at the area of the first dam below a subbasin rather than at the subbasin itself. Until then the hand-typed
areas and points, which the dock now holds, are the way to his runs.

## The older scenarios

The ten W99 and W101 used, each in its own throwaway QGIS 3.44.8 (`scripts/run_old_batch.ps1`), on a frozen copy of the
base (`b126c09`, by `git archive`) and on this branch (code at `4863e34`); logs in `old_scenarios/`:

| Scenario | Base `b126c09` | Branch |
|---|---|---|
| `dock_cell_grid.py` (W17) | 3 passed, 1 failed, stopped by an exception | 3 passed, 1 failed, stopped by an exception |
| `dock_boundary_table.py` (W18) | 34 passed, 0 failed | 34 passed, 0 failed |
| `dock_profile_editor.py` (W22) | 120 passed, 0 failed | 120 passed, 0 failed |
| `dock_mesh_controls.py` (W23) | 44 passed, 1 failed, stopped by an exception | 44 passed, 1 failed, stopped by an exception |
| `dock_suggest.py` (W26) | 32 passed, 0 failed | 32 passed, 0 failed |
| `dock_dam_start.py` (W34) | 23 passed, 0 failed | 23 passed, 0 failed |
| `dock_flow_line.py` (W61) | 13 passed, 1 failed | 13 passed, 1 failed |
| `dock_breach.py` (W68) | 14 passed, 0 failed | 14 passed, 0 failed |
| `dock_basin_points.py` (W73) | 36 passed, 0 failed | 36 passed, 0 failed |
| `dock_gauges.py` (W77) | 42 passed, 1 failed | 42 passed, 1 failed |

The same counts as W101's at the end, scenario for scenario; the four that do not pass stop at the same check on the
base. **Every job they wrote is the same** (W99's `compare_jobs.py` and `compare_previews.py`): the 22 run jobs identical
to the character once each batch's folder is taken out, and the 5 profile-editor preview jobs on each side pair up, 3
identical and 2 differing only in their random scratch draft names, as in W99 and W101. None of these models has a
subbasin edit or a point inflow, so this is the proof that an older model writes the job it wrote.

Plugin tests that need no QGIS window, every file of `tests/plugin` alone: **727 passed of 727** (52 files, the headless
smoke test on the fake and the real engine among them); `test_entry_rows.py` 16 new, `test_contract.py` 104 (7 new).

## Not done

- `hydrology.curve_number` beside a CN grid, `outputs.live_every_s`, `run.checkpoint_every_s`: still not held (W102).
- A table hydrograph at a point (`hydrology.inflows[].times_s`, `flows`): not held; a job with one lists it in the
  comparison.
- Storm areas and entries on a generated basin: the engine's resolve drops them, so the columns are hidden there.
- The main checkout's `W102 Block 2 models in the dock/README.md` carries no superseded line: this session could not
  write the shared checkout; the branch's copy (`W101 dock redesign part 2/W102_README.md`) has it.
- No 2D run of any of the six scenarios (none asked; no 2D solver on Block 2).
