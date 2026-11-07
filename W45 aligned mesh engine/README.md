# W45 aligned mesh engine

**Status (2026-11-07): started on his instruction of the same day: "no matter the cost. build me the best engine, works
with the aligned mesh." The mesh generator comes first; the cap, the EA gate and everything else that was argued on
square faces is parked until the mesh is in (`W43` stays on its branch, unmerged).** Nothing built yet beyond the plan
below; the MeshKernel trial of `W44` is still running.

## What is being built, in one paragraph

The engine keeps its square tiles everywhere a breakline is not, and along every breakline it carries a **strip of cells
aligned with the line**, built by MeshKernel, whose faces lie on the line: the face reads the line's own ground, with no
staircase and no half-cell offset. The strip's cells are general polygons (quads along the line, triangles and
pentagons where it joins the tiles). One scheme steps both: level per cell, normal momentum per face, sub-grid tables on
cells and faces, implicit friction, crest faces with the critical-flow cap. Decision 19's scheme already runs on any
polygon in the W3 prototype (`W3 breakline faces test/graph.py`: skew-corrected level gradient, Perot cell momentum,
the same [1] to [6] order as the lattice kernel); that prototype is the reference for the port. The tiles keep their
kernels untouched; the strips get their own cell and face kernels, CUDA and a Numba twin from one statement order; the
faces between a tile cell and a strip cell are strip faces that read the tile cell's state.

## Architecture decisions (his engineering rules: small modules, one source of truth, contracts, extension points)

1. **A hybrid grid, not a replacement.** `TileGrid` stays the unit of the lattice; a new `StripSet` holds the aligned
   cells as structure-of-arrays in along-line order: cell centroid, area, the faces of each cell; per face the two cells
   (a tile cell by its state index, or a strip cell), length, unit normal, midpoint, centre-to-centre distance along the
   normal `dn`, and the skew vector. Cells under a strip are masked out of the tiles. The job asks for strips through the
   Mesh section: rows and widths per breakline kind, off by default; a job without strips runs to the last digit as today.
2. **One scheme.** The strip kernels implement exactly the W3 polygon scheme, which on a square lattice reduces to the
   production rule (W3 proved the time-step rule identical and the channel cases within the lattice's). No second
   physics: the same `NumericsRecord`, the same sub-grid lookups, the same crest cap with the energy head.
3. **Tables from the DEM pixels of each polygon**, cell by cell (volume against level) and face by face along the face
   segment (wet width and conveyance against level), the lattice's own `cell_table` and `face_table` kernels on a pixel
   set instead of a square block. A breakline face's profile is the line's ground along the face, read from the DEM
   pixel by pixel; nothing is lifted, nothing is a ridge rule.
4. **The join.** Interface faces are strip faces whose one side is a tile cell: the strip kernel reads and writes the tile
   cell's level through the state index, the tile kernel never sees the strip. Fluxes into a tile cell from strip faces
   are gathered in a fixed order, never with atomics, so GPU runs stay bitwise repeatable (W31, W33).
5. **Time step.** One global step from the smaller of the tile rule and the strip rule; the strip's local time-stepping
   class comes after the race shows the cost.
6. **Mesh contract.** The strips are written beside the tables as one file (nodes, faces, cells, the tile cells masked,
   the interface faces), cached by the same key as the tables, read by the engine, the plugin (as a mesh layer through
   MDAL) and the tests alike. MeshKernel writes it; nothing else in the engine imports MeshKernel.
7. **Outputs.** Series lines and points read strip faces and cells as they read tiles; frames carry the strip cells as
   an unstructured part of the NetCDF; pixel products resample strip cells to the DEM pixel as tiles are.

## Stages and gates (each on its own branch, merged behind the full suite; a feature is done when the dock runs it)

| Stage | What | Gate |
|---|---|---|
| 1 | The polygon-cell solver in the engine, CPU (Numba), from W3's `graph.py`; a `StripSet` contract; tests | W3's 45-degree channel cases within 3 %; still water exact on any polygon; the lattice as polygons gives the tile kernel's numbers |
| 2 | Sub-grid tables for polygon cells and faces from the DEM | Volume and conveyance of a square polygon equal the tile tables to float32; a triangle's volume equals its pixels' |
| 3 | The hybrid grid: tiles plus strips, interface faces, one stepper | Mass closes to 1e-8; still water across the join exact; a channel through a strip and tiles agrees with all-tiles within 1 % |
| 4 | MeshKernel strips from the breakline layer, the mesh contract, the cache | Faydh 01's banks meshed; orthogonality and distance to the line measured (W44) |
| 5 | CUDA kernels for the strip path, the twin, speed | CPU and GPU within 1e-4 m; ns per strip cell step measured against 0.6 for tiles |
| 6 | Breaklines, crest lines, walls, the cap on aligned faces | The flume overfall 0.97 to 1.01 of critical; the levee holds to its top |
| 7 | Inflows, boundaries, hand-backs, lines, points, frames, pixel products on strips | Every existing dock scenario passes with strips off; the W41 Block 2 hybrid with strips on finishes and its books close |
| 8 | The plugin: Mesh section controls, the mesh layer, Make map | Through the real dock on Bidah |
| 9 | The race, through the dock: Faydh 01 at 20 m and 10 m, the W26 bank cases, the flume | Faydh 01 within 3 % of no lines; the W26 bank losses gone; the overfall capped |

## [PRESERVE-CHECK]

- KEEP: every tile kernel and every result of every job without strips, to the last digit, cache key and hash
  included; the mesher of `W10` (the quadtree) as it is; every dock section.
- CHANGE: additions only, behind `mesh.strips` (off): the strip set, its tables, its kernels, the join, the mesh
  contract, the MeshKernel step, the plugin controls. One line in the stepper to step the strips after the tiles.
- FILES: new packages `wadi2d/strips/` (contract, tables, mesher bridge) and `wadi2d/solver/poly/` (CPU and GPU
  kernels); `wadi2d/solver/stepper.py`, `model.py`, `backend.py` (the strip step and state); `wadi2d/run.py` (build the
  strips when asked); `plugin/wadi2d_qgis/sections/mesh.py`; tests under `tests/strips/` and `tests/solver/`.

## Stage 1 (2026-11-07): the polygon-cell solver on the CPU, passed

`wadi2d/solver/poly/`: `mesh.py` (the contract, `PolyMesh`, `finish`), `kernel.py` (the W3 scheme in the lattice
kernel's order, float32 as the tile twin, the energy-head cap on the upstream cell's velocity with this face's own
flow left out), `model.py` (a model on one polygon mesh, the lattice's time-step rule), `from_tiles.py` (the lattice
itself as polygons, the tile tables copied face by face). Tests `tests/solver/test_poly.py`, on W3's channel (bed
falling 0.2 %, 2:1 banks, 60 m3/s on 60 m, 20 m cells, 96 x 96, 3,000 s), the engine's own tables for both kernels:

