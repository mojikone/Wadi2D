# W104 Block 2 from the dock

**Live (2026-11-16), branch `test/block2-from-dock` off `feature/fast-products` (`b126c09`); not merged, nothing pushed.**
His order: "run the four models only through the dock; check if the dock can create all from ground up: 2D mesh and
streams, subbasins and reaches, dams etc., Hybrid Lumped, Hybrid 2D." Done in throwaway QGIS 3.44.8 windows
(`tests/dock/run_check.ps1`), every model input through the dock's own widgets, from his raw layers; no HMS file, no
W79 job, no engine command line. The QGIS project with the four models in the plugin's groups:
`Block2_from_the_dock.qgz` (here). Runs in `runs/` (out of git).

## The answer in short

- [Certain] **The dock builds 2D, Lumped and Hybrid Lumped from the ground up**: domain completed upstream from a rough
  outline and aligned, the basin generated from the DEM with its five reservoirs from the drawn crest lines, Suggest
  breaklines and the aligned centre mesh, the storm typed into Data tables, the split area reduction, the runs, the
  results page, scenarios, all saved in one QGIS project that reopens with the model.
- [Certain] **It cannot build Hybrid 2D on a generated basin**: the Hybrid 2D card changes nothing of the routing
  there (the generated basin keeps its reaches and lumped reservoirs). It was run through a three-step workaround of
  the dock's own fields (below), which a user would not find.
- [Certain] **His CN grid stops two of the four models in the dock as it is**: its holes (no value beside a CN grid in
  the dock) refuse every rain-on-grid run, and leave two coastal generated subbasins without a CN, which refuses the
  Lumped run. Filled with CN 88 (W79's value) by QGIS's own Fill NoData cells; then all four run.
- [Certain] **The 2D model equals W79's run 1 within 0.7 % at all five dams**, in and out; 48.8 min from Run to maps
  loaded (W79: 101.6). The generated basin is not HMS's Basin 3: the Lumped and hybrid peaks at R5A, R2A and Z4C are
  1.4 to 1.6 x W79's at the same volume (finer subbasins and reach n 0.04 against HMS's 0.1).

## Inputs a designer has (loaded as layers; `scripts/s01_inputs.py` writes the drawn ones)

