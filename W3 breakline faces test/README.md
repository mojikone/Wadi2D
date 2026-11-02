# W3 breakline faces test

Status: finished 2026-11-01. Question: are grid faces aligned to breaklines worth building? Stand-alone CPU prototype, float64, Numba. Nothing here
touches `wadi2d/`, `plugin/`, `tests/` or `W2 full extent run/`. Nothing committed, nothing pushed, GPU never used.

**Answer: not yet. A 9-line kernel fix removes most of the defect aligned faces were meant to cure.** Details and limits below. Every figure comes from
the final code state; raw output is in `results/`.

## Pass mark (fixed before option b was run; not to be changed)

Written 2026-11-01 before any option other than the baseline had been run. All four must hold, for an option, in the case
**vertical walls, 3 cells wide, 45 degrees**:

| Item | Limit |
|---|---|
| Normal-depth error | within 3 % of Manning normal depth |
| Still water | exact (stays still to round-off) |
| Time step | no worse than 0.7 x baseline |
| Cost per cell-step | no more than 1.5 x baseline |

The baseline must first reproduce the recorded numbers (45 degrees: vertical walls +11 % at 3 cells, +2 % at 6; 2:1 banks +2.0 % and +0.8 %;
30 degrees +4 to 5 %) within a small margin, or nothing else here is believed.

## 1. The premise was out of date, in three ways

**+11 % is an old kernel.** [Certain] `W1 .../prototypes/channel_scan.py` run verbatim on the production CPU twin, read-only, kernels extracted per commit:

| Commit | 45 deg vertical 1.5 / 3 / 6 cells | 2:1 banks 3 / 6 cells |
|---|---|---|
| 35ad921 (first solver core) | +27.85 / **+11.09 / +1.91** | **+2.04 / +0.83** |
| 3f32ca6 | +7.77 / +2.20 / +0.99 | +1.94 / +0.85 |
| eb8583a (today) | +8.03 / **+2.01 / +0.99** | +1.94 / +0.85 |

The design note's "final code" row and decision 19 quote 35ad921 for vertical walls. Commit 3f32ca6 changed the section blend (`min(edown/eup, 1)` to `min/max`), and that removed most of it. **W1 `design_note.md` section 3 and `CLAUDE.md` decision 19 need correcting; not done here, as instructed.**

**+2 % is a lucky phase.** [Certain] `channel_scan` only ever ran one lateral position. Today's code, 45 degrees, vertical, 3 cells, error against Manning by offset of the axis:

| Offset, m | 0 | 2.5 | 5 | 7.5 | 10 | 12.5 | 15 | 17.5 |
|---|---|---|---|---|---|---|---|---|
| Today | +1.84 | +7.99 | +7.06 | +6.83 | +7.13 | +7.56 | +2.17 | +7.16 |

The small values are where the walls run near lattice diagonals. The real 45 degree defect is **+7 to +8 %**, and about +3.5 % at 6 cells.

**The reference flatters the case.** [Certain] Manning here uses the wetted perimeter; sub-grid strip conveyance has no wall friction, so the aligned channel reads -2.96 %. Against a strip reference (`err_strip`, no wall friction, what the solver should converge to) every 3-cell figure reads about 1.1 points higher, and the aligned channel still reads -1.9 %. The pass mark was not changed; both are reported.

Also: at 0 degrees `channel_scan` reads +265 %, because its outlet lies beyond the active domain (grid padded to 160, cells 1 to 128 active). Its 0 degree line was never valid. This folder uses a centred 128 x 128 domain.

**Baseline check.** The port matches the twin on the identical domain within 0.12 points (+2.13 / +2.01, +1.93 / +1.94, +0.99 / +0.99, +0.85 / +0.85, +4.43 / +4.54, +4.15 / +4.15), matches the recorded banks and 30 degrees, and on the real fan matches the frozen GPU run to 0.01 cm. It does not reproduce +11 %, because that is not today's kernel. Noise floor on vertical walls about 0.1 point. Steady by 3,000 s (`results/probe_steady.txt`).

## 2. What actually causes the defect

Measured on the live kernel (`results/probe_terms.txt`, `probe_fix.txt`). It is not grid alignment:

1. **A dry or closed neighbour face is advected as if its u = 0 were a velocity.** Water arriving beside a blocked face brings zero momentum, a sink at every stair. Fixing only this: 30 degrees +4.35 to -0.36 %, 45 degrees at a generic phase +7.06 to -0.23 %.
2. **The sheet-flow section misfires on deep cut cells.** `Avol = hup dx` reads a half-wet deep cell as thin. This is the residual at exact-diagonal phases.

