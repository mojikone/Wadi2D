# W48: the aligned cells' race excess, the second cause (2026-11-08, `feature/face-depth-carry`)

His go after W47's option A: hunt the cause of the race excess that the face fix left (the centre mesh +4.6 % over
the 5 m squares at 20 m, +1.7 % at 10 m, on the option A kernels), and use the aligned mesh at 10 m until it is
found. Diagnosis only: no kernel or mesher change here. Live. Also here: `speed_and_accuracy.md`, the model's speed
and accuracy as of today, asked for the same night.

## Where the water goes missing (`where_the_water_is.py`, `reach_character.py`, `thalweg_profiles.py`)

Faydh 01's main stem, 4 to 20 km, a steady 300 m3/s (W47's `depth_carry/steady` runs), every cell's water under its
final level against the 2 m squares' final surface over the same 0.5 m pixels:

- [Certain] **All of the 20 m strip's deficit (-4.5 %, 55.7 thousand m3) is in the pair of cells on the thalweg; the
  band's polygons hold the right water (-0.1 thousand m3).**
- [Certain] It is patchy along the stem: the pair's level stands 0.34 and 0.43 m low at 4 to 6 and 6 to 8 km, 0.25 m
  at 12 to 14 km, within 0.07 m elsewhere; and it is worst where the water fills under half the cell (-9.6 % of the
  water in pair cells 25 to 50 % wet, -2.9 % in cells over 75 % wet).
- [Certain] Per 2 km bin, the deficit correlates with the depth (r = -0.95) and the wet width (r = +0.82), not with
  the guide line's offset from the true thalweg (1 to 2 m, r = -0.56) nor the slope (r = -0.38).
- [Certain] On the true thalweg the squares are right in those reaches (20 m +0.07 m, 10 m +0.05 or -0.12, 5 m within
  0.04 m of the 2 m squares) and the strip is not (20 m -0.32 / -0.31 m, 10 m -0.17 / -0.26 m at 4 to 6 / 6 to 8 km).
- [Certain] The thalweg bends tightly all the way from 4 to 16 km (median radius 170 to 230 m, 58 to 70 % of the
  length under 300 m), so bends alone do not mark the bad reaches: the reaches at 8 to 12 km bend as tightly and the
  strip is right there, where the channel is 32 to 35 m wide and 2.9 to 3.2 m deep. **The deficit is where tight bends
  meet a deep channel narrower than the pair: about 20 m of water, 4.6 to 4.8 m deep, inside 40 m of cells.**
- [Certain] The flow through the gorge crosses the thalweg face heavily, a median of 25 m3/s per 20 m face (90th
  percentile 56) against 13 in the wide reaches, as the channel weaves inside the pair; each side's station faces carry
  150 m3/s at the median and up to 212.

## Reproduced on synthetic ground (`narrow_gorge.py`, `gorge_reading.py`, `probe/`)

A 12 m bed with walls rising 7 m over 1.5 m each side, a 10 m ledge, hills at 50 %, 1 % slope, 300 m3/s steady, on the
W46 probe valley; read between 1 and 8 km, the water pixel by pixel and the level 3 m either side of the axis, against
the 2 m squares (the first reading sampled the axis itself, which is the strip's thalweg face, and missed the strip's
cells; it is superseded):

| Gorge | Squares 20 m | Squares 10 m | Squares 5 m | Strip 20 m | Strip 10 m |
|---|---|---|---|---|---|
| Straight | -0.045 m, -0.9 % | -0.032 m, -0.9 % | -0.025 m, -0.9 % | **-0.009 m, -0.6 %** | -0.021 m, -0.6 % |
| Sine, radius 729 m at the bends | +0.105 m, +3.2 % | +0.028 m, +0.2 % | -0.025 m, -0.5 % | **-0.058 m, -1.0 %** | -0.079 m, -1.6 % |
| Sine, radius 243 m | **+2.251 m, +55 %** | +0.293 m, +6.7 % | +0.051 m, +1.5 % | **-0.220 m, -3.3 %** | **-0.255 m, -4.7 %** |