| Layer | Source |
|---|---|
| DEM | his `GGC_2_MERGE_HDSM.tif`, 0.5 m (read only) |
| CN grid | his `CN_Include_Hill_Area.tif` (read only); in session 1 its holes filled with 88 by QGIS (see gap 1) |
| Manning grid | W79's `manning_hills_100.tif` (plain 0.04, hills 0.1), the raster W79's jobs name |
| Rough outline | `inputs/rough_outline.gpkg`, 1,416.6 km2: W79's edge kept within 100 m of the four outflow lines (the coast and three side outlets, drawn exactly); elsewhere one vertex every 4 km swung alternately 1 km out and 0.7 km in |
| Outflow lines | `inputs/outflow_lines.gpkg`: Sea, Wadi HAT north, Wadi Fizh branch, North stream (W79's four); kind and slope typed in the dock |
| Dams | `inputs/crest_lines.gpkg` (name, z) and `spillways.gpkg` (name, z, c, length): W79's five dams |
| Result lines | `inputs/dam_lines.gpkg`: the five dam lines |
| Storm numbers | `inputs/storm_numbers.json`: 251 mm in 24 h, the 145-row pattern of his FM_200yr.met, his 12-row ARF FM table, 100 km2 for the 2D part, the slopes; typed into the dock |
| Basin points | clicked in the dock (session 3 and 4), saved as `inputs/basin_points_hybrid.gpkg` and `basin_points_hybrid2d_outfalls.gpkg` |

## The steps, as a user does them

Scenario scripts: `s1_setup_lumped.py`, `s2_2d.py`, `s3_hybrid_lumped.py`, `s4_hybrid_2d.py`, `s5_project.py`, sharing
`w104_help.py`. Each session reads the project the last one saved. Step times in `logs/<session>_steps.json`, engine
stages in `logs/<session>_<run>_stages.json`, the harness logs `logs/log_<session>.txt`, pictures in `shots/`.

### Session 1: the domain, the basin, Lumped (20 of 20 checks)

1. **Start page** (`shots/01_start_page.png`): four cards. **The 2D card first**, because the Lumped card hides
   Terrain's domain-from-outline box (gap 5).
2. **Terrain**: the DEM, 20 m, Manning "a grid of n" with 0.04 elsewhere, Fill pits. **Boundaries**: the outflow
   lines, each row typed `normal` and its slope (0.003, 0.0057, 0.005, 0.005). **Structures**: crest lines (z field),
   spillways (z, C, length). **Results points**: the dam lines.
3. **Complete upstream** (115 s; 169 s the first time, which also built the DEM's 30 GB store in `runs/wadi2d_cache`):
   "Domain 1,399.36 km2, the outline of 1,416.58 km2 completed upstream: 17.40 km2 added, 22.76 km2 removed ... Kept
   edges: 4 lines; the ground read at 5 m." W79's hand-made domain is 1,398.9 km2.
4. **Lumped card; Hydrology**: CN grid chosen (the value box closes beside it: gap 1); **Generate the basin from the
   DEM**: the stream threshold searched as a user would (first attempt, `logs/s1_first_steps.json`): 10 km2 gave 78
   subbasins (100 s), **7.5 km2 gave 108** (62 s), against Basin 3's 104. Kept at 7.5 km2. Lag Kirpich (the default).
5. **2D card again; Align to catchments** to the generated subbasins (204 s): "Domain 1,398.25 km2, the outline of
   1,399.36 km2 aligned to 173 catchments: a rim of 1.27 km2 removed ... Cells of 20 m outside every catchment: 85,426,
   34.17 km2." The completed domain had to be loaded again as a layer and chosen as the rough outline (gap 4).
6. **Lumped card; Generate basin again** on the aligned domain (63 s): 111 subbasins, 51 reaches, 58 junctions, 5
   reservoirs (the crest lines; the three dike parts "drain under 1 km2, a saddle: no node"); 31.45 km2 reach the
   edge without meeting a stream. Reservoir areas against Basin 3: Bidah 03 20.03 (20.97, -4.5 %), Faydh 01 74.42
   (74.30), R5A 117.12 (117.10), R2A 175.94 (175.87), Z4C 211.56 (211.09).
7. **Data tables**: New, renamed "FM 10-1000yr", percent and cumulative, the 145 rows pasted; New, "ARF FM", the 12
   rows, no reduction below the table (`shots/05_tables.png`). **Storm**: Depth and pattern, 251 mm, 24 h, that
   pattern. **Area reduction**: lumped part "a curve: each subbasin at the area where its water enters the grid", ARF
   FM (in a Lumped model each element at its own area, the dock says). **Simulation**: 48 h, 5 min, GPU.
8. **Run** (12.5 s): "Finished. rain: each of the 225 elements read at the area-reduction table of its own drainage
   area, HMS's depth-area analysis". Saved as scenario Lumped; the project saved.

First attempt, kept in `runs/first_attempt/` and `logs/log_s1_first.txt`: the Lumped run was **refused**: "subbasins
S37, S36 are rain-on-grid, and a lumped-only run has no grid" (two coastal subbasins the CN grid covers under 90 %:
gap 2); and Align had aligned the rough outline itself, 1,416.5 km2, losing the completion (gap 4).

### Session 2: the 2D model (10 of 10)

The project opened in a fresh QGIS: "The model was restored from the QGIS project. Could not be restored: 4b. Area
reduction, grid.curve: no choice "Curve"" (gap 10). **2D card**, output folder `runs/2D`.

1. **Mesh**: kind "Aligned centre mesh" (makes the cells from centres). **Suggest breaklines** (240 s): "Suggested
   4756 bank lines along 769 thalwegs and 13725 crests (13160 other crest, 563 dam, 2 road), from the ground at 5 m";
   the layer saved as it came and chosen. **Build mesh** (145 s): "3,461,260 cells: 535,042 aligned along the
   streams, 2,926,218 squares (559,642 squares replaced). Smallest cell 154 m2" (`shots/s2_mesh_built.png`).
2. **Area reduction**, 2D part: "at one storm area" on ARF FM, 100 km2: "Factor at 100 km2: 0.9130". The job is
   W79's form: the design storm with `storm_area_km2` 100.
3. **Run**: the cell that sets the step named; **2,929 s (48.8 min) from Run to the layers loaded** (table below).
   Saved as scenario 2D.

### Session 3: Hybrid Lumped (10 of 10)

1. **Hybrid Lumped card**, folder `runs/HybridLumped`. **Basin points: New layer**; "Outfall" and **Click on the map**
   six times: 200 m down the generated reach below each dam, and at the HAT-S7 / HAT-S8 confluence (his HMS icon of
   HAT-J4; it snapped to the 260.36 km2 junction); the points renamed; **the layer saved** (a memory layer otherwise:
   gap 6).
2. **Generate basin** (60 s): "73 subbasins, 34 reaches, 36 junctions, 5 reservoirs; 534.8 km2 reach the edge ...
   and rain on the grid". Outfall areas: Bidah 03 20.06, Faydh 01 74.46, R5A 117.13, R2A 175.96, Z4C 211.61, HAT-J4
   260.36 km2 (859.6 km2 in all; W79 860.30). Junction table: each dam routed by a reach to its outfall, each outfall
   "water enters the 2D grid here".
3. **Area reduction**: lumped curve (each subbasin at its outfall's area, so at its dam's), 2D at 100 km2. The card
   leaves the catchments out of the mesh (`grid.exclude_lumped`).
4. **Run: 1,216 s (20.3 min)**. The engine: 73 subbasins, 859.58 km2, 2,149,311 cells left out (W79: 860.30 km2,
   2,149,911); entries 19 to 46 m from the clicks, "the lowest cell on the edge of the catchments it brings in"; the
   HAT water enters at junction J6, one pixel above the HAT-J4 outfall (the reach between is under 100 m).

First try (`runs/first_attempt/HybridLumped_R2A_outfall_off_stream`, stopped): W79's own entry point below R2A lies
over 100 m off the D8 stream and snapped to a 0.08 km2 rill, so R2A's 176 km2 were left to rain on the grid; the
summary says only "4 reservoirs" (gap 6).

### Session 4: Hybrid 2D, by a workaround (9 of 9)

The card alone, on Hybrid Lumped's basin (`logs/s4_first_card_alone_job.json`): `reach_routing: hms`, no
`lumped_entry` (the engine refuses `network` on a generated basin and `outlet` changes nothing there), the catchments
kept in the mesh: the lumped water still follows the generated reaches and the lumped reservoirs and enters at the
outfalls below the dams, so **the card gives Hybrid Lumped with the catchments dry in the mesh, not Hybrid 2D** (gap 3).
The nearest the dock's fields reach, all three needed:

1. **Structures: crest lines and spillways set to None, Generate basin, set back**: the basin holds no reservoir.
2. **Basin points**: an outfall 150 m above each dam on every stream of 5 km2 or more crossing its crest line (Suggest's
   thalwegs on the map, the upper side by the DEM; R5A 4, R2A 3, the others 1) and HAT-J4's; the first try put the
   outfalls 200 m below the dams as in Hybrid Lumped and lost about 84 km2 of the dams' branches to rain on the grid,
   because with no crest line nothing joins a dam's branches (`runs/first_attempt/Hybrid2D_branches_below_outfalls`).
   Lumped area: Bidah 03 19.31 of 20.03, Faydh 01 72.91 of 74.42, R5A 109.19 of 117.12, R2A 174.65 of 175.94, Z4C
   210.28 of 211.56, HAT-J4 260.36 km2; the rest (0.7 to 7.9 km2 a dam: pool flanks and streams under 5 km2) rains on
   the grid.
3. **Reach routing "Muskingum" with no K and X typed**: every generated reach is left out, the engine says so per reach
   ("reach R1 lacks muskingum_k_hours, muskingum_x: the water of J10 enters the 2D grid there"), so each subbasin's
   water enters at its own junction and the grid routes it, the dams as 2D pools.

4. **Area reduction** as Hybrid Lumped's; **Run: 2,289 s (38.2 min)**. Every reach "lacks muskingum_k_hours,
   muskingum_x: the water of J.. enters the 2D grid there"; 71 subbasins enter at their own junctions, read on the
   curve at those junctions' areas. Saved as scenario Hybrid 2D.

### Session 5: the project

The project of the four sessions opened once more (9 of 9); each run opened with Open a run and its results page
drawn (`shots/s5_results_*.png`: Lumped 230 elements of record, the five reservoirs shown by default; 2D 5, the dam
lines; Hybrid Lumped 153; Hybrid 2D 117); the four runs compared side by side on the results page and the table
exported (`compare_runs.xlsx`, `shots/s5_compare_runs.png`; but see gap 14); the project written back. Depth maps of
the three 2D runs drawn off the screen: `shots/map_s5_depth_*.png`; the domain `shots/map_s5_domain.png`. Its tree is `logs/s5_tree.txt`: one
group per model (`Wadi2D â€“ Lumped`, `â€“ 2D`, `â€“ HybridLumped`, `â€“ Hybrid2D`), each with Inputs (Terrain: the domains;
Hydrology: the generated basin; Mesh: Suggest's layers) and `Results â€“ <run>`.

## Times from pressing Run to the maps loaded (GPU, RTX 5080)

| Stage, s | 2D | Hybrid Lumped | Hybrid 2D | W79 2D / Hybrid Lumped / Hybrid 2D |
|---|---|---|---|---|
| Before the solver (job, tables from the DEM store, strips, pits, entries) | 397 (tables 374) | 157 (tables 144) | 338 (tables 318) | 2,096 / 1,374 / 573 |
| Solver loop, 48 h | 2,292 (426,926 steps) | 950 (519,596 steps) | 1,744 (423,984 steps) | 2,143 / 789 / 1,762 |
| Products (ground, 193 maps, rasters) | 213 | 84 | 207 with the loading | 1,833 / 984 / 1,516 |
| Layers loaded into the project | 26 | 25 | | - |
| **Run to maps loaded** | **2,929 (48.8 min)** | **1,216 (20.3 min)** | **2,289 (38.2 min)** | 6,093 / 3,151 / 3,867 to products done |
| Cells (squares / aligned cells + polygons) | 2,926,218 / 186,620 + 348,422 | 1,090,418 / 97,592 + 137,830 | 2,926,218 / 186,620 + 348,422 | 2,927,615 / 1,090,811 / 2,927,615 squares |
| Mass error | 3.7e-9 | -2.4e-8 | 4.7e-8 | 2.3e-9 / -1.3e-8 / 6.0e-8 |
| Water, Mm3: rain / lumped inflow / out | 271.0 / 0 / 214.9 | 101.2 / 112.4 / 207.6 | 103.7 / 178.3 / 226.4 | 271.8 / 0 / 215.6; 102.0 / 113.0 / 209.2; 102.0 / 161.6 / 207.9 |

Lumped: 12.5 s. The steps before a run: Complete upstream 115 s, Generate basin 52 to 100 s, Align 204 s, Suggest
breaklines 240 s, Build mesh 145 s. The DEM's store (30 GB) is built once, by the first engine step that reads it.

## Dam peaks against W79 (`dam_peaks.csv`, `scripts/s05_compare.py`; m3/s)

Read as W79 read its own: a lumped reservoir's inflow and outflow series (Lumped, Hybrid Lumped); for a 2D pool (2D,
Hybrid 2D) the outflow on the dam line and the inflow by the pool's balance (the water in W79's pool polygon between
two maps plus the dam-line outflow, a 15-min mean), the same pool polygons.

