# W102 Block 2 models in the dock

**Superseded for the two Hybrids (2026-11-16): the Hybrid Lumped and Hybrid 2D scenarios here are not W79's runs 3 and 4; use `W103 Block 2 scenarios complete`, where the dock holds each subbasin's storm area, entry and outlet and the six point inflows.**

**Live (2026-11-16).** The four Block 2 jobs of W79 (`W79 Block 2 four ways/jobs/rerun2_run*.json`), which the dock did
not write, imported into the dock of branch `feature/dock-redesign-2` (W101) with its new Import a job, and saved as
four scenarios. Made in a throwaway QGIS 3.44.8 by `W101 dock redesign part 2/dock_import_block2.py` (46 of 46
checks); nothing of W79 or his HMS project was written to. This README is kept in the branch as
`W101 dock redesign part 2/W102_README.md`.

## What is here

| File | What |
|---|---|
| `scenarios/2D.wadi2d.json`, `Lumped`, `Hybrid Lumped`, `Hybrid 2D` | the dock's model of each job, to open with Open scenario (output folder: this folder) |
| `rerun2_run*_imported_inputs.gpkg` | the lines and polygons each job held inline (outflow lines, crest lines, spillways, result lines), the layers the scenarios use |
| `rebuilt/<job>/job.json` | the job the dock writes from each scenario, as Run writes it (the HMS import included) |
| `report.json` | per scenario: the import's words, the dock's own comparison, the engine's comparison, each section's status |

## The proof

Each rebuilt job was compared field by field with the original, both read through the engine's own schema (every
default written out, the domain as its polygon, the terrain objects in the order the engine applies them). **What is
not listed below is identical**: the DEM, cell size, domain, Manning grid and value, pit fill, the aligned centre mesh
(`strips.generator: centres`) on the same Suggest file, the four normal-depth outflow lines and their slopes, the 15
crest lines and spillways of the five dams, the ten result lines, the 251 mm design storm with its 24 h pattern, its
area reduction (the ARF FM table read at 100 km2, factor 0.913, `reduces_below_table` off and its table type kept),
the 48 h, the 5 min lumped step, the 15 min maps, the GPU, the CN grid, the HMS basin and its 104 subbasins' modes,
the catchments left out of the mesh in Hybrid Lumped. The dock's own comparison (in its Model box) lists the same
fields as the engine's.

## What the dock cannot hold yet, by scenario

| Scenario | Model type | Not held |
|---|---|---|
| 2D | 2D | Hydrology: `curve_number` 88 beside the CN grid (the dock writes the grid alone). Simulation: `outputs.live_every_s` 0 and `run.checkpoint_every_s` 0 (no controls; the engine's defaults are written) |
| Lumped | Lumped | the same three; and `run.lumped_only`, which the dock's Lumped type writes and the job does not: W79 ran this one lumped by a script, so the job alone names no lumped run |
| Hybrid Lumped | Hybrid Lumped | the same three; **`hydrology.inflows`, the six point entries of the dams' and HAT-J4's outflows; each subbasin's own `storm_area_km2` (its dam's area, 20.97 to 260.97 km2); the subbasins' `entry` and `outlet` as W79 edited them** |
| Hybrid 2D | Hybrid 2D | the same three; **each subbasin's `storm_area_km2`, `entry` and `outlet`** |

[Certain, from the comparison] **Hybrid Lumped and Hybrid 2D as the dock holds them are not W79's runs 3 and 4**: without
the per-subbasin storm areas the lumped catchments are reduced at 100 km2 instead of their dams' areas, and without the
six point inflows Hybrid Lumped's dam outflows do not enter the grid. The 2D and Lumped scenarios differ from their
jobs only in the three small fields (and Lumped's type). [Likely] The missing `curve_number` matters only where the CN
grid has no value: there a cell takes no loss instead of CN 88.

## How the import read them

- The run folders keep `config.resolved.json`, not `job.json`: Open a run now reads either; these were imported from
  the job files with Import a job.
- The dock's HMS route needs a meteorologic and a control file; the jobs name neither. Control_1.control (the folder's
  only one) and FM_200yr.met (its storm depth is the job's 251 mm) were chosen and said so in words; the rain is the
  Storm section's, as each job's own, and the control file's 48 h at 5 min equal the job's.
- The model types were set to the four his names give; the jobs themselves name none.