Directional conveyance does nothing (+8.19 stays +8.19): the defect is not a distance metric.

## 3. Options

Each at 0, 15, 22.5, 30, 45 degrees, 3, 6, 12 cells, vertical and 2:1, lateral offsets 0, 5, 10 m, plus 5 more offsets at 45 degrees and at 15 to 30 degrees: 1,035 runs, none failed. Settings were fixed from `probe_variants` and `probe_v2` before the matrix.

| Name | What |
|---|---|
| a | Today's lattice, port of production |
| m | Fix 1: a neighbour face with u exactly 0 gives the current face's velocity. Reads nothing new |
| ms3 | m plus section volume over the wet plan, `hup/om dx` |
| dir | Directional conveyance folded into the tables |
| P | Lattice kept, advection by cell vectors (Perot): V U = sum (xf - c) Q; a wall carries no Q, so sinks no momentum. Momentum first order here |
| b | Lattice vertices moved onto the line, logical grid kept, skew-corrected gradient, Perot advection |
| c | Cut cells: two bodies per crossed cell, two parts per crossed face, an internal face on the chord |
| t20, t26 | Conforming Delaunay triangles on circumcentres, vertex spacing 20 m, and 26.3 m for equal face count |

### Pass mark, as written: vertical, 3 cells, 45 degrees

Still water exact for all: largest speed at or below 2e-15 m/s on aligned meshes, 1e-14 on the lattice, rough bed at 1,500 m. Cost is per cell-step on one CPU thread, all cells wet.

| Option | Error vs Manning, recorded phase | Range over 8 phases | dt / a | Cost | Verdict |
|---|---|---|---|---|---|
| a | +1.84 | +1.84 to +7.99 | 1.00 | 1.00 | Passes the recorded phase only; fails 6 of 8 |
| m | +2.58 | -0.82 to **+3.16** | 0.99 to 1.00 | 1.02 | Passes 7 of 8; misses by 0.16 at one phase |
| ms3 | -2.44 | -2.44 to +1.74 | 0.99 to 1.00 | 1.02 | Passes the mark; **disqualified, section 7** |
| dir | +1.63 | +1.63 to +7.99 | 1.00 | 1.00 | Fails as a |
| P | -0.31 | -2.82 to +0.27 | 0.99 to 1.00 | 1.04 | **Passes all** |
| b | -2.71 | -2.72 to -1.03 | 1.28 to 1.70 | 0.91 | **Passes all**, but see banks and bends |
| c | +2.84 | -0.82 to **+3.80** | 0.81 to 0.85 | 1.00 per lattice cell | Passes 7 of 8 |
| t20 | -1.79 | -1.83 to -1.07 | **0.68** to 1.10 | 0.88 per triangle | Misses dt by 0.02 at its worst phase |
| t26 | -2.22 | -2.26 to -1.48 | 1.17 to 1.81 | 0.81 per triangle | **Passes all** |

### Everything else

| Option | Runs over 3 % vs Manning (of 115) | Largest strip error, 90 runs | Largest Q error, % | dt / a median, worst | Extra memory, bytes per cell (a = 444) |
|---|---|---|---|---|---|
| a | 27 | 8.45 | 0.74 | 1.00, 1.00 | 0 |
| m | 4 | 3.66 | 0.71 | 0.99, 0.85 | 0 |
| ms3 | 3 | 2.31 | 0.56 | 0.93, 0.61 | 0 |
| dir | 27 | 8.45 | 0.90 | 1.00, 0.99 | 0 |
| P | 0 | 1.97 | 2.13 | 1.00, 0.95 | 16, work only |
| b | 3 | 30.26 | 13.60 | 0.95, 0.18 | 124, in tiles holding a line |
| c | 3 | 4.89 | 0.72 | 0.70, 0.34 | 568, in tiles holding a line, as a second layer |
| t20 | 0 | 1.09 | 0.10 | 0.62, 0.28 | about 490, cell count 2.16 x |
| t26 | 0 | 1.38 | 0.11 | 0.83, 0.37 | about 80, cell count 1.21 x |

Of m's 4 misses, 2 are the aligned channel at -3.1 and -3.3 %, the wall-friction offset, which the baseline shares; ms3's 3 are the same thing. The other 2 for m are 45 degrees, 3 cells: vertical +3.16, banks +5.50.

