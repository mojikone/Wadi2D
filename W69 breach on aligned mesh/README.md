# W69 breach on aligned mesh

**Live.** Branch `feature/breach-aligned` off `feature/fast-products` at `c299429`; not merged, not pushed. Extends `W63 dam breach in
2D` (the breach on the squares), which stays as it was.

His word of 2026-11-14: the breach on the aligned mesh is very important. Scope in his order: the breach on a dam whose crest lies on strip
faces, CPU and GPU, mixed dams; the quadtree if cheap; an embankment's breach reading the edited ground; the breach weir with submergence if the
face law allows it.

## What was built

- **Strip faces** (`wadi2d/breach/strip.py`). A strip face carries the dam where its two cells lie on different sides of the dam's line, the
  rule that put the crest there (`wadi2d/strips/objects.py`, W45 stage 6); the corridors and the centre mesh alike. Per face: the ground along its
  segment at the pixel spacing, the higher of the pixels either side (`face_profile`, as the strip's table builder reads it), raised to the
  crest the job's objects give that face; the ground without the dam; each sample's station along the dam line. As the breach grows each face
  reached is rebuilt: profile = max(ground without the dam, min(crested ground, breach surface)), floored at the two cells' lowest bed, through
  the table builder's own `_face_table`; then the invert is raised to both cells' floors as `PolyMesh.finish` does, and fl, fr, gl, gr, the
  table top, the table and the weir coefficient go into the strip state's arrays (numpy or CuPy, one path), so the polygon kernels are
  untouched. The roughness is read back from the held table (the conveyance at the table's top over that of n = 1), so a Manning raster needs
  nothing more.
- **The bed drops of W47's carry.** A strip face reads the upwind level lowered by half the drop from the upwind cell's opposite face, and the
  dam face is that opposite face for the faces beside it. The drops of every face of the cells beside the dam are recomputed from the new
  inverts, the opposite faces as the mesh chose them. (The dam face itself is a crest face, which the carry leaves alone.)
- **Self-check at the start of every run**, as on the squares: the unbreached strip faces rebuilt from their pixels against what the strip
  holds, refused in words beyond 1 mm of invert or 0.1 % of a table.
- **Mixed dams.** The squares' faces (W63) and the strip's are found and rebuilt together; the centre station, the dam top and the default
  centre (the lowest ground) are read over both. The pool and tail cells are the two cells of whichever face is nearest the centre: strip cells
  read from the strip state, a ghost (a tile cell beyond the join) as that tile cell. A pipe between strip cells is an equal and opposite pair of
  volumes over each cell's own area (on the squares the two areas are equal and the numbers are W63's to the digit).
- **Embankments** (W63's "not done"): the ground without the dam is the job's edits with that dam left out, on the squares and the strip; W63
  took the raw DEM, which undid a channel or burn line under or beside the dam. A crest line's breach reads the edited ground as before.
- The refusal of corridors is dropped. The quadtree, local time stepping and resume keep theirs.

## Tests (`tests/engine/test_breach_strips.py`, 7 tests, 6 on the CPU and one marked `gpu`)

W63's synthetic V valley (8 m cells on a 2 m DEM, falling 1 % east, sides 0.2 m/m, crest line at 103 m across it at x = 200 m), the pool
started by an initial water polygon at 102.5 m (12,570 m3; the grid pool of `dam_levels` fills squares only), a free boundary at the east edge.
Corridors along the axis with their rows on lattice lines and a station face on the dam: five rows (40 m, 56 m with the gap triangles) or one
row (8 m, 24 m with the triangles). The centre mesh with the dam as its one hard line (100 four-sided cells, 150 polygons).

| Check | Result |
|---|---|
| Unbreached strip faces rebuilt against the strip's tables | within 1 mm and 0.1 % in every case (the run refuses otherwise) |
| Final faces against the trapezoid, all on the strip (16 m) and mixed (32 m, the middle on the strip, the rest on squares) | opened area under the crest within 3 % of the trapezoid cut between the ground and 103 m; the deepest strip invert on the valley floor to a pixel's rise; strip faces outside the trapezoid unchanged bit for bit |
| Trigger at 60 s, formed at 360 s | to 1e-9 s on every mesh |
| Mass balance, overtopping, 32 m breach | relative error under 1e-6 on all four meshes (centre mesh 6.1e-10, GPU corridor 3.7e-9) |
| Peak 100 m below the dam, 32 m breach in 300 s, linear | squares 69.34 m3/s; corridor 69.92 (+0.8 %); mixed 69.84 (+0.7 %); centre mesh 69.87 (+0.8 %) |
| GPU against CPU, corridor | 69.9151 against 69.9150 m3/s, peak at 287.1 s (one short GPU run) |
| A trigger never reached, corridor | storage and the line series equal to the run without a breach, to the digit |
| Pipe between strip cells, 100 m, trigger 102 m | flows, collapses into an open breach, books closed under 1e-6 |
| Embankment with a 1 m burn line under it | the ground without the dam 97.21 m at the axis (the burn); W63 read 98.21 m |

Old numbers: W63's overtopping and piping jobs on the squares give the same line and breach series to the digit (SHA-256 of both CSVs equal,
`c299429` against this branch); `test_breach.py`, `test_strips_run.py`, `test_dam_levels.py`, `test_earthworks_solver.py` pass. No schema change,
no kernel change. The full suite was not run (his rule: at merge).

The corridors here are squares on the lattice's lines, so the equal peaks test the mechanics on two meshes of the same geometry, not a
breach on oblique aligned faces; the centre mesh is the one case with cells that are not the squares.

## The quadtree: refusal kept

[Certain] The breach's face finder and cell reader use the uniform grid's `TileGrid.locate`, which the `QuadGrid` does not have; with the
refusal lifted the run stops there. The faces themselves would carry over: crests must lie in finest tiles (`wadi2d/tables/quad.py`), whose faces
are the uniform grid's from the same pixels (W49), but a fine tile's east and south faces against a coarser tile live in extra table tiles
after the real ones, and the cells are indexed by level. A port is a face-slot map for the quadtree plus a test domain big enough to coarsen
(the valley here is two tiles) [Guessing: half a day]. Not cheap enough for this pass.

## Submergence on the breach weir: not built, and why

[Likely] It would count drowning twice. A breached face is a 2D momentum face whose flow is capped at `Q = C A (A/T)^0.5` (the breach weir
coefficient, W63); the cap binds only in free flow. As the tailwater rises the momentum equation's own level difference falls and the face's
flow drops below the cap with no factor at all: drowned flow is already the momentum equation's, as in HEC-RAS when a connection's overflow is
computed with the 2D equations rather than the weir equation. A Villemonte-type factor on the cap would bite only where the momentum flow
exceeds the reduced cap, a second law for the same physics with no case to fix it against, and it needs a new face flag in four kernels
(squares and polygons, CPU and GPU). Recorded, not built; a drowned-breach case against HEC-RAS's weir mode would decide whether it is wanted.

## Not done

- The quadtree (above). Local time stepping and resume with a breach (W63's refusals stand).
- A breach on oblique aligned faces (a corridor at an angle to the lattice) and on real ground with corridors (Bidah, a Block 2 dam).
- The centre mesh's own face choice when two faces of a cell are equally opposite (gorge rows, W52): the bed drops keep the opposite face
  chosen at the start, where `opposite_drops` would pick the lowest piece anew.
- A dam's strip faces under a spillway take the spillway's crest as their unbreached top, as the strip holds it; not tested.
- No dock row (W63's decision stands).
