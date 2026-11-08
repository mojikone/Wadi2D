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

**How the bed is defined, his question:** station by station along each stem, going outward along the station's
normal, the bank is the first of a 1 m scarp within 10 m read on the 5 m pixels, the ground 2 m above the thalweg's
lowest pixel, and the 5 % slope cap where a climb begins and holds over 40 m; never inside the first cell; none
within 300 m is no bank on that side. The distance, rounded to whole cells and smoothed over five stations, is the
row count, so the strip's outer edge is the bed quantised to the cell. The rule's own bank points are now written as
the `bed_edges` layer of `mesh_centres.gpkg`, one line per stem and side, broken where a side has no bank, and drawn
green in the QGIS group 6; the green "floor edges" of groups 4 and 5 are W45's older 5 % rule from the Suggest file.

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
ground, the sub-grid tables of polygon cells and faces or the hybrid step on them, not in the geometry.

**The investigation, his go of 2026-11-08** (`aligned_cells_probe.py`, `probe/`; the Faydh variants in `race_faydh/`):

| Experiment | Result |
|---|---|
| Centres at 10 m on Faydh | 1,918.8: +2.5 % on the 10 m squares, +1.7 % on the 5 m squares. **The aligned cells converge from above (1,987 at 20 m, 1,919 at 10 m), the squares from below (1,835, 1,871, 1,887): a coarse-cell error of the aligned cells, not a bias that refinement keeps** |
| W3's channel, straight, flat bed, squares against centres | 0 degrees -1.4 against -1.4 %, 45 degrees +2.6 against -1.0 % of the normal depth: no difference to hunt |
| The same section along a sine wave, 120 m amplitude, 800 m wavelength, radius 135 m at the bends | squares +1.6 %, centres -0.2 % of the straight channel's normal depth: on a bend the aligned cells lose the staircase's friction and sit closer to the answer, so bends are not the mechanism |
| The same with a 10 m by 1.5 m slot on the axis, the thalweg on a face | the probe's initial and boundary state put the flow three to four normal depths deep, for squares and centres alike: not a valid test yet, to be rebuilt |
| Squares against centres at 20 m on a DEM averaged to 20 m blocks, no sub-grid content | centres 1,050 against squares 1,158, -9.3 %, where on the 0.5 m DEM the centres read +8.3 %: **the sign of the difference turns with the sub-grid content, so the mechanism is in how the aligned cells read sub-grid ground**, and the one arrangement where they read it differently from the squares is the deepest line lying on a face, each pair cell holding half the channel |

| The same Faydh job with every thalweg shifted 5 m sideways before the mesh is built (`race_faydh/thalwegs_shift5.gpkg`), so the deepest line lies inside one pair cell and not on the face between them, everything else equal | 1,994.2, +8.7 %: **no change. The deepest line on a face is not the mechanism** |

Two traps of the night that are not the engine's: a fiona write whose geometry type differs from the layer's schema
(a LineString into a MultiLineString layer) dies mid-transaction and leaves a 64 KB GeoPackage that opens nowhere,
with the error reported only by the opener; and the venv has no GDAL Python bindings, so an in-place edit through
`osgeo` silently did nothing and a run went out on unshifted lines. Both cost relaunches before the shifted run ran.

[Certain, measured] The 20 m aligned cells are not wrong in kind; they are wrong by 5 % at 20 m and by 1.7 % at 10 m
on this ground, where the squares are wrong by -2.8 and -0.8 %. A design line read from them at 20 m is not within
the 3 % rule, at 10 m it is. Rejected as the mechanism: bends on aligned cells, oblique faces sampling a channel, the
band's relaxation, the floor's width, and the deepest line lying on a face. What every probe above shares, and the
Faydh number does not, is steady flow: each read a normal depth, where the race reads the peak of a wave. The
unsteady probe below took it from there.

## The unsteady probe and the Faydh split (`wave_probe.py`, `probe_wave/`; `faydh_split.py`, `race_faydh/split/`)