| Case | Tile kernel | Polygon kernel on the same squares | Rule |
|---|---|---|---|
| Channel along the axis, depth / normal depth | 0.9855 (-1.45 %) | **0.9856 (-1.44 %)** | within 3 %; the two within 1 % |
| Channel at 45 degrees | 1.0251 (+2.51 %) | **1.0132 (+1.32 %)** | within 3 % |
| Still water at 101 m, 600 s, largest speed, m/s | 3.5e-6 (axis), 6.3e-6 (30 degrees) | 4.4e-6, 1.1e-5 | within 3 x the tile kernel's float32 noise |
| Still water, volume after 600 s | | 1 + 4.4e-8, 1 + 5.0e-8 | within 1e-7 |

[Certain, measured] On squares the polygon kernel is the tile kernel to 0.01 % on a straight channel; at 45 degrees
its Perot advection reads 1.2 points closer to normal depth than the lattice's upwinding, as W3 found.

## Stage 2 (2026-11-07): sub-grid tables for polygon cells and faces, passed

`wadi2d/strips/geometry.py` (`MeshGeometry`: nodes, rings, faces, with areas, centroids, lengths and normals from them,
and `from_rings` to find the faces of a set of rings) and `wadi2d/strips/tables.py` (`Pixels`, `build_poly_tables`:
a cell's table from the pixels inside its ring by the crossing rule, a face's from the ground sampled along its
segment at the pixel spacing, the higher pixel either side, both through the lattice's own `_cell_table` and
`_face_table`). Tests `tests/strips/test_tables.py`:

| Case | Result |
|---|---|
| An 8 x 8 lattice at 10 m on 1 m pixels, described as polygons, against `build_tables` | zmin, mean bed, hc and the cell tables equal; every face's invert, table top and table equal to float32 (112 faces); the skew is 0 |
| A square cut into two triangles | the south-east triangle's table equals `_cell_table` on exactly its own pixels; one face, the diagonal |
| A 30 x 10 m quad turned 30 degrees on a plane falling 5 % | area 300 m2; full to the brim the surface stands at the highest pixel; the mean bed is the plane's at the centroid |
| A face along a one-pixel ridge | reads the ridge on every sample; a face short of it reads the plain |

A breakline face on a strip will sample the line's own ground this way: nothing to lift, no ridge rule.

## Stage 3 (2026-11-07): the hybrid step on the CPU, passed

`wadi2d/strips/hybrid.py` (`HybridCpu`, `ghosts_for`): the tile backend steps its faces and positivity as ever; in its
new `before_update` hook (`solver/cpu/backend.py`) the strip mirrors the tile cells it touches into ghost entries of
its own cell list, adds those cells' four lattice faces to the Perot velocity, the Green-Gauss gradient and the
advection rate (a neighbour's velocity from that neighbour's own four faces), steps its faces, limits its outflows
(a real cell gives what it holds, a ghost what its lattice faces left it), updates its real cells, and hands each
ghost's net outflow to the tile update as a source term; `after_update` restores the sources and writes each
interface's discharge and velocity into the tile's closed face on that edge, own slot and halo copies, so the next
tile step's momentum stencil sees the flow the strip carries. One global step: the smaller of the tile and strip rules.
Interface faces are lattice edges sampled from the DEM like any strip face. Tests `tests/strips/test_hybrid.py`: the
middle 10 x 10 cells of W3's channel masked out of the tiles and carried by a strip of the same squares.

| Case | All tiles | Tiles + strip | Rule |
|---|---|---|---|
| Channel along the axis, depth / normal depth | 0.9855 | **0.9848** (-0.077 points) | within 0.2 points |
| Channel at 45 degrees | 1.0251 | **1.0250** (-0.005 points) | within 1 point |
| Still water at 101 m across the join, 600 s: largest speed | 6.1e-6 m/s (tiles) | 1.6e-6 (strip) | under 2e-5 |
| Still water, volume | | 1 + 7e-9 | within 1e-7 |
| A closed box, a 0.6 m step released across the join, 300 s | | 9.9 m3/s crosses the join; volume 1 + 5e-9 | within 1e-7 |