| Dam | 2D in / out (W79) | Lumped in / out (W79) | Hybrid Lumped in / out (W79) | Hybrid 2D in / out (W79) |
|---|---|---|---|---|
| Bidah 03 | 584 / 0 (581 / 0) | 479 / 0 (455 / 0) | 479 / 0 (455 / 0) | 463 / 0 (444 / 0) |
| Faydh 01 | 2,304 / 0 (2,314 / 0) | 1,198 / 0 (1,240 / 0) | 1,198 / 0 (1,240 / 0) | 1,214 / 0 (1,221 / 0) |
| R5A | 2,056 / 612 (2,071 / 608) | 1,673 / 927 (1,144 / 754) | 1,673 / 927 (1,144 / 754) | 1,538 / 839 (1,115 / 671) |
| R2A | 3,929 / 1,153 (3,958 / 1,151) | 2,732 / 979 (1,736 / 818) | 2,732 / 979 (1,736 / 818) | 2,684 / 1,369 (1,516 / 857) |
| Z4C | 3,226 / 3,434 (3,240 / 3,455) | 2,978 / 2,743 (2,101 / 2,025) | 2,978 / 2,743 (2,101 / 2,025) | 2,801 / 2,958 (1,941 / 2,018) |

| Dam | Inflow volume, Mm3: 2D / Lumped / Hybrid 2D (W79) | Inflow peak time, h: 2D / Lumped / Hybrid 2D (W79) |
|---|---|---|
| Bidah 03 | 3.82 / 4.14 / 4.15 (3.8 / 4.3 / 4.3) | 12.5 / 12.6 / 12.5 (12.5 / 12.8 / 13.3) |
| Faydh 01 | 14.88 / 15.26 / 15.59 (14.9 / 15.2 / 15.3) | 12.3 / 12.9 / 13.0 (12.3 / 13.2 / 13.8) |
| R5A | 22.81 / 22.88 / 24.45 (22.8 / 22.9 / 22.8) | 12.8 / 13.6 / 14.0 (12.8 / 14.7 / 15.0) |
| R2A | 34.32 / 32.97 / 36.82 (34.3 / 32.9 / 32.8) | 12.8 / 13.2 / 13.5 (12.8 / 14.2 / 14.0) |
| Z4C | 41.67 / 39.30 / 44.87 (41.6 / 39.2 / 39.1) | 13.8 / 13.7 / 14.3 (13.8 / 15.4 / 16.0) |

