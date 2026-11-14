# W57 made-up cases for the race excess (2026-11-14, branch `study/race-synthetic` off `7f2fb3e`, not merged)

**Live, diagnosis only; no engine code changed.** The Faydh 01 race (rain on the grid, peak at the dam axis) reads
the aligned centre mesh +3.5 % at 20 m and about +2 % at 10 m over the 5 m squares (1,796.2 m3/s), the 20 m squares
-3.3 %. The steady gorges of W48 and W52 do not reproduce it. Here made-up unsteady cases, cheapest first, each on
squares 20, 10, 5, 2 m and the centre mesh (`strips.generator: centres`) 30, 20, 10, 5 m, with the engine's defaults
at `7f2fb3e` (local radius, face depth carry, centroid fix, no gorge rows), GPU. Ground: W48's narrow gorge (12 m
bed, walls 7 m over 1.5 m, a 10 m ledge at 5 %, hills at 50 %, 1 % along, n 0.05) in an 8.4 by 1 km valley, straight
on the lattice, on the tight sine (radius 243 m) or turned 30 degrees; peaks read across the whole valley 7.5 km down
(`s3`), and 1.5 and 4.5 km down (`s1`, `s2`).

## Headline

[Certain, measured] **Rain on the grid gathering into a narrow channel that is not on the lattice is where the meshes
part, and there the squares are the wrong mesh, not the aligned cells.** On the straight valley turned 30 degrees,
whose true answer is the same valley's on the lattice (every mesh agrees there within 0.4 %), the aligned cells read
the outlet peak -1.0, -0.1 and -1.2 % at 20, 10 and 5 m; the squares read -20, -23, -18 and **-11 % at 2 m**. The
same channel carrying an inflow wave of the same size with no rain, the 5 m squares are right (+0.2 %). On the
sinuous valley under rain the aligned cells read the same peak at every size (96 to 100 m3/s) while the squares climb
with refinement without settling (77, 81, 86, 92 m3/s at 20, 10, 5, 2 m): against the 2 m squares the aligned mesh
reads +5 to +9 %, the race's pattern (centres above and flat, squares below and rising) at two to three times its
size.

[Likely] So the race's excess is most probably the yardstick's deficit: 5 m squares are not a converged answer where
rain gathers into channels a few cells wide that run oblique to the lattice, and the aligned mesh's +2 to +3.5 % is
nearer the truth than the squares. Not proven on Faydh; the decisive test there is the Faydh DEM turned 30 degrees,
rerun on the 5 m squares and the 20 and 10 m centres (the physics does not change; a mesh whose answer moves is the
wrong one).

The other three cases do not reproduce an excess: a Faydh-sized flash flood down the tight-bend gorge, a tributary
junction at 45 and 90 degrees, and a gorge opening into a 300 m plain all read the aligned mesh within -0.7 to +1.1 %
of the 2 m squares at 30 to 10 m.

## Case 1: a flash flood down the tight-sine gorge (`wave`)

50 -> 2,000 -> 50 m3/s, 40 min up, 80 min down, no rain; the flow overtops the walls onto the ledge and hills.

| Mesh | s3 peak, against 2 m squares (1,892.2 m3/s) | Peak time | Reach storage at its peak, s1 to s3 |
|---|---|---|---|
| Squares 20 / 10 / 5 m | -1.50 / -1.21 / -0.39 % | +1.9 / +1.3 / +1.1 min | +7.3 / +3.5 / +2.1 % |
| Centres 30 / 20 / 10 / 5 m | -0.10 / -0.72 / -0.07 / **-2.64** % | -0.1 / +1.9 / +1.3 / +5.6 min | +1.3 / +2.2 / -0.4 / +5.5 % |

No excess. The 5 m centre mesh reads 2.6 % low and 5.6 min late with 5.5 % more water in the reach, the same sign
as W52's +1.5 % water on the steady sine; it recurs at the junctions' outlet (below). Not chased: it is small and the
5 m centre mesh is not a design mesh.

## Case 3: rain on the grid (`rain`, `rain_straight`, `rain_rot30`)