Two things were wrong on the way and are now in the tests: a ghost's advection rate left at zero read the straight
channel +0.56 points high; with it, and the tile's closed face still reading zero discharge, +0.4; with the
interface flow written into that face, -0.08.

## Stage 4 (2026-11-07): the strip mesher in the engine, and the first race, passed

`wadi2d/strips/mesher.py`: a `Corridor` is a curvilinear grid, stations every `along` metres on the smoothed centre
line, rows at fixed offsets along the station normals, the rows that carry a breakline snapped onto it along their own
cross lines with the outer rows carried (the step of the W44 trial that MeshKernel could not do; the engine needs no
MeshKernel). The lattice cells under a corridor and within half a cell of it are removed, the gap triangulated on the
existing nodes alone (shapely's constrained Delaunay), so every gap face shares its edge with a lattice cell, a corridor
cell or another triangle, and every interface face is a lattice edge. A corridor that folds at a bend is refused by
name with its stations. `breakline_faces` names the faces on each snapped row for stage 6. Tests
`tests/strips/test_mesher.py`: a corridor of ten 10 m rows along W3's channel's middle 1,152 m, the toes at +-30 m on
its rows, through the hybrid of stage 3 with the tables of stage 2.

| W3's channel, depth / normal depth | Square tiles (the staircase) | The lattice as polygons | **Tiles + an aligned corridor** |
|---|---|---|---|
| Along the axis | 0.9855 (-1.45 %) | 0.9856 (-1.44 %) | **0.9868 (-1.32 %)** |
| At 45 degrees | 1.0251 (+2.51 %) | 1.0132 (+1.32 %) | **0.9914 (-0.86 %)** |
| Steps, 3,000 s, axis / 45 degrees | 1,535 / 2,909 | 1,549 / 2,840 | 3,313 / 4,692 |

The corridor: 580 cells of 20 x 10 m, 272 to 320 gap triangles, 464 to 476 lattice cells replaced; the largest skew
27 to 37 degrees, in the gap triangles. [Certain, measured] The aligned faces take the 45-degree channel from +2.5 %
to under 1 %, the best of the three; [Certain] the 10 m rows halve the time step, the cost the strip's own
local-time-stepping class will have to pay back (W40's finding, now measured here).

## Stage 7, first piece (2026-11-07): a job carries corridors through `run_job`, passed

The `strips` section of a job (`config/schema.py`: `Strips`, `CorridorSpec`, `SnapRow`; off by default and popped from
the hash when off, so every existing job keeps its hash) names each corridor by its centre line, its row offsets and the
rows that snap to a line. `wadi2d/strips/build.py` takes the lattice cells under the corridors out of the mask before
the tables are built (so their faces close as any inactive cell's do), builds the strip's own tables from the DEM window
under it through the run's bed reader, and gives a result line the strip faces it crosses, signed as the lattice signs
them. `run.py` wires the hybrid of stage 3 into the CPU backend's hooks, books the strip's water and rain in the balance
(`engine/monitor.py`), and adds the strip's crossings to every line. A strip run is CPU only for now and refuses a GPU
backend, a resume, a CN raster, gridded rain, a depth grid and subbasins by name; stage 5 and the rest of stage 7 lift
those. `wadi2d/strips/banks.py` turns W26's suggested banks into corridors by the W44 recipe (chain the parts of a side
along the thalweg, pair the left chain with the right chain it faces longest, the mid-line as the centre, the banks on
the rows at +-10 m, each corridor clear of the accepted ones and the domain edge). Tests `tests/engine/test_strips_run.py`
on a tilted plane at 4 m with one corridor and a line across it:

| Case | Result | Rule |
|---|---|---|
| The job runs on the CPU; rain 1,129 m3 in, 1,014 out, 115 held | mass error **2e-9** (1.5e-6 before the strip kept its clamp residual as the tiles keep theirs) | under 1e-6 |
| The line across the corridor against the same job without strips | peak within the rule | within 3 % |
| A job without strips | hash unchanged | identical |
| `backend: gpu` with strips | refused in words | InvalidJob |

Found on the way, now in the code: the strip's `update` clamped a cell at zero and dropped the remainder, 1.5e-6 of the
rain; the tile kernel keeps that remainder in a residual and so does the strip now. A result line that passes through a
strip node counted the faces that end on it; those carry flow along the line and are left out. Faydh 01's W26 banks give
225 bank parts on 21 wadis, 41 pairs, 41 corridors along 38.0 km (304 to 3,658 m), against W44's 39 pairs and 30
corridors (its clearance rule was stricter). Full suite on the branch: one failure, the frozen schema sample, since
regenerated and passing.

## Stage 5 (2026-11-07): the CUDA twin of the polygon step, passed

`wadi2d/solver/gpu/kernels/poly.cu` carries `kernel.py` statement for statement: one thread per face or per cell, a
cell gathering over its faces through a CSR (`cell_faces`) so no sum needs an atomic and every launch gives the same
bits; the ghosts read the lattice arrays as the CPU hybrid does. `wadi2d/solver/poly/gpu.py` (`PolyGpuState`) holds
the strip on the device and its nine launches; `wadi2d/strips/hybrid_gpu.py` (`HybridGpu`) drives them in the GPU
backend's new hooks, nothing leaving the device inside a step; `hybrid.py` keeps what the backends share in `Hybrid`,
and `make_hybrid` picks by the model's backend, so a job with strips runs on the GPU. Tests
`tests/strips/test_hybrid_gpu.py` and the GPU case of `tests/engine/test_strips_run.py`:

| Case | CPU hybrid | GPU hybrid | Rule |
|---|---|---|---|
| W3's channel through the strip, depth / normal depth, axis / 45 degrees | 0.9848 / 1.0250 | within 2e-3 of it | within 2e-3 |
| A 0.6 m step released across the join, 120 s, depth field cell by cell | | worst difference **under 1e-4 m** | within 1e-4 m (the stage gate) |
| Still water across the join, 600 s | | largest speed under 2e-5 m/s, volume within 1e-7 | as the CPU |
| The plane job's line through the corridor | | peak within 1 %, volume within 0.1 % of the CPU run | within 1 % |

Faydh 01 at 20 m, 16 h, 188,814 squares and 19,886 strip cells: no lines 88,589 steps in 13.4 s on the GPU against
496 s on the CPU; with corridors 143,739 steps (the 10 m rows and the small gap triangles set the step, `dt_min` 0.04
against 0.33 s) in 72 s against 1,317 s. [Certain, measured] The strip costs the GPU run 5 x: 1.6 x the steps and nine
small launches plus a few CuPy reductions a step on 20,000 cells, which is launch-bound. The strip's own
local-time-stepping class and one fused kernel are the next speed items; W40 said so.

## Stage 7, second piece, and the race (2026-11-07): Faydh 01 at 20 m, passed

Three things the Faydh run found, each now in the tests: **a strip that reaches an outflow boundary lost its outflow
from the books** (a boundary cell's depth is reset after every step, so what the strip hands it has left; the boundary
tally saw only lattice faces: 40 % of the rain missing at hour 10; the hybrid now tallies its interface faces onto
boundary cells and the monitor adds that to the outflow; a corridor ending on the plane's free boundary closes to
1e-6); **a result line across a corridor read a third of the flow** (it runs parallel to the station faces that carry
the flow and cut only the row faces; the rule is now the lattice's, a cell left or right of the line by its centroid
against the nearest stretch of it, a face counting when its two cells differ, ghosts included, and the staircase gives
up a join slot the strip counts); and **a corridor whose row crosses itself two stations apart kept every cell's area
while the cells overlapped**, which the fold test now catches, with a corridor past the active cells refused in words,
and `fold_free_pieces` cutting a corridor clear of its folds and of what it must keep out of, so the bank builder
gives what the mesher accepts. The run writes `maps/strip_mesh.gpkg`, the strip's cells with the largest depth and
level of the run and its faces with the largest discharge; `map_close.py` draws a window of it.

`race_faydh.py`: W36's base, W11's rain-on-grid job on the 20 m wadi domain, 16 h, no maps; the corridors from W26's
suggested banks by `banks.py` (225 bank parts on 21 wadis, 41 pairs, 39 corridors along 36 km after 12 cuts, 6 rows of
10 m, the banks on the rows at +-10 m), 10,716 corridor cells, 9,170 gap triangles, 10,215 squares replaced.

| Faydh 01 at 20 m, GPU | No lines | **Corridors on W26's banks** | W36's staircase, banks as breakline faces |
|---|---|---|---|
| Dam axis, peak m3/s | 1,835.2 at 12.21 h | **1,881.7 at 12.21 h (+2.5 %)** | -11.1 % |
| `box_mid`, 600 m downstream, peak | 1,838.5 | **1,875.0 (+2.0 %)** | |
| Volume through the axis, Mm3 | 9.751 | 9.854 (+1.1 %) | |
| Outflow / rain | 0.915 | 0.925 | |
| Mass error | -2.0e-8 | -2.1e-8 | |

[Certain, measured] The aligned corridors pass W36's rule, within 3 % of no lines, where the staircase of breakline
faces on the same banks read -11.1 %; the peak sits 2.5 % above the squares, the direction W3 and stage 4 found on the
45-degree channel (the aligned faces lose less to the staircase's cross-advection). The CPU twin on the same job
(`faydh20_strips`, 143,017 steps in 1,425 s, books closed to 3e-8): axis 1,889.2 m3/s (+2.96 % on no lines, 0.4 %
above the GPU), `box_mid` 1,873.7 (0.07 % below the GPU), volumes within 0.1 %: W33's spread between the backends, and
the CPU sits at the edge of the 3 % rule where the GPU has 0.5 % in hand. Not in this race: 10 m, the W26 bank cases on
Bidah, the flume; and the corridors here are 60 m wide on banks 20 m apart, so the flood's margins run on squares.

## Stage 7, third piece (2026-11-07): pixel depth over the strip, and the corridors from the Suggest file

His remark on the first map, one colour per cell: the solver's sub-grid was applied, the drawing was not, and the
strip had no pixel product. `wadi2d/strips/pixels.py` is W9's rule on polygons: a run saves the strip's cells with every
map (level, mean depth, cell speed) and their maxima; the product step puts a surface through each polygon's nodes (a
node the mean of the cells round it that are one body of water there, joined across a face by the face's ground as the
squares are), interpolates it at the pixels inside the ring by Wachspress weights, fills every cell to its own water
exactly (W9's Newton, ragged over the cell's pixels) and blends the fill offsets across joined edges through the same
node means; the three maxima per pixel are painted into the pixel rasters where the squares the strip replaced left
them blank, so the depth drawing and the hazard classes carry the strip. Tests `tests/strips/test_pixels.py`: a cell
holds its water to 1e-3 under a surface that follows the ground; two joined cells share one flat surface (within 2 mm);
a dry neighbour keeps its own; the plane job with a corridor paints the corridor's pixels beside the squares'. Faydh 01
with corridors, maps every 10 min, 96 maps, 0.5 m pixels: 16.3 M strip pixels beside 12,659 kept squares, the product
step in about 3 min on the GPU; `race_faydh/map_axis_pixels.png` is the window of the first map at the pixel.

A job's `strips` may name the Suggest breaklines GeoPackage instead of corridors outright (`banks`, `layer_m`,
`rows_per_side`, `min_length_m`): the engine pairs its banks along the thalwegs and builds the corridors inside the
domain, the banks file in the cache key, what was cut in the `strips` event; corridors with the mesh refinement are
refused in words. The dock's Mesh section gained the corridor controls (tick, the suggestion layer, row spacing, rows),
the job builder carries them and refuses a missing layer or the mesh together with them, and after a run the corridor
cells and faces load under Model setup beside the cell grid. Dock check `dock_corridors.py` on Bidah at 20 m through the
real dock (QGIS 3.44.8, throwaway profile): **27 of 27**, log `log_dock_corridors.txt`: refused without the suggestion
layer; Suggest breaklines then corridors from its file, 12 corridors (2,208 cells, 2,058 triangles, 2,609 squares
replaced, two pairs cut); the GPU took the run, books closed to 1e-8; faces on the banks 736, at the join 1,176; the
corridor layers under Model setup beside the cell grid; the pixel maps carry 41,744 strip pixels; the dam lines P1 and
P6 at 1.008 and 0.942 of the same 2 h storm on squares; corridors with the mesh refinement refused in words.

## Speed, first cut (2026-11-07): the strip's bookkeeping fused into kernels

`profile_hybrid.py`, Faydh 01 at 20 m on the GPU, uniform rain, 3,000 steps after a warm-up, ms per step:

| | Tiles alone | Hybrid | Hybrid without maxima and tally | Strip hooks alone |
|---|---|---|---|---|
| Before | 0.087 | 0.320 | 0.216 | 0.257 |
| After (mirror, restore, maxima, tally as kernels) | 0.085 | **0.208** | 0.187 | 0.109 |

[Certain, measured] The strip's per-step bookkeeping through CuPy array operations (about ten launches of 10 us) cost
a third of the hybrid step; as four RawKernel launches it costs a tenth. The hybrid is now 2.4 x the tiles per step on
19,886 strip cells and 3,710 ghosts, launch-bound still (13 launches a step beside the tiles' own). The 16 h Faydh run
with corridors: 72 s before, 41.5 s after.

**The slivers.** The faces that set the step were gap triangles: the smallest centre-to-centre distances (3.0 m, the
`DN_MIN` floor) all lay between two gap triangles, where a corridor node stands near a lattice corner and the
constrained Delaunay on the existing nodes leaves a sliver. `merge_slivers` joins pairs of gap triangles closer than
half a cell along their shared face into one quad when it is convex, closest first, until nothing merges. Faydh 01:
9,170 gap cells to 7,719; the smallest step 0.040 to 0.057 s; 143,739 to 134,632 steps; **35.7 s on the GPU against
13.4 with no lines (2.7 x)**; the dam axis 1,879.9 m3/s (+2.4 % on no lines, 0.1 % from the unmerged mesh), `box_mid`
1,868.4. Left for later: folding the level differences into the sums kernel and the scaling and the ghosts' source into
the update kernel (about four launches), and the strip's own time stepping (the strip still takes 1.5 x the tiles'
steps over the run).

## Stage 6 (2026-11-07): terrain objects on the strip's ground and faces, passed

`wadi2d/strips/objects.py`. Burn lines and shaped objects rebuild the strip's ground through the same `edit` hook as
the squares', in the tables and in the pixel products. Crest lines, spillways, walls and the standing stretches of
shaped objects land on the strip's own faces by the rule the result lines use: a face carries the object when its two
cells lie on different sides of its line, so a crest along a bank row sits on that row's faces exactly, no staircase
and no length factor; the face's invert is lifted to the crest's elevation at the nearest point of the line, the
higher of two crests wins, a spillway sets its own level, a shaped crest reads the energy head (W8's negative
coefficient, W43's form in the kernel), a wall closes the face. Tests `tests/strips/test_objects.py`:

| Case | Result |
|---|---|
| A crest between two cells, a wall there | the shared face lifted to the crest with the critical coefficient, the outer faces untouched; the wall closes that face alone |
| A spillway under a higher crest | the face takes the spillway's level and coefficient |
| A crest 200 m high across the plane and its corridor, squares alone against corridor | outflow 422.2 against 422.1 m3 (the rain east of the crest), 63 % of the rain held on both; the 8 lifted strip faces, one per row, carry nothing |
| A burn line 1 m deep along the corridor | the strip's ground on the centre row 1.00 m lower |

[Certain] The first form of the crest test asked for no outflow at all and failed on both grids by the same 422 m3: the
rain east of the crest. The test now compares the two grids; the lesson is recorded so nobody reads that first failure
as a leak. Not done: the levee and flume cases on aligned faces (EA Tests 1, 3 and 7, the Iber flume), which need the
stage-series and line-inflow boundaries on strips.

## One set of cells (2026-11-07): the strip takes what the squares take, by construction

His remark: the strip's behaviour was kept separate, each feature (losses, storms, inflows, resume) a question to
him. The fault was in the design: the strip was a second cell list with its own kernels, and every feature written
against the lattice's cell index had to be taught the strip one by one. The fix is one principle, the model has one
set of cells and the squares and the strip cells are two storage layouts of it:

- **Forcing by cell position.** `Forcing` takes the strip's cells after the lattice's, by their centres, areas and
  lowest ground; rain, curve-number losses, depth grids, gridded storms, the lumped subbasins' masks and inflow
  placement are evaluated per cell position, so every storm kind and every loss works on a corridor the day it works
  on the squares. The run reads the strip's share of the source vector into it. The uniform-rain shortcut and the four
  refusals (CN raster, gridded rain, depth grid, subbasins, resume) are gone.
- **State is state.** The strip is a checkpoint part: its cells' state, its maxima and its outflow per ghost; a stopped
  run with corridors resumes to the unbroken one byte for byte (the series of record identical).
- **One balance.** The checkpoint keeps the lattice tally apart from the strip's outflow; the hand-back link reads the
  strip's share of each line through the monitor; a ghost's tile stays pinned active through every source window.
- **Initial water** polygons fill corridor cells too, and a polygon lying wholly on a corridor is not refused for
  wetting no square.
- **The strip in the local time stepping.** With `numerics.local_time_stepping` the strip is the finest class: its hooks
  run on every smallest step between the tiles' positivity and their update, its ghost tiles are pinned to the smallest
  level, its own wave caps the smallest step; before this a job with corridors and local stepping skipped the strip
  without a word. Faydh 01 at 20 m on the GPU: no lines 100,401 smallest steps in 19.6 s (uniform 88,589 in 13.4 s);
  corridors 140,689 in 50.5 s (uniform 134,632 in 35.7 s), tile-steps 24.0 M against 29.9 M, the dam axis 1,883.8
  against 1,879.9 m3/s. [Certain, measured] Correct, and no faster: W10's finding holds (local stepping saves no time on a
  uniform grid, the lists cost more than the tile-steps they save), and the strip itself still steps 140,000 times.
  The lever left is the reverse: the strip sub-cycling inside one tile step at the tiles' own step, worth about 1.5 x
  on the tiles' share [Guessing].
- Not yet: the bed (transmission) loss stays on the squares and says so in the code.

**The Block 2 hybrid with corridors** (`race_bidah_hybrid.py`): W41's PMP job as the dock wrote it, Bidah 03 at 30 m
through the HMS route, S13 lumped above the dam and the rest rain-on-grid, the CN raster, the PMP depth grid, the
design line, 48 h on the GPU; with and without corridors from W26's suggested banks on Bidah (7 corridors, 1,170 cells,
871 triangles, 969 squares replaced, one pair cut). Every one of those inputs was refused with corridors a day ago.

