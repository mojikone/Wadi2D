# W71 breach on quadtree and real ground

**Live.** Branch `feature/breach-quadtree` off `feature/fast-products` at `c2a2097`; not merged, not pushed. Extends `W63 dam breach
in 2D` (squares) and `W69 breach on aligned mesh` (strips), which stay as they were.

His word of 2026-11-14: the breach on the aligned mesh is very important. Scope: the breach on the quadtree; an oblique corridor on the
synthetic valley; Bidah's dam on real ground on the squares, the centre mesh and the quadtree.

## 1. The quadtree (built)

[Certain] W69's guess held: the faces themselves carry over, only the lookup was missing. `wadi2d/breach/faces.py` gains `face_slot`,
the index of a raster face in the face arrays on either grid: on the uniform grid and in a quadtree's finest tile its own slot; the east or
south face of a finest tile against a coarser one in the extra table tiles, at the interface row's base plus its place along the side (the
layout `tables/quad.py` writes), with the fine cell's roughness as the builder takes it. The cell beside the dam may be coarse:
`Model.cell_state_index` answers through `QuadGrid.state_index` and the pipe's cell areas are the cell's own. The mesh refusal is
dropped; local time stepping and resume keep theirs. No kernel, table or schema change; the uniform and strip paths are untouched.

A crest face can never be an east or south interface face today: `tables/quad.py` refuses a crest whose face lies in a coarse tile, and
the high side of such a face is the coarse cell. The slot is mapped and tested all the same, so the refusal can be lifted without a hidden
gap. A dam on the **west** edge of a fine tile with coarse cells behind it is reachable (refinement zones, `refine_lines` off) and tested.

Tests (`tests/engine/test_breach_quad.py`, 6, one on the GPU): a V valley 1,536 x 512 m (8 m finest cells, 16 m coarse, 2 m DEM, 1 %
fall, sides 0.2), crest 103 m, pool by an initial water polygon at 102.5 m, breach 16 m wide, 1:1, 300 s, at 60 s.

| Check | Result |
|---|---|
| Unbreached faces rebuilt against the quadtree's tables | within 1 mm and 0.1 % (the run refuses otherwise) |
| Dam on the west edge of fine tiles, the pool in 16 m cells | opened area within 3 % of the trapezoid, deepest invert on the floor to a pixel's rise, faces outside unchanged bit for bit; pool cell area 256 m2, tail 64 m2 |
| East interface face | its slot past the real tiles, open |
| Peak 100 m below the dam against 8 m squares, same pool | pool coarse behind the interface: 74.95 against 74.91 m3/s (+0.05 %); dam fine, the flood through a 16 m square: 70.87 against 70.89 (-0.04 %) |
| Books, timing | relative error under 1e-6; start at 60 s and formed at 360 s to 1e-9 s |
| Trigger never reached | storage and line series equal to the run without a breach, to the digit |
| GPU against CPU | 74.9544 against 74.9543 m3/s |

## 2. Oblique aligned faces (tested, no code)

`tests/engine/test_breach_oblique.py`: the same valley shape rotated 30 and 45 degrees in a 480 m box at 8 m (fall 3 % so the 150 m pool lies
inside the box at every angle; 5,062 m3 by hand), dam across the axis, a corridor of five 8 m rows along the axis with a station on the dam,
breach 32 m wide (past the corridor, so the dam is mixed), and the centre mesh with the dam as its hard line. The yardstick, fixed before
the run, is the same valley along the grid on the squares (W69: aligned cells within 1 % of it), 5 %.

| 100 m below the dam, m3/s | along the grid | squares at the angle | corridor | centre mesh |
|---|---|---|---|---|
| 30 degrees | 39.32 | 42.69 (+8.6 %) | 41.24 (+4.9 %) | 40.86 (+3.9 %) |
| 45 degrees | 39.32 | 37.26 (-5.3 %) | 41.28 (+5.0 %) | 40.29 (+2.5 %) |

