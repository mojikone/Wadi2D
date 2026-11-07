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

## Iterations

- `W44 mesh race`: the MeshKernel trial on Faydh 01 and the W3 solver assessment; its NOTES feed stage 4.
- `W45` (this folder): the plan and the stage records.