| Bidah 03, PMP, HMS route | Squares | Corridors |
|---|---|---|
| Dam line peak, m3/s | 1,463.79 at 12.89 h (W41's 1,463.8) | **1,464.63 (+0.06 %)** |
| Rain / lumped inflow, Mm3 | 8.711 / 23.722 | the same to the digit |
| Mass error | 2.3e-8 | 2.3e-8 |
| Steps, time | 154,098, 14 s | 154,098, 35 s |

[Certain, measured] The lumped inflow carries this peak and the corridors change it by 0.06 %; the strip's cost is its
fixed launch cost a step (2.5 x on a run this small, the same 0.12 ms a step as on Faydh). The first timing of this
pair, 86 s, overlapped the full suite's GPU tests and is discarded. This is the dock's own job on the engine CLI, not
clicked through the dock; the dock path with corridors is `dock_corridors.py` (rain on grid).

Tests on the plane with a corridor (`tests/engine/test_strips_run.py`): a curve number of 75 leaves 20 to 90 % of the
rain with the books closed; an inflow of 1 m3/s landing on the corridor's cells runs down it, the corridor's middle
rows the deepest of the run, nothing upstream; a run stopped at 910 s and resumed gives the unbroken run's series and
strip depths; an initial level fills the corridor cells inside its polygon. The lumped-subbasin mask and the gridded
storm run through the same cell positions as the squares' and have no strip code of their own; their Block 2 and W39
checks with corridors are the next dock run.

## The banks and the cell size (2026-11-07): his rules as parameters, calibrated on small models

His words of the day: the banks the Suggest command drew were wrong; he sketched the approximately correct banks on
three Bidah windows (`bed_types/sketches/`, a narrow wadi of 7.9 km2, a medium one of 7.2 km2, a fan belt of 20 km2);
the banks are to be checked against the 2D depth results, since the flow runs inside the wadi course; a narrow wadi runs
on cells no smaller than about 20 m, a wide one needs none larger than about 50 m and a fraction of its width, a fan
with no defined wadi gets no corridor, the total run time matters, and all of it is to be parameters in the dock.

**The sketches, and a mistake on record.** `digitise_sketch.py` maps the purple strokes of his phone screenshots to
the ground through the map frame; its first frame finder took the first row that was mostly grey, which was the
title's own text, and so stretched the frame and pulled every stroke south, by up to 90 m on the narrow wadi and
140 m on the fan. He saw it on the first figure ("they are not in correct location"). The finder now takes the
longest grey run and the dark axes spines, and the map is square, which gives the edge the screen cut off; the
independent check is the thalweg, known on the ground, drawn back onto his screenshot by the same frame, where it
lies on his blue dashed line (`bed_types/sketch_check_*.png`). The first sweep's conclusion, "a rise of 5 m matches
his strokes", was built on the misplaced strokes and is withdrawn. His strokes are 10 to 12 m wide bands, so a
distance under about 6 m to them says nothing.

**What his strokes are** (`bank_check.py`, against the 100-yr run at 5 m, `conv_dx5_s1`): the 0.5 m depth margin of
the flood lies inside his stroke band on 92 % of its length on the narrow wadi and 79 % on the medium one; the 0.2 m
margin lies about 8 m further out each side. On the fan he drew the hill toe and the margin is 11 m off. Widths
between the banks, m:

| Bidah window | His strokes | Flood 0.5 m | Flood 0.2 m | Rise 1.5 | Rise 2.0 | Rise 2.5 | Rise 3.5 | Rise 5.0 |
|---|---|---|---|---|---|---|---|---|
| Narrow, 7.9 km2 | 31 | 28 | 50 | 26 | 29 | 32 | 39 | 51 |
| Medium, 7.2 km2 | 44 | 47 | 59 | 42 | 46 | 49 | 55 | 62 |
| Fan, 20 km2 | 286 (one side drawn in part) | 224 | 322 | 307 | 308 | 331 | 338 | 319 |

[Certain, measured] The ground rising 2 m over the bed is the lip of the active channel, where his strokes and the 0.5 m
margin lie (within 3 to 4 m per side on the two wadis); the 0.2 m margin is nearest 4 to 5 m of rise by bias but with
8 m of scatter, because the shallow skirt follows the flood, not the ground. The slope-break detector of W5's kind
(slope over 4 % for 40 m, 3 m up) matches the strokes as well on the two wadis and finds the fan's open side on 4
of 59 sections, so it is not the rule. [Likely] A corridor on the 2 m banks leaves a skirt under 0.5 m deep on the
squares either side; that is sheet flow, which the squares carry.

**In the engine.** The job has a `breaklines` section (`Breaklines` in the schema), the one place the Suggest command
reads its numbers from, so the dock sets them and the run folder records them: the bank where the ground rises
`bank_rise_m` (2 m) over the bed, looked for within `bank_reach_m` (300 m); or, given `bank_depth_map` (a run's
`maps/max_depth.tif`), the edge of the flooded course, where the depth falls under `bank_depth_m` (0.2 m) for
`bank_dry_m` (10 m) across; the top-hat's disc, height and ground-slope limit. Before this the rise was the mesher's
incision depth, 0.5 m, and the reach half its window: the low-flow channel's lip, which W26 had noted. The Mesh section
has the controls under the Suggest button, with a raster picker for the depth map, and the dock's words name the rule
that placed the banks.

**The corridor rows follow the width.** A corridor from the banks file spans the wadi between its two banks; the cell
across is `strips.width_fraction` (0.25) of the width held between `strips.cell_min_m` (20 m) and `strips.cell_max_m`
(50 m), the width split into the nearest whole number of such cells, one at least, and `strips.rows_outside` (1) rows
stand beyond each bank at that size, so the bank's faces lie inside the corridor and the join to the squares does not.
A 16 m wadi gets one cell across, a 60 m one three of 20 m, a 300 m one six of 50 m. The fixed rows of the first
build (`layer_m`, `rows_per_side`) put two cells across every wadi whatever its width, and all the spacing set was the
rows outside the banks. In the mesher a snapped row finds its line out from the station's centre, so a corridor with no
row at offset zero snaps, and the rows between two snapped rows are spaced in the proportion of their offsets. The
strips event reports the rule per corridor. A wadi with one bank or none keeps its squares (his rule for fans).

**The races and the cell-size trials** (`race_faydh.py`, `race_bidah_hybrid.py`, the banks re-suggested with the 2 m
rule by `suggest_banks.py`: Faydh 274 banks over 111 km on 40 thalwegs, Bidah 03 128 over 39 km on 21). Faydh 01 at
20 m, 16 h, on the GPU, the dam axis against the same run with no lines (1,835.2 m3/s; the 10 m squares of W11 read
1,873.8 and HEC-RAS 1,872.2):

| Rule (smallest, largest, share, rows outside) | Corridors | Strip cells, triangles | Cells across, size | Dam axis, m3/s | Against no lines | Steps | GPU time |
|---|---|---|---|---|---|---|---|
| Fixed rows of 10 m on W26's 0.5 m banks (the first build) | 30 | about 20,000 | 6 of 10 m | 1,879.9 | +2.4 % | 134,632 | 36 s |
| **20, 50, 0.25, 1 (the defaults)** | 34 | 5,114, 5,603 | 2 to 3 of 18 to 24 m | **1,875.0** | **+2.2 %** | 110,084 | 42 s |
| 30, 80, 0.5, 1 | 30 | 3,534, 4,967 | 1 to 2 of 24 to 45 m | 1,883.6 | +2.6 % | 98,820 | 38 s |
| 10, 30, 0.125, 1 | 35 | 8,265, 5,915 | 4 to 6 of 10 to 11 m | 1,866.6 | +1.7 % | 136,712 | 49 s |
| 20, 50, 0.25, 2 | 30 | 6,587, 5,045 | 2 to 3 of 18 to 24 m | 1,868.1 | +1.8 % | 98,431 | 39 s |

[Certain, measured] Every rule passes the 3 % gate, and all four land within 0.6 % of the 10 m squares' 1,873.8
where the 20 m squares with no lines read 2.1 % under it: the corridors give the 10 m answer on the 20 m grid.
Finer cells across move the peak down toward the 10 m figure and cost steps; a second row outside the banks changes
the peak as much as halving the cells, which says the join's position matters as much as the cells inside [Likely].
The default rule keeps a quarter of the strip cells the fixed rows had and the run time within 3 x the squares'
(the step is the strip's: 110,000 against 88,600). Timings were taken with CPU studies running alongside.

The Block 2 PMP hybrid on Bidah 03 at 30 m (W41's job through the HMS route, S13 lumped, the CN raster, the PMP
depth grid), the dam line against the same run on squares (1,463.79 m3/s, 14 s):

| Rule | Corridors | Strip cells | Cells across, size | Dam line, m3/s | GPU time |
|---|---|---|---|---|---|
| 20, 50, 0.25, 1 (the defaults) | 7 | 702 | 3 to 4 of 18 to 22 m | 1,464.01 (+0.015 %) | 54 s |
| 30, 80, 0.5, 1 | 7 | 532 | 2 of 30 to 44 m | 1,463.95 | 54 s |
| 10, 30, 0.125, 1 | 8 | 1,217 | 6 to 8 of 10 to 11 m | 1,464.02 | 54 s |

[Certain, measured] The lumped inflow carries this peak; the corridors move it by a hundredth of a per cent whatever
the rule. **The first attempt was refused**: the new banks reach 300 m from the thalweg, the corridors spread into
the rained part of the catchment, and a curve-number raster was read at the active squares alone, so the strip's
cells, standing where squares had left the mask, read no CN (585 rained cells). The same read served the depth grid
and the Manning raster, and the strip took one mean of the squares' Manning grid. Fixed: a raster is read at the
squares under the strip too, and each strip cell takes its own square's roughness. The old corridors had passed this
job by lying inside the lumped S13, where no CN is read. **The timings of this afternoon are not the morning's:** the
squares-only run re-timed at 20.0 s against the 14 s on record, the GPU idling at 1,717 of 3,090 MHz with a dozen
desktop programs holding it, so the 57 s of the default corridors alone (54 to 57 s in every trial, with or without
eight sub-steps) reads as about 40 s on the morning's machine, against the first build's 35 s on the same step count.
[Likely] No regression in the strip's step; a clean timing needs a quiet machine.

**Roads and dams** (`crest_sweep.py`): the crest settings through the Suggest command on a 4 km by 4 km job across
the Batinah Highway (the one surveyed line he named, 4.19 km in the window), scored as W5 scored the top-hat: the
share of the highway within 30 m of a suggested crest, and the crest length farther from it (other roads, bunds,
noise; no layer separates them).

| Height, m | Disc, m | Highway found | Crest km elsewhere | Pieces on the highway (median length) |
|---|---|---|---|---|
| 0.3 | 20 / 40 / 80 | 65 / 65 / 75 % | 9.0 / 23.8 / 42.7 | 10 / 13 / 16 (140 to 180 m) |
| **0.5** | 20 / **40** / 80 | 26 / **72** / 66 % | 1.3 / **6.9** / 17.1 | 4 / **12 (177 m, longest 487)** / 15 |
| 1.0 | 20 / 40 / 80 | 10 / 30 / 54 % | 0.0 / 0.5 / 1.8 | 1 / 4 / 7 |

[Certain, measured] W26's setting, 0.5 m over a 40 m disc, stands (`crest_sweep/crest_sweep.png` shows it against
0.3 m and 1 m on an 80 m disc): nothing finds more of this highway without 2.5 to 6 times the lines elsewhere, 1 m loses it (the embankment stands under 1 m over its fitted ground on this plain), and
the ground-slope limit changes nothing on a plain. The `road` kind never fires: culverts and underpasses cut the
highway's crest into pieces of 140 to 240 m median (longest 579 m), straight to 0.99, under the 1,000 m a road needs;
`road_length_m` is his to lower (300 m would read most of these as road). Dams: the kind is "a crest across a defined
wadi"; no built dam lies in a small window of this ground, so it rests on the synthetic test alone.

Found on the way: `~` on a Python bool in `faces_from_objects` made the second crest line on a face set its own level
over a higher first one; fixed with a test in both orders.

**Through the real dock** (`dock_corridors.py`, `log_dock_corridors.txt`, 34 of 34 on QGIS 3.44.8): the Suggest
settings start at the schema's numbers, a rise typed as 3 m reaches the suggestion's job and the dock's words ("Banks:
ground 3 m over the bed of the wadi"), the width rule reaches the run's job and the strips event reports it per
corridor as the schema's rule gives it, a run on Bidah with corridors closes its books on the GPU, its lines stay
within 0.1 % of the squares, the corridor layers load under Model setup and the pixel maps carry the corridors, and
corridors with the mesh refinement are refused in words. The full suite passes.

**Still open after this:** the Suggest command's speed on the full domain (the measurement of the old rule on Block 2
at 30 m with 0.1 km2 streams, `scale_block2.py`, had run over two hours and not finished when this was written; the
banks are found per thalweg in Python loops, and the new reach is three times the old), confluences, the strips with
the quadtree (coarser cells on the dry mountains, his wish), the bed loss on strips, and his full-domain run at 30 m
with smooth streams as corridors, which waits on the first of these.

## Iterations

- `W44 mesh race`: the MeshKernel trial on Faydh 01 and the W3 solver assessment; its NOTES feed stage 4.
- `W45` (this folder): the plan and the stage records.