HAT-J4: Hybrid Lumped's entry 4,136 m3/s at 13.25 h, 46.97 Mm3 (W79: 2,472 m3/s at 15.75 h, 47.07 Mm3).

What each difference comes from:

- **2D** [Certain]: within 0.7 % of W79's run 1 at every dam, in and out, volumes to 0.1 Mm3 and peak times to 0.05 h.
  The dock's domain (1,398.25 km2, completed and aligned) and its own Suggest file gave the same answer as W79's
  hand-made domain and job: the model is the same model.
- **Lumped and Hybrid Lumped** [Certain for the volumes, Likely for the cause of the peaks]: the inflow volumes equal
  W79's within 0.2 Mm3 (3.7 % at Bidah 03, whose generated catchment is 4.5 % smaller than Basin 3's), so the rain,
  the area reduction (each dam read at its own area in both: 0.976 to 0.861) and the losses are the same. The peaks
  are 5 % higher at Bidah 03, 3 % lower at Faydh 01, and 46, 57 and 42 % higher at R5A, R2A and Z4C, 0.2 to 1.7 h
  earlier: that is the generated basin, not the dock's hybrid rules. It has 47 subbasins above the five dams against
  Basin 3's 18 (mean 7 to 20 km2 against 33; `basin_facts_lumped.json`), each with its own Kirpich lag on its own shorter path, and its reaches
  take n 0.04 from the Manning grid on the wadi beds against HMS's 0.1 (gap 7; W1 found +26 % on mode (b) from that
  n alone). The two are not separated here: the dock has no field to set a reach's n. Hybrid Lumped's dams equal
  Lumped's to the digit, as W79's run 3 equalled its run 2.