Option b on 2:1 banks at 45 degrees, 3 cells: **an oscillation, up to +29 % with Q off by 22 %**, at 3 of 8 phases, dt 0.18 to 0.55 x a. The toe face is fully wet on a thin wet wedge of bank cell. A lower CFL did not cure it, and smoothing only moved it. On vertical walls b is excellent.

Dry bank behind a line, 30 and 45 degrees, offsets 0 and 5: **far side exactly dry in all 28 runs**. Overtopping 0.3 m against ideal critical flow per true metre: 0.93 to 1.02 for all. Today's staircase reads 0.93 at 45 degrees; aligned options 0.98 to 1.02. P was not run here: it has no crest object in this prototype and would use today's.

Non-orthogonality in b: skew up to 45 degrees at 45, 58 at 30. Handled by the gradient correction; without it the error reaches +6 %.

Time step: on vertical walls b and t26 beat the baseline, because a wall-fitted cell has no slivers and the baseline's slivers set its step.

## 4. Alignment, proved

`run_alignment.py`, `results/alignment.csv`. Largest distance from any point of the line (0.5 m samples) to the nearest cell edge; cells with the line through them; shape of cells within 1.1 dx of the line. Bends and junctions start 7 and 11 degrees off the lattice, so no reach is aligned by luck. Worst of each group, no smoothing unless stated:

| Group | Option | Distance, m | Straddled cells | Inverted | Smallest angle | Largest angle | Smallest cell, dx2 | Longest / shortest edge | Vertex conflicts |
|---|---|---|---|---|---|---|---|---|---|
| Straight | a | 10.0 | 143 | 0 | 90 | 90 | 1.00 | 1.0 | 0 |
| Straight | b | **0.00** | 0 | 0 | 8.2 | **180** | 0.085 | 6.4 | 0 |
| Straight | b, 8 smoothing passes | 0.00 | 0 | 0 | 26.8 | 180 | 0.30 | 4.8 | 0 |
| Straight | t20 | 0.00 | 0 | 0 | 39.5 | 80 | 0.30 | 1.5 | 0 |
| Bend under 135 | b | 0.00 | 0 | 0 | 18.2 | 180 | 0.18 | 11.1 | 0 |
| Bend 135 to 165 | b | **8.9 failed** | 3 | 0 | 18.2 | 180 | 0.18 | 11.1 | 0 |
| Bend 15 to 165 | t20 | 0.00 | 0 | 0 | 14.1 | 113 | 0.13 | 4.1 | 0 |
| Junction 45 to 90 | b | **10.6 failed** | 1 | 0 | 12.0 | 180 | 0.12 | 7.9 | 3 |
| Junction 10 to 30 | b | **11.1 failed** | 8 | **1** | 6.7 | 207 | 0.07 | 10.1 | 7 |
| Junction 10 to 90 | t20 | 0.00 | 0 | 0 | 9.7 | 113 | 0.09 | 5.9 | 0 |

[Certain, topology] A straight line at any angle other than 0 or 90 is a staircase in logical coordinates, so each stair corner becomes a 180 degree vertex: **those quads are triangles**. Option b cannot have a good cell there, only a less bad one. Two lines needing one vertex is the junction failure, and smoothing cannot remove it.

Cut cells: the internal face is the chord, so distance is 0 by construction while a cell holds two bodies, and a bend inside a cell is two chords. Junctions need three bodies in 1 to 4 cells of each case, which a two-layer tile cannot hold: **failure at every junction tested**. Smallest body 0.0075 dx2 at 45 degrees. Folding small bodies into a neighbour broke one phase (+10.6 %).

Bent channel at 30, 60, 90, 135 degree deflection, reaches off the lattice, reference 5 m lattice with m (`results/bent.txt`). All options stable. Upstream depth within 2 cm of the reference for all. Downstream reach at 135 degrees: a +5.83 %, m -0.35, P -1.78, b -1.48, c +0.28, t20 -1.74, t26 -2.16. The baseline at 5 m, 12 cells across, still reads +3.39 % there, so **refinement does not cure this defect and the fix does**. At 90 degrees: a -3.31, m -3.62, t20 -1.60.

## 5. Triangles at equal spacing and equal face count

scipy has unconstrained Delaunay only and nothing was installed, so `meshes_poly.py` builds the point set: each line at h, an offset row each side, background relaxed, close points dropped, any missing segment split. 0 unresolved segments. Band of the 45 degree, 3 cell case, against the lattice's 2,578 cells and 4,900 faces:

| | Cells | Faces | dt / a median, worst, pass case | Cost per cell | Cost per step, same area | Cost per unit area and time, median, worst | Largest strip error |
|---|---|---|---|---|---|---|---|
| t20, equal spacing | 5,575 | 8,132 | 0.62, 0.28, 0.68 to 1.10 | 0.88 | 1.79 | **2.9 x, 6.4 x** | 1.09 % |
| t26, equal faces | 3,116 | 4,498 | 0.83, 0.37, 1.17 to 1.81 | 0.81 | 0.93 | **1.1 x, 2.5 x** | 1.38 % |

For scale, other options per unit area and time, median: m 1.03, ms3 1.10, P 1.04, b 0.96, c 1.43.

A real mesher (Triangle, Gmsh) is not installed and should improve the worst cases. On banks the thin wet wedges cost dt here too: 0.28 to 0.57 at t20.

**Share replaced:** all 334 GPU kernel lines, the 289-line CPU twin, the tile layout, halos and active-tile list, `state.py`, `grid/`, the table builder and every parity test. Indirect neighbour lists everywhere, which is what decision 4 refused. Results stop being rasters without a resampling step. Momentum here is first order; second order on triangles is not written. Decision 4's 2 to 4 x slower per cell on a GPU is not contradicted: this bench cannot see it.

## 6. Fit to the code

| Option | 32 x 32 tiles, no indirect lists | GPU kernel change (334 lines) | Other |
|---|---|---|---|
| m | Yes | About 9 lines, 3 %, `faces.cu` section 3 | CPU twin |
| ms3 | Yes | About 10 lines | Twin; `om` read every step |
| dir | Yes | None | Table builder; no benefit |
| P | Yes | New cell pass about 60 lines; section 3 replaced, about 25 % | Second-order form to write |
| b | Yes, fixed offsets; metric arrays in flagged tiles | About half; new gradient pass; every `dx` becomes per-face | Table builder rewritten for slanted faces and quads |
| c | No list, but a second layer per flagged tile and a per-face layer bit, or else a sparse list | About 70 % | Table builder rewritten; 3 bodies not representable |
| t20, t26 | **No** | 100 % | Section 5 |

## 7. Does the fix hurt anything?

| Case | a | m | ms3 |
|---|---|---|---|
| Ritter L1 / h0 | 0.00288 | 0.00287 | not run |
| Stoker L1 / h0, plateau (2.207 m) | 0.00194, 2.206 | 0.00188, 2.206 | not run |
| Rain on 5 % plane, storage over kinematic wave | 1.0216 | 1.0216 | **0.054, broken** |
| Synthetic valley 20 m, peak m3/s, wadi depth m | 26.588, 0.2527 | 26.588, 0.2527 | not run |
| **Real fan 10 m, against HEC-RAS 6.6: level mean, rms, F** | +2.50, 5.73 cm, 0.956 | +2.48, **5.44 cm**, 0.955 | +1.74, 4.90 cm, **0.938** |
| Same, 20 m | +7.23, 11.47 cm, 0.956 | +7.16, 11.48 cm, 0.956 | +4.07, 8.45 cm, **0.925** |

Frozen GPU run on the same scoring: +2.49, 5.81, 0.957 at 10 m; +7.24, 11.47, 0.954 at 20 m. So the port is right on real terrain. **m is safe here. ms3 is disqualified:** it holds 5 % of the correct storage on a rain plane, which undoes decision 19's sheet flow, and it costs the fan 2 to 3 points of F. Its pass in section 3 stands as a measurement and must not be read as a candidate. One cell moved 58 cm under m at 20 m; not examined. The fan was replayed with inflows at the cell under each point, on cells near the frozen wet map. The last line of `results/fan_*.txt` is a dry-cell sentinel, not a result.

## 8. Refinement by change of slope

`run_valley.py`, `run_valley2.py`. Mountain plane 12 %, slope break, plain 1 %, wadi with 2.5 m 1:1 banks and a 60 m bed, plain back up, valley fall 0.5 %, 2.2 x 2 km, rain 60 mm/h for 25 min, no losses, polygon kernel on all meshes. By change of slope: split a 40 m block while pixels leave a best-fit plane by over 0.2 m, so a tilted plane stays coarse. Quadtree 10 / 20 / 40 m, 2:1 balanced. Depths at two wadi sections.

