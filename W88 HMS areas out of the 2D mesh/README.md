# W88 HMS areas out of the 2D mesh

**Live.** Item 1 on `feature/hms-areas-out-of-mesh` (off `8bf9fd7`), merged into `feature/fast-products` at
`0a87ffe` by the coordinator. Items 2 to 6 on `feature/hms-dock-and-lumped` off `0a87ffe`, not merged. Nothing pushed.

## What was asked

His design of 2026-11-15, for run 3 of `W79 Block 2 four ways` (HMS in the mountains, 2D downstream): one
project-wide 2D domain stays in the job, and the cells under the catchments that HMS routes are left out of the mesh
for that run: no tables, no solver work, no maps there, the edge on the catchment a closed wall, the inflow points
still on active cells.

## 1. The mesh leaves out the carried catchments

### The rule, as built

- **Job:** `grid.exclude_lumped` (off by default) leaves out every *carried* lumped subbasin. `grid.exclude_subbasins`
  names lumped subbasins outright, with or without it. `hydrology.entry_snap_m` (500 m) is how far an entry may move.
- **Carried** means: lumped, with no outlet of its own, and above an inflow's element or the end of a hand-back's
  route on links the grid does not carry. It is the engine's own reading of who brings each subbasin's water in
  (`_check_routes`, now shared as `_carried`), so the mesh and the water books cannot disagree.