70 mm in 4 h with 30 mm in 20 min after hour 2 (W46's storm), on the whole valley, hills included, no losses, as the
race has.

| Mesh | Tight sine, against 2 m squares (91.5 m3/s) | Straight on the lattice, against 2 m squares (112.3) | Straight turned 30 degrees, against the truth (112.3) |
|---|---|---|---|
| Squares 20 m | -15.9 % | -0.3 % | -20.4 % |
| Squares 10 m | -11.7 % | -0.3 % | -22.7 % |
| Squares 5 m | -6.2 % | -0.3 % | -18.2 % |
| Squares 2 m | reference | reference | **-11.0 %** |
| Centres 30 m | +5.2 % | | |
| Centres 20 m | +7.9 % | -0.4 % | -1.0 % |
| Centres 10 m | +8.9 % | -0.3 % | -0.1 % |
| Centres 5 m | +8.0 % | | -1.1 % |

Volumes through s3 agree within 1.4 % everywhere (the 20 m squares on the sine 3.2 % short); the peaks differ in
attenuation and timing (centres 4 to 8 min earlier than the 2 m squares on the sine and the turned valley, the squares
up to 21 min later). The turned valley's 20 m centres and squares cost 11 and 4 s of solver, its 2 m squares 374 s.

Where the squares lose it (`wave_low*`, `split_*`, `rotated_vs_true.json`, `split_vs_true.json`):

| Test, turned valley against the same on the lattice | Squares 5 m | Squares 20 m | Centres 20 m |
|---|---|---|---|
| Inflow wave 2 -> 100 -> 2 m3/s, no rain, s3 | +0.2 % | +30.8 % (surges past its inflow) | +1.5 % |
| Rain only beyond 30 m of the axis (the hills), s3 | -17.6 % | | -0.1 % |
| Rain only within 30 m (bed, walls, ledge), s3 | -4.7 % of 3.2 m3/s | | -15.5 % of 3.2 m3/s |

On the sine the same inflow wave routes alike on centres and 5 m squares (+0.3 %; both +2.3 to +2.8 % over the 2 m
squares). [Certain] The squares route a flood that enters the channel as a wave correctly at 5 m and lose 18 % of the
peak when the same order of flow is fed from the hills along an oblique channel; at `s1`, 1.5 km down, they are right
(+0.3 %) and the deficit grows downstream (-12 % at 4.5 km, -18 % at 7.5 km). [Likely] The mechanism is the staircase
of a narrow oblique channel slowing shallow, laterally fed channel flow (the reach upstream of the peak's water is
shallow, where the inflow wave keeps it deep), so the hills' contributions arrive out of step and the peak attenuates;
whether the loss sits in the hill-to-channel entry or in the shallow channel itself is not separated. The rain falling
on the channel itself is a trickle and does not matter. The 20 m squares surging past the inflow peak on the turned
channel is a separate defect, recorded only.

## Case 2: a tributary gorge joining at 45 and 90 degrees (`junction45`, `junction90`)

A straight main gorge 5 km long at 1 %, turned 30 degrees off the lattice, a tributary 1.5 km at 2 % joining
half-way, the narrow section on both; the main as two D8-style segments (44 and 74 km2), the tributary 30 km2, so the
generator chains the main and stops the tributary short (two cells across on both, 4 to 5 stations given up near the
junction). Inflows 0.6 and 0.4 of case 1's flood, peaking together.

| Mesh | 45 degrees, 700 m below the junction | 45, outlet | 90 degrees, 700 m below | 90, outlet |
|---|---|---|---|---|
| Squares 20 / 10 / 5 m | -0.38 / -0.36 / -0.30 % | -2.4 / -2.6 / -2.6 % | -0.55 / -0.67 / -0.50 % | -1.9 / -2.3 / -2.1 % |
| Centres 30 / 20 / 10 / 5 m | +0.43 / +0.69 / +0.74 / +0.85 % | -1.6 / -1.6 / -2.0 / -3.5 % | +0.23 / +0.53 / +1.09 / +0.74 % | -1.0 / -1.3 / -1.5 / -3.0 % |

Against the 2 m squares (outlet 1,949.3 and 1,939.9 m3/s). No excess at the junction. At the outlet line, 300 m above
the normal-depth boundary, every mesh reads 1 to 3.5 % below the 2 m squares, so that is the 2 m run's own reading
there, not a mesh effect [Likely]. The water stood 5.9 m deep against the tributary's head edge, upstream of its
inflow (the engine's warning), on every mesh.

## Case 4: the gorge opening into a plain and narrowing again (`plain`)

The gentle sine (radius 729 m), the bed widening from 12 to 300 m over 300 m from 3 km down, 300 m wide for 1.4 km
with a 0.5 % fall to its middle, narrowing back; case 1's flood. The centre mesh puts up to 14 rows of 20 m across the
plain's floor.

| Mesh | s3 (gorge, 2.4 km below the plain), against 2 m squares (1,494.7 m3/s) | s2 (mid-plain) |
|---|---|---|
| Squares 20 / 10 / 5 m | -0.22 / -0.27 / -0.17 % | -0.03 / -0.25 / -0.14 % |
| Centres 30 / 20 / 10 / 5 m | -0.47 / +0.93 / -0.09 / -0.86 % | -0.34 / **+5.41** / -0.09 / -0.71 % |

No excess at the outlet. The 20 m centres read 5.4 % high on the line across the middle of the plain and not at 30
or 10 m, a local reading of the fanned rows, not chased.

## What this means for the race

- The cases that carry a flood into the channel as a hydrograph (1, 2, 4) route alike on both meshes; the excess
  needs rain gathering along the channel (3), as W46's split of Faydh found.
- Under rain the aligned cells are self-consistent at every size and right on the turned straight valley; the squares
  are biased low on oblique narrow channels and converge slowly or not at all (-11 % still at 2 m on a 12 m bed).
- So the race's "+3.5 % over the converged peak" uses a 5 m squares yardstick that this mechanism biases low, by an
  amount that depends on how much of Faydh's peak comes down narrow oblique channels; the squares' own rise from 20
  to 5 m on Faydh (-3.3 % to 0) is the same signature. [Likely] the aligned mesh is the better answer, not the worse.
- Next, his call: Faydh turned 30 degrees on the 5 m squares and the 20 and 10 m centres (two of the three runs are
  minutes; the 5 m squares as long as the race's own). Until then neither mesh's Faydh number is a converged answer.

## Run time and failures

71 runs, 74.8 min of solver and tables on the shared GPU (the 2 m squares under rain 6 to 15 min each). No driver
crash, no failed run; three rotated-inflow runs first failed on a wrong ground path in the script (fixed, rerun).

## Files

Scripts (in git): `race_cases.py` (cases, jobs, runs, reading), `ground.py` (the junction, plain and turned grounds,
the rain split grids), `score_rotated.py`, `score_split.py`. Results: `<case>.json` (per-mesh peaks, times, volumes,
steps), `rotated_vs_true.json`, `split_vs_true.json`, `ground_check.png`. Runs, caches and grounds (`runs/`, `cache/`,
`ground/`, 3.5 GB) stay out of git. The W48/W49 grounds are read from the main checkout.
