# W49 local hydraulic radius face table

**Live (2026-11-08), branch `feature/face-local-radius` off `feature/face-depth-carry`, not merged.** His go of the
same night on W48's recommendation (`W48 aligned cells race excess/reports/Wall shear in sub-grid friction.md`): a face
conveyance after Spada et al.'s local hydraulic radius, in the table builder, behind a switch.

## Why

W48 found that Wadi2D reads a narrow deep gorge about 17 % shallow. A face's conveyance is the sum over the pixels
across it of (1/n) d^(5/3) on plan width: no shear on the walls, the choice of SFINCS, 3Di and TUFLOW's sub-grid by
default. On W48's gorge (a 12 m bed, walls rising 7 m over 1.5 m, bed slope 1 %, n 0.05, 300 m3/s) that gives 4.40 m
at every cell size. HEC-RAS 6.6 gives 5.28 m at 20 m and 4.70 m at 5 m, because it puts the walls in each face's own
wetted perimeter. Manning on the whole section's hydraulic radius gives 5.39 m; smooth-flume data put about 40 % of
the shear on the walls at this width-to-depth ratio, and Spada et al.'s method gives about 5.3 m.

## What it does

`tables.face_conveyance: local_radius` (default `strips`, today's tables to the digit) and `tables.local_radius_beta`
(default 9). At each level of a face's table, each pixel i of the face conveys (1/n) d_i R_i^(2/3) per unit width,
where R_i is the wetted area over the wetted perimeter of the pixels within beta d_i of it on the same wet run, each
weighted 1 - |s - s_i| / (beta d_i). That is Spada et al. 2015 (HESSD 12, 2607), eqs. 14 to 17, with their beta of 9,
calibrated on the HR Wallingford flood channel series and insensitive by their account. Four points of construction:

- **The window reaches past the face's own ends.** A face's line is read `ceil(beta x table top / pixel)` pixels
  beyond each end, so a face on the bed sees the walls of the next face and the answer does not depend on where the
  faces fall. The table builder reads each tile with that margin (`face_depth_max` x beta, 144 m at the defaults).
- **The wetted perimeter is continuous in the level.** The ground between two pixel centres is taken as straight and
  counted only where it lies under the water. The first build gave a just-wet wall pixel the full slope length of its
  half-segments, which dropped the gorge's conveyance by 7 % between 5.8 and 5.9 m; found by the test against a direct
  evaluation, fixed before any run.
- **On a bed with no relief across a face it is the strips sum**, R_i = d_i, to round-off (tested).
- **Crest faces keep their strips table**, since their cap reads the crest. Polygons of the aligned strips take the
  same rule along each face's own line. The quadtree refuses the switch for now.

Window sums are prefix sums, so the cost is linear in the line's length whatever the window.

## Tests (`tests/tables/test_local_radius.py`)

1. A face on a bed with no relief across it: local radius equals strips, rel 1e-5.
2. W48's gorge section at 20, 10 and 5 m cells: the conveyance the x faces of one column carry together equals an
   independent O(n^2) evaluation of Spada et al.'s integrals on the same pixels within 1 %, at 2, 4 and 5.3 m.
3. The gorge's normal depth by the tables: the same at 20 m and 5 m, and over 1.15 x the strips sum.

| Cells | Strips, m | Local radius, m |
|---|---|---|
| 20 m | 4.407 | 5.318 |
| 10 m | 4.407 | 5.314 |
| 5 m | 4.407 | 5.314 |
| 2.5 m | 4.407 | 5.314 |
| Direct evaluation on the pixels | | 5.310 |

At exact table rows the tables match the direct evaluation to 1e-4; between rows the linear interpolation of the
conveyance's 3/5 power adds up to 0.25 %.

## The gorge in the solver (`gorge_local_radius.py`, `probe/`)

W48's two gorges rerun with the switch on, read with W48's `gorge_reading.py` (the water surface over the 0.5 m DEM
between 1 and 8 km, the level 3 m either side of the axis). Depth on the axis, m:

| Mesh | Straight, strips (W48) | Straight, local radius | Tight sine, strips (W48) | Tight sine, local radius |
|---|---|---|---|---|
| Squares, 2 m | 4.407 | **5.317** | 4.806 | **5.369** |
| Squares, 5 m | 4.382 | 5.291 | 4.843 | 5.386 |
| Squares, 10 m | 4.383 | 5.304 | 5.075 | 5.600 |
| Squares, 20 m | 4.383 | 5.307 | 7.082 | 7.601 |
| Centres, 10 m | 4.408 | 5.316 | 4.532 | 5.483 |
| Centres, 20 m | 4.407 | 5.319 | 4.569 | 5.531 |
| HEC-RAS 6.6, squares 2.5 m | 4.724 | | | |
| HEC-RAS 6.6, squares 5 m | 4.698 | | 5.319 | |
| HEC-RAS 6.6, squares 20 m | 5.276 | | 4.974 | |
| HEC-RAS 6.6, aligned 20 m | 5.273 | | 5.287 | |

Against the 2 m squares on the same table rule, level and water held in the reach:

| Mesh | Straight, local radius | Tight sine, strips (W48) | Tight sine, local radius |
|---|---|---|---|
| Squares, 5 m | -0.026 m, -0.88 % | +0.037 m, +1.48 % | +0.003 m, +0.76 % |
| Squares, 10 m | -0.040 m, -0.84 % | +0.269 m, +6.67 % | +0.230 m, +6.05 % |
| Squares, 20 m | -0.048 m, -0.79 % | +2.276 m, +54.78 % | +2.246 m, +55.86 % |
| Centres, 10 m | -0.038 m, -0.64 % | -0.274 m, -4.68 % | **+0.125 m, +3.08 %** |
| Centres, 20 m | -0.048 m, -0.58 % | -0.237 m, -3.26 % | **+0.171 m, +4.85 %** |

[Certain, measured] Three things:

1. **The straight gorge reads 5.29 to 5.32 m on every mesh**, the tables' own normal depth (5.31 m) and within 0.03 m of
   HEC-RAS at 20 m (5.28 m), where the strips sum read 4.38 to 4.41 m. The cell-size independence holds in the solver,
   not only in the tables: the walls carry their shear whatever the faces are.
2. **On the tight sine the converged answer is now within 0.07 m of HEC-RAS's 5 m mesh** (5.37 to 5.39 m against
   5.32 m), where the strips sum read 0.51 m under it. With the walls carrying shear, the bends add 0.05 to 0.10 m at 2
   and 5 m, where with the strips sum they added 0.40 m; HEC-RAS's 5 m mesh adds 0.62 m, on a straight answer of its own
   that depends on the cell size.
