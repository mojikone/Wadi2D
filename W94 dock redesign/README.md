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

Results view, his remark of 2026-11-16 on the mockup ("not all projects have dams"): the results table is not a dam
table. It lists the run's elements of record with a kind filter (design points, dams and reservoirs, junctions, reaches,
subbasins, outlets, result lines and points, observed gauges), a search box, and a pinned set the user picks, saved with the
project and shown first in every run and in Compare. Default when nothing is pinned: the user's design points and lines; if
none, the dams; if none, the outlets to the sea or the domain edge. Every row opens the hydrograph chart; the right-click
chart on the map stays.

## Review of the current dock (2026-11-16)

Biggest gap: the dock saves nothing of a model. Only the engine path, the last folders and the depth cutoff persist (QGIS
settings); every field is lost when QGIS closes, and choosing a finished run's folder does not refill the dock from its
`job.json`. To build first: the model saved with the QGIS project, open a run's job into the dock, save as a scenario. His decision of 2026-11-16: built with the redesign, as its first piece, not patched into the current dock.

Redundant or in the wrong place, to fold into the redesign:
- Three "Run starts at" fields (gridded rain, rain gauges, 7b gauges): one start time in the simulation panel.
- ARF in three places (Storm's area reduction, Hydrology's "each element at its own drainage area", section 9): one ARF
  section with its lumped and 2D parts, the depth-area study one of the 2D choices.
- Hydrology's "The HMS way only", "Leave the catchments out of the mesh" and "Lumped water enters the 2D model", and the
  per-subbasin mode table's role in it: set by the model type, shown only where the type leaves a choice.
- Two time sliders: the cell mesh layer (2.3 GB on Block 2, hung his PC) and the pixel layer: keep the pixel layer, the mesh
  layer as an export under Results.
- The "Steady" rain kind (mm/h for hours): a test case; "Fixed depth" with a uniform pattern covers it.
- 7b Gauges now holds only observed flow and level gauges: it belongs with the results (calibration), renamed.
- Run mixes the run, the products and map-making (title, background, cutoff, Make map, sliders, lines, workbook): split into
  Run (simulation panel, Check and run) and Results.
- Mesh holds two mesh systems (quadtree refinement, corridors) plus eight bank and crest thresholds of Suggest breaklines:
  a mesh choice (squares, quadtree, aligned centre mesh), the thresholds under Advanced. Local time stepping under the
  quadtree only (it saves nothing on a uniform grid, W10).
- "Name the cell that sets the time step": a diagnostic, Advanced.
- Two engine controls (Engine... at the top, Engine in Run): one, in the simulation panel.
- Section numbers 7 and 7b: renumber, or drop numbers once sections show by model type.

Mesh section of the redesign (his question of 2026-11-16, "mesh generation is included?"): one section between Domain and
Hydrology for every type with a 2D part:
- Mesh kind: squares, quadtree (coarse cells on steep hills, fine on wadis and plains), aligned centre mesh (cells along
  the smoothed streams, squares beyond), and the aligned streams inside quadtree hills when W82's speed is solved.
- Cell sizes: finest, coarsest, the slope over which hills coarsen; for the aligned mesh the stream threshold (km2), the
  floor rule (height above the channel, capped by the slope) and fixed cell across.
- Lines: streams (generated, smoothed, editable), high ground (roads, dykes, dams) from a layer or Suggest, refinement
  zones and lines (near size, rows, far size).
- Build mesh: builds and draws the cells on the map before any run, with cell count, smallest cell, the time-step
  estimate and the refusals in words (tiling guard, overlapping corridors); cached, so Run reuses it.
- Advanced: the bank and crest thresholds of Suggest, gorge rows, local time stepping (quadtree only).

His answers on item 7, the map controls (2026-11-16): a map pixel field, yes; the window button named for the
terrain's finest resolution, not "0.5 m" (other projects' DEMs differ); no surface choice: the pixel maps use the
continuous surface only, the cell maps (one value per cell) stay; a depth x speed tick, off by default, yes; Lumped
models without cell size or Manning in Terrain, yes. Sent to the part 2 worker after its current item. His question the
same day, "there's no water surface output?": a cell map of the highest water level exists (`maps/max_level.tif`, one
value per cell); no water-surface raster at the pixel; proposed, not built: a pixel water-surface raster of record
(the continuous surface where wet), as RAS Mapper's WSE map.

His rule of 2026-11-16 for the map controls: one depth threshold for the maps in the dock, default 0.1 m, applied to
every output (pixel depth, speed, water level, hazard, the slider's frames, the renderer, the cell maps) and to the
display cutoff of the depth layers, so files and screen agree; no second threshold anywhere. Sent to the part 2 worker
with item 7.

His rule of 2026-11-16 (answer on W103's finding): "in run 4 every lumped catchment takes its dam's ARF. The dams are
actually the last point of the lumped model." So a lumped model ends at its dams (and junctions marked as last points,
HAT-J4 on Block 2); in Hybrid Lumped the lumped water enters the 2D model at those points; with the lumped reduction in
the curve form every lumped subbasin is read at the drainage area of the first last point below it. Being built as W105.
His clarification the same day: "In Lumped and Hybrid Lumped, the ARF applies to each point's upstream area. But in
Hybrid 2D, the ARF applies to the area upstream of the last point of each basin, like the dams and the one defined in
HAT, since in Hybrid 2D we cannot run the 2D model for each upstream point." Lumped and Hybrid Lumped: HMS depth-area
practice, each element at its own drainage area, the hydrograph handed to the grid at a last point that point's own;
Hybrid 2D: one factor per basin, its last point's.
