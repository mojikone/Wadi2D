# W46 centre-based mesh generator (2026-11-08): cells from their centres, his rules

Branch `feature/centre-mesh` off `feature/aligned-mesh`, not merged. The engine's second generator of aligned cells,
beside W45's ring corridors, selected by `strips.generator: centres`; off by default, every job runs as before.

## His rules, as built

His words of 2026-11-08, after the W45 fixed-cell corridors and the zoom-window review:

1. A breakline is a chain of faces: every cell on it has exactly one face on the line. The two cells either side are
   4-sided, squares on a straight reach; they repeat outward as 4-sided cells.
2. A cell under a minimum area merges and may have more faces, up to 8 as in HEC-RAS; the transition rows may have
   more than four faces. The generator handles faces and sizes, never the user.
3. At a junction the main stream keeps its clean rows and the tributary stops short. Rank by drainage area (his
   Strahler order ties exactly where the order rises; area never ties and agrees with Strahler elsewhere), hard lines
   (crests, walls) first. The main stem wins every cell aligned to it: a branch and its mesh never disturb its rows
   (his word on the circled junction, 2026-11-08).
4. The rows stop at the bank; the minimum area governs merging only. Lines are guide (smoothed within a cell where a
   bend is too sharp for a 4-sided cell) or hard (reported).
5. The bank: going outward from the centre line, the first of a scarp inside one step read on the sub-grid pixels
   (his rule: a rise of `bank_scarp_m` 1 m within `bank_scarp_run_m` 10 m) and the rise above the bed (`bank_rise_m`
   2 m, height above the channel, which decides on the fans where no scarp exists); the 5 % slope over 40 m a cap
   only; the first cell always bed; past `bank_reach_m` 300 m no bank, and a line with banks on both sides along under
   half its stations keeps the squares. The floodplain beyond the banks is squares.

## The construction (`wadi2d/strips/centres.py`, `wadi2d/strips/floor.py`, `wadi2d/strips/build.py`)