- **The two rules of the W103 note in Hybrid Lumped explain none of it** [Certain]: each subbasin is read at its
  outfall's area, the dam's own within 0.06 km2 (`arf_rules_hybrid_lumped.json`: runoff ratio 1.000 at every dam), and
  the water enters 19 to 28 m from the outfalls 200 m below the dams, as W79's run 3: the outfall points end the
  generated network at the dams, so no reach below a dam carries the water down to a rain-on-grid junction.
- **Hybrid 2D**: the dock's curve reads each subbasin at its own junction's area, his rule at the dam's area
  (`arf_rules_hybrid_2d.json`). Mean factor applied against the dam's: Bidah 03 0.980 / 0.976, Faydh 01 0.950 / 0.931,
  R5A 0.964 / 0.905, R2A 0.967 / 0.876, Z4C 0.970 / 0.861 (HAT-J4 0.964 / 0.846). By SCS runoff on each subbasin's
  CN that is **+0.5, +2.3, +7.5, +12.0 and +14.6 % of runoff**; the inflow volumes against Hybrid Lumped's (the same
  generated catchments) are +0.2, +2.2, +6.9, +11.7 and +14.2 %: [Certain] the rule makes the whole volume difference.
  Against W79's run 4 the peaks are 1.04, 0.99, 1.38, 1.77 and 1.44 x; taking the rule out to first order (peak in
  proportion to runoff) leaves 1.04, 0.97, 1.28, 1.58 and 1.26 x, [Likely] the generated basin's finer subbasins with
  their shorter lags entering the grid (19 of them above Z4C against HMS's 4), and the 0.7 to 7.9 km2 a dam (R5A the
  most) between the outfalls above the dams and the crest that rains on the grid with the 2D response. R2A's outflow
  (1,369 against 857) follows its larger, earlier inflow.

