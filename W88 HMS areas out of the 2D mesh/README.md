# W88 HMS areas out of the 2D mesh

**Live.** Branch `feature/hms-areas-out-of-mesh` off `feature/fast-products` (`8bf9fd7`), not merged, not pushed.
Item 1 below is built and tested in the engine; items 2 and 3 of the order (a lumped-only run as a first-class run,
the display cutoff for depth layers) and the run group's HMS catchments layer are not built yet.

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
written into the job only when ticked. **Through the dock's HMS route it leaves nothing out today**: the HMS import
gives every subbasin its own outlet (run 4's way), so no subbasin is carried, and the run says "no cell is left out".
Run 3's way (subbasins kept in the HMS reaches down to a dam or a junction) is written by script so far
(`W79 .../scripts/s02_jobs.py`: `inflows` from elements, subbasins without outlets); a choice for it in the dock is
the next piece.

### Not done, not tested

- No run on Block 2 (run 3 is the coordinator's); no GPU run of a job with left-out catchments (the mask is made
  before the backend is chosen, so none is expected to differ).
- A generated basin (`hydrology.basin_json`): the carried rule reads its routes, but no test runs one with cells
  left out, and a hand-back line built at a junction whose whole upstream is left out is untested.
- A dam's crest line or pool polygon inside a left-out catchment is simply on no cell; not looked at.
- The edge check after the run names a pool against the wall in the words it uses for the outline ("the domain
  polygon likely cuts a valley there"); there the cause is a catchment polygon off the divide. Wording not changed.
- The real-QGIS dock check waits for items 2 and 3.
