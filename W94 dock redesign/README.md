# W94 dock redesign

Status (2026-11-15): requirements recorded, design proposed, nothing built. The mockup of the first round is
https://claude.ai/artifact/1hX7UmbU2CTtgUi3BazMtP (six screens); this folder holds the second round's requirements.

## His requirements, 2026-11-15 (his words, lightly ordered)

The plugin must generate every requirement by itself. HMS met and basin files stay as options, never as the only way.

**Model types:** the four runs: 2D, Lumped, Hybrid Lumped, Hybrid 2D. The user picks one first, and only its sections show; or picks a finished run and sees its results.

**Hydrology**
- ARF: two subsections, one for the lumped part and one for the 2D part, since they take different settings. Each offers all three: a curve (table entry, shown as a chart), a fixed area (its reduction computed from the curve), a fixed coefficient.
- Rainfall: a fixed depth; a depth and a pattern; a single TIF grid and a pattern; DSS; NetCDF.
- Infiltration: a CN grid, and a table to override CN values.
- Manning: one value for all; two values, one for the square and one for the aligned mesh; a Manning grid with a table of n per land use.

**Domain**
- For 2D the domain is the area drawn.
- A domain that holds upstream catchments in the mountains needs automated delineation: as when a catchment is delineated, every catchment up to the drawn area is dissolved into it. Block 2 is the example: it holds all upstream catchments, and downstream it is drawn to the sea.
- The user draws the downstream part (the sea here) and an approximate polygon towards the mountains; the edge in the mountains is adjusted automatically to match the catchments, exactly, so a hybrid model has no rain-on-grid rim at the edge.
- In hybrid runs the cells are deactivated (Hybrid Lumped), or only the wet cells active (Hybrid 2D), as built.
- Where the user makes the catchments, the 2D domain's edge is aligned to them by a button or an option.

**Data tables (patterns, curves, hydrographs):** my call: a separate section to manage them as HMS does, or each section with its own table entry.

**Breaklines**
- Streams: the smoothed streams and the aligned mesh stay; a threshold of catchment size is needed.
- Long high ground (roads, dykes, dams): manual from a loaded shapefile, or automatic with options such as a minimum height (exists).

**Boundary conditions**
- Inside the domain the catchments are handled by the model.
- External inflows: a table entry with a chosen time step as HEC-RAS does, with a slope option, shown as a chart.
- Outflow as HEC-RAS does.
- Initial conditions: a point option that sets an initial level, at a dam, the sea and so on.

**Lumped:** automated: a user threshold for delineation, separate point shapefiles for outfalls and required points, split and merge; keep the HMS basin option; diversions and other elements as I see best.

**Terrain modification:** as discussed before (crest lines, spillways, embankments, channels, burn lines, walls, pit fill).

## What already exists in the engine (so the redesign is mostly the dock)

Rain sources: uniform, hyetograph, design storm with ARF table, gridded NetCDF/DSS/GeoTIFF stack, gauges, HMS met; ARF at one area, a given factor (W83), depth-area study, per element in lumped runs (W88); per-subbasin storm area (`38dc74e`). CN raster and per-subbasin parameters; Manning grid (strips take their own Manning). Basin generation from the DEM with threshold, points layer (outfall, design point, dam, diversion, source, junction edits, joins), walls and burns in delineation (W73); HMS import. Exclusion of lumped catchments from the mesh (W88). Flow-hydrograph boundary lines with momentum (W61, W70); normal, free, stage lines; initial water polygons and dam levels (W34). Breaklines Suggest with thresholds (W26, W45, W46). Pit check and fill (W85). Structures, culverts, gates, pumps, diversions (W59 to W76).

## Not in the engine yet (to build with the dock)

- ARF settings split between the lumped and the 2D part in one run (today: per-subbasin storm area and one 2D factor; a curve shown as a chart in the dock).
- A single TIF depth grid with a pattern as a rain source (the PMP-raster path exists for HMS's depth grid; make it a first-class source).
- A CN override table by land use or by value; Manning two-value square/aligned option and a land-use table.
- Domain from a drawn outline plus automatic upstream delineation, the mountain edge snapped to catchment boundaries, and an "align the domain to the catchments" action.
- Inflow table entry with a time step and a slope option; initial level points.
- The four model types as a saved setting that drives what the dock shows.

## Dock to-do list (2026-11-16): everything the engine has and the dock lacks

Status: the engine pieces above are built and merged (W95, W96, W97); nothing below is in the dock yet. The look is the
mockup's: one model type chosen first, only its sections shown, a status tick per section (Ready, Optional, Missing), a
check list before the run, a results view with compare. QGIS widgets styled to match (Qt style sheets: colours, rounded
panels, tabs and progress bars all work in a QGIS dock).

From the redesign requirements (built in the engine, no dock yet):
- Model type first: 2D, Lumped, Hybrid Lumped, Hybrid 2D (`run.model_type`), or open a finished run.
- ARF split into a lumped and a 2D part, each a curve (table and chart), a fixed area or a coefficient (`storm.area_reduction`).
- Rain: fixed depth, depth and pattern, TIF depth grid and pattern, SCS types, DSS, NetCDF (`storm.kind`, `storm.pattern`).
- One Data tables section for patterns and ARF curves (`data_tables`), as HEC-HMS's paired data.
- CN override table by land use, CN range or subbasin (`hydrology.cn_override`).
- Manning: one value, squares and aligned apart, a grid, land-use classes (`terrain.roughness`).
- Inflow line typed as a table at a time step, with a chart (`flow.step_s`); point inflows typed as a table.
- Initial-level points (`initial_points`).
- Domain from a drawn outline, completed upstream, and an Align to catchments button (`wadi2d domain`).

Found by the audit of 2026-11-16 (in the engine, never in the dock, not in the requirements):
- The aligned centre mesh (`strips.generator: centres`, the mesh of the four Block 2 runs), the thalweg corridor and fixed
  cells, gorge rows, the slope bank rule.
- Simulation panel: start date and time, duration, the 2D step (automatic: Courant number, max and min step; fixed under
  Advanced, warned when unstable), the lumped step (`hydrology.time_step_min`), map and series intervals, frames window.
- Resume from a checkpoint, and the checkpoint interval.
- Leaving out named subbasins from the mesh (`grid.exclude_subbasins`), not only all lumped ones.
- Breach estimator inputs (dam type, slopes, erodibility, pool volume) and the weir and piping coefficients.
- The ARF study's exact reruns at chosen points (`arf.exact_points`).

Proposed with it (his question of 2026-11-16, not yet his decision): scenarios as HMS runs and RAS plans (components,
a scenario inherits a base and stores only its differences), a batch queue (all return periods or all model types), stop
rules (end when every dam inflow has peaked and fallen), hot start from a saved state, batch sensitivity, run notes.
