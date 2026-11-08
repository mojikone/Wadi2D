# W47: the face section on sloping cells (2026-11-08)

**Live: option A, the upwind depth carry, at the end of this file, on branch `feature/face-depth-carry`.** The two
mean-level forms before it (`feature/face-level`) are superseded and kept as the record of why they failed; the
research between them is `reports/Face depth on sloping cells.md`.

## What W46 found

On Faydh's main stem the aligned strip under-attenuated a flood by 4 % over 14 km at 20 and 10 m alike against
squares converged to 0.2 %, because at the same steady discharge its water surface lay 0.20 m (20 m) and 0.08 m
(10 m) below the converged one and it held 9 and 4 % less water with the same storage tables. On a straight valley
squares and aligned cells shared that depression to the digit (2.5 % of the stored water at 20 m, 1.0 % at 10 m),
about half the bed's drop within a cell; on real channels the squares' staircase deepening hid it. [Likely] The
reading behind it: a face took its section at the upwind cell's level over the face's own invert, a level held half
a cell upstream of the face, so a cell conveying the right discharge through its downstream face stood too low along
its length.

## The change (`wadi2d/solver/cpu/kernels.py`, `gpu/kernels/faces.cu`, `poly/kernel.py`, `gpu/kernels/poly.cu`)

1. **The face section is read at the level carried to the face.** Where both sides of a face are wet (the downstream
   side over `e_wet`), the depth for the face table is the mean of the two cells' levels over the face invert; at a
   front, the downstream side dry, the upwind reading stays, so a dam-break front and a wetting sheet advance as
   before. The dry test on the upwind side, the thin-sheet section and the disconnected drive, the crest faces (a
   weir reads the upstream head), friction and the time step are unchanged.
2. **On polygons the advection flux reads the upwind cell's rate.** With the section at the mean level, the mean of
   the two cells' Perot rates left a standing wave of 20 % in the level along a uniform channel (the upwind depth had
   been damping it); the upwind cell's rate alone leaves none, and the polygon kernel then gives the tile kernel's
   depth to four digits on the same lattice. The lattice's own advection, upwinded already, is untouched.

Both CUDA twins carry the same statements in the same order.

## The test (`tests/solver/test_face_level.py`)

W3's channel at a slope of 1 % with 300 m3/s at 20 m, where the old reading is 0.1 m on a normal depth of 1.25 m:
the depth at the axis within 1.5 % of the normal depth on the tile kernel and on the polygon kernel laid over the
same lattice. Before the change both read 0.966 of the normal depth; after it both read 1.010.

## Results, all on the GPU unless said

**W3's channel** (`tests/solver/test_poly.py`, a 60 m bed at 0.2 % with 60 m3/s, three cells wide at 20 m, CPU; the
depth at the axis over the normal depth):

| | Tiles, before | Tiles, after | Polygons on the lattice, before | Polygons, after |
|---|---|---|---|---|
| 0 degrees | 0.986 | 1.007 | 0.986 | 1.007 |
| 45 degrees | 1.026 | **1.071** | 1.026 | **1.048** |

**The straight synthetic valley at steady state** (`W46 .../probe_wave/straight`, 300 m3/s ramped over an hour, 1 %,
a 40 m bed, normal depth 2.111 m): the water stored after the change is 770.1 (20 m squares), 770.1 (20 m centres,
the same cells), 771.2 (10 m) and 772.9 (5 m) thousand m3, equal to 0.4 %, where before it was 742.9, 754.1 and
762.1, falling 2.5 % and 1.0 % short at 20 and 10 m; the strip's depth on the axis is 2.111 m, the normal depth to
four digits. **On a resolved prismatic channel the change does what it was built to do.**

**Faydh's main stem, 4 to 20 km, the flash flood with no rain** (`reach_long` before, `W47/reach_long_after`; the
peak 18 km down against the 2 m squares):

| | Squares 20 m | Squares 10 m | Squares 5 m | Strip 10 m | Strip 20 m |
|---|---|---|---|---|---|
| Before | -5.0 % | -0.7 % | +0.2 % | +3.7 % | +4.2 % |
| After | -3.6 % | -0.5 % | -0.7 % | +2.7 % | **+0.6 %** |

**The same reach at a steady 300 m3/s**, the final surface read from the saved frames (`steady_surfaces.py`; the
maxima rasters carry the arrival transient and are not the steady surface, which is why the W46 reading of the
squares differs from this one), inside the 20 m strip's footprint against the 2 m squares:

| After the change | Squares 5 m | Squares 10 m | Squares 20 m | Strip 10 m | Strip 20 m |
|---|---|---|---|---|---|
| Surface, mean | +0.035 m | +0.054 m | +0.120 m | -0.060 m | -0.101 m |
| Water held | +1.7 % | +2.8 % | +6.5 % | -2.5 % | -4.0 % |