## The gaps (what, where in the dock, what a user would need)

Blocking (a model cannot be built or run from the dock without a way round):

1. **No CN beside a CN grid** (Hydrology, Curve number): choosing a CN grid closes the value box, so the job holds the
   grid alone; the engine refuses a rain-on-grid run whose grid leaves rained cells without a CN (W79's first try:
   14,561 cells of his grid). Blocks 2D, Hybrid Lumped and Hybrid 2D. Way round: his grid's holes filled with 88 by
   QGIS's own Fill NoData cells (session 1), so the dock is not involved. Needed: the box kept open beside a grid,
   "CN where the grid has none" (the engine's `hydrology.curve_number` already does exactly that; `job_builder`
   already writes both).
2. **A generated subbasin the CN grid covers under 90 % gets no CN, and the dock cannot give it one** (Hydrology,
   Generate basin and the subbasin table): it turns rain-on-grid with its row greyed, the tip says "fill the value in
   basin.json, then generate again", and a Lumped model is then refused ("subbasins S37, S36 are rain-on-grid, and a
   lumped-only run has no grid"). Way round: the same filled grid. Needed: a CN (parameter) column in the subbasin
   table writing `hydrology.subbasins[].parameters`, or the generator taking the value of gap 1 for a grid's holes.
   (Left to the worker on the subbasin table.)
3. **Hybrid 2D on a generated basin** (start page, the card): it sets `lumped_entry: outlet`, which only an HMS basin
   reads; a generated basin's lumped water follows its reaches and lumped reservoirs whatever the card, so the card
   gives Hybrid Lumped with the catchments kept dry in the mesh. Way round in session 4 (three steps, none of which a
   user would guess). Needed: the card setting, on a generated basin, each subbasin's water into the grid at its own
   outlet with no reach and no reservoir routed, and the dams' branches gathered above the dam.

Not blocking, but each cost a try or a number:

4. **Align to catchments aligns the Rough outline, not Terrain's domain** (Terrain, Domain from an outline): after
   Complete upstream the domain is the completed layer, but Align reads the outline picker, so the first attempt
   aligned the rough outline itself and lost the completion (1,416.5 km2 instead of 1,399.4); and Align replaces the
   completed layers, so choosing the completed layer as the outline means loading it again first. Needed: Align on
   Terrain's domain, or its words saying which outline it aligns.
5. **The Lumped card hides Domain from an outline** (Terrain), though a generated basin is delineated inside Terrain's
   domain: a Lumped model from the ground up needs another card first.
6. **Basin points that land on the wrong stream are not shown before the run** (Hydrology, Basin points): a click
   snaps to a stream within 100 m, else the largest drainage in reach; W79's point below R2A snapped to a 0.08 km2 rill
   and the summary said only "4 reservoirs"; the junction table shows Tc but no drainage area. Needed: the drainage
   area of each point's node in the table. Also "New layer" is a memory layer, lost with the project unless the user
   saves it (the dock says so in words).