Pools 5,052 to 5,172 m3 against 5,062 by hand, except the squares at 45 degrees (4,793, -5.3 %; [Guessing] the initial
polygon's edge on the staircase dam leaves cells along it dry); books under 1e-6 on all six. The aligned meshes pass and read nearer the yardstick than the squares at the angle, but **the corridor
sits on the 5 % line at both angles** (+4.9, +5.0 %), reading high in both; why is not looked at (the line across the corridor's gap
triangles, or the corridor's +2.2 % pool at 45 degrees, are candidates). [Likely] it is the coarse-cell excess aligned cells showed on Faydh
(W56), here at 8 m on a 40 m breach.

## 3. Bidah's dam on real ground (run, `bidah_breach.py`)

Inputs: the validation dam job (`W1 .../validation/block2_full/jobs/dam_Bidah03_100yr_20.json`): NSA 2 m DEM, domain, Manning 0.04, the
three crest pieces at 105 m, the spillway at 100 m, the two normal boundaries; no storm, no inflow. The main piece named for the breach,
the others walls. Pool full to the spillway crest, 100 m. Breach by time at 600 s, centre 620 m along the main piece (the flat floor, 85.1
to 85.5 m; the spillway is at 428 to 500 m), bottom 85 m, Froehlich (2008) from the pool: B_ave 57.2 m, bottom width 37.2 m, slopes 1:1,
formation 2,395 s. 3 h on the GPU, one job at a time.

**The pool is 5.63 Mm3, not W34's 3.833.** `dam_levels` at 100 m on this DEM fills 2,202 cells of 20 m with 5,632,675 m3. W34 filled 1,810
cells on the GGC 5 m DEM (the dock harness's terrain), which stands 2.39 m above the NSA datum of the dam's levels; [Likely] W34's figure is
the pool on the wrong datum, about 1.8 Mm3 short. `dam_levels` fills a grid pool on the uniform grid only, so every mesh here starts from
that pool's cells drawn as one polygon in `initial_levels` (`bidah_pool_100m.geojson`); on the squares the polygon gives the same
5,632,675 m3 and the same series as `dam_levels`.

| | 20 m squares | 20 m centre mesh | quadtree (20 to 80 m) |
|---|---|---|---|
| Cells | 71,940 | 71,072 (298 aligned on the dam lines) | 32,715 |
| Pool at the start, m3 | 5,632,675 | 5,631,459 | 5,631,664 |
| Peak through the dam line, m3/s (at s) | 2,582.6 (3,000) | 2,683.4 (3,000), +3.9 % | 2,581.6 (3,003), -0.04 % |
| Peak 300 m below the dam, m3/s | 2,517.6 | 2,632.0, +4.5 % | 2,518.4, +0.03 % |
| Pool level 1 h after the trigger / at 3 h, m | 93.56 / 88.41 | 93.38 / 88.41 | 93.56 / 88.41 |
| Water left at 3 h, m3 | 23,856 | 19,385 | 23,905 |
| Mass balance, relative | -2.2e-8 | -2.1e-8 | -2.1e-8 |
| Wall time, GPU | 3.6 s | 10.3 s | 9.1 s |

The peak comes at the end of formation (3,000 s), the pool still 96.4 m high. Indicative check: Froehlich's (1995b) regression for the
peak, Q = 0.607 V^0.295 h^1.24 with V 5.63 Mm3 and h 15 m, gives **1,710 m3/s, so the 2D runs read 1.51 x it**. The regression is a fit
through scattered failures with a wide band, and the formation time here is Froehlich's own mean, not a regressed outcome, so this says the
order is right and nothing finer. The weir coefficient is W63's default 1.44 (2.6 US).

The quadtree reads the squares' numbers to 0.04 % with 45 % of the cells; the centre mesh reads 4 to 5 % higher, as it did on the oblique
valley and on Faydh (W56, +3.5 % at 20 m converging at 5 m); nothing here says which of the two 20 m answers is nearer the converged one:
no 10 m or 5 m run was made.

## Not done

- A converged reference for Bidah (10 m and 5 m squares) and a run against HEC-RAS's breach on the same dam.
- Why the corridor reads +5 % on the oblique valley (section 2).
- `dam_levels` on the quadtree and the strips (a pool polygon is the way today); a breach on a dam drawn in pieces under one name (the
  breach takes one object; Bidah's pieces were given their own names here).
- Local time stepping and resume with a breach; a dock row (W63's decisions stand).
- The east and south interface faces with a crest (unreachable while the table builder refuses crests in coarse tiles).
- The full suite (his rule: at merge). Run: `test_breach.py`, `test_breach_strips.py`, `test_breach_quad.py`, `test_breach_oblique.py`.