(level against the 2 m squares, and the water held; the 2 m squares' depth on the axis is 4.41, 4.61 and 4.81 m)

[Certain, measured] **The strip is right in a straight deep narrow gorge and stands low in a bending one, more as the
bends tighten (-0.01, -0.06, -0.22 m), and refining from 20 to 10 m does not help.** [Certain] The strip has exactly
two cells across the gorge at 20 m and at 10 m alike (the pair; the bank rule stops the rows at the walls), and at
5 m too, so refining along the flow never adds cells across this channel. [Certain] The squares on the same tight bends
go the other way and much further at 20 m (+2.25 m: the staircase chokes a narrow sinuous channel), while on Faydh's
own gorge they were right; Faydh's gorge is gentler or wider than this synthetic one where it matters.

[Likely] **The second cause: a channel narrower than the pair of aligned cells, through tight bends, conveys too
easily; with two cells across, and the water filling only part of each, the cross-channel redistribution of velocity
in a bend that the fine squares resolve (and that adds resistance in depth-averaged 2D) is not represented.** What in
the polygon kernel makes the pair under-dissipate (the momentum advection on two curved cells, the cell velocity from
faces that the water only partly wets, the friction's transverse velocity) is not yet isolated; each is a kernel-side
test, and by his rule of today a kernel change waits for a research pass and his go.

## Against HEC-RAS (`ras_gorge.py`, `ras/`, `ras_narrow/`; his question: is the aligned mesh perhaps right and the squares wrong?)

The same two gorges in HEC-RAS 6.6, SWE-EM, n 0.05, written as text with seed points and run headless: 5 m squares,
20 m squares, and 20 m and 10 m cells aligned on the thalweg the way a HEC-RAS breakline makes them (seeds mirrored at
half a cell either side of the centreline every cell along it, the lattice beyond 1.5 cells); the gorge with 60 m
either side, a flow hydrograph across the upstream end and normal depth downstream, 300 m3/s ramped over an hour,
5 h. Volume errors under 0.0001 %. Depth on the axis, read 3 m either side of it, 1 to 8 km:

| Mesh | HEC-RAS, straight | HEC-RAS, tight sine | Wadi2D, straight | Wadi2D, tight sine |
|---|---|---|---|---|
| Squares, 2 m | | | 4.407 | 4.806 |
| Squares, 5 m | **4.698** | **5.319** | 4.382 | 4.843 |
| Squares, 20 m | 5.276 | 4.974 | 4.383 | 7.082 |
| Aligned, 20 m | 5.273 | 5.287 | 4.407 | 4.569 |
| Aligned, 10 m | | 5.347 | 4.408 | 4.532 |

Normal depth of the straight section: 4.398 m by the face sum Wadi2D uses, 5.392 m by Manning on the hydraulic radius
with the walls in the wetted perimeter.

[Certain, measured] Four things:

1. **The two solvers' friction differs in a narrow deep channel, and HEC-RAS's depends on the cell size.** Wadi2D
   reads a face's conveyance as a sum over the pixels across it, with no shear on the walls: the straight gorge reads
   4.38 to 4.41 m at every size, the face-sum normal depth (4.398 m). HEC-RAS reads each face's hydraulic radius from
   its own profile, walls in the wetted perimeter: one 20 m face spanning the gorge gives 5.28 m, close to Manning on
   the whole section's hydraulic radius (5.39 m); at 5 m the section is cut into faces that mostly see the bed, 4.70 m.
   That is 0.58 m, 12 % of the depth, between HEC-RAS's own 20 m and 5 m on a straight channel.
2. **Bends add resistance in both, and neither 20 m mesh captures it.** From straight to the tight sine the fine meshes
   rise 0.40 m (Wadi2D, 2 m) and 0.62 m (HEC-RAS, 5 m); the aligned 20 m meshes rise 0.16 m (Wadi2D) and 0.02 m
   (HEC-RAS). Two cells across a narrow bending channel miss most of it in either solver: **the bend deficit is the
   construction's, not a Wadi2D kernel fault.**
3. **HEC-RAS's aligned 20 m mesh matches its 5 m mesh on the sine (-0.02 m) by two errors cancelling:** the coarse
   face's wall friction (+0.58 m on the straight) against the missing bend resistance (-0.60 m). On the straight it
   stands 0.57 m above its own 5 m answer.
4. **His point holds for the squares:** at 20 m in a tight narrow bend the squares are the worse mesh in both solvers,
   Wadi2D +2.28 m above its converged answer (the staircase chokes the channel), HEC-RAS -0.35 m below its own; the
   aligned cells are within 0.24 m (Wadi2D) and 0.03 m (HEC-RAS). Neither 20 m mesh is the right answer, and the
   aligned one is the nearer.

[Likely] What this leaves: the aligned mesh at 20 m is the better 20 m mesh in narrow gorges, and its remaining error
there is the bends' resistance that two cells across cannot carry, in any solver; a cure is more cells across the
channel, a mesher matter. Separately, Wadi2D carries no wall shear in a narrow deep channel, which is the sub-grid
literature's choice (the face sum, Volp et al.'s friction depth) and not HEC-RAS's; how much wall shear a
depth-averaged model should carry, and whether HEC-RAS's cell-size dependence is the price of carrying it, is a
research question for before any change.

**The HEC-RAS 2.5 m run (`ras_narrow/ras_sq2p5`, `ras_narrow_2p5.log`, 155,400 cells, 1 h 48 min), added the same
night:** the straight gorge reads **4.724 m**, +0.029 m and +0.37 % water over HEC-RAS's own 5 m mesh. [Certain,
measured] HEC-RAS settles near 4.7 m below 5 m cells; it does not fall toward the face sum (4.40 m). The emulation of
its per-face rule predicted 4.46 to 4.69 m at 2 m faces, so by the test the wall-shear report set itself before the
run, something beyond the per-face hydraulic radius holds HEC-RAS up (eddy viscosity in SWE-EM or a wall treatment
the emulation omits, [Guessing] which), and the reading of its extra depth as a coarse-face artefact is withdrawn for
the fine end. Its 20 m answer (5.28 m) still carries the coarse-face lumping, 0.55 m over its converged one. The
literature's estimate of the physical depth, about 5.3 m, is unchanged by this run: HEC-RAS converged reads about
11 % under it, Wadi2D's strips sum 17 %. W49 built the local hydraulic radius that the report recommended.