7. **Reach n of a generated basin** (Hydrology): the reaches take Terrain's Manning (0.04 on the wadi beds here) and the
   dock has no field for it (W101 found 1); HMS's Basin 3 uses 0.1 (W1). Part of every lumped difference below.
8. **Ground that meets no stream** (Hydrology, Generate basin): 31.45 km2 of the domain in the Lumped model; the
   summary says it "rains on the grid", which a Lumped model has none of, and the run says nothing about it.
9. **No per-subbasin storm area** (Area reduction): his rule reads every lumped subbasin above a dam at the dam's area;
   the dock's lumped curve reads the area of the element where the water enters the grid (W98). Equal to his rule in
   Hybrid Lumped here (the outfalls are at the dams); not in Hybrid 2D (below). (The coordinator's W103 note, put to him
   as a rule change.)
10. **A reopened project does not restore the 2D part's curve** ("Could not be restored: 4b. Area reduction,
    grid.curve: no choice "Curve""); the sessions set it again.
11. **The Lumped card shows the Area reduction's 2D part** (`shots/05_reduction_lumped.png`), which W101 says it hides.
12. **Suggest breaklines gives 13,725 crests to review** (13,160 "other crest") beside 4,756 banks on Block 2; the
    aligned mesh does not use them, but a user is told to delete what is wrong.
13. **Fixed here** (`e3b116c`): Generate basin built its own 27 GB DEM store in each model folder.
14. **Compare runs cannot put a dam side by side across the model types** (results page): a 2D pool has no inflow of
    record, only its dam line (outflow), and a lumped reservoir and the dam line of the same name are two elements; the
    four-run table shows the dam lines (zero in Hybrid Lumped, whose dams are left out of the mesh; none in Lumped). The
    dam table above was made by script with W79's pool balance (`scripts/s05_compare.py`). Needed: a pool's inflow by
    balance as an element of record (a polygon or the crest line's pool), and a match of a reservoir to its dam line.
15. **The outflow lines no longer sit where the streams leave the completed domain**: on the dock's domain the pre-run
    check of all three 2D runs says "a stream draining 269.87 km2 leaves the domain at (452352, 2715540) with no
    outflow line there" (Wadi Fizh's branch, which W79's domain sent out 2.7 km east) and "35.72 km2 ... at (441114,
    2740396)"; the Fizh branch and North stream lines open 0.3 of 0.6 km and 0.4 of 0.7 km. The depth maps show the Fizh
    branch running along the south edge to the sea; no dam is affected (they lie 11 km and more upstream). Not redrawn
    here; a user would redraw the two lines where the dock says. The dock's words were enough to find it.

The dam kind of the Basin points was not needed: the crest lines in Structures make the reservoirs (a dam point only
adds an alias name).

## Fixes committed on this branch

- `e3b116c` **Generate basin reads the runs' own DEM store** (`dock.py`, `generate_basin`): its job's cache was
  `<output>/wadi2d_cache`, so every model folder that generated a basin built a second 27 GB store of Block 2, again
  each time; now the runs' own, as Build mesh already did. Checked through the real dock (session 1's check "Generate
  basin reads the runs' own DEM store").

## Files

`s1_setup_lumped.py` to `s5_project.py`, `w104_help.py`: the dock scenarios. `scripts/s01_inputs.py` the drawn layers
and the typed numbers; `s05_compare.py` the dam peaks (W79's pool balance for 2D pools); `s06_basin_facts.py` what a
generated basin holds above each dam; `s07_arf_rules.py` the area-reduction rule's share. `logs/`, `shots/`,
`dam_peaks.csv/json`, `basin_facts_*.json`, `arf_rules_*.json`, `compare_runs.xlsx` (the dock's own comparison).
`inputs/basin_points_hybrid2d.gpkg` is the first Hybrid 2D try's points (outfalls below the dams), kept as its record. `runs/` (out of git): the four run folders, their
domain, breaklines and basin folders, `first_attempt/`, the throwaway QGIS folders `qgis/`.