Before, by the balance's stored water in the whole reach: squares 5 m -0.7 %, 10 m -1.1 %, 20 m +1.0 %, strip 10 m
-4.2 %, strip 20 m -9.3 %. [Certain, measured] The strip's deficit halves; the coarse squares now stand above the
fine ones (the staircase's deepening of a one-cell channel, unmasked), and the lattice converges more slowly than
before (5 m and 2 m 1.7 % apart where they were 0.7 %).

**The Faydh race** (`race_after_fix.py`, the W45 and W46 race jobs rerun, the dam axis at 16 h):

| Run | Peak before | Peak after | Change |
|---|---|---|---|
| 20 m squares | 1,835.2 | 1,800.1 | -1.9 % |
| W45 ring corridors, 20 m | 1,879.9 | 1,837.1 | -2.3 % |
| Centres, 20 m | 1,987.0 | 1,966.3 | -1.0 % |
| 10 m squares | 1,871.3 | 1,833.9 | -2.0 % |
| Centres, 10 m | 1,918.8 | 1,896.8 | -1.1 % |
| 5 m squares | 1,887.1 | 1,854.2 | -1.7 % |

[Certain, measured] **The change does not close the race.** Every peak falls 1 to 2 %; the centre mesh at 20 m
stands +9.2 % over the 20 m squares (was +8.3 %) and +6.0 % over the 5 m squares (was +5.3 %), at 10 m +2.3 % (was
+1.7 %). The flood routed down the strip is now right at 20 m, and the rain-fed excess at the axis is untouched, so
the rain-fed delivery into the strip carries a mechanism the flood alone does not exercise and this change does not
reach. A second change tried on the way, the polygon's thin-sheet section as the cell volume over the face spacing
(the kernel comparison's inconsistency), moved the centre peak 0.3 % and was taken out.

**The test suite** (`pytest_full.log`, `pytest_poly_strips.log`): 22 of about 1,860 fail, in five groups, each a
place where the mean of the two levels is not the level at the face:

1. *Boundary faces.* The earthworks trapezoid at 0 degrees runs at 1.258, 1.359 and 1.539 m against a normal depth
   of 1.243 m at its three stations, deepening toward the outlet: at a boundary cell whose depth is reset or held,
   the mean reading halves the outflow face's section and a backwater climbs the channel. MacDonald's three
   profiles (dx 5 m) carry 11 % less discharge for the same reason, and the lined channel, the channel between dykes
   and the products tests downstream of these go with them. The boundary face must keep the upwind reading, which
   needs the face to know it is one.
2. *Crest faces.* The two overtopped-dyke tests: the crest's section is read at the mean where its cap reads the
   upstream head, so less than critical flow passes. A crest face must keep the upwind reading; not done here.
3. *Tile interfaces.* The four quad tests: between cells of two sizes the face is not midway between the centres,
   so the mean is not the level at the face; the carry must weight the two levels by their distances.
4. *Fronts.* Ritter's dam break on a dry bed reads twice the depth near the tip on both backends: the switch from
   the mean to the upwind reading at a downstream depth of `e_wet` is a step, and just behind the tip the mean halves
   the section. The carry must fade toward the upwind reading as the downstream side thins, as the thin-sheet limit
   already fades by the fourth power of the depth ratio.
5. *The staircase.* W3's channel at 45 degrees on squares, 7 % deep on tiles and 5 % on polygons over a 3 % rule: the
   old reading's depression had been cancelling half the staircase's own deepening; this one is real and was always
   in the stored water. The aligned cells have no staircase, which is their point.

## The full form (`410446c` and after, same branch)

His "Go": the carry made aware of what the first form was not. A face now reads the upwind level alone at a crest
(the cap reads the upstream head), against a boundary cell (a per-cell flag `bnd` in the state arrays, set with the
boundary cells and exchanged into the halos, so both kernels know one), and at a front, into which the carry fades
as the downstream depth over the face invert falls from `carry_fade_to` (0.5) to `carry_fade_from` (0.25) of the
upwind one (`Numerics`, through the record into both kernels' constants). Elsewhere the level is carried by where
the face stands between the two centres: a half on the lattice, a third of the way from the fine centre on a quad
interface (`tface`, from the interface's side), and on polygons each face's own fraction from its geometry
(`PolyMesh.tf`, since a relaxed band cell is not exactly bisected). Four kernels, both polygon backends, the level
and quad callers and the strips' hybrid carry it; the modules import and the GPU compiles.

**What it mended** (`pytest_quad_iface_weights.log`, `pytest_earthworks_products_full_form.log`,
`pytest_strips_full_form.log`): the earthworks channels run at normal depth again (the boundary flag), the planar
flow across quad interfaces and the mesh pixels' step (the interface weight), the two overtopped dykes (the crest
rule), the strips' whole suite. **What stays failing**, with the ladder's numbers on the old kernels beside, read
on a worktree of `feature/centre-mesh` with the same script (`ladder_before.json`, `ladder_after.json`):

| Analytic case | Old kernels | Full form | Limit |
|---|---|---|---|
| Ritter dam break, depth RMSE, m | 0.0085 | 0.0117 | 0.01 |
| MacDonald subcritical, depth RMSE, m | 0.0100 | 0.0206 | 0.015 |
| MacDonald supercritical, depth RMSE, m (discharge carried) | 0.0105 (1.000) | 0.0341 (0.986) | 0.012 |
| MacDonald jump, depth RMSE, m (discharge carried) | 0.0324 (1.000) | 0.0581 (0.959) | 0.05 |
| Quad dam break into coarse cells, against the uniform run | passed | 0.0223 | 0.02 |
| W6's 45-degree channel, 3 cells, depth error, % | 0.13 | 3.86 | 3 |
| W3's channel, tiles, 0 / 45 degrees, depth over normal | 0.986 / 1.025 | 1.007 / 1.069 | 3 % |
| W3's channel, polygons on the lattice, 0 / 45 degrees | 0.986 / 1.013 | 1.007 / 1.048 | 3 % |

[Certain, measured] **The carry is right where friction sets the depth and wrong where inertia does.** On W3's
aligned channel and the straight valley, friction-dominated uniform flow on coarse cells, it takes the depth from
1.4 % low to 0.7 % high and makes the stored water equal across cell sizes. On MacDonald's profiles it deepens the
body 1 to 9 % and, in the supercritical and jump cases, passes 1.4 and 4 % less discharge than the inlet imposes,
where the upwind reading matched them to 1 %: in rapidly varied flow the depth at a face is the upstream cell's, as
the characteristics say, and the mean pulls in the downstream cell. Ritter's rarefaction is the same story in time.
And W6's 45-degree staircase was not a cancelled error: the dry-face fix had made it right to 0.13 % with the
upwind reading, and the carry makes it 3.9 % deep, so on an oblique channel of squares the carry over-corrects as
well. The old reading is the consistent one for the scheme as built; its one fault is the friction-dominated uniform
flow on a slope, where it under-reads the stored water by half the bed's drop within a cell.

[Likely] The form that would hold both is regime-aware: carry the level into the friction's hydraulic radius alone
(the conveyance the face is read with) and keep the upwind depth for the transported section, the pressure and the
momentum, or fade the carry with the Froude number of the face. Neither is a day's work with the ladder as the gate;
it is a scheme study with its own W. The race does not depend on it: with the first form the Faydh gap did not
move, and the full form's rules (crest, boundary, interface, a front's fade) do not touch the strip's channel
faces, where the downstream depth stands at 0.75 to 0.9 of the upwind one and the carry is full.

## The mean-level forms: where they stood

[Certain] On branch `feature/face-level`, off `feature/centre-mesh`, the full form built and gated: 8 of about
1,860 tests fail, all analytic cases of rapidly varied or oblique flow listed above, none by more than the table
shows; `feature/centre-mesh` keeps the old kernels and passes. Not shippable as it stands, for the reason above,
and the Faydh race is not its to close. His call: a regime-aware carry as a study of its own, or the branch
shelved and the 3 % rule read against the converged peak at 10 m, where both constructions already pass.

## Option A: the upwind depth carry (`feature/face-depth-carry`, off `feature/centre-mesh`, his go of 2026-11-08)

The research (`reports/Face depth on sloping cells.md`) found the codes without sub-grid tables avoid the bias by
reading a face at the upwind cell's *depth*, not its level over the face invert (TUFLOW HPC at first order,
LISFLOOD-FP, Delft3D's flooding scheme), and that the mean-level forms above were neither published form. Built:

- **The rule.** A face reads its section at the upwind level lowered by the bed's drop from the upwind cell's centre
  line to the face invert, never raised: `e_face = e_up - phi * max(0, z_centre_up - z_face)`. The centre bed is the
  lowest pixel of the cell's middle pixel column (x faces) or row (y faces), stored per cell in the tables
  (`zcx`, `zcy`, above the cell's lowest pixel; the grid cache format moves to 2). On a cell of one pixel the face
  invert is already the higher of the two beds and the drop is zero, so the reading is today's; on a sub-grid cell
  on a slope it is half the bed's drop. Polygons take the drop to each face from the face whose normal is most
  opposite (half the difference of the two inverts), and the lattice laid out as polygons takes the tables' values.
- **Mine, not published:** `phi` fades the carry from 1 to 0 as the upwind level falls from two cell-drops to one
  cell-drop above the face invert, so a cell holding only a wedge of thin flow at its low edge keeps today's reading
  (the sheet read handles it); the published codes have no wedge to guard against. Crest faces keep today's reading.
- **The switch.** `numerics.face_depth_carry`, on by default on this branch; off gives every number before W47.

**Gate** (`ladder_depth_carry.json`, `pytest_full_depth_carry.log`):

| Case | Before (upwind level) | Option A | Mean-level full form | Limit |
|---|---|---|---|---|
| Ritter dam break, depth RMSE, m | 0.0085 | 0.0085, to the digit | 0.0117 | 0.01 |
| MacDonald subcritical, m | 0.0100 | 0.0100, to the digit | 0.0206 | 0.015 |
| MacDonald supercritical, m (discharge) | 0.0105 (1.000) | 0.0105 (1.000) | 0.0341 (0.986) | 0.012 |
| MacDonald jump, m (discharge) | 0.0324 (1.000) | 0.0324 (1.000) | 0.0581 (0.959) | 0.05 |
| W6's 45-degree channel, depth error % | 0.13 | 1.33 | 3.86 | 3 |
| Uniform flow at 1 %, 20 m, both kernels, over normal | 0.966 | **1.002** | 1.010 | 1.5 % |
| W3's channel at 0 degrees, tiles and polygons | 0.986 | **1.004** | 1.007 | 3 % |
| W3's channel at 45 degrees, polygons on the lattice | 1.013 | 1.025 | 1.048 | 3 % |
| W3's channel at 45 degrees, tiles (not gated by a test) | 1.025 | **1.039** | 1.069 | 3 % |

The whole suite passes, the frozen job schema regenerated for the new switch. [Certain, measured] The analytic cases
are untouched because they are one pixel per cell; the uniform-flow bias is gone on both kernels; the one number
over its rule is W3's 45-degree channel of squares on the tile kernel, 3.9 % deep: the staircase's own deepening of
an oblique channel three cells wide, which the old depression had been offsetting by about 1.4 %. No test gates it
(the polygon kernel's 1.025 is the gated number); his call whether that rule is read for squares at 45 degrees.

**The slope cases** (`carry_runs.py`, `depth_carry/`; each W46 job rerun with its own cache):

| Against the finest squares on the same ground | Before | Option A |
|---|---|---|
| Straight valley, steady, stored water: 20 m squares / 20 m centres / 10 m squares, against 5 m | -2.5 / -2.5 / -1.0 % | **-0.25 / -0.27 / -0.10 %** |
| Faydh reach, steady, water in the strip's footprint: strip 20 m / 10 m, against 2 m | -9.3 / -4.2 % (balance) | **-4.5 / -1.2 %** |
| Faydh reach, steady, the same: squares 20 / 10 / 5 m | +1.0 / -1.1 / -0.7 % (balance) | +6.9 / +2.8 / +1.4 % |
| Faydh reach, flash flood, peak 18 km down: strip 20 m / 10 m | +4.2 / +3.7 % | **+1.7 / +2.5 %** |
| Faydh reach, the same: squares 20 / 10 / 5 m | -5.0 / -0.7 / +0.2 % | -3.2 / -2.6 / -0.9 % |
| Faydh race, dam axis, against 5 m squares: squares 20 / 10 m | -2.8 / -0.8 % | -4.3 / -1.5 % |
| Faydh race, the same: rings 20 m / centres 20 m / centres 10 m | +0.9 / +5.3 / +1.7 % | -0.6 / **+4.6** / +1.7 % |
| Faydh race, centres 20 m against squares 20 m (the 3 % rule) | +8.3 % | **+9.3 %** |

The race peaks of record: 5 m squares 1,866.9 m3/s (was 1,887.1), 20 m squares 1,785.8 (1,835.2), centres 20 m
1,952.0 (1,987.0). (The "before" storage of the squares on Faydh is the balance's whole-reach figure; the option A
figures read the footprint from the saved frames, the better reading, so the two rows are not a like-for-like change
for the squares.)

[Certain, measured] **Option A does what the research said it would, and no more.** The bias of the face reading is
gone where the answer is known (the straight valley to a quarter of a per cent, uniform flow to 0.2 %), the strip's
deficit on real ground halves at 20 m and nearly closes at 10 m, and no analytic case moves. The squares on Faydh's
sinuous gorge now hold more water than the converged answer at coarse sizes (+6.9 % at 20 m): the staircase's
deepening, no longer offset. **The race is unchanged in kind:** every peak 1 to 3 % lower, the centre mesh still
+9.3 % over the 20 m squares and +4.6 % over the 5 m ones. That excess has a second cause, as the research said, and
it stays unnamed.

## Where it stands

`feature/face-depth-carry` holds option A, the suite passing; not merged, his call. `feature/centre-mesh` keeps the
old kernels. `feature/face-level` holds the two superseded mean-level forms.