## Found on the way

1. [Certain] **The centre mesh at 5 m is broken**: on the tight synthetic gorge it holds 59 % more water than the 2 m
   squares (+0.65 m), 24 % on the gentle one; on Faydh's reach the tiling guard refused it (233 m2 of 660,625). A
   mesher defect at 5 m, not yet looked at; the generator is not usable below 10 m until it is.
2. [Certain] Sampling a strip on its own guide line hits the thalweg face, not a cell: every strip reading must sit
   off the line (the first gorge report read the masked squares and gave -1.1 m).

## What this means for use

- [Certain] At 10 m the aligned mesh is within 1.7 % of the converged peak on Faydh, the squares within 1.5 %: use 10 m
  for design lines, either mesh.
- [Likely] At 20 m the aligned mesh is not trustworthy where a deep channel narrower than two cells bends tightly; the
  W45 ring corridors (cells a quarter of the width, on bank pairs, so none in the narrow gorge) read -0.6 % on the
  race on the option A kernels, which fits.

## Not done

The kernel-side isolation is no longer the lead: HEC-RAS shows the same bend deficit with two cells across. Next, his call: more cells across a narrow channel in the mesher, and a research pass on wall shear in sub-grid conveyance; the 5 m mesher
defect; whether more cells across a narrow channel (narrower rows than the along spacing) cures it, which is a mesher
change; the HEC-RAS 6.6 face-level probe of W47.
