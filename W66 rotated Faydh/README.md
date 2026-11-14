# W66 rotated Faydh (2026-11-14, branch `study/rotated-faydh` off `feature/fast-products` at `c299429`, not merged)

**Live, diagnosis only; no engine code changed.** W57's settling test. W57's made-up case, rain on 50 % hills running
into a 12 m channel turned 30 degrees to the grid, read the squares 18 to 23 % low at 5 to 20 m (11 % at 2 m), while
the aligned cells were within 1 %. Does that bias show on real ground? Here Faydh 01's own race job is turned 30
degrees and compared with the unturned runs at the dam axis.

## Verdict

[Certain, measured] **The finding does not hold on Faydh at anything like its synthetic size.** Turning the catchment
30 degrees moves the squares' dam-axis peak by -3.0 % at 20 m and -0.9 % at 10 m. It moves the aligned centre mesh by
-1.75 % and -0.95 %. At 10 m the two meshes move alike, so what is left is the noise of the turn itself (bilinear
resampling of the 0.5 m ground and a new lattice phase), not a bias of the squares. The gap between the meshes does
not change with the turn: centres over squares +3.05 % unturned and +3.01 % turned at 10 m, +7.0 % and +8.4 % at 20 m.
Only the 20 m squares sit at the edge of the 3 % trigger the brief set, and the aligned mesh moves by more than half
as much there too. The 5 m squares were not run, because 20 and 10 m settle the question.

[Certain, geometry] **The turn is a weaker test on Faydh than it was on the synthetic, and this changes how the result
reads.** Faydh's thalwegs already lie at every angle to the grid: weighted by length, they sit 21.9 degrees off the
nearest grid axis unturned and 23.3 degrees turned, where a fully random spread gives 22.5. Only 22 % and 21 % of the
length lies within 10 degrees of an axis (`thalweg_angles.json`; stems over 30 km2 give the same). Turning the ground
therefore does not make the network more oblique. It shows whether the answer depends on the orientation, and it
barely does. A bias on oblique channels would already be inside the unturned squares, so the bound on it comes from a
different place. W56's 5 m squares and 5 m centres agree within 0.6 % on this network, which is about 78 % oblique. On
W57's turned valley the same pair of meshes differed by about 17 % (squares -18.2 %, centres -1.1 %). [Likely] So on
Faydh the W57 mechanism is worth at most a few per cent. It is of the size of the squares' own coarse-cell deficit
(-3.3 % at 20 m, -1.0 % at 10 m against the 5 m squares) and goes the same way. It is nowhere near 20 %.

**What it means for square-mesh design flows.** [Likely] On ground like Faydh (a wadi network whose channels wander
at every angle and are wider than a 12 m bed at flood), rain-on-grid design peaks on 10 m squares stand within about
1 to 2 % of the aligned mesh's after allowing for the turn, and within about 1 % of the 5 m answer. 20 m squares read
3 to 6 % low, depending on which converged figure is taken. The 18 to 23 % of W57 comes from its own construction: a
single straight narrow channel at one fixed oblique angle, which makes one coherent staircase over 8 km, under steep
bare hills. Real ground that comes close to that (a long straight incised channel at about 30 to 45 degrees to the
grid, fed laterally by steep hills) has not been tested. There a square-mesh peak should still be checked against an
aligned mesh before it is quoted.

## Peaks at the dam axis

Faydh 01 race job: rain on the grid, 163.1 mm over 24 h, 16 h simulated, n 0.05, local-radius faces. Peaks are the
largest absolute value of `series/line_axis.csv`. The unturned squares are W49 `race_faydh_top_fix` and the unturned
centres are W56. `u_sq20` and `u_ce20` reran both on this commit and reproduced them to the digit (1,737.3 and
1,859.6 m3/s).

| Mesh | Unturned (m3/s) | Turned 30 degrees (m3/s) | Change | Turned, against the unturned 5 m squares (1,796.2) |
|---|---|---|---|---|
| Squares 20 m | 1,737.3 | 1,685.9 | **-2.96 %** | -6.1 % |
| Squares 10 m | 1,779.1 | 1,762.8 | **-0.91 %** | -1.9 % |
| Centres 20 m | 1,859.6 | 1,827.1 | -1.75 % | +1.7 % |
| Centres 10 m | 1,833.3 | 1,815.9 | -0.95 % | +1.1 % |

Volume through the axis is 9.66 to 9.79 Mm3 turned and 9.70 to 9.81 unturned. Peak times are 12.21 to 12.28 h.
The turned runs keep their cells: 188,813 against 188,814 squares at 20 m, and 165,260 against 165,249 centres
(21 corridors). The rain is 10.7385 Mm3 against 10.7392 Mm3, a difference of 0.006 %. The mass error is about 2e-8.
Every run, turned or not, warns of water 9 to 15 m deep against the domain edge at the turned position of W56's spot.
The solver loop took 15 s (20 m squares), 38 s (20 m centres), 100 s (10 m squares) and 130 s (10 m centres).

## How it was turned (`rotated_faydh.py`, `rotation_check.json`)

- Centre: the domain polygon's centroid (425,466 / 2,730,797), turned 30 degrees anticlockwise. Everything with
  coordinates is turned about it: the domain polygon, the normal-depth outflow line, the `axis` and `box_mid` lines,
  and both layers of the Suggest breaklines file (`breaklines`, `thalwegs`; z and attributes kept). The storm is
  uniform, so it needs nothing.
- DEM: the 0.5 m `faydh_0p5m.tif`, with the turn written into the source transform. GDAL resamples it bilinearly to a
  north-up 0.5 m grid over the turned domain plus 300 m (20,908 x 26,388 pixels, kept out of git in `ground/`).
- Checks: the domain area is 75.5256 km2 before and after, and the axis length 882.20 m before and after. Over 100,000
  random points inside the domain the ground differs by a mean of -0.6 mm, a median of 0.09 m and a 99th percentile of
  0.59 m. That is nearest-pixel sampling on steep ground, not a shift. Along the axis the lowest ground is 177.706 m
  against 177.704 m, and the mean 226.635 m against 226.634 m.

## Files

`rotated_faydh.py` (`ground`, `check`, `build`, `run`, `report`, `angles`); `rotation_check.json`;
`rotated_peaks.json`; `thalweg_angles.json`; the jobs `runs/*.json`. The runs, cache and turned ground stay out of git.