The race's own hydrographs, read first (`race_faydh/`): the centre mesh passes the axis 0.9 % more water than the
squares (9.85 against 9.76 Mm3, the same rain, 0.10 Mm3 less left standing in the catchment at 16 h), its centroid
comes 5.5 min earlier, its rising limb runs 7 to 14 % above the squares from hour 9 to 12.5 and its recession 8 to
16 % below. The squares' centroids converge from late (12.576, 12.542, 12.530 h at 20, 10, 5 m), the centre mesh's
from early (12.484, 12.501): **the aligned cells route the flood faster than the converged answer, the squares
slower.** So the question was whether the speed sits in the channel cells or in how the hills' water reaches them.

**The synthetic valley** (`wave_probe.py`): an 8.4 km valley on a 0.5 m DEM whose centreline is a sine wave of 150 m
amplitude and 1,200 m wavelength (radius 243 m at the bends), bed slope 1 %, Manning 0.05, one section translated
along it: `gorge`, a channel 40 m wide and 3 m deep with 2:1 banks, a floodplain 80 m each side at 1.5 %, hills at
25 % to the edge, so the floor rule stops at the lip and the aligned cells are the channel pair with the band on the
floodplain; `plain`, a wadi 60 m wide and 0.8 m deep with 4:1 banks (under the scarp and the rise) and a floodplain
100 m each side, so the rows reach the hill toe; `straight`, the gorge section with no bends, the thalweg on a
lattice line, where the squares have no staircase and the centre generator's cells are squares. Forcings: a wave
with a 1.5 h rise (hardly attenuates, 1.6 % over 7 km), a flash flood of 1,500 m3/s with a 20 min rise and a 40 min
fall (Faydh's own half-peak width is 50 min), and rain on the whole valley, hills included, 70 mm in 4 h with 30 mm
in the 20 min after hour 2, as Faydh's storm has; and the rain as a depth grid falling only within 200 m of the
thalweg (the pair, the band, the nearest squares) or only beyond it, the run handing every strip cell its own rate
by position. Read at a section across the whole valley 7.5 km down, against the 5 m squares of the same run:

| Ground, forcing | Squares 20 m | Centres 20 m | Squares 10 m | Centres 10 m |
|---|---|---|---|---|
| gorge, slow wave | +0.2 % | +0.2 % | +0.1 % | +0.1 % |
| plain, slow wave | 0.0 % | 0.0 % | -0.1 % | 0.0 % |
| gorge, flash flood | +1.5 % | +0.1 % | +0.6 % | +0.1 % |
| plain, flash flood | +0.4 % | +0.4 % | +0.2 % | +0.3 % |
| straight, flash flood | -0.4 % | -0.4 % | | |
| gorge, rain everywhere | **-3.0 %** | **+2.2 %** | +1.2 % | +2.4 % |
| plain, rain everywhere | **-3.6 %** | **+2.3 %** | +0.4 % | +2.4 % |
| gorge, rain within 200 m of the thalweg only | -6.4 % | -2.4 % | | |
| gorge, rain beyond 200 m only | -5.7 % | -1.6 % | | |
| straight, rain everywhere | **+2.9 %** | **+2.9 %, the squares' numbers to the digit** | +1.7 % | +1.8 % |

[Certain, measured] Four things follow. A flood that enters as a hydrograph routes the same on both meshes and both
converge: there is no coarse-cell error of the aligned cells in the channel, flash flood or slow wave, gorge or
plain. Rain-fed, the pattern of Faydh appears at a third of its size: squares on the sinuous channel -3 %, centres
+2 %, the squares converging from below and the centres staying above at 10 m. On the straight valley the centre
mesh gives the squares' numbers to the last digit (the polygon kernel on square cells is the lattice kernel), and
both stand +2.9 % over the 5 m squares at 20 m and +1.7 % at 10 m under rain, -0.4 % under the flash flood: **the
coarse-cell error under rain belongs to the scheme on coarse cells, squares and polygons alike, and the inflow runs
say it is in how rain on the ground becomes flow, not in the channel.** Whether the rain falls on the strip's own
cells or only on the hills beyond the band changes nothing between the meshes (a spread of 4.3 % either way). So on
the synthetic sinuous channel the aligned cells carry the scheme's coarse-cell error and nothing else, while the
squares carry it plus the staircase's slowdown of 5 to 6 %, which lands them below the converged answer. That is the
synthetic valley's verdict; Faydh's own, below, is harsher on the strip.

**Faydh itself, split** (`faydh_split.py`, 20 m, GPU, the race job with lines across the main stem 5, 10 and 15 km
from its head and across two tributaries at mid-length; the centre mesh on all 21 stems, on the main stem alone
(22 km, 2,189 cells) and on the 20 tributaries alone; then the rain as a depth grid within 150 m of the main stem
only, or beyond it only). Peaks against the 20 m squares with the same rain:

| Rain | Strip on | Axis | Main 5 km | Main 10 km | Main 15 km | Tributary 3 | Tributary 6 |
|---|---|---|---|---|---|---|---|
| everywhere | all stems | +9.0 % | +12.8 % | +15.6 % | +16.4 % | +5.0 % | +85 % of 13 m3/s |
| everywhere | the main stem alone | +4.3 % | +11.1 % | +13.6 % | +12.7 % | -0.6 % | +23 % |
| everywhere | the tributaries alone | +5.2 % | +1.0 % | -0.4 % | +5.6 % | +4.0 % | +94 % |
| within 150 m of the main stem | the main stem alone | +13.7 % of 78 m3/s | +16.1 % | +18.4 % | +18.0 % | dry | dry |
| beyond 150 m of the main stem | the main stem alone | +3.4 % of 1,699 m3/s | +11.1 % | +12.4 % | +11.1 % | -0.3 % | +4.7 % |

The squares' peaks: axis 1,835, main stem 356, 629 and 884 m3/s at 5, 10 and 15 km. [Certain, measured] **The excess
sits on each strip's own channel**: the main stem's strip alone reads 11 to 14 % above the squares on its own lines
from 5 km on, where its catchment is a few square kilometres, and a flat 11 to 13 % along the next 10 km; the
tributaries' strips leave the main's lines untouched (+1.0, -0.4 %) and add their own excess where they join. Whether
the water falls on the strip and its band or comes off the hills through the squares makes no difference (+11 to
12 % either way), so it is not the rain on polygon cells. The strip's hydrographs peak 3 to 4 min earlier.

**The two kernels read side by side** (a read of `solver/cpu/kernels.py`, `faces.cu`, `cells.cu` against
`solver/poly/kernel.py`, `poly.cu`, `strips/hybrid.py` and the two table builders; `poly.cu` matches `kernel.py`
statement for statement). [Certain, read] The same on both paths: the rain source, each cell's own rate by position
once per source window and `dt x source` every step with no depth gate; the dry-face threshold, the thin-sheet fade
and the disconnected mean-surface drive; the velocity desingularisation; the upwind depth rule and the table read at
it; the friction law; the sub-steps, each applying its own share of the source; the CFL test; the cell table and the
Lotter sum of the face table with its depth limits. Different, none of it large: the polygon's thin-sheet section is
the cell volume times the face length over the cell area where the lattice reads volume over the cell size, the same
on a rectangle and not on a 5- to 8-faced band cell, and not the same as the kernel's own momentum section, volume
over the face spacing; a polygon face's Manning n is the mean of its two cells where the lattice takes the right
cell's, and the lining weights of the pixels are ignored on polygons; the lattice's second-order upwinding of the
advection is first order on polygons; the strip always steps at the finest step while thin squares climb to coarser
levels; the join face hands the lattice a velocity of q over h times dx with the depth floored and no clamp; and the
invert clamp of a polygon face is applied after its table is built, so that face reads too little area, which slows
polygons, not speeds them. The straight valley's identity to the digit says the physics are the same where the cells
are squares, and the synthetic sinuous valley says the band's polygons add at most a per cent; what remains
is the aligned cells on Faydh's real ground, read against the fine squares on the same lines.

**Faydh's main stem against the converged peak** (the no-lines job at 10 and 5 m with the same lines, the main
stem's strip at 10 m; the 5 m squares' peaks 1,887, 368, 646 and 905 m3/s at the axis and 5, 10 and 15 km):

