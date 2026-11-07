# Can the W3 Graph solver run the mesh race? Assessment, read-only (2026-11-07)

**Yes, in 8 to 11 days of harness work on the solver side, and only if both meshes run on it.** [Likely] The Graph kernel of
`W3 breakline faces test/graph.py` is decision 19's staggered scheme on arbitrary polygons: it already ran quads, snapped
quads, cut cells and triangles through 1,035 channel runs, bends, still water, a dyke and a rain-on-grid valley, and it
takes a cell as nothing but a list of faces, so a MeshKernel strip of quads joined to squares by triangles or pentagons is
the case it was written for. The uncomfortable part: **it is first-order in momentum and differs from production by up to
2 points on the 45-degree channel** (option P -0.31 against the lattice port +1.84 at the recorded phase, README section 3),
while W36's pass mark on Faydh 01 is 3 %. A race that puts the strip on the Graph and the squares on the GPU cannot say
whether a 3 % gap is the mesh or the kernel. Both sides go through the Graph, and one extra run ties the Graph's square
mesh to production's 1,835.2 m3/s. Everything below is read from the code; nothing was run or edited. Paths are relative
to `D:\Mojtaba\Renardet\Wadi2D\W3 breakline faces test\` unless given in full.

## 1. What the Graph solver takes, and how it computes

**Cell shapes.** [Certain] Any polygon with any number of faces. The `Mesh` dataclass (`graph.py:29-52`) holds per cell
only `Ac`, centroid `cx, cy`, `zmin`, `zbar`, `hc`, `dtab`; per face only `L`, `R`, length `ln`, unit normal `nx, ny`
(L to R), midpoint `xf, yf`, `dn`, skew `sx, sy`, invert `zf`, table top `ef`, table `ftab`, crest coefficient `cw`.
No vertex list reaches the kernel. The kernel `gstep` (`graph.py:72-254`) loops over the face list and scatters to `L`
and `R`, so a square with a hanging node (a pentagon with two collinear faces), a triangle at a join, a strip quad, are
all the same thing to it. The mesh builders are where shape enters: `meshes.py` (lattice as polygons, snapped quads, cut
cells) and `meshes_poly.py` (triangles).

**Orthogonality: not required, corrected for.** [Certain] `finish` (`graph.py:54-69`) computes `dn = n.(cR - cL)`,
floors it at `dn_min = 0.15 dx` (line 62), and the skew `s = (cR - cL) - dn n` (lines 63-64). The level difference that
drives a face is `d_eta = e_R - e_L - 0.5 (G_L + G_R).s` (lines 152-154), `G` the Green-Gauss cell gradient built from
face level differences only, on faces wet on both sides (lines 110-128), so still water gives `G = 0` exactly and the
correction vanishes at a wet-dry edge. W3 ran this at skews up to 58 degrees on option b (README section 3: "Handled by
the gradient correction; without it the error reaches +6 %") and chose circumcentres for the triangles so the skew is
zero by construction (`meshes_poly.py:248-249, 280`). Two traps for the join cells: (i) the `dn` floor silently rescales
the pressure gradient, `press = dt g d_eta / dn` (line 179), the section `abar = 0.5 (v_L + v_R) / dn` (line 178) and
the wave speed (line 220) on a face whose centre-to-centre line runs nearly along it; `mesh_tri` counts those
(`clipped_dn`, `neg_dn`, `meshes_poly.py:307-312`, 0 to 0.1 % on the triangles) and the strip builder must too;
(ii) a mixed mesh needs one centre convention for every cell, and centroid plus skew correction is the only one that
works for quads, pentagons and triangles alike, so the triangles' circumcentre trick is not available at the joins.
[Likely] The correction is first-order consistent, not exact: option b's -2.7 % on vertical walls against the lattice
port's -2.0 % at 0 degrees says it leaves about a point.

**Pressure, advection, friction, cap, per face (`graph.py:131-209`).**
- Upwind side by the face velocity sign (line 138); dry if the upwind level over the invert is under `e_wet` (140-144);
  area, `K^(3/5)` and top width `w` from the face table at the upwind level (`face_lookup`, `lattice.py:140-160`).
- Section blend and the disconnected drive exactly as production's [1] and [2] (lines 155-177): `rho` from the volume
  over `dn` against the table area, the drop rule when the downstream side is dry. `sheet` 1 is `v_up / dn`, 3 is
  `h_up ln` (production's `h_up dx` on any polygon; on the lattice 1 and 3 coincide). Do not confuse the Graph's
  `sheet=3` with the lattice's `ms3`, which is `h_up / om dx` and is the disqualified one (README section 7).
- Advection by Perot cell vectors (lines 79-108): `V U = sum (xf - c) Q_out`, rate `R = sum Q_out U_upwind`, face flux
  `n.(R_L + R_R)/2` (line 181), `u* = (m - dt flux / dn) / abar - press` (182). A closed or dry face carries `Q = 0`
  and sinks no momentum, which is why no `mirror` flag exists here. **First order**: no `ustar`/`minmod`
  (`lattice.py:103-113` has them, `gstep` does not; README section 5, "Momentum here is first order").
- Friction point-implicit (lines 185-199): transverse velocity from the cell vectors projected on the face tangent,
  averaged over the wet sides; `fric = A^2 / K^(10/3)`, `un = 2 u* / (1 + sqrt(1 + 4 dt g fric |U|))`, `u_max` cap.
- Crest cap (lines 200-206): `qc = cw A sqrt(A / w)`, critical flow on the **static** section, the same form as
  production's [6] (`lattice.py:283-290`). `cw` is set once in `finish` (line 67): `CW = 1.7046` where the invert stands
  more than `tol = 0.05 m` above both cells' mean bed (`zbar`), the natural-crest rule, else 0. There is no per-face
  coefficient input from a drawn line in the Graph path (README section 3: "P ... has no crest object in this
  prototype"); on the aligned meshes W3's dyke was the DEM ridge under the face, which the natural rule capped. The
  energy-head cap of W40's answer 2 exists nowhere, Graph or production.
- Positivity limiter per cell, divergence, depth update with `src`, level and plan share from the cell table (lines
  223-249); boundary cells overwritten (250-253); global step from the worst face, refreshed every `dt_every = 8` steps
  (`Graph.advance`, lines 318-339).

**Sub-grid tables on a non-square cell.** [Certain] Per cell, `cell_table` (`lattice.py:24-47`) takes any pixel set
(`z.ravel()`), sorts it and writes the 16-row `hbar`-to-level curve; the pixels of a polygon come from point-in-polygon
at pixel centres, `assign_pixels` (`meshes.py:174-196`), which is **hard-coded to 4 vertices** (line 189, `range(4)`);
`mesh_tri` feeds it triangles by repeating the third vertex (`meshes_poly.py:265-266`). A cell with no pixel gets the
nearest pixel (`meshes.py:237-238`); area is floored at `1e-3 dx^2` (line 235). Per face, `face_samples`
(`meshes.py:39-50`) walks any segment at pixel spacing and takes the higher of the two pixels at half a pixel either
side, production's "max of the two pixels that meet" rule generalised to a slanted face; `face_table`
(`lattice.py:51-73`) turns that profile into area and `K^(3/5)` over 16 rows, top between `e_lo = 8` and `e_hi = 16` m,
production's `face_depth_min/max`. `finish` lifts every invert to at least both cells' `zmin` (line 59). Pixels come
from a `Bed` (`meshes.py:17-25`): one padded array with its origin at the lattice corner, `k` pixels per cell.

## 2. What drives it, what it outputs, how W3 validated it

**Drivers.** [Certain] `src` per cell in m/s of depth (`graph.py:244`): rain is a uniform `src`
(`run_valley.py:192-193`), a point inflow is `Q / Ac` on a cell or a set of cells (`options.py:44-46`, and
`run_fan.py:84-88` on the lattice port, refreshed every 30 s from a hydrograph). Boundary cells `bcell, bd0, bh0` reset
to a held depth and level every step (lines 250-253); **`bkind` is passed and ignored**, so the Graph has only kind 0,
held. The lattice port has three kinds (`lattice.py:351-361`): 0 held, 1 dry, 2 "follow a reference cell with the level
lowered by `d0`", which is how `run_fan.py:57-73` builds production's normal-depth edge. Initial water:
`hbar_at_level(level)` then `set_depth` (`graph.py:291-316`). Domain edges: a face with one owner is dropped
(`meshes_poly.py:296-297`), so the rim is a wall, as the lattice's `CLOSED`.

**Outputs.** [Certain] State arrays only: `h, d, om` per cell, `u, m, q` per face. No series writer, no maps, no
checkpoint. A line discharge is the signed sum of `q` over faces whose `L` and `R` lie on opposite sides of a mask
(`options.py:56-65`, `run_valley.py:194-220`); a peak is the max over a Python sampling loop (`advance` every 30 or
100 s). Momentum is first order; the time step is global.

**Validation in W3, with the Graph (the lattice port `lattice.py` is a separate kernel; the real fan against HEC-RAS,
`run_fan.py`, ran on the port only, never on the Graph).** [Certain, README sections 3 to 5 and 8, `results/`]
- Rotated channel matrix (`cases.py`, `options.py`, `run_matrix.py`): 0 to 45 degrees, 3/6/12 cells, vertical and 2:1
  banks, 8 lateral phases, 1,035 runs. Pass case vertical 3 cells 45 degrees, error against Manning over 8 phases:
  lattice port a +1.84 to +7.99; P (lattice as polygons on the Graph) -2.82 to +0.27; b -2.72 to -1.03; c -0.82 to
  +3.80; t20 -1.83 to -1.07; t26 -2.26 to -1.48. Q error 0.10 to 0.11 % on triangles, 2.13 % on P, 13.6 % on b.
  Option b oscillated to +29 % on 2:1 banks at 45 degrees, 3 of 8 phases, "the toe face is fully wet on a thin wet
  wedge of bank cell" (README section 3): the warning for any strip whose cell sits on a bank toe.
- Still water on a rough bed at 1,500 m with dry cells (`run_still_dry.py:51-78`): largest speed 0 to 1.3e-15 m/s on the
  polygon meshes (`results/still_dry.txt`).
- Dry bank behind a thin dyke, 30 and 45 degrees: far side exactly dry on every option, the lattice staircase too; free
  overtopping at 0.3 m head: 0.93 to 1.02 of critical for all (capped by the natural rule on the aligned meshes).
- Bent channels 30 to 135 degrees (`run_bent.py`): t20 -1.74 % downstream at 135, lattice +5.83, m -0.35.
- Rain-on-grid synthetic valley (`run_valley.py`): uniform 5/10/20/40 m and two quadtrees on the Graph with `sheet=3`,
  the only Graph case with rain and an outlet; convergence 5 to 10 m within 2 % on the wadi peak.
- Baseline tie: the lattice port matches the production twin within 0.12 points and the frozen GPU fan run to 0.01 cm
  (README section 1); P against a differs by the Perot form and the advection order, 2 points at 45 degrees.
- **How the triangles were built** (`meshes_poly.py:129-235, 248-313`): scipy Delaunay only, so conformity comes from
  the point set: each line resampled at `h`, an offset row each side at `h sqrt(3)/2`, a triangular background kept
  off the lines, Laplace relaxation of free points, short edges dropped, then any line segment not yet an edge is
  split with a Steiner point until all are (0 unresolved). Cells are the triangles inside the band with area under
  `6 x 0.433 h^2`, no cell beyond the terrain (lines 256-260); centres are circumcentres; pixels by `assign_pixels`;
  faces from the edge map, normal oriented away from the opposite vertex (lines 302-305). t20 at equal spacing 2.16 x
  the cells, t26.3 at equal face count.

## 3. Speed, and what Faydh 01 would take

**Recorded** (`results/bench.txt`, `run_bench.py`: one thread, float64, all 16,384 cells wet, 160 steps, least of five):
lattice port 144.0 ns per cell-step (72 ns per face); P 132.5 without skew, 149.2 with; b 130.8; c 125.1; t20 127.3
(85.3 per face); t26 116.1 (77.9 per face). The cost is per face, 65 to 85 ns, about 1.5 faces per triangle and 2 per
quad. [Certain] On a real driver loop (`results/valley.csv`): uniform 5 m, 176,000 cells x 9,890 steps in 281.3 s is
6.2 M cell-steps per second, 162 ns; 10 m 5.9 M/s; 20 m 4.8 M/s; the 3,950-cell quadtree 4.1 M/s, where the Python loop
shows. So **5 to 6 M cell-steps per second per thread**, every cell and face every step: there is no active list, a dry
face costs the early `continue` at `graph.py:140-144`.

**Production on the same case** [Certain, `.claude/worktrees/agent-a692f5e4bb3647a2b/W36 breakline faces/runs/faydh_20_breakline/progress.jsonl`]:
Faydh 01 at 20 m, 188,814 cells, 16 h, 98,419 steps with the breaklines (88,589 without), GPU loop 12.64 s, tables
14.48 s, mass error -1.6e-8: 1.47 G cell-steps per second. HEC-RAS 6.6 SWE-EM took 3 h 44 min on 8 cores for the same
case at 20 m (`W11 validation round two/t2_faydh/ras_timing.csv`).

**Estimate for the race** [Likely, arithmetic on the numbers above]:
- Squares, 20 m: 1.67e10 to 1.86e10 cell-steps at 5 to 6 M/s = **45 to 60 min** on one thread, 250 x the GPU.
- With strips, 20 m: the global step follows the thinnest wet face. W3 measured the penalty: t20 `dt / a` median 0.62,
  worst 0.28; b 0.18 to 0.55 on banks; c 0.70 and 0.34. So **1.5 to 3 h** per run, and the step count itself is the
  measurement the owner wants (W40's "time step of thin cells" risk); record steps as W26 and W36 did, not seconds.
- 10 m (the other two W26 Faydh cases): 755,164 x 154,391 = 1.17e11 cell-steps, 5 to 6 h squares, 10 to 18 h strips.
  Bidah: 20 m 6 min, 10 m 50 min. All cases are independent, so a `ProcessPoolExecutor` fills the 16 cores, as
  `chain.sh` did with 11.
- Memory 444 bytes per cell (README section 3): 84 MB at 20 m, 335 MB at 10 m. The pixel pass is the heavy part: 75 km2
  at 0.5 m is 302 M pixels, 2.4 GB as float64 in the padded `Bed` array, 1.2 GB as float32; `assign_pixels` tests about
  1,600 pixels per 20 m cell in Numba, seconds to a minute. [Guessing] Table build 2 to 5 min at 20 m.
- Not measurable here: GPU cost of a strip inside 32 x 32 tiles. The CPU face-list cost says nothing about it (README
  section 9 says the same of every W3 cost column).

## 4. Gap list for the race

| Gap | State | What it takes | Days |
|---|---|---|---|
| **Read a MeshKernel mesh** (nodes, edge-node table, cell-edge table; note MeshKernel calls the polygon a "face" and the segment an "edge") into `Mesh` | missing; every piece exists for one shape | per cell: signed area and centroid for any n (`meshes.py:199-204` `polygon` uses `np.roll`, any n); per face: length, midpoint, normal oriented by the sign of `n.(cR - cL)` (`meshes.py:252-253`); drop one-owner faces (`meshes_poly.py:296-297`); `finish` for `dn`, skew, `cw`; print `quality()` (`meshes.py:384-388`) and a `clipped_dn` count for the join cells | 1 |
| **Non-orthogonal faces at the joins** | exists | centroid centres and `skew=True` everywhere (option b's path, skew to 58 degrees); audit the `dn` floor on pentagons and join triangles; the false sideways drive W40 named is testable on the synthetic case below; the Green-Gauss sum already excludes dry faces (`graph.py:117`) | 0 to use, 1 to audit |
| **DEM sub-grid tables on strip cells** | adaptable | generalise `assign_pixels` to `nv` vertices per cell (as `audit.py:60-75` does); replace the padded `Bed` by a windowed rasterio read with the origin from the transform; float32 pixels; `face_samples` and `face_table` as they are. **Use `faydh_0p5m.tif`**, the DEM of the W11, W26 and W36 runs; `W44 mesh race/meshkernel/common.py` points at the 5 m GGC, which is fine for the mesher and wrong for the tables, or the comparison carries a DEM difference | 1 to 2 |
| **Breakline faces on the strip** (closed until the level passes the line's ground) | exists by construction | a strip face on the line reads the DEM at half a pixel either side, so its invert is the bank's own ground and it is closed below it (`graph.py:140`); a line Z override is `max(prof, z)` before `FaceList.add` (`meshes.py:61-73`) | 0.5 |
| **No weir law on breaklines** (W36's rule) | missing, trivial | a `free` mask zeroing `cw` after `finish`; today `finish` caps every natural crest, which is why W3's aligned dykes read 0.98 to 1.02 and W36's uncapped breakline 2.6 to 3.8 x | 0.5 |
| **Energy-head cap, TUFLOW style** (W40 answer 2) | missing in Graph and production | replace lines 200-206: `qc = C ln H_e^1.5`, `H_e` the upstream level plus `u^2/2g` minus the crest, a drowned curve on the downstream head; the flume of W36 (`flume.py`) as the test, 4 cells wide, 80 long | 1 to 2 |
| **Faydh 01 driver**: hypothetical storm 163.08 mm, 24 h pattern, 16 h run, no losses (`curve_number` null, transmission off), no inflows [Certain, `config.resolved.json`] | adaptable | `src` from the pattern every 30 s, as `run_fan.py:84-88` does for inflows; import the engine's hyetograph reader read-only or reimplement `time_percent`/`depth_percent` | 0.5 to 1 |
| **Boundaries**: one `normal` line at the outlet, slope 0.015, `snap_m` 150 | missing in `gstep` | port kinds 1 and 2 from `lattice.py:351-361` (dry; follow a reference cell lowered by `S dn`), pick cells by centroid distance to the line as `run_fan.py:57-73` picks the edge | 1 |
| **Dam-line discharge on the strip** (the `axis` polyline, 4 vertices across the gorge; `box_mid`) | exists as a mask sum | the side-of-line mask works because a dam line spans the gorge (`options.py:60-64`); a true polyline-face intersection needs face endpoints, reconstructible as `xf +- 0.5 ln t`; write the series every 120 s and take the peak, as production | 0.5 to 1 |
| **The square side on the Graph** (P on `mesh_lattice`, plus rule G) | exists / adaptable | `mesh_lattice` (`meshes.py:82-109`) with `band` from the domain polygon; rule G, the ridge-only lift, from W36's `wadi2d/terrain/ridge.py` on the worktree, as a face-profile option | 1 |
| **Tie to production**: Graph-P with no lines against 1,835.2 m3/s at the axis | missing | one run, 45 to 60 min; the margin found is the floor under every later reading | 0.5 |
| Progress print, periodic series dump, a wall-clock per run | missing | `Graph.advance` is a bare loop | 0.5 |
| Parallel kernel | missing, not needed | `gstep` is serial with scatter-adds; `parallel=True` needs a gather form or colouring | 2 to 3, optional |

Solver side in all: **8 to 11 days** [Guessing], the strip generation itself not counted. The 225 Faydh bank lines,
"overlapping within a cell of each other" on braided reaches and broken into pieces at gorge meanders (W26 README
line 84), will collide as strips; option b failed at every junction for the same reason (README section 4). That is the
mesher's problem and the likely blocker on the Faydh case, not the solver's.

## 5. Recommendation

**Use the Graph, extend it; do not write a new one and do not race on the production engine.** [Likely] A new polygon
kernel would be this one again, minus 1,035 runs of evidence; and the strip cannot enter the tiles without the engine
work W40 listed, which is what the race is meant to decide first. Three conditions, or the race proves nothing:

1. **Both meshes on the Graph.** Strip against P-plus-rule-G, same kernel, same tables, same driver; one extra run ties
   P to production's no-line peak. Otherwise the 2-point kernel difference eats the 3 % pass mark.
2. **Steps, not seconds, as the cost.** The CPU face list cannot see GPU cost; the step count is the thin-cell penalty.
3. **State the first-order momentum and float64** in every result table, and keep `results/` style raw output.

**The smallest decisive first case is not the flume.** [Certain, from `run_still_dry.py` and W36's `flume.py`] On the
flume the crest sits on a lattice face already, so the strip and the square are the same mesh; the 2.6 to 3.8 x is the
face law, and the Graph's static cap already reads 0.93 to 1.02 there. The flume decides the cap, not the mesh: run it
third, on both meshes, once the energy-head cap exists. Nor is a dyke or levee decisive: W3 found the lattice staircase
keeps the far side exactly dry in all 28 runs.

**The decisive first case is W3's own 45-degree channel with 2:1 banks, 3 cells wide, 20 m, with the bank toes as
breaklines**, the geometry of the gorge failure: a bank line on a steep wall where the staircase puts wall ground on
faces inside the channel (W36: at Faydh 20 m half the breakline faces rise over 0.5 m, a tenth over 4.3 m). Three runs
per phase, 8 phases, minutes each (`cases.py` and `options.py` as they stand, plus the strip): squares with the W36
staircase rule, squares with rule G, the MeshKernel strip along the toes. Expectation [Likely]: the staircase rule reads
-5 to -11 % as at Faydh, rule G reads the no-line error of P, -0.6 to -1.2 % at 2:1 (`matrix_summary.txt`, theta 45),
and the strip reads within 2 % if its toe cells do not do what option b's did (+29 %, thin wet wedge). If rule G and the
strip agree within a point here, Faydh 01 at 20 m is confirmation; if the strip beats rule G by more, Faydh is the
measurement. Then Faydh 01 at 20 m (an hour a run), then the flume with the cap, then the 10 m cases overnight.

## What was read

`README.md`, `graph.py`, `lattice.py`, `meshes.py`, `meshes_poly.py`, `cases.py`, `options.py`, `run_alignment.py`,
`run_valley.py`, `run_valley2.py`, `probe_tri.py`, `run_bench.py`, `run_still_dry.py`, `run_fan.py`, `run_bent.py`,
`audit.py`, `results/bench.txt`, `results/valley.csv`, `results/valley.txt`, `results/valley2.txt`,
`results/still_dry.txt`, `results/probe_tri.txt`, `results/matrix_summary.txt` (head); `W40 mesh and breakline
research/README.md`; `W26 suggested breaklines/README.md` (the bank table); on the `feature/breakline-faces` worktree,
`W36 breakline faces/README.md`, `flume.py`, `runs/faydh_20_breakline/config.resolved.json` and `progress.jsonl`;
`W11 validation round two/t2_faydh/ras_timing.csv`; `W44 mesh race/meshkernel/common.py`, `probe_splines.py`,
`s00_inputs.py` (head). Not run: anything.