3. **The aligned cells' bend error changes sign and stays about the same size**: +0.17 m at 20 m and +0.13 m at 10 m
   over the converged answer, where the strips sum gave -0.24 and -0.27 m. The 20 m squares are unchanged in kind
   (+2.25 m, the staircase choking the channel), so the aligned cells remain the better 20 m mesh in a narrow gorge;
   why the pair now reads high in a bend is not looked at.

[Certain, measured] **Against HEC-RAS converged, the two solvers now differ the other way.** HEC-RAS settles at 4.70 to
4.72 m on the straight gorge at 5 and 2.5 m cells (W48), 0.6 m under the local radius's 5.31 m and 0.3 m over the
strips sum. [Likely] The physical answer is near 5.3 m by the flume-based literature (W48's report), which is what the
local radius reads; nothing measured on a gorge of this shape decides it, and the flume data (Knight and Demetriou,
Molls et al.) are not yet obtained.

The cost is the table build, once per terrain since tables are cached: 2.7 to 6.6 s on the 20 m gorge, 7.6 to 48.9 s
on the 2 m one (the line read past each face's ends, 144 m at the defaults).

## The Faydh race (`race_local_radius.py`, `race_faydh/`)

Option A's six race jobs (`W47 .../depth_carry/race`, rain on Faydh 01's grid, the dam axis at 16 h) rerun with the
switch on and their own cache. Dam axis peak, m3/s:

| Run | Option A, strips | Option A, local radius | Change | Strips against 5 m squares | Local radius against 5 m squares |
|---|---|---|---|---|---|
| Squares, 20 m | 1,785.8 | 1,731.9 | -3.0 % | -4.3 % | -3.6 % |
| Rings, 20 m (W45) | 1,855.6 | 1,787.8 | -3.7 % | -0.6 % | -0.5 % |
| Centres, 20 m | 1,952.0 | 1,876.3 | -3.9 % | +4.6 % | +4.4 % |
| Squares, 10 m | 1,839.2 | 1,779.2 | -3.3 % | -1.5 % | -1.0 % |
| Centres, 10 m | 1,899.5 | 1,835.9 | -3.3 % | +1.8 % | +2.2 % |
| Squares, 5 m | 1,866.8 | **1,797.0** | **-3.7 %** | 0 | 0 |

Centres against squares at 20 m, the 3 % rule: +9.3 % with the strips sum, **+8.3 %** with the local radius.

[Certain, measured] **The walls' shear lowers Faydh 01's peak by 3 to 4 % on every mesh and leaves the race as it
was.** The converged answer moves from 1,866.8 to 1,797.0 m3/s: Faydh's gorge is narrow and deep enough for the walls
to matter, and the extra resistance attenuates the flood. The meshes keep their order and their gaps within a
per cent, so the race's excess is not the wall shear; it stays where W48 put it, in the aligned pair at tight bends
of a deep narrow channel. Table build time on Faydh: 25 to 140 s a run, once per terrain.

## The ladder and the suite

- **Switch off (the default): the full suite passes, 1,947 of 1,947** (`pytest_full_switch_off.log`); the tables are
  today's to the digit, and the schema sample gains the two fields.
- **Switch forced on for every table build (an experiment, `ladder_local_radius_forced.log`): the CPU solver and
  validation ladder passes 222 of 223.** Stoker, Ritter, MacDonald, Thacker, still water, the weirs and the steady
  channels do not move past their rules. The one failure is W3's channel on polygons at 45 degrees, 1.032 of its
  reference against 1.025 with the strips sum; the reference is the strips sum's own normal depth by construction,
  and the local radius's normal depth of that section is 0.47 % deeper (60 m bed, 2:1 banks, width over depth about
  77), so against its own normal depth the run reads 1.027, inside the 3 % rule. Not a defect; a gate written for the
  strips sum.
- [Likely] On a face oblique to the flow the window reads the ground along the face's line, so a bank is seen
  flatter and farther by 1 / cos of the angle; at 0 degrees it is exact. Not measured.

## Where it stands

Built and tested on `feature/face-local-radius`, off by default, not merged. What it does: the walls of a narrow
deep channel carry shear whatever the cell size, which lowers Faydh 01's converged peak by 3.7 % and reads W48's gorge
0.9 m deeper. What it does not do: close the race (centres +8.3 % over squares at 20 m), nor rest on measured data for
a gorge of this shape. Not done: the flume data (Knight and Demetriou, Molls et al., his permission to obtain them);
the quadtree's tables (it refuses the switch); the dock control; why the aligned pair reads high in a bend with the
walls on; Bidah and Block 2 with the switch on. His call: whether it becomes the default after the flume test, or now.