Mirrored centres half a cell either side of each segment of the line, at its midpoint along its own normal, make
that segment a face by construction, HEC-RAS's way of enforcing a breakline: the four centres round every vertex of
the line are equidistant from it, so the diagram's vertex falls on the line's vertex and the chain of faces is the
polyline itself (mirroring across the station along the mean normal left a short jog at every bend, which he circled);
rows of centres a cell apart repeat outward to the bank. The Suggest file cuts every stream into segments at the
junctions, each with its outlet's area; the generator chains them into stems first, the larger inflow at every
junction continuing downstream, so a stem carries its outlet's rank along its whole length, is placed first and runs
unbroken through every junction, and the tributaries alone end short of it (his circles of 2026-11-08, where the
main's upstream segment ranked below its downstream one and the band filled the seam). The D8 streams hold braids,
twin segments carrying the same area into one junction (a 74 m piece beside the 425 m main, a 1.4 km twin beside a
2.1 km one): inflows within 2 % of each other's area are one stream, the longest path upstream continues, and at
equal rank the longer stem is placed first, so a braid's twin never takes the main's continuation or its stations
(his second round of circles); the lattice centres
within 3.5 cells of a line centre join the diagram (those within 0.75 of a line centre go); the mesh is the clipped
Voronoi diagram of all of them, bounded by the lattice positions beyond. A cell under 0.4 of a square loses a centre:
a cell of a higher line squeezed by a lower line's centre drops that centre (his rule: the main stem wins the cells
aligned to it; at his circled junction the tributary's last pair had cost the main its second row), a mirrored pair
never its own (the centre behind it goes, outward); the lattice centres within one cell of a line relax to
their cell's centroid twice; a band cell over 8 faces loses its centre; a 3-sided cell on a line loses the centre
behind or the lattice centre beyond it; faces shorter than 0.15 of a cell, the diagram's near-degenerate edges, are
contracted to a node; cells reaching outside the domain are cut back to the squares the strip replaces; a lower line's
station whose pair would land within two cells of a placed centre (so a band cell always separates a tributary's
cells from the main's rows), outside the active cells or within 3.5 cells of a boundary line's square ends the line
there. Because no lattice centre on the band's rim ever moves (the band is wider
than the relaxed zone by more than a cell's diagonal), every face between the strip and the squares is a lattice edge,
which the hybrid step needs, and the cells cover exactly the squares they replace (checked to 1e-6 on every build).

The solver's contract takes any polygon: one ring of any length per cell (`MeshGeometry`), a cell-to-face CSR on the
GPU. Nothing in the kernels changed.

## Tests (`tests/strips/test_centres.py`, 10)

The floor rule finds a 2 m scarp at 70 m, a 1.5 m scarp under the 2 m rise, the 2 m rise at 67 m on a 3 % fan, no bank
on a 0.5 % plain, and never a bank in the first cell. A straight line is a chain of faces with 4-sided cells, two rows
to a 70 m bank, every join face a lattice edge, the rim cells exact squares, nothing under the minimum, polygons in the
transition. A 120 m bend keeps its chain whole and merges its inner cells into polygons of at most 8 faces. A junction
keeps the main's chain whole and stops the tributary about a cell and a half short. A hard line outranks a stream and
its faces lie on it. A guide line is smoothed at a 90 degree corner, a hard one reported. A line ends at the domain's
edge, one wholly outside is refused in words. The strip ends clear of a boundary's squares. **W3's channel at 0 and
45 degrees holds the 3 % rule on these cells: 0.986 and 0.990 of the normal depth with a 70 m floor, 0.979 and 1.009
with the flow forced into the band polygons (floor 20 m).**

## Block 2 at 30 m, geometry only (`block2_centres.py`, `block2/`)

| | Count |
|---|---|
| Thalwegs, 1 km2 | 432 segments chained into 203 stems with cells |
| Cells on the lines | 58,519 |
| Cells around them | 131,013, of which exact squares 68,861 |
| Faces per cell | 3: 278, 4: 116,116, 5: 54,373, 6: 16,984, 7: 1,664, 8: 116, 9: 1 |
| Cells under 0.4 of a square | 2, smallest 340 m2 |
| Faces on the lines | 23,351 |
| Squares replaced | 198,158 |
| Total cells against 900,861 squares | 892,235, -1.0 % |
| Build | 101 s |

The 278 three-sided cells are the end cells of stems, most over half a square; the two cells under the minimum and
the one over the face limit are what three merge rounds left, a rounds setting away. With the two-cell clearance a
tributary ends two cells short of the main's outer row and a band cell sits between; the main's rows run whole
through every junction. The strip ends 3.5 cells before
the job's boundary lines, which took three lines' cells away at the domain's edge. Maps `block2/mesh_centres.png`
(four windows), `block2/mesh_centres_overview.png`; the QGIS group 6 of `W45 .../compare_meshes.qgz` (`qgis_centres.py`).

## The race on Faydh 01 at 20 m (`race_faydh_centres.py`, `race_faydh/`)

W45's rule: the dam-axis peak within 3 % of the run with no lines (1,835.2 m3/s); the ring corridors of the W45 race
(cells a quarter of the width, 20 to 50 m, on the bank pairs' mid-line) read +2.4 %, W45's fixed 20 m cells on the
thalweg +2.2 %.

| Run, GPU, 16 h | Axis peak m3/s | Against no lines | Steps | Loop s | Mass error | Strip cells |
|---|---|---|---|---|---|---|
| No lines, 20 m squares | 1,835.2 | | 88,589 | 13 | -2e-8 | |
| W45 ring corridors (its race) | 1,879.9 | +2.4 % | 134,632 | 36 | -2e-8 | 10,716 |
| Centres, the floor rule's defaults | 1,987.0 | **+8.3 %, FAIL** | 94,152 | 40 | -1e-8 | 6,068 |
| Centres, a wide floor (8 m rise, no scarp, no cap) | 2,008.4 | **+9.4 %, FAIL** | 94,542 | 38 | -2e-8 | 8,562 |
| Centres, no relaxation of the band | 2,002.3 | +9.1 % | 93,834 | 30 | -2e-8 | 6,068 |
| W45's ring generator, fixed 20 m cells on the thalweg, this job | 2,124.6 | **+15.8 %** | 113,627 | 55 | -2e-9 | 5,643 |
| No lines, 10 m squares | 1,871.3 | +2.0 % | 147,968 | 66 | -2e-8 | |
| No lines, 5 m squares | 1,887.1 | +2.8 % | 286,725 | 479 | -2e-8 | |

[Certain, measured] Both centre meshes close the books to 1e-8 and hold less water at the end than the squares
(0.81 against 1.08 Mm3), so the pond is gone; the same volume passes the axis (9.85 Mm3 in all three), the peak is
higher and the flood narrower (48 against 54 minutes at half the peak). **The squares converge: 20 m 1,835, 10 m
1,871, 5 m 1,887, and W45's HEC-RAS at 10 m read 1,872. The centre mesh at 1,987 stands 5 % above the 5 m squares,
and W45's own ring generator with fixed 20 m cells on the thalweg, run on this job tonight for the first time, stands
13 % above them.** So the excess is not this generator's: it belongs to 20 m cells aligned along the thalweg with
the thalweg on a face, whichever construction makes them, and it is an error. The corridors that passed W45's gate
at +2.2 to +2.4 % had 20 to 50 m cells across on the bank pairs' mid-line, coarser across the channel. The channel
gate passes within 2 % on both constructions, so the defect lives in the aligned cells' physics on real sinuous
ground, the sub-grid tables of polygon cells and faces or the hybrid step on them, not in the geometry. [Likely]
That is the next investigation, before any mesh of this kind carries a design flow.

## Found on the way, in order

1. The slope cap of the bank rule fired a run's length before the scarp it had not reached, at the foot of every
   channel: the cap now fires where a climb steeper than it begins and holds over the run.
2. The Voronoi diagram leaves faces of centimetres to metres where four centres are nearly equidistant from a vertex:
   3,766 faces under a metre on Faydh, 5,823 with a wide floor. They are contracted to nodes.
3. **The strip covered the squares of Faydh's outflow boundary, and a strip face on the domain's edge is a wall: a pond
   15 to 23 m deep stood at the outlet, backed up 1.3 km to the dam axis, read +8.7 % there, and with a wide floor
   exceeded the tables' range and lost 4.5 % of the water from the books** (the CPU twin on the same mesh lost 7.2 %
   in 38 minutes: the geometry's fault, not the kernel's). The cells of the job's boundary lines, as
   the run picks them, and one ring of squares round them now stay squares and the strip ends 3.5 cells before them,
   so its water leaves strip to square to boundary as the ring corridors' does.
4. His circled jog: mirroring the pair across the station along the mean normal left a short face across the line at
   every bend, where the two cells diagonally across the line met. Mirroring across each segment makes the four
   centres round a vertex equidistant from it, and the chain of faces is the polyline itself.
5. **The engine's grid cache keyed the lattice tables on the job alone, not on the cells the strip replaces.** With
   the job unchanged and the mesher changed, four reruns took the first run's tables: a lattice masked where the new
   strip was not left a wall between them, the pond stayed whatever the mesh did, and the wide run's books lost up
   to 20 %. The key now carries a hash of the replaced cells (`run.py`); every result above the line was rerun on a
   fresh cache.

## Not done

**First, the physics of 20 m cells aligned along a thalweg on real ground**, which over-read Faydh's peak by 8 to 16 %
under both generators while the channel gate passes: the sub-grid tables of polygon cells and faces where the deepest
pixels lie on a face, and the hybrid step on them, against the converged squares and a bend case with an analytic
answer. Then the split rule for over-long outer cells on a bend (his square rule's mirror: a cell over about 1.6 squares gets a
centre); the dock controls (`generator`, the face limit, the minimum area, the bank numbers); the Bidah hybrid race;
his drawn bank lines for calibrating `bank_rise_m` and `bank_scarp_m`; the full Block 2 run.