| Mesh | Cells | Cell-steps, x ref | Total peak | Wadi peak | Peak time, h | Wadi depth at 1,000 m | At 300 m |
|---|---|---|---|---|---|---|---|
| Uniform 5 m (reference) | 176,000 | 1.000 | 26.1 m3/s | 22.3 m3/s | 0.93 | 0.210 m | 0.336 m |
| Uniform 10 m | 44,000 | 0.125 | +0.5 % | -1.9 % | 0.91 | -13 % | -7 % |
| Uniform 20 m | 11,000 | 0.019 | +0.8 % | -10.0 % | 0.87 | -26 % | -21 % |
| Uniform 40 m | 2,750 | 0.002 | +2.2 % | -16.1 % | 0.79 | -44 % | -8 % |
| **By change of slope** | 3,950 | **0.011** | **-0.3 %** | **-18.2 %** | 0.81 | -27 % | -26 % |
| Same, plane cells capped at 20 m | 11,600 | 0.032 | +0.9 % | -9.2 % | 0.88 | -27 % | -20 % |
| By slope | 22,250 | 0.062 | +0.4 % | -10.4 % | 0.85 | -24 % | -4 % |
| By slope, capped at 20 m | 26,300 | 0.073 | +1.4 % | -6.5 % | 0.88 | -27 % | -18 % |

Total peak flatters everything: it barely moves on any mesh, because valley-wide outflow is mostly conserved rain. Change of slope matches it at 1.1 % of the cost, and **puts 18 % too little in the wadi, 27 % too shallow, 7 min early**. The wadi is at 10 m in that mesh, so the loss is on the plain: coarse sloping cells carry thin sheet flow too fast and in the wrong direction. Capping them at 20 m halves it, which supports that reading; tightening the threshold to 0.05 m gives the same mesh. Depths this shallow (0.2 m) are the hard case. Uniform 5 m is not fully converged, so about 2 % of any figure is reference error [Likely].

## 9. Not tested

GPU, float32 on the options, GPU cost of any kind: the cost column is one CPU thread, and polygon kernels use first-order momentum, so it favours them. Real DEMs for b, c and the triangles. A 3-body junction in c. Moving water on both sides of a cut line. m on real rain-on-grid (the fan is inflow only). Second-order momentum for P, b, c, triangles. A real mesher.

## 10. Recommendation

- **Do not build aligned faces now.** [Likely] m takes the worst case from 8.45 to 3.66 % and rotation misses over 3 % from 25 to 2 of 115, improves the fan against HEC-RAS, with no memory, at 1.02 x cost, in about 9 lines. It needs a GPU parity test first.
- **Option b: no.** [Certain on the measurements] It fails at bends of 135 degrees and over and at junctions, inverts cells, and oscillates on banks at 45 degrees. Its quads are triangles anyway.
- **Option c: no.** [Likely] No accuracy gain over m, a worse time step, and it cannot do junctions.
- **Triangles: the only option that held at every bend and junction**, under 1.4 % everywhere with Q within 0.11 %. [Likely] Worth a separate decision if exact crests and channels become the product, but it is a new engine: 100 % of the kernels and the tile layout. [Guessing] Months, not weeks.
- **P is the next step if m is not enough**, and it keeps the tiles. [Likely] Write its second-order form, then re-test the banks, where its Q error reaches 3.4 %.
- **Refinement by change of slope: not on its own.** [Likely] Keep plane cells at 20 m or finer where sheet flow feeds a wadi, and score wadi peak, never total peak.
- **Correct the stale record** in the design note and decision 19. [Certain]

## 11. Files

`lattice.py` port of production, flags for m and ms3. `lattice_fast.py` the same statements inlined for timing; `check_fast.py` shows 0.0 difference. `graph.py` polygon kernel. `meshes.py`, `meshes_poly.py` mesh builders. `audit.py` alignment measures. `cases.py`, `options.py` case and entry point. `run_*.py` each test; `chain.sh`, `chain2.sh` the order they ran. `probe_*.py` scans that chose settings. `xcheck_*.py` baseline checks. `results/` all output.

Faults found in this folder's own harness, each fixed before the final numbers: first-step size in Ritter; a storm long enough to saturate the valley; polygon face inverts below a cell minimum, which gave phantom dry-face speeds; `band` draining water at its edge in the dyke test; sides read from circumcentres; triangle lines stopping short of the domain edge, and cells beyond the terrain; mean depth set where level was meant; a bench measuring call overhead (first result 0.17 x, discarded).