- **Not carried, so not left out:** a lumped subbasin that enters at its own outlet (run 4's way). The grid routes
  its water through its own polygon, and usually a routed wadi from above crosses it. Where none does, the user names
  it in `grid.exclude_subbasins`; its entry then moves to the wadi just outside. A 2D subbasin named there is refused.
- **Which cells:** those whose centre lies in a left-out polygon, picked exactly as the rain mask picks cells
  (`rasterio.features.rasterize`, a polygon at a time). So a cell is either left out, or in the mesh and rained on or
  masked as before. There is no buffer and no rim.
- **The edge** is the domain's edge there, to everything: the tables close the faces, the pit check reads it as an
  outlet as it reads any edge, the strip ends against it.
- **Entries:** an inflow (or a named subbasin's outlet) whose point lies in a left-out cell moves to the lowest cell of
  the mesh that touches the catchments that entry itself brings in, within `entry_snap_m` of the point. A catchment's
  pour point is the lowest point of its edge, so this is the wadi just outside. Reading only the entry's own
  catchments keeps it off a lower wadi beside another left-out catchment. None within reach stops the run: "inflow X
  at (x, y) lies in the catchments left out of the mesh, and no cell of the mesh on the edge of the N catchments it
  brings in lies within 500 m of it (the nearest is 122 m away): move the point to the wadi below them, or raise
  hydrology.entry_snap_m". An entry whose point is already on an active cell stays where it is. A moved entry with
  `entry: wadi` then walks up clear of the lines as before. `entries.json` holds the asked and the entered point.

### Where it reaches

| Part | What happens | How |
|---|---|---|
| Uniform grid | cells leave the mask before the tables | `prepare_grid`; the grid cache key takes the cells left out |
| Aligned centre mesh (his choice) | the strip is built on the mask that is left: stations in left-out cells give no centre, rows stop at the edge, the cells there are cut to the squares they replace | the generator's own domain-edge rule (W46); nothing new in `wadi2d/strips/` |
| Corridors from a banks file | cut a cell clear of the left-out area | the domain polygon handed to the corridor builder |
| Quadtree | the same mask before the mesher | `mesh_grid`; `wadi2d mesh` and the cost estimate count the same cells |
| Rain | unchanged code: a left-out cell is not in the forcing | - |
| Edge check before the run (W78) | a stream across the outline along a left-out catchment is not named | `stream_crossings(..., left_out)` |
| Edge check after the run | the wall is an edge: a pool against it is named, as against any edge; the cells of a moved entry count as open, so water running in is no pool | `_write_outputs` |
| Pit check (W85) | cells on the wall are edge cells, as on the outline | unchanged code |
| Maps, pixel maps, cell-grid layer, remake of the maps | nothing under the catchment | they read the grid's mask; `prepare_grid` finds what is left out from the run's own job |
| Record | a `left_out` event (subbasins, cells, km2, who brings each in) and a warning in words | `progress.jsonl` |

A job where everything is left out raises `NothingOnTheGrid` ("nothing is left for the 2D model"); item 2 turns that
into a lumped run.

### Also changed, and why

- `entries.json` no longer lists a point for a lumped `entry: wadi` subbasin that an inflow below it carries (W79's
  record fault: "enters at the wadi outlet of its polygon" where no water enters). With its cells left out it has no
  cell to give, so the fault had to go first. A subbasin that does enter under its own name is listed as before.
- `_check_routes` in `wadi2d/run.py` is split in two (`_carried` and the check); no behaviour changed.

### Tests (`tests/engine/test_left_out.py`, 18)

A valley of 384 x 128 m at 4 m cells falling east; `Up`, the west 160 m, lumped and carried to an inflow from the
junction below it; rain on the grid on the rest; a free outlet at the east end.

| Check | Result |
|---|---|
| Cells left out against the centre rule read with shapely (straight and oblique edge) | equal, cell for cell |
| Outflow of the run without the catchment against the full domain, same entry 40 m below the edge | rain and inflow equal to 1e-9, outflow volume to 1e-5, peak and line volume to 1e-4; mass error under 1e-6 |
| Entry given inside the catchment, off the wadi | enters on the wadi cell beside the edge; against the full domain with the entry given there: outflow within 1e-3, peak within 1 % (the wall holds no backwater) |
| No cell within reach | exit 2 with the words above |
| Aligned centre mesh, a thalweg through both parts | no aligned cell under the catchment, the strip reaches the edge, its cells tile the squares they replace, the same strip from the cache; run closes to 1e-6, outflow within 1 %, peak within 3 % of the full domain's aligned run |
| Quadtree | cells left out, books close, outflow within 1 % |
| Maps, pixel depth, cell-grid layer, `wadi2d products` again | nothing west of the edge |
| Carried subbasin with `entry: wadi` | no record; no pool or pit named at the wall |
| Nothing carried; everything left out; a 2D subbasin named | said in words |
| Stream check | a crossing inside the left-out area is dropped, one elsewhere kept |

**Old jobs.** Three jobs written without the new fields (hybrid, aligned, quadtree) hashed and run with the code
before (`8bf9fd7`) and after: job hash, grid cache key and strip cache key identical; steps, inflow, outflow, storage
and the outlet line's series file identical to the byte. The rain total moves in its 16th digit from one run to the
next with the same code (a float sum), before and after alike.

Suites on the branch: `tests/engine`, `tests/strips`, `tests/basin` and `tests/hydrology/test_network.py` 712 of 712
(the 17 here among them; an 18th, the estimate and the mesh preview, was added after and passes); `tests/plugin`
whole 584 of 584. The full suite was not run (his rule: at the merge).

### Dock

Hydrology has a tick, "Leave the catchments the lumped network carries out of the 2D mesh" (`grid.exclude_lumped`),
written into the job only when ticked. On the HMS route it leaves something out once the lumped water is kept on
the network (item 2); with each subbasin entering at its own outlet nothing is carried and the run says "no cell is
left out".

### Not done, not tested

- No run on Block 2 (run 3 is the coordinator's); no GPU run of a job with left-out catchments (the mask is made
  before the backend is chosen, so none is expected to differ).
- A generated basin (`hydrology.basin_json`): the carried rule reads its routes, but no test runs one with cells
  left out, and a hand-back line built at a junction whose whole upstream is left out is untested.
- A dam's crest line or pool polygon inside a left-out catchment is simply on no cell; not looked at.
- The edge check after the run names a pool against the wall in the words it uses for the outline ("the domain
  polygon likely cuts a valley there"); there the cause is a catchment polygon off the divide. Wording not changed.

## 2. Lumped water down the HMS reaches, in the dock (`hydrology.lumped_entry`)

`wadi2d/engine/network_entries.py`. `outlet` (the default, the HMS import as before): each lumped subbasin enters at
its own outlet and the grid routes it (run 4). `network`: an element is *lumped all the way* when every subbasin
above it is lumped; a lumped subbasin's water goes down its links while the next element is lumped all the way, and
enters at the last one, the element where rain-on-grid water first joins (run 3: the dams and HAT-J4). That element
gets one inflow of its outflow at its HMS icon (a reach: its downstream end), `entry: point`, unless the job already
gives an inflow from it (W79's points 200 m below the dams), and the subbasins it carries lose their outlets. Where
the walk ends at an outlet of the network (an HMS sink, or Basin 1's dam junctions, which drain nowhere) the water
leaves the model, as in HMS: the inflow is written with `enters: false`, nothing enters the grid, the series is kept,
and the subbasins above count as carried, so the mesh can leave them out. Refused in words: an element with no icon,
a second outlet (diversion, auxiliary spillway) feeding rain-on-grid water, `network` on a generated basin. The
resolution runs where a generated basin's does (`_resolved`), so `config.resolved.json` holds the inflows.

Dock, Hydrology > HMS: "Lumped water enters the 2D model": "At each subbasin's outlet" or "Down the HMS reaches and
dams, entering where rain-on-grid joins"; only the second is written into the job.

## 3. The lumped-only run (`run.lumped_only`)

`wadi2d/engine/lumped_run.py`. Asked for, or taken when every cell of the domain is under a left-out catchment (the
run says so). No grid, no tables, no DEM needed. The folder: `config.resolved.json`, `progress.jsonl` (start, and
done with `lumped_only`), `results.h5` with every element's series under `series/network` and the attribute
`lumped_only` (no mask, no maps), `series/network_<element>.csv`, `network.gpkg` and `network_peaks.csv`, and the
marker `lumped_run.json`. Every element is written, the network computed whole as HMS does. Refused: a rain-on-grid
subbasin, a hand-back, no rain.

Dock: "The HMS way only" in Hydrology > HMS. The run's group gets "Lumped network, the HMS way": catchments hatched
and labelled with name, area, peak and time; reaches, junctions, reservoirs and outlets labelled with peak and time
(highest pool on a reservoir). The time-slider buttons stay off; Result lines lists every element (the engine's
listing reads the file unchanged), and a right-click on any of these features opens its chart, since each carries the
element's `name`. Choosing the folder again brings its network back.

## 4. Each element at its own area (`hydrology.arf_by_element`)

In a lumped-only run every element is read as HMS's depth-area analysis reads it: its sub-network run again at the
storm area of its own drainage area (`wadi2d.hydrology.depth_area.analyse_point`), its series of record from that run;
`network_peaks.csv` and the marker give each element's area and factor. What `W79 .../scripts/s03_lumped.py` did by
script. Needs `storm.arf`; refused beside a given factor, beside subbasins with storm areas of their own, and on a run
with a 2D part. Dock: "Each element at its own drainage area's area reduction", offered with the HMS way only.

## 5. The depth display cutoff

`plugin/wadi2d_qgis/style.py` `DEPTH_CUTOFF_M` = 0.05 m; the user's value is saved in QGIS settings
(`wadi2d/depth_cutoff_m`) and set in Run > "Draw depth from" (0 to 1 m; 0 draws every wet cell). Every depth style
(cell maps and the live layer, pixel depth, the depth picture, the time slider's mesh, the pixel slider) starts its
ramp at the cutoff with the colour the ramp had there and clips below it; the values are not touched. A new value
restyles the project's depth layers at once. The aligned cells get a layer of their own, "Aligned cells: maximum
depth, m", in Model setup, off. Make map's depth sheet says "Depth under X m is not drawn; the rasters of record keep
it."

## 6. The HMS catchments in a run's group

A run with a 2D part writes `network.gpkg` too (the elements whose series it wrote), its subbasins with `left_out` and
`enters_at`; the dock puts it in the run's group, the left-out catchments in grey with "left out of the 2D mesh" in
their label.

## Tests of items 2 to 6

- `tests/engine/test_lumped_network.py` (8), on the valley of item 1 with an HMS basin of its own (Up, J1, reach R1,
  Low, J2, sink Out): the rule enters Up's water at R1's icon and the run equals the same inflow given by hand to the
  digit; with the tick Up is left out and the outflow holds to 1e-5; resolving twice adds nothing; a missing icon and
  `network` on a generated basin are refused; all lumped leaves at the sink, and the domain wholly left out runs
  lumped only (six elements, no mask, no maps); a lumped-only run writes every element, the junction sums its
  inflows, the engine's listing reads it, the layers carry the peaks; refusals; each element at its own area equals a
  plain run at that area to 1e-12 for Up, Low and J2; old jobs keep their hash with the new fields at their defaults.
- `tests/plugin/test_network_qgis.py` on QGIS 3.44.8's Python: the layers land in the run's group, labelled and
  categorised, with the left-out mark; a cell under 0.05 m draws transparent and one over it does not; 0 draws them;
  the restyle; the cut colour read off the ramp.
- `tests/plugin` whole; the QGIS smoke and sheets tests now accept a cut ramp in place of a transparent first stop.
- Real dock (`dock_hms_way.py`, QGIS 3.44.8, throwaway profile, CPU engine; `log_dock_hms_way.txt`): **30 of 30**.
  Block 2 Basin_1 under FM_100yr the HMS way with each element at its own area: 40 elements in about 3 s, the
  network group with 18 catchments labelled, time-slider buttons off, Result lines listing 40 elements, a right-click
  name at Bidah 03's junction matching its chart, which holds the record's peak (362.4 m3/s; Faydh 01 993.5, R5A
  887.1, R2A 1,356.1, Z4C 1,666.4, each at its own drainage area); the folder chosen again brings the network back.
  Bidah at 20 m, S13 rain-on-grid and the other 17 down the reaches with the tick: Bidah 03 takes S13's grid water so
  it gets no inflow, the other four dams' water leaves at the network's outlets, 17 subbasins and 1,106 cells of the
  domain left out and marked in the layer, the depth layers cut at 0.05 m and restyled at 0.1 m, Make map wrote the
  sheets with the cutoff in the depth sheet's notes. The first attempt failed one check, the scenario's: it expected
  Bidah 03 among the outlets, where S13's water joins on the grid.
- Suites on the branch: `tests/engine`, `strips`, `basin`, `hydrology`, `storm`, `products`, `render`, `workbook`,
  `tables`, `terrain` 1,322 passed, 9 skipped; `tests/plugin` 590 passed. Full suite not run (his rule: at the merge).

### Not done, not tested (items 2 to 6)

- No Block 2 run 3 through the dock (Wadi HAT's HAT-J4 and the 200 m dam points are the W79 job's own inflows,
  which the rule keeps); no GPU run.
- `arf_by_element` runs every element's sub-network again: Basin_1's 40 elements took 3 s, Basin_3's 281 about 1 s
  by W79's script; not timed on a larger basin.
- A generated basin as a lumped-only run is coded (its network run whole) and not tested.
- The time slider and Make map ignore the network layers; the right-click chart works only while they are shown.
- The QGIS-side cutoff test writes and then removes the user's `wadi2d/depth_cutoff_m` setting in the default profile
  of QGIS's Python; a value set by hand before would be lost.
- Commits: the engine's three pieces (network entry, lumped-only run, per-element ARF) are one commit and the dock's
  one, because they share `run.py`, the schema and the Hydrology section; the cutoff is its own.
