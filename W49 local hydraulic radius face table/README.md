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
- **The table's top reaches the window's relief** (at most `face_depth_max`, the table rebuilt at the new levels).
  Above its top a table grows its conveyance with its area, the strips law on a flat face; a face on the flat bed
  of a deep channel had a top of `face_depth_min` (8 m), so deeper than that its walls were read away. Found by the
  flume test's self-check after the gorge and race runs below were first made: a 12 m rectangle at b/h 1 read 0.896
  of section Manning with cells inside the bed and 0.991 with one cell across; now 0.991 at every size. The runs
  were remade into new folders (`probe_top_fix`, `race_faydh_top_fix`); the first runs stay, superseded.
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

**Superseded by the runs after the table-top fix (next section); kept as the record of the first build.**

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

**Superseded by the runs after the table-top fix (next section); kept as the record of the first build.**

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

## After the table-top fix: the gorge and the race remade (`probe_top_fix/`, `race_faydh_top_fix/`) - live

| Gorge, depth on the axis, m | Straight | Tight sine |
|---|---|---|
| Squares 2 m | 5.325 | 5.379 |
| Squares 5 m | 5.301 | 5.391 |
| Squares 10 m | 5.314 | 5.587 |
| Squares 20 m | 5.315 | 7.584 |
| Centres 10 m | 5.326 | 5.484 (+0.120 m on the 2 m squares) |
| Centres 20 m | 5.326 | 5.534 (+0.169 m) |

The tables' own normal depth of the straight gorge: 5.325 m at 20, 10, 5 and 2.5 m cells (5.310 by the direct
evaluation; the bed faces' tables now span 16 m with the same 16 rows).

| Faydh 01 race, dam axis, m3/s | Option A, strips | Local radius | Against 5 m squares |
|---|---|---|---|
| Squares 20 m | 1,785.8 | 1,737.3 | -3.3 % |
| Rings 20 m | 1,855.6 | 1,807.5 | +0.6 % |
| Centres 20 m | 1,952.0 | 1,865.5 | +3.9 % |
| Squares 10 m | 1,839.2 | 1,779.1 | -1.0 % |
| Centres 10 m | 1,899.5 | 1,839.2 | +2.4 % |
| Squares 5 m | 1,866.8 | **1,796.2** | 0 |

[Certain, measured] The fix moves nothing by more than a per cent: the straight gorge 5.30 to 5.33 m on every mesh,
the converged Faydh peak 1,796.2 m3/s (3.8 % under the strips sum's), the centre mesh at 20 m +3.9 % over the 5 m
squares (+4.6 % with the strips sum).

## The flume test (`flume_test/`, his go on the download; sources in `flume_test/data_sources.md`)

Open measured data, transcribed and checked by script: Lansford and Mitchell 1949 (University of Illinois Engineering
Experiment Station Bulletin 381), a 5 ft rectangular flume at S0 0.003 with one artificial roughness on bed and walls
(cross-section 2, wire mesh; cross-section 4, chain link with wooden strips), measured normal depth and discharge; and
Knight, Demetriou and Hamed 1984 (smooth rectangular channels 70 to 610 mm wide, the measured share of the boundary
shear on the walls), from the tables of Chlebek's 2009 Birmingham thesis. Neither is in Spada et al.'s calibration set
(the HR Wallingford flood channel series). `flume_test.py` evaluates the engine's own `_local_radius_conveyance` on each
section; `flume_tables.py` shows the engine's tables give the same at 12, 4 and 1 m cells on the Froude-scaled channel.

**One roughness on the whole perimeter, so the right law needs one n at every breadth-to-depth ratio.** The n each law
needs to carry the measured discharge at the measured depth, runs deeper than 0.24 m (the shallower runs need a higher
n under any law, the roughness elements' own low submergence):

| Lansford and Mitchell | Runs, b/h | Strips sum | Local radius | Section Manning |
|---|---|---|---|---|
| XS2, wire mesh (authors' n about 0.019) | 12, 2.7 to 6.2 | 0.0231 to 0.0276, scatter 5.6 % | **0.0190 to 0.0201, 1.5 %** | 0.0186 to 0.0196, 1.5 % |
| XS4, chain link (authors' n about 0.026) | 12, 1.8 to 4.9 | 0.0348 to 0.0444, scatter 8.1 % | **0.0270 to 0.0284, 1.4 %** | 0.0265 to 0.0278, 1.3 % |
| Depth error at the narrowest run with the widest run's n | | -10.2 / -13.4 % | **+0.6 / +2.1 %** | +0.1 / +1.6 % |

All runs (22 and 14, down to 0.06 m deep): scatter 6.6 / 7.9 % for the strips sum, 3.6 / 6.3 % for the local radius.

**The walls' share of the shear, smooth channels, b/h 0.31 to 19 (25 runs):** measured 6.9 to 85.2 %. The local
radius, on its own premise that the bed under a pixel carries rho g R_i S0: **within 1.3 points RMS** (mean +0.9).
Section Manning, the perimeter share: 3.0 points RMS. The strips sum gives the walls nothing: 46.5 points RMS.

[Certain, measured] **The strips sum fails both tests and the local radius passes both.** In a rough rectangle the
strips sum needs n to rise 20 to 27 % as the channel narrows from b/h 6 to 2, so with one n it reads the narrow
channel 10 to 13 % shallow, the same bias W48 found on the gorge; the local radius holds n within 1.5 % and reads the
depth within about 2 %. It also puts the measured share of the shear on smooth walls, which section Manning
overstates in wide channels. [Likely] For the design question this settles the method, not the wadis: these are
flumes with one roughness all round, straight and prismatic; rock walls rougher than the bed are not tested (Al-Hamid's
rough-wall data in `flume_test/` need a wall n of their own, a lining per pixel, not run).

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
- After the table-top fix the forced ladder is the same, 222 of 223, the same case at 1.032
  (`ladder_local_radius_forced_top_fix.log`); the full suite with the switch off is in `pytest_full_switch_off_top_fix.log`.
- [Likely] On a face oblique to the flow the window reads the ground along the face's line, so a bank is seen
  flatter and farther by 1 / cos of the angle; at 0 degrees it is exact. Not measured.

## Where it stands

Built, fixed and tested on `feature/face-local-radius`, off by default, not merged. It passes the measured flume tests
the strips sum fails (one n within 1.5 % across b/h 1.8 to 6.2 in a rough rectangle; the walls' share of shear within
1.3 points on smooth ones), reads W48's gorge at 5.3 m on every mesh, and lowers Faydh 01's converged peak by 3.8 %.
It does not close the race: the centre mesh at 20 m reads +3.9 % over the converged answer, the squares -3.3 %. Not
done: rough walls on a smoother bed (Al-Hamid's data, a wall lining); the quadtree (refuses it); the dock; Bidah and
Block 2 with it on; why the aligned pair reads high in a bend. His call: make it the default, and the merges.