| Against the 5 m squares on the same lines | Axis | Main 5 km | Main 10 km | Main 15 km |
|---|---|---|---|---|
| Squares, 20 m | -2.8 % | -3.1 % | -2.6 % | -2.3 % |
| Squares, 10 m | -0.8 % | -2.0 % | -1.6 % | -1.7 % |
| The main stem's strip, 20 m | +1.4 % | **+7.7 %** | **+10.7 %** | **+10.1 %** |
| The main stem's strip, 10 m | 0.0 % | +5.2 % | +6.0 % | +4.9 % |

[Certain, measured] **This overturns the synthetic valley's comfort.** On Faydh's own channel the squares' staircase
costs 2 to 3 % at 20 m, not the 8 % the axis figures suggested, and the strip stands 8 to 11 % above the converged
peak on its own lines at 20 m and 5 to 6 % at 10 m: an excess of the aligned cells themselves, on real ground, fed
by lateral inflow along the channel, halving with refinement and so a coarse-cell error, but one the synthetic
channel does not have at any size (+2 %, the scheme's own) and the squares do not have on the same ground. The axis
hides it: the main stem's strip alone reads +1.4 % there because the tributaries' water arrives through squares and
dilutes it, and with every stem aligned the tributaries add their own share to make the race's +5 %.

**A flood down the strip with no rain** (`*_flood` in `race_faydh/split/`: a flash flood of 300 m3/s, 20 min up and
40 min down, entering the main stem 2 km below its head, read against the 10 m squares on the same lines; the
squares at 20 and 10 m agree within 0.5 % along the stem, so the lattice is converged here):

| Flood, no rain, against the 10 m squares | Main 5 km | Main 10 km | Main 15 km | Axis, 20 km |
|---|---|---|---|---|
| Squares, 20 m | -0.4 % | +0.1 % | -0.5 % | -3.9 % |
| The main stem's strip, 20 m | -0.1 % | +2.2 % | +4.6 % | +7.2 % |
| The main stem's strip, 10 m | +0.6 % | +1.8 % | +3.1 % | +7.2 % |

[Certain, measured] **The strip attenuates a flood wave less than the squares on this ground, by about 0.4 % per
kilometre, the same at 20 and 10 m.** The squares take the wave from 275 to 218 m3/s over 16 km, the strip to 234;
the strip's centroid runs 7 min ahead at 15 km. A difference that does not shrink with the cell size is not a
coarse-cell error but a difference of construction between the two paths; and it is not the face reading: making a
polygon face read two distinct pixels as a lattice face does (the one sampling rule that differed on oblique faces)
moved the axis from +7.2 to +7.1 % and the rain lines by under 1 %, so that change was taken out again. Under rain
the strip's excess on its own lines (+8 to 11 %) is larger than the flood's at the same stations because the hills'
water enters all along the channel and each parcel is routed with the same deficit of attenuation.

[Likely] The 5 m squares are not above suspicion as the reference on this channel: Faydh's gorge channel is 5 to
15 m wide, one to three cells at 5 m, where W3 measured the staircase's own depth error at +3.5 to +8 % on an
oblique channel, and a deeper, slower lattice flood attenuates more. The synthetic valley, 40 m wide, 8 cells at 5 m,
had no such bias. So the test went to a reference the staircase cannot bias.

**The reach, squares to 2 m** (`faydh_reach.py`, `race_faydh/reach/` and `reach_long/`): the main stem from 4 km
below its head in a domain 250 m either side, the same flash flood entering at 4 km, no rain, squares at 20, 10, 5
and 2 m against the strip at 20 and 10 m, read on lines across the valley at kilometre marks. Each mark is read as
the median of three lines 100 m apart, because on 20 m cells one line is not a reading: across the strip a line that
falls between two station faces at a bend read half the flow (-55 %), and across 20 m squares one line read 15 %
high where its neighbours read 5 and 3 % high; the 2 m squares' three agree to 1 %. The lattice is converged here:
5 m within 0.2 % of 2 m on every mark.

| Flood, no rain, against the 2 m squares | 6 km | 10 km | 14 km | 18 km |
|---|---|---|---|---|
| Squares, 20 m | +6.4 % (one line's noise) | +3.2 % | +2.5 % | **-5.0 %** |
| Squares, 10 m | +1.8 % | +0.7 % | +0.6 % | -0.7 % |
| Squares, 5 m | +0.1 % | 0.0 % | 0.0 % | +0.2 % |
| The main stem's strip, 20 m | +2.0 % | +2.2 % | (two lines over-read) | **+4.2 %** |
| The main stem's strip, 10 m | +1.4 % | +0.8 % | +1.3 % | **+3.7 %** |

The 2 m squares' peaks: 288, 278, 274 and 253 m3/s, a flood that loses 16 % of its peak over the 14 km; the strip's
loses 12 %. (The 4 to 12 km reach read alike: at 10 m both constructions within 2 % of the 2 m squares at every mark
to 12 km, the strip +0.9 to +1.5 %, the squares +0.5 to +2.0 %.)

[Certain, measured] **The strip under-attenuates a flood on Faydh's channel by about 4 % over 14 km, at 20 and 10 m
alike, against a lattice converged to 0.2 %.** The squares at 20 m under-read the same wave by 5 % there and are
within 0.7 % at 10 m. So on this ground the strip's error is of construction, not of cell size: it does not come
from the sub-grid reading of the faces (tested), not from the band's polygons (the synthetic valley), not from the
rain (the flood has none), and the lattice's own asymptote is not the culprit (5 m and 2 m agree). [Likely] What
the synthetic channel has and Faydh's does not is a guide line that is the channel's own centreline: on Faydh the
strip follows a D8 thalweg smoothed over five stations, so its station faces stand at an angle to the flow wherever
the line and the channel part, and a face oblique to the flow by an angle phi reads its conveyance 1 / sqrt(cos phi)
too high in this scheme (+3 % at 20 degrees, +7.5 % at 30), at every cell size, since the misalignment is the
line's and not the cells'. [Certain, measured] **Tested and rejected.** The synthetic gorge with a guide line that
wobbles 30 m either side of the true centreline every 400 m (station faces up to 25 degrees off the flow) gives the
flash flood's peak at +0.1 % against the 5 m squares at 20 and 10 m, the gorge's own number to the digit; and the
Faydh reach with the line smoothed over 1 and 15 stations in place of 5 moves the 18 km excess from +3.7 to +3.9
and +2.5 % at 10 m, from +4.2 to +4.0 and +5.4 % at 20 m, a per cent either way and not with the smoothing. The
excess does not follow the faces' alignment. What is left between the two paths is the momentum advection, a
limited second-order upwinding on the lattice and a first-order Perot scheme on the polygons, which a prismatic
channel never exercises and a real channel of pools and constrictions does. [Certain, measured] **Not that either:**
the lattice run first order on the same reach (`numerics.limiter: none`, `sq*first` in `reach_long/`) moves the
18 km peak by -0.5 % at 5 m, -0.5 % at 10 m and +1.4 % at 20 m, nowhere near the strip's +4 %, so the order of the
advection does not make a lattice behave like the strip. Nor do expansions and contractions as such: on a synthetic
gorge whose bed widens from 40 to 80 m and back every 300 m, the strip reads the flash flood's peak at -1.5 % (20 m)
and -1.2 % (10 m) against the 5 m squares, the squares at 20 m -0.3 %: a little more attenuation on the strip there,
not less.

**The steady reach: where the water is** (`reach_long_steady_ramp/`, a constant 300 m3/s for 6 h down the same
16 km, ramped up over the first hour so the maximum level is the final one; the first set, `reach_long_steady/`,
started at 300 m3/s into a dry channel and its maximum-level rasters carried the arrival bore, with the same stored
volumes. `reach_levels.py`, and the pixel comparison of the session: each run's final water surface laid over the
0.5 m DEM inside the 20 m strip's footprint, the strip's cells at their own final level, the squares at theirs):

| Steady 300 m3/s, against the 2 m squares | Water stored in the reach | Water surface on the footprint, mean | Water in the footprint |
|---|---|---|---|
| Squares, 20 m | +1.0 % | +0.08 m | +4.3 % |
| Squares, 10 m | -1.1 % | -0.01 m | -0.1 % |
| Squares, 5 m | -0.7 % | -0.01 m | -0.4 % |
| The main stem's strip, 20 m | **-9.3 %** | **-0.20 m** | **-8.4 %** |
| The main stem's strip, 10 m | **-4.2 %** | **-0.08 m** | **-3.5 %** |

[Certain, measured] **At the same discharge the strip's water surface lies 0.20 m (20 m cells) and 0.08 m (10 m)
below the converged one, over the same ground with the same storage tables** (the water under the strip's own
final levels, counted pixel by pixel on the 0.5 m DEM, is the water the balance reports), **so it holds 8 to 9 and
4 % less water; a flood has less to fill and rides through with less attenuation: the race's "same volume, narrower
flood".** The depression halves with the cell size. The 20 m squares on the same channel stand 0.08 m *above* the
converged surface and hold 1 % more water. The strip at 5 m was refused by the tiling guard, 233 m2 of 660,625
between the diagram and the lattice (3.5e-4, not a sliver): a mesher defect at that size, recorded, not fixed.

**The straight valley at steady state, the inflow ramped over an hour** (`probe_wave/straight/straight_steady_*`;
the 5 m squares hold 2.107 m on the axis against the section's normal depth of 2.111 m by the same Lotter sum):

| Steady 300 m3/s, straight valley, against the 5 m squares | Water stored | Surface on the axis |
|---|---|---|
| Squares, 20 m | -2.5 % | -0.11 m |
| Centres, 20 m (the same cells) | -2.5 %, the squares' number | |
| Squares, 10 m | -1.0 % | -0.09 m |

[Certain, measured] **Where neither construction has a staircase, both stand low by about half the bed's drop within
one cell (1 % over 20 m is 0.2 m; the surface sits 0.11 m low) and hold 2.5 % less water at 20 m, 1.0 % at 10 m,
to the digit the same for squares and aligned cells.** [Likely] The reading behind it: a face takes its depth from
the upwind cell's level over the face's own invert, which lies half a cell downstream of where that level is held,
so a cell that conveys the right discharge through its downstream face stands too low over its length and its
storage table is read too low. On Faydh's channel, steeper (1.5 to 3 %) and 2 to 3 m deep in a 20 m cell, that
reading is 5 to 10 % of the depth, which is the strip's 9 and 4 %; the 20 m squares on the same channel hold 1.5 %
*more* water than the converged lattice, because the lattice carries the same reading and also the staircase's
deepening of an oblique channel one cell wide (W3's +3.5 to +8 % of depth), which here more than covers it. So
the aligned cells do not add an error; they take one away, the one that happened to cancel the scheme's own.

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

**First, his call on the scheme's face reading**, found by the hunt above: a cell holds its level about half a cell's
bed drop too low at steady flow because a face reads its depth from the upwind cell's level over the face's own
invert, half a cell downstream; squares and aligned cells share it (2.5 % of the stored water at 20 m, 1.0 % at
10 m on a 1 % channel; 9 and 4 % on Faydh's gorge for the strip), the squares' staircase deepening hides it on real
channels. The candidate fix is to read the face depth from the level carried to the face (the upwind level less the
bed's drop from the cell's centre to the face, or the two cells' mean), which touches the core kernels on both paths
and every validation number; not built. With it, the 3 % rule should be read against the converged peak (5 m
squares, HEC-RAS at 10 m), not against the 20 m squares, whose own error the rule had inside it. Then: the mesher
defect that refuses the centre mesh at 5 m on the Faydh reach (233 m2 of 660,625 between the diagram and the
lattice, over the loosened guard's 1e-4; the guard now notes a sliver under that and refuses over it); result lines
on 20 m cells of either kind that read 15 % high or 55 % low at some stations (the reach was read as the median of
three lines 100 m apart); the split rule for over-long outer cells on a bend (his square rule's mirror: a cell over
about 1.6 squares gets a centre); the dock controls (`generator`, the face limit, the minimum area, the bank
numbers); the Bidah hybrid race; his drawn bank lines for calibrating `bank_rise_m` and `bank_scarp_m`; the full
Block 2 run. The two-pixel face reading tried and withdrawn, the small kernel differences listed above (the
polygon's thin-sheet section, the mean Manning, the ignored lining weights, the invert clamp after the table) stay
recorded, none measured to matter here.
